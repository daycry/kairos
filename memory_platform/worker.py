"""Durable leased worker. Remote operations always occur outside database transactions."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import signal
import socket
import uuid
from .config import Settings
from .store import Store
from .providers import Ollama, Embeddings, ProviderError
from .errors import MemoryError


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
                deadline = getattr(self.settings, 'embedding_worker_timeout', 120.0)+10
            else:
                deadline = self.settings.provider_timeout+10
            async with asyncio.timeout(deadline):
                if job['destination'] == 'embed':
                    payload = job['payload']
                    text = str(payload.get('title', ''))+'\n'+str(payload.get('content', ''))
                    embedded = await provider.embed(text[:8000])
                    receipt = {'vector': embedded['embedding'], 'model': embedded['model'], 'verified': True, 'canonical_hash': job['canonical_hash']}
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
