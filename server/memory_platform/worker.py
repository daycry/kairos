"""Durable leased worker. Remote operations always occur outside database transactions."""
from __future__ import annotations
import asyncio
import random
from datetime import datetime, timedelta, timezone
import signal
import socket
import time
import uuid
from . import observability
from .config import DEFAULT_BACKOFF_MAX, Settings, embedding_job_timeout
from .store import Store
from .store_jobs import stored_item_vector
from .providers import Ollama, Embeddings, ProviderError
from .errors import MemoryError, StoreUnavailable, is_store_unavailable
from .chunking import chunk_text, embedding_text

JOB_DEADLINE_MARGIN = 10  # seconds the job may outlive the provider's own deadline
IDLE_SECONDS = 1.0  # wait between two claims when the queue is empty
BACKOFF_FIRST = 1.0  # ceiling of the wait after the first consecutive database failure; it doubles up to MEMORY_WORKER_DB_BACKOFF_MAX


def backoff_delay(failures, cap, rng=random.random):
    """Seconds to wait after `failures` consecutive database failures: the ceiling doubles from BACKOFF_FIRST and stops at `cap`; the wait is a point of
    [ceiling/2, ceiling] chosen with `rng` (equal jitter: many workers do not retry together, yet the wait still grows and reaches the cap)."""
    ceiling = min(float(cap), BACKOFF_FIRST*2**min(max(failures, 1)-1, 30))
    return ceiling/2+rng()*ceiling/2


def embed_plan(settings, payload):
    """(embedding text, fragments, inputs): the most `embed_receipt` can send. One whole fragment is one input (the text itself); anything else is
    its fragments plus the whole text (n+1), so the item vector keeps meaning what it always meant (the embedding of the first 8,000 characters).
    Whether that last input travels in the same call, is skipped (a stored vector is reused) or becomes one extra call is decided by `embed_receipt`;
    `worker_deadline` covers the worst case."""
    text = embedding_text(payload.get('title', ''), payload.get('content', ''))
    chunks = chunk_text(text, getattr(settings, 'chunk_chars', None), getattr(settings, 'chunk_overlap', None), getattr(settings, 'chunk_max', None))
    return text, chunks, (1 if len(chunks) <= 1 and not chunks.truncated else len(chunks)+1)


def worker_deadline(settings, inputs, stored_vector=True):
    """Seconds an embed job of `inputs` planned inputs may take: the batches of the n+1 inputs plus, when there are several AND an item vector is
    stored (`stored_vector`), the single-text call that a stored vector of other dimensions needs after the fragments. Without a stored vector
    that call can never happen, so it is not added (`Worker.run_once` starts without it and extends the deadline once a stored vector is found)."""
    return embedding_job_timeout(settings, inputs)+(embedding_job_timeout(settings, 1) if inputs > 1 and stored_vector else 0)+JOB_DEADLINE_MARGIN


async def embed_receipt(provider, settings, payload, canonical_hash, item_vector=None):
    """The `embed` receipt of one resource: one whole fragment keeps the previous receipt shape, longer text is split and embedded in batches.

    Used by the worker and by the retrieval evaluation, so both index exactly the same way. A failure in any fragment raises and
    nothing partial is returned. The item-level `vector` is always the embedding of the text itself (its first 8,000 characters, as
    before fragments existed), so a rollback to the previous release finds the vector it expects. A cap that stops the coverage
    (`MEMORY_CHUNK_MAX`) is declared in the receipt even when only one fragment fits.
    """
    text, chunks, inputs = embed_plan(settings, payload)
    if not chunks:
        raise ProviderError('embedding_empty_input')
    if inputs == 1:
        embedded = await provider.embed(text)
        return {'vector': embedded['embedding'], 'model': embedded['model'], 'verified': True, 'canonical_hash': canonical_hash}
    # `item_vector`: the item vector already stored for this very version, hash and model (the backfill of a resource that only lacks fragments).
    # With it the text is NOT embedded again: only the fragments are sent. Without it the whole text travels in the SAME call as the fragments
    # (last input). If the stored vector has other dimensions than the fragments (another model size) the whole text is embedded in one extra
    # call, which `embed_plan` and the job deadline account for (`worker_deadline`).
    sent = [chunk.text(text).strip() for chunk in chunks]
    embedded = await provider.embed_many(sent if item_vector else sent+[text])
    vectors = embedded.get('embeddings')
    if not isinstance(vectors, list) or len(vectors) != len(sent)+(0 if item_vector else 1):
        raise ProviderError('embedding_invalid')
    verified = bool(embedded.get('verified'))
    if item_vector and len(item_vector) == len(vectors[0]):
        whole = item_vector
    elif item_vector:
        extra = await provider.embed(text)
        whole = extra['embedding']
        verified = verified and bool(extra.get('verified', True))
        if len(whole) != len(vectors[0]):
            raise ProviderError('embedding_invalid')
    else:
        whole = vectors[-1]
    receipt = {'vector': whole, 'model': embedded['model'], 'verified': verified, 'canonical_hash': canonical_hash,
               'chunks': [{'ordinal': chunk.ordinal, 'char_start': chunk.char_start, 'char_end': chunk.char_end, 'vector': vector} for chunk, vector in zip(chunks, vectors)]}
    if chunks.truncated:
        receipt.update(chunks_truncated=True, chunks_covered_chars=chunks.covered_chars)
    return receipt


