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
from .store_pool import attach_pool, close_pool
from .store_jobs import job_outcome, stored_item_vector
from .providers import Ollama, Embeddings, ProviderError
from .errors import MemoryError, StoreUnavailable, is_store_error, is_store_transient, is_store_unavailable
from .chunking import chunk_text, embedding_text

JOB_DEADLINE_MARGIN = 10  # seconds the job may outlive the provider's own deadline
IDLE_SECONDS = 1.0  # wait between two claims when the queue is empty
WRITE_RETRY_MAX = 5  # failed writes of one outcome (`complete_job`/`fail_job`) after which the worker stops repeating it, however well the renewal of the lease works
BACKOFF_FIRST = 1.0  # ceiling of the wait after the first consecutive database failure; it doubles up to MEMORY_WORKER_DB_BACKOFF_MAX


class Abandoned(Exception):
    """The worker gave up writing the outcome of a job (the lease is gone, or it was told to stop): the job stays as the database has it and is claimed again."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


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
        self.store.max_attempts = settings.max_attempts  # the cap `claim_job` applies to a job whose lease expired (`attempts_exhausted`); same value as the retry policy below
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

    async def _landed(self, job, stage, args):
        """After an ambiguous failure of the write (the connection broke, the answer was lost) the lease can no longer be renewed because the write DID land: ask the
        database. True only when the job is as this very write leaves it (`succeeded` after `complete_job`; `failed`/`pending`/`unknown` with the code of this
        `fail_job`, under our fence). Any doubt, or a database that does not answer, is False: the job is the database's to say."""
        try:
            row = await self._store('read', job_outcome, self.store, job['id'], job['fence'])
        except Exception as exc:  # StoreUnavailable (also logged by `_store`) or any other error: not proven
            observability.log_failure('job_outcome_unread', exc, 'warning', reason=stage)
            return False
        if not row:
            return False
        if stage == 'complete':
            return row['state'] == 'succeeded'
        return row['state'] in ('failed', 'pending', 'unknown') and row['error_code'] == args[0]

    async def _persist(self, job, lease, lost, destination, stage, call, *args):
        """Write the OUTCOME of a job (`complete_job` or `fail_job`) and do not lose it to a database that does not answer: the result stays in memory and the
        write is repeated, each time after the same growing, jittered, stop-aware wait as a claim (`backoff_delay`), and once the database answers the lease is
        renewed before writing again. An error the database ANSWERED with that is worth repeating (`is_store_transient`: 40001, 40P01, 57014, 55P03, class 53) is
        repeated the same way. The repetition has a BUDGET per write: at most `MEMORY_WORKER_WRITE_RETRY_SECONDS` from the first failure (default: the lease) and
        `WRITE_RETRY_MAX` failed writes, even while the renewal works. It ends when the write lands (returns what the store answered; `False` means the lease or
        fence was no longer ours: logged and returned, never counted as written) or raises `Abandoned` when the lease is gone (expired by the clock this worker
        keeps, or `renew_lease` says so and the job is not already as this write leaves it), the budget is spent (`retry_budget`: it stops renewing, so the job
        returns to the queue when the lease ends and the cap of `claim_job` applies to a poisoned receipt) or the worker is told to stop. A transient error that
        outlasts the budget of `complete_job` is raised as it is (the caller fails the job with `store_error` and a retry). Only an abandoned job is left
        `running`, with the attempt its claim charged. If the worker process dies with the result in memory, or the outage outlasts the lease (a lease that
        ran out is never revived), that attempt is lost with the result."""
        cap = getattr(self.settings, 'worker_db_backoff_max', DEFAULT_BACKOFF_MAX)
        budget = getattr(self.settings, 'worker_write_retry_seconds', None)
        if budget is None:
            budget = self.settings.lease_seconds
        def abandon(reason):
            observability.log_event('job_write_abandoned', 'warning', destination=destination, reason=stage+':'+reason)  # `reason` is `<stage>:<why>`, e.g. complete:lease_expired
            raise Abandoned(reason)
        failures, first = 0, None
        while True:
            transient = None
            try:
                written = await self._store(stage, call, job['id'], job['fence'], *args)
            except StoreUnavailable:
                pass  # logged by `_store`
            except Exception as exc:
                if not is_store_transient(exc):
                    raise
                transient = exc
                observability.log_failure('store_retry', exc, 'warning', reason=stage, count=failures+1)
            else:
                if written is False:
                    observability.log_event('job_write_abandoned', 'warning', destination=destination, reason=stage+':fence')
                return written
            failures += 1
            if first is None:
                first = self.clock()
            while True:  # the write failed: wait, then renew the lease as soon as the database answers
                if failures >= WRITE_RETRY_MAX or self.clock()-first >= budget:
                    if transient is not None and stage == 'complete':
                        raise transient
                    abandon('retry_budget')
                await self._wait(backoff_delay(self.store_failures or failures, cap, self.rng))
                if self.stopping.is_set():
                    abandon('stopping')
                if lost.is_set():
                    abandon('lease_lost')
                if self.clock() >= lease[0]:
                    lost.set()
                    abandon('lease_expired')
                if self.clock()-first >= budget:
                    continue  # the budget check at the top of the loop decides
                try:
                    beat = self.clock()
                    renewed = await self._store('heartbeat', self.store.renew_lease, job['id'], job['fence'], self.settings.lease_seconds)
                except StoreUnavailable:
                    continue
                except Exception as exc:
                    if is_store_transient(exc):
                        continue
                    raise
                if not renewed:
                    if await self._landed(job, stage, args):
                        return True  # the write that looked lost had landed: it counts as written
                    lost.set()
                    abandon('lease_lost')
                lease[0] = beat+self.settings.lease_seconds
                break

    async def _fail(self, job, lease, lost, destination, *args):
        """`fail_job` through `_persist`: the failure is recorded as the provider/application left it even if the database is down for a while. Returns False when
        it could not be written (lease lost, fence lost, stop): the job is then the database's to say."""
        try:
            return await self._persist(job, lease, lost, destination, 'fail', self.store.fail_job, *args) is not False
        except Abandoned:
            return False

    async def run_once(self):
        job = await self._store('claim', self.store.claim_job, self.id, self.settings.lease_seconds)
        if not job:
            return False
        lost = asyncio.Event()
        destination = observability.closed(job['destination'], observability.DESTINATIONS)
        started, outcome = time.monotonic(), 'failed'
        lease = [self.clock()+self.settings.lease_seconds]  # when this worker's own clock says the lease runs out; moved by every renewal that works
        async def heartbeat():
            while True:
                await self._heartbeat_wait(max(0.1, self.settings.lease_seconds/3))
                try:
                    beat = self.clock()
                    renewed = await self._store('heartbeat', self.store.renew_lease, job['id'], job['fence'], self.settings.lease_seconds)
                    if renewed:
                        lease[0] = beat+self.settings.lease_seconds
                    else:
                        observability.log_event('lease_lost', 'warning', destination=destination)
                        lost.set()
                        return
                except StoreUnavailable:
                    continue  # logged by `_store`: the lease is what the database says, so the next beat tries again; the job is lost only when it says so
                except Exception as exc:
                    if is_store_transient(exc):  # the database answered with an error worth repeating: the next beat tries again while the lease lives
                        observability.log_failure('store_retry', exc, 'warning', reason='heartbeat')
                        continue
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
            if await self._persist(job, lease, lost, destination, 'complete', self.store.complete_job, receipt) is False:
                outcome = 'lost'  # the lease or fence was no longer ours: somebody else owns the job, nothing was completed
            else:
                outcome = 'completed'
                observability.log_event('job_completed', destination=destination, duration_ms=observability.elapsed_ms(started))
        except Abandoned:
            outcome = 'lost'  # already logged (`job_write_abandoned`): the job stays as the database has it and is claimed again
        except StoreUnavailable:
            # The database did not answer reading the stored vector: not the provider's failure, so the job is neither failed nor given a `provider_error`.
            # It stays `running` and is claimed again when its lease expires (the attempt of this claim is spent; `complete_job`/`fail_job` are retried in place instead).
            outcome = 'lost'
        except ProviderError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code=exc.code, duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                retry_at = None
                if exc.retryable and job['attempts'] < self.settings.max_attempts:
                    retry_at = datetime.now(timezone.utc)+timedelta(seconds=min(60, 2**job['attempts']))
                if not await self._fail(job, lease, lost, destination, exc.code, retry_at, False):
                    outcome = 'lost'
        except TimeoutError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code='provider_timeout', duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                retry_at = datetime.now(timezone.utc)+timedelta(seconds=30) if job['attempts'] < self.settings.max_attempts else None
                if not await self._fail(job, lease, lost, destination, 'provider_timeout', retry_at, False):
                    outcome = 'lost'
        except MemoryError as exc:
            observability.log_failure('job_failed', exc, 'warning', destination=destination, code=exc.code, duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                if not await self._fail(job, lease, lost, destination, exc.code):
                    outcome = 'lost'
        except Exception as exc:
            # An error of the database that is not an outage (a cancelled query, a lock timeout...) is told apart from a provider failure by its code.
            code = 'store_error' if is_store_error(exc) else 'provider_error'
            observability.log_failure('job_failed', exc, 'error', destination=destination, code=code, duration_ms=observability.elapsed_ms(started))
            if not lost.is_set():
                retry_at = None
                if is_store_transient(exc) and job['attempts'] < self.settings.max_attempts:
                    retry_at = datetime.now(timezone.utc)+timedelta(seconds=min(60, 2**job['attempts']))  # it may well work next time; not terminal until the attempts run out
                if not await self._fail(job, lease, lost, destination, code, retry_at, False):
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
    attach_pool(store, settings, 'worker')
    worker = Worker(store, settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stopping.set)
        except NotImplementedError:
            pass
    try:
        await worker.run()
    finally:
        await asyncio.to_thread(close_pool, store)  # the connections are closed on SIGTERM too: the process leaves no session behind in PostgreSQL


if __name__ == '__main__':
    asyncio.run(serve())
