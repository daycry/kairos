"""Explicit synthetic live-provider proof; never included in ordinary test discovery."""
import asyncio
import hashlib
import json
import os
import time
import uuid

from memory_platform.config import Settings
from memory_platform.models import Search
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.tests.test_store import create_core, event
from memory_platform.worker import Worker


def run(dsn):
    if not os.environ.get('MEMORY_LLM_MODEL'):
        raise SystemExit('This probe exercises extraction against a live model: set MEMORY_LLM_MODEL (the server has no default model).')
    asyncio.run(_run(dsn))


async def _run(dsn):
    start = time.monotonic()
    _, actor, pid = create_core()
    settings = Settings(dsn, ollama_url='http://host.docker.internal:11434', llm_model=os.environ['MEMORY_LLM_MODEL'], extract_enabled=True, provider_timeout=90,
                        embedding_worker_timeout=45, embedding_query_timeout=20)
    store = Store(dsn, embedding_enabled=True)
    store.extraction_enabled = True
    text = 'El trabajador debe comprobar el token de fencing antes de confirmar una proyeccion. No reutilices un resultado de una version anterior.'
    value = event(pid)
    value['payload'] = {'title': 'Prueba: "memoria", acentos á '+chr(0x1f9e0), 'content': text,
                        'tags': ['area:despliegue', 'nota:uno,dos', 'comilla:"valor"'],
                        'source': {'uri': 'fixture://live-provider'},
                        'facts': [{'subject': 'trabajador', 'predicate': 'comprueba', 'object': 'token de fencing',
                                   'evidence_quote': 'El trabajador debe comprobar el token de fencing'}]}
    accepted = store.ingest_event(actor, value)
    content = chr(0xfeff)+'\r\n'.join(['---', 'tags: ["nota:uno,dos"]', '---', '# Documento sintético', text])
    document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Documento: "canónico" '+chr(0x1f9e0),
                'content': content, 'tags': value['payload']['tags'],
                'source': {'uri': 'fixture://live-document', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
                'validation': {'status': 'validated', 'evidence': ['synthetic test fixture'], 'validated_by': 'isolated fixture'}}
    store.publish_document(actor, pid, document)
    worker = Worker(store, settings)
    for _ in range(8):
        if not await worker.run_once():
            break
    with store.transaction() as c:
        jobs = c.execute('SELECT destination,state,error_code FROM memory.jobs WHERE project_id=%s', (pid,)).fetchall()
        derived = c.execute('SELECT id,payload,parent_hash FROM memory.memory_items WHERE project_id=%s AND parent_item_id=%s', (pid, value['item_id'])).fetchone()
        vectors = c.execute('SELECT count(*) AS n FROM memory.embeddings WHERE project_id=%s', (pid,)).fetchone()['n']
    assert jobs and all(j['state'] == 'succeeded' for j in jobs), jobs
    assert derived and derived['payload']['validation_status'] == 'unverified', derived
    assert derived['payload']['provenance']['model'] == settings.llm_model
    assert vectors >= 2, vectors
    # Fresh objects and separate connections reload canon and vectors from disk.
    reloaded = Store(dsn, embedding_enabled=True)
    assert reloaded.get_document(actor, pid, document['document_id'])['content'] == content
    graph = reloaded.graph_data(actor, {'project_ids': [pid], 'layers': ['episodic', 'documental', 'temporal']})
    doc_node = next(n for n in graph['nodes'] if n['id'].startswith('documental:'))
    assert doc_node['name'] == document['title'] and doc_node['tags'] == document['tags']
    assert graph['links'] and all(link['evidence_refs'] for link in graph['links'])
    retrieval = Retrieval(reloaded, settings)
    found = await retrieval.search(actor, Search(project_ids=[pid], q='evitar resultados obsoletos al publicar', semantic=True))
    assert found['backends']['semantic']['status'] == 'ok', found['backends']
    assert found['items'] and any(item['layer'] == 'documental' for item in found['items'])
    assert reloaded.get_event_receipt(actor, accepted['event_id'])['item_id'] == value['item_id']
    print('MEMORY_LIVE_RESULT '+json.dumps({'passed': True, 'environment': 'isolated-postgres-synthetic-live-provider',
          'models': [settings.llm_model, 'nomic-embed-text'], 'jobs': len(jobs), 'vectors': vectors,
          'derived_unverified': True, 'source_hash_verified': True, 'unicode_tags_reloaded': True,
          'graph_nodes': len(graph['nodes']), 'graph_links': len(graph['links']), 'semantic_hits': len(found['items']),
          'seconds': round(time.monotonic()-start, 3)}, sort_keys=True), flush=True)
