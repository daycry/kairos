"""Durable leased worker. Remote operations always occur outside database transactions."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import signal
import socket
import uuid
from .config import Settings, embedding_job_timeout
from .store import Store
from .store_jobs import stored_item_vector
from .providers import Ollama, Embeddings, ProviderError
from .errors import MemoryError
from .chunking import chunk_text, embedding_text

JOB_DEADLINE_MARGIN = 10  # seconds the job may outlive the provider's own deadline


def embed_plan(settings, payload):
    """(embedding text, fragments, inputs): what `embed_receipt` will send. One whole fragment is one input (the text itself); anything else is
    its fragments plus the whole text last, so the item vector keeps meaning what it always meant (the embedding of the first 8,000 characters)."""
    text = embedding_text(payload.get('title', ''), payload.get('content', ''))
    chunks = chunk_text(text, getattr(settings, 'chunk_chars', None), getattr(settings, 'chunk_overlap', None), getattr(settings, 'chunk_max', None))
    return text, chunks, (1 if len(chunks) <= 1 and not chunks.truncated else len(chunks)+1)


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
    # `item_vector`: the item vector already stored for this very version, hash and model (the backfill of a resource that only lacks fragments): not embedded again.
    embedded = await provider.embed_many([chunk.text(text).strip() for chunk in chunks]+([] if item_vector else [text]))
    vectors = embedded.get('embeddings')
    if not isinstance(vectors, list) or len(vectors) != inputs-(1 if item_vector else 0):
        raise ProviderError('embedding_invalid')
    receipt = {'vector': item_vector or vectors[-1], 'model': embedded['model'], 'verified': bool(embedded.get('verified')), 'canonical_hash': canonical_hash,
               'chunks': [{'ordinal': chunk.ordinal, 'char_start': chunk.char_start, 'char_end': chunk.char_end, 'vector': vector} for chunk, vector in zip(chunks, vectors)]}
    if chunks.truncated:
        receipt.update(chunks_truncated=True, chunks_covered_chars=chunks.covered_chars)
    return receipt


class Worker:
    def __init__(self, store, settings, providers=None, worker_id=None):
        self.store, self.settings = store, settings
        self.id = worker_id or socket.gethostname()+':'+str(uuid.uuid4())
        self.providers = providers if providers is not None else {'extract': Ollama(settings), 'embed': Embeddings(settings)}
        self.stopping = asyncio.Event()

    async def run_once(self):
        job = await asyncio.to_thread(self.store.claim_job, self.id, self.settings.lease_seconds)
        if not job:
            return False
        lost = asyncio.Event()
        async def heartbeat():
            while True:
                await asyncio.sleep(max(0.1, self.settings.lease_seconds/3))
                try:
                    renewed = await asyncio.to_thread(self.store.renew_lease, job['id'], job['fence'], self.settings.lease_seconds)
                    if not renewed:
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return
        pulse = asyncio.create_task(heartbeat())
        try:
            provider = self.providers.get(job['destination']) if job['destination'] in {'extract', 'embed'} else None
            if not provider:
                raise ProviderError('unsupported_destination')
            if job['destination'] == 'embed':
                # Proportional to the number of batches the text needs (MEMORY_EMBED_BATCH_TIMEOUT each), up to MEMORY_EMBED_JOB_MAX_TIMEOUT.
                deadline = embedding_job_timeout(self.settings, embed_plan(self.settings, job['payload'])[2])+JOB_DEADLINE_MARGIN
            else:
                deadline = self.settings.provider_timeout+10
            async with asyncio.timeout(deadline):
                if job['destination'] == 'embed':
                    stored = None
                    if embed_plan(self.settings, job['payload'])[2] > 1:
                        stored = await asyncio.to_thread(stored_item_vector, self.store, job['project_id'], job['item_id'], job['resource_type'], job['version'], job['canonical_hash'], self.settings.embedding_model)
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
            await asyncio.to_thread(self.store.complete_job, job['id'], job['fence'], receipt)
        except ProviderError as exc:
            if not lost.is_set():
                retry_at = None
                if exc.retryable and job['attempts'] < self.settings.max_attempts:
                    retry_at = datetime.now(timezone.utc)+timedelta(seconds=min(60, 2**job['attempts']))
                await asyncio.to_thread(self.store.fail_job, job['id'], job['fence'], exc.code, retry_at, False)
        except TimeoutError:
            if not lost.is_set():
                retry_at = datetime.now(timezone.utc)+timedelta(seconds=30) if job['attempts'] < self.settings.max_attempts else None
                await asyncio.to_thread(self.store.fail_job, job['id'], job['fence'], 'provider_timeout',
                                        retry_at, False)
        except MemoryError as exc:
            if not lost.is_set():
                await asyncio.to_thread(self.store.fail_job, job['id'], job['fence'], exc.code)
        except Exception:
            if not lost.is_set():
                await asyncio.to_thread(self.store.fail_job, job['id'], job['fence'], 'provider_error')
        finally:
            pulse.cancel()
            try:
                await pulse
            except asyncio.CancelledError:
                pass
        return True

    async def run(self):
        while not self.stopping.is_set():
            if not await self.run_once():
                try:
                    await asyncio.wait_for(self.stopping.wait(), 1)
                except TimeoutError:
                    pass


async def serve():
    settings = Settings.from_env()
    worker = Worker(Store(settings.dsn, settings.project_maps, embedding_enabled=getattr(settings, 'embed_enabled', True)), settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stopping.set)
        except NotImplementedError:
            pass
    await worker.run()


if __name__ == '__main__':
    asyncio.run(serve())
