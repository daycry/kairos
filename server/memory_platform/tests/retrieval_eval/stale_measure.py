"""Cost of stale item vectors (versions older than the current one, written before fragments existed) in the unchunked probe, before and after `admin backfill-chunks`.

Run inside the harness container only (python -m memory_platform.tests.retrieval_eval.stale_measure): the DSN guard and the pinned loopback address of the retrieval
evaluation apply, and the script works in a database of its own that it creates and drops. STALE resources, each with ONE old version still flagged
`chunked=false` and a current version already chunked. By default 8-dimension synthetic vectors under a model without index (the probe does not depend on the width; no HNSW involved).
With STALE_MODEL=nomic-embed-text STALE_DIMS=768 the rows go through the REAL partial HNSW index of `memory.embeddings` (and of `memory.embedding_chunks`): flagging a stale row
updates `chunked`, which prevents a HOT update, so every flagged row inserts a new entry in that graph; that is the cost the `backfill` phase pays (`stale_marked`).
Result: `STALE_COST_RESULT {json}`."""
import json
import os
import re
import time
import unittest
import uuid

import psycopg
from psycopg.conninfo import make_conninfo

from memory_platform.admin import backfill_chunks
from memory_platform.store import Store
from memory_platform.store_vectors import CURRENT_RESOURCE, UNCHUNKED_ONLY_LIMIT
from memory_platform.tests.retrieval_eval.run import check_dsn, connect_dsn

STALE = int(os.environ.get('STALE_ROWS', '40000'))
MODEL = os.environ.get('STALE_MODEL', 'stale-model')
DIMS = int(os.environ.get('STALE_DIMS', '8'))
PROBE = ('SELECT e.project_id,e.item_id,e.resource_type FROM memory.embeddings e WHERE e.project_id=ANY(%s) AND e.model=%s AND e.dims=%s AND NOT e.chunked AND '
         + CURRENT_RESOURCE + ' LIMIT %s')


def explain(c):
    params = (['p1'], MODEL, DIMS, None, None, None, None, None, None, None, None, UNCHUNKED_ONLY_LIMIT + 1)
    lines = [row[0] for row in c.execute('EXPLAIN (ANALYZE, BUFFERS) ' + PROBE, params).fetchall()]
    text = '\n'.join(lines)
    return {'execution_ms': float(re.search(r'Execution Time: ([\d.]+) ms', text).group(1)),
            'planning_ms': float(re.search(r'Planning Time: ([\d.]+) ms', text).group(1)),
            'shared_buffers': re.findall(r'Buffers: (shared[^\n]*)', text)[0], 'plan_top': [line.strip()[:160] for line in lines[:6]],
            'uses_partial_index': 'memory_embeddings_unchunked' in text}


class Measure(unittest.TestCase):
    def runTest(self):
        base = os.environ['MEMORY_TEST_DSN']
        check_dsn(os.environ.get('MEMORY_DSN'), base)
        base = connect_dsn(base)
        name = 'stale_' + uuid.uuid4().hex[:10]
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        dsn = make_conninfo(base, dbname=name)
        report = {'stale_versions_one_per_resource': STALE, 'postgres': 'isolated container build', 'dimensions': DIMS, 'model': MODEL}
        try:
            store = Store(dsn, embedding_enabled=True)
            store.migrate()
            from memory_platform.auth import hash_password
            actor_id = str(uuid.uuid4())
            with psycopg.connect(dsn) as c:
                c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
                c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (actor_id, 'stale', hash_password('fixture-password-123')))
                c.execute(f"""INSERT INTO memory.documents(project_id,id,version,canonical_hash,body)
                              SELECT 'p1','d'||n,2,repeat('b',64),jsonb_build_object('title','Documento '||n,'content','contenido '||n) FROM generate_series(1,{STALE}) n""")
                vector = f'ARRAY(SELECT random()+0.01 FROM generate_series(1,{DIMS}))'
                c.execute(f"""INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector,chunked)
                              SELECT 'p1','d'||n,'document',1,repeat('a',64),%s,{vector},false FROM generate_series(1,{STALE}) n""", (MODEL,))
                c.execute(f"""INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector,chunked)
                              SELECT 'p1','d'||n,'document',2,repeat('b',64),%s,{vector},true FROM generate_series(1,{STALE}) n""", (MODEL,))
                c.execute(f"""INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding)
                              SELECT 'p1','d'||n,'document',2,repeat('b',64),%s,0,0,12,ARRAY(SELECT random()+0.01 FROM generate_series(1,{DIMS}))::vector FROM generate_series(1,{STALE}) n""", (MODEL,))
            with psycopg.connect(dsn, autocommit=True) as c:
                for table in ('embeddings', 'documents', 'embedding_chunks'):
                    c.execute('VACUUM ANALYZE memory.' + table)
            actor = {'id': actor_id, 'credential_type': 'bootstrap'}
            queries = [[(n * 7 + i) % 11 + 1.0 for i in range(DIMS)] for n in range(30)]

            def measure(label):
                with psycopg.connect(dsn) as c:
                    rows = c.execute('SELECT count(*) FILTER (WHERE NOT chunked), count(*) FROM memory.embeddings').fetchone()
                    explain(c)  # cold run discarded
                    probe = explain(c)
                store.search_vectors(actor, ['p1'], queries[0], MODEL, limit=10)
                started = time.monotonic()
                truncated = 0
                for vector in queries:
                    truncated += bool(store.search_vectors(actor, ['p1'], vector, MODEL, limit=10).candidates_truncated)
                report[label] = {'rows_in_partial_index_unchunked': rows[0], 'embeddings_rows': rows[1], 'probe_explain': probe,
                                 'search_ms_avg': round((time.monotonic() - started) / len(queries) * 1000, 1), 'queries': len(queries), 'queries_truncated': truncated}
            measure('before_backfill')
            started = time.monotonic()
            result = backfill_chunks(store, MODEL, batch=200)
            report['backfill'] = dict(result, seconds=round(time.monotonic() - started, 2))
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute('VACUUM ANALYZE memory.embeddings')
            measure('after_backfill')
            started = time.monotonic()
            report['backfill_repeat'] = dict(backfill_chunks(store, MODEL, batch=200), seconds=round(time.monotonic() - started, 3))
        finally:
            with psycopg.connect(base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        print('STALE_COST_RESULT ' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.defaultTestLoader.discover = lambda *a, **k: unittest.TestSuite([Measure()])
    from memory_platform.tests import run_postgres
    run_postgres.main()
