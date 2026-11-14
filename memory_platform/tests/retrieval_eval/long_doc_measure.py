"""Deadline of long documents with a REAL embeddings model: chunking + `embed_many` exactly as the worker does it (`embed_receipt`).

Measures, for synthetic texts of growing size, how many fragments, inputs and batches the worker sends, how long the real model takes and how that compares
with the deadlines of the job (`embedding_job_timeout`, `worker_deadline`). No database and no deployed service: it only talks to the disposable Ollama named in
MEMORY_RETRIEVAL_EVAL_OLLAMA_URL (same guard as the retrieval evaluation, see `check_ollama_url`). Embeddings only, no LLM.

Run: MEMORY_RETRIEVAL_EVAL_OLLAMA_URL=http://<disposable-ollama>:11434 python -m memory_platform.tests.retrieval_eval.long_doc_measure
Result: `LONG_DOC_RESULT {json}`.
"""
import asyncio
import json
import os
import time

from memory_platform.config import Settings, embedding_job_timeout
from memory_platform.tests.retrieval_eval.run import OLLAMA_URL_ENV, check_ollama_url
from memory_platform.worker import embed_plan, embed_receipt, worker_deadline

SIZES = [int(value) for value in os.environ.get('LONG_DOC_SIZES', '8000,20000,50000,100000,200000,320000').split(',')]
PARAGRAPH = ('Procedimiento {n}: antes de desplegar el servicio se comprueba la copia de seguridad, se revisan las migraciones y se anota el resultado de cada '
             'fase en el registro de operaciones. The rollback plan {n} lists the previous image, the database dump and the owner of the change. ')


def synthetic_text(size):
    parts, total, n = [], 0, 0
    while total < size:
        n += 1
        if n % 12 == 1:
            parts.append(f'## Seccion {n // 12 + 1}\n')
        paragraph = PARAGRAPH.format(n=n) * 3 + '\n\n'
        parts.append(paragraph)
        total += len(parts[-1])
    return ''.join(parts)[:size]


async def measure(settings, provider, size):
    from memory_platform.providers import Embeddings
    text = synthetic_text(size)
    payload = {'title': 'Documento largo sintetico %d' % size, 'content': text}
    _, chunks, inputs = embed_plan(settings, payload)
    batches = -(-inputs // settings.embedding_batch_size)
    started = time.monotonic()
    receipt = await embed_receipt(provider, settings, payload, 'h' * 64)
    seconds = time.monotonic() - started
    return {'characters': size, 'fragments': len(chunks), 'truncated': bool(chunks.truncated), 'inputs': inputs, 'batches': batches,
            'seconds': round(seconds, 2), 'seconds_per_batch': round(seconds / batches, 2),
            'embedding_job_timeout_s': embedding_job_timeout(settings, inputs), 'worker_deadline_s': worker_deadline(settings, inputs, stored_vector=False),
            'worker_deadline_with_stored_vector_s': worker_deadline(settings, inputs, stored_vector=True),
            'fraction_of_job_timeout': round(seconds / embedding_job_timeout(settings, inputs), 3), 'fragments_in_receipt': len(receipt.get('chunks', []))}


async def main():
    from memory_platform.providers import Embeddings
    settings = Settings('unused', ollama_url=check_ollama_url(os.environ.get(OLLAMA_URL_ENV)))
    provider = Embeddings(settings)
    await provider.embed('warm-up of the model', query=True)  # loads the model: not part of any measure
    rows = [await measure(settings, provider, size) for size in SIZES]
    print('LONG_DOC_RESULT ' + json.dumps({'ollama': 'disposable (MEMORY_RETRIEVAL_EVAL_OLLAMA_URL)', 'model': settings.embedding_model, 'chunk_chars': settings.chunk_chars,
                                           'chunk_overlap': settings.chunk_overlap, 'chunk_max': settings.chunk_max, 'batch_size': settings.embedding_batch_size,
                                           'batch_timeout_s': settings.embedding_batch_timeout, 'job_timeout_max_s': settings.embedding_job_timeout_max, 'rows': rows},
                                          sort_keys=True), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