class Worker:
    def __init__(self, store, settings, providers=None, worker_id=None, *, clock=None, rng=None, waiter=None, heartbeat_wait=None):
        """`clock` (monotonic seconds), `rng` (jitter, [0, 1)), `waiter` (the wait between claims; default: ends early when the worker is told to stop)
        and `heartbeat_wait` (the pause of the lease heartbeat) exist so that a test drives time and does not wait for it."""
        self.store, self.settings = store, settings
        self.id = worker_id or socket.gethostname()+':'+str(uuid.uuid4())
        if providers is None:
            # The language-model provider exists only when the operator turned extraction on (MEMORY_EXTRACT_ENABLED).
            providers = {'embed': Embeddings(settings)}
            if getattr(settings, 'extract_enabled', False):
                providers['extract'] = Ollama(settings)
        self.providers = providers
        self.stopping = asyncio.Event()
        self.clock = clock or time.monotonic
        self.rng = rng or random.random
        self._wait = waiter or self._wait_or_stop
        self._heartbeat_wait = heartbeat_wait or asyncio.sleep
        self.last_store_ok = self.clock()  # `clock()` of the last access to the database that worked (R-01: an outage must not look healthy)
        self.store_failures = 0  # consecutive failures of the database or of the loop; any access that works sets it back to 0

    async def _wait_or_stop(self, seconds):
        """Wait `seconds`, or less when the worker is told to stop: a stop never waits for a backoff."""
        try:
            await asyncio.wait_for(self.stopping.wait(), seconds)
        except TimeoutError:
            pass

    async def _store(self, stage, call, *args):
        """Every access of the worker to the database goes through here (claim, heartbeat, stored vector, complete, fail). A database that does not answer is
        logged as `store_unavailable` (stage in `reason`, consecutive failures in `count`, never the DSN) and raised as `StoreUnavailable`; one that
        answers advances `last_store_ok`. Every other error passes through for the caller to classify."""
        try:
            result = await asyncio.to_thread(call, *args)
        except Exception as exc:
            if not is_store_unavailable(exc):
                raise
            self.store_failures += 1
            observability.log_failure('store_unavailable', exc, 'warning', reason=stage, count=self.store_failures)
            raise StoreUnavailable(getattr(exc, 'cause_type', None) or type(exc).__name__) from None
        self.store_failures = 0
        self.last_store_ok = self.clock()
        return result

    async def _fail(self, job, *args):
        """`fail_job`, unless the database does not answer: then the job is left as it is (running, with its attempts), and it is claimed again when its lease
        expires. Returns False in that case."""
        try:
            await self._store('fail', self.store.fail_job, job['id'], job['fence'], *args)
        except StoreUnavailable:
            return False
        return True

    async def run_once(self):
        job = await self._store('claim', self.store.claim_job, self.id, self.settings.lease_seconds)
        if not job:
            return False
        lost = asyncio.Event()
        destination = observability.closed(job['destination'], observability.DESTINATIONS)
        started, outcome = time.monotonic(), 'failed'
        async def heartbeat():
            while True:
                await self._heartbeat_wait(max(0.1, self.settings.lease_seconds/3))
                try:
                    renewed = await self._store('heartbeat', self.store.renew_lease, job['id'], job['fence'], self.settings.lease_seconds)
                    if not renewed:
                        observability.log_event('lease_lost', 'warning', destination=destination)
                        lost.set()
                        return
                except StoreUnavailable:
                    continue  # logged by `_store`: the lease is what the database says, so the next beat tries again; the job is lost only when it says so
                except Exception as exc:
                    observability.log_failure('heartbeat_failed', exc, 'warning', destination=destination)
                    lost.set()
                    return
        pulse = asyncio.create_task(heartbeat())
        try:
            provider = self.providers.get(job['destination']) if job['destination'] in {'extract', 'embed'} else None
            if not provider and job['destination'] == 'extract':
                # A job queued while extraction was on: it fails with its own reason, stays in the table and can be retried once extraction is enabled.
                raise ProviderError('extraction_disabled')
            if not provider:
                raise ProviderError('unsupported_destination')
            if job['destination'] == 'embed':
                # Proportional to the number of batches the text needs (MEMORY_EMBED_BATCH_TIMEOUT each), up to MEMORY_EMBED_JOB_MAX_TIMEOUT.
                # The extra single-text call exists only when an item vector is stored: the deadline grows by it once that is known.
                planned = embed_plan(self.settings, job['payload'])[2]
                deadline = worker_deadline(self.settings, planned, stored_vector=False)
            else:
                deadline = self.settings.provider_timeout+10
            async with asyncio.timeout(deadline) as limit:
                if job['destination'] == 'embed':
                    stored = None
                    if planned > 1:
                        stored = await self._store('read', stored_item_vector, self.store, job['project_id'], job['item_id'], job['resource_type'], job['version'], job['canonical_hash'], self.settings.embedding_model)
                        if stored:
                            limit.reschedule(limit.when()+embedding_job_timeout(self.settings, 1))
                    receipt = await embed_receipt(provider, self.settings, job['payload'], job['canonical_hash'], stored)
                elif job['destination'] == 'extract':
                    # Extraction is explicitly scheduled, never inferred from a capture event.
                    # Store read views include routing IDs, refs and a nested raw
                    # payload. Those are not model output fields and encourage
                    # copying an invalid storage envelope instead of a memory.
                    view = job['payload']
                    source = view.get('payload', view)
                    receipt = await provider.extract(source)
            if lost.is_set():
                return True
            if job['destination'] == 'embed' and not receipt.get('verified'):
                raise ProviderError('embedding_unverified')
            await self._store('complete', self.store.complete_job, job['id'], job['fence'], receipt)
            outcome = 'completed'
            observability.log_event('job_completed', destination=destination, duration_ms=observability.elapsed_ms(started))
        except StoreUnavailable:
            # The database did not answer (reading the stored vector or completing): this is not the provider's failure, so the job is neither failed nor
            # given a `provider_error`. It stays `running` and is claimed again, counting only that claim, when its lease expires.
            outcome = 'lost'
        except ProviderError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code=exc.code, duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                retry_at = None
                if exc.retryable and job['attempts'] < self.settings.max_attempts:
                    retry_at = datetime.now(timezone.utc)+timedelta(seconds=min(60, 2**job['attempts']))
                if not await self._fail(job, exc.code, retry_at, False):
                    outcome = 'lost'
        except TimeoutError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code='provider_timeout', duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                retry_at = datetime.now(timezone.utc)+timedelta(seconds=30) if job['attempts'] < self.settings.max_attempts else None
                if not await self._fail(job, 'provider_timeout', retry_at, False):
                    outcome = 'lost'
        except MemoryError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code=exc.code, duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                if not await self._fail(job, exc.code):
                    outcome = 'lost'
        except Exception as exc:
            observability.log_failure('job_failed', exc, 'error', destination=destination, code='provider_error', duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                if not await self._fail(job, 'provider_error'):
                    outcome = 'lost'
        finally:
            observability.record_job(destination, time.monotonic()-started, 'lost' if lost.is_set() else outcome)
            pulse.cancel()
            try:
                await pulse
            except asyncio.CancelledError:
                pass
        return True

    async def run(self):
        """Claim and run jobs until told to stop. It never ends because of an error: while the last access to the database failed it waits
        `backoff_delay` (growing, with jitter, up to MEMORY_WORKER_DB_BACKOFF_MAX) before the next claim; any access that works resets it."""
        cap = getattr(self.settings, 'worker_db_backoff_max', DEFAULT_BACKOFF_MAX)
        while not self.stopping.is_set():
            try:
                worked = await self.run_once()
            except Exception as exc:
                worked = True
                if not isinstance(exc, StoreUnavailable):  # a database failure is already logged and counted by `_store`
                    self.store_failures += 1
                    unavailable = is_store_unavailable(exc)
                    observability.log_failure('store_unavailable' if unavailable else 'worker_loop_error', exc, 'warning' if unavailable else 'error',
                                              reason='loop', count=self.store_failures)
            if self.store_failures:
                await self._wait(backoff_delay(self.store_failures, cap, self.rng))
            elif not worked:
                await self._wait(IDLE_SECONDS)


async def serve():
    observability.configure_logging()
    settings = Settings.from_env()
    store = Store(settings.dsn, settings.project_maps, embedding_enabled=getattr(settings, 'embed_enabled', True))
    store.extraction_enabled = getattr(settings, 'extract_enabled', False)
    worker = Worker(store, settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stopping.set)
        except NotImplementedError:
            pass
    await worker.run()


if __name__ == '__main__':
    asyncio.run(serve())
