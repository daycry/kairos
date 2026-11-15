"""B-09: cost of `has_vectors` and of the final payload fetch of `search_vectors`, BEFORE (the previous query, kept below verbatim) and AFTER (the store).

Runs only inside the harness container (the DSN guard of the retrieval evaluation applies first: loopback, port 55432, database memory_test) in a
database of its own that it creates and drops. Vectors are random; no network. Not part of the regression suite (its name does not match test_*.py).

    docker run --rm --network=none -e MEASURE_B09=1 kairos-test:IMG python -m memory_platform.tests.measure_vector_candidates
"""
import json
import os
import statistics
import time
import unittest
import uuid

import psycopg
from psycopg.conninfo import make_conninfo

from memory_platform.auth import hash_password
from memory_platform.store import Store
from memory_platform.store_common import canonical
from memory_platform.tests.retrieval_eval.run import check_dsn, connect_dsn

ROWS = int(os.environ.get('MEASURE_ROWS', '10000'))  # per table: ROWS documents and ROWS items, every one embedded
REPEATS = int(os.environ.get('MEASURE_REPEATS', '15'))
MODEL = 'nomic-embed-text'

# The query as it was before B-09 (memory_platform/store_vectors.py at the start of the task), same parameters.
OLD_QUERY = """WITH current_resources AS (
            SELECT i.project_id,i.id,i.version,i.canonical_hash,'item'::text AS resource_type,i.payload,to_jsonb(i) AS current_row
            FROM memory.memory_items i LEFT JOIN memory.memory_items p ON p.project_id=i.project_id AND p.id=i.parent_item_id
            WHERE i.project_id=ANY(%s) AND NOT i.deleted AND i.superseded_by IS NULL
            AND (i.parent_item_id IS NULL OR (p.version=i.parent_version AND p.canonical_hash=i.parent_hash AND NOT p.deleted AND p.superseded_by IS NULL))
            UNION ALL
            SELECT d.project_id,d.id,d.version,d.canonical_hash,'document'::text,d.body,to_jsonb(d)
            FROM memory.documents d WHERE d.project_id=ANY(%s) AND NOT d.deleted
        ) SELECT e.project_id,e.item_id,e.resource_type,e.version,e.canonical_hash,r.payload,r.current_row FROM current_resources r JOIN memory.embeddings e
            ON e.project_id=r.project_id AND e.item_id=r.id AND e.resource_type=r.resource_type
            AND e.version=r.version AND e.canonical_hash=r.canonical_hash
            WHERE e.model=%s AND (%s::text[] IS NULL OR r.payload->>'category'=ANY(%s))
            AND (%s::text[] IS NULL OR (r.payload->'tags') ?| %s)
            {selection} ORDER BY e.project_id,e.resource_type,e.item_id LIMIT %s"""
OLD_SELECTION = """ AND EXISTS (SELECT 1 FROM jsonb_to_recordset(%s::jsonb)
                AS wanted(project_id text,item_id text,resource_type text)
                WHERE wanted.project_id=e.project_id AND wanted.item_id=e.item_id::text
                AND wanted.resource_type=e.resource_type)"""


def old_candidates(c, projects, model, identities, limit):
    params = [projects, projects, model, None, None, None, None]
    selection = ''
    if identities is not None:
        selection = OLD_SELECTION
        params.append(canonical(identities))
    params.append(limit)
    return c.execute(OLD_QUERY.format(selection=selection), params).fetchall()


def timed(fn):
    samples = []
    result = None
    for _ in range(REPEATS):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1000)
    return result, {'median_ms': round(statistics.median(samples), 2), 'min_ms': round(min(samples), 2), 'max_ms': round(max(samples), 2)}


class Measure(unittest.TestCase):
    def runTest(self):
        base = os.environ['MEMORY_TEST_DSN']
        check_dsn(os.environ.get('MEMORY_DSN'), base)
        base = connect_dsn(base)
        name = 'b09_' + uuid.uuid4().hex[:10]
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        dsn = make_conninfo(base, dbname=name)
        report = {'rows_per_table': ROWS, 'repeats': REPEATS, 'postgres': 'isolated container build'}
        try:
            store = Store(dsn, embedding_enabled=True)
            store.migrate()
            actor_id = str(uuid.uuid4())
            with store.transaction() as c:
                c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (actor_id, 'm-' + actor_id[:8], hash_password('fixture-password-123')))
            actor = {'id': actor_id, 'credential_type': 'bootstrap'}
            store.create_project(actor, {'id': 'p1', 'title': 'Project 1'})
            started = time.monotonic()
            with psycopg.connect(dsn) as c:
                body = "jsonb_build_object('title','Documento '||n,'content',repeat('contenido de ejemplo del despliegue ',70),'source',jsonb_build_object('uri','fixture://'||n))"
                c.execute(f"INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) SELECT 'p1','d'||n,1,repeat('a',64),{body} FROM generate_series(1,{ROWS}) n")
                c.execute(f"""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector)
                              SELECT 'p1','i'||n,1,repeat('b',64),'note',jsonb_build_object('title','Nota '||n,'content',repeat('contenido de ejemplo de la nota ',70)),'s','a',clock_timestamp(),to_tsvector('simple','x') FROM generate_series(1,{ROWS}) n""")
                for table, rtype in (('documents', 'document'), ('memory_items', 'item')):
                    c.execute(f"INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) SELECT 'p1',id,%s,1,canonical_hash,%s,ARRAY(SELECT random()+0.01 FROM generate_series(1,768)) FROM memory.{table}", (rtype, MODEL))
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute('ANALYZE')
            report['seed_seconds'] = round(time.monotonic() - started, 1)
            # has_vectors: before = the candidate query with LIMIT 1, after = the store method
            with store.transaction() as c:
                before_ready, report['has_vectors_before'] = timed(lambda: bool(old_candidates(c, ['p1'], MODEL, None, 1)))
            after_ready, report['has_vectors_after'] = timed(lambda: store.has_vectors(actor, ['p1'], MODEL))
            report['has_vectors_same_answer'] = before_ready is True and after_ready is True
            # final fetch of the winners: ten identities (five documents, five items), as search_vectors asks for them
            identities = [{'project_id': 'p1', 'item_id': ('d%d' if number % 2 else 'i%d') % (number * 37 + 1), 'resource_type': 'document' if number % 2 else 'item'} for number in range(10)]
            with store.transaction() as c:
                old_rows, report['final_fetch_before'] = timed(lambda: old_candidates(c, ['p1'], MODEL, identities, 10))
                new_rows, report['final_fetch_after'] = timed(lambda: store._vector_candidates(c, ['p1'], MODEL, None, None, 10, identities=identities))

            def key(row):
                return (row['project_id'], row['resource_type'], str(row['item_id']))
            report['final_fetch_same_rows'] = len(new_rows) == 10 and [key(r) for r in old_rows] == [key(r) for r in new_rows] and [r['current_row'] for r in old_rows] == [r['current_row'] for r in new_rows]
            for stage in ('has_vectors', 'final_fetch'):
                before, after = report[stage + '_before']['median_ms'], report[stage + '_after']['median_ms']
                report[stage + '_speedup'] = round(before / after, 1) if after else None
        finally:
            with psycopg.connect(base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        print('VECTOR_CANDIDATES_RESULT ' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    if os.environ.get('MEASURE_B09') != '1':
        raise SystemExit('Set MEASURE_B09=1: this script only runs inside the isolated harness container.')
    unittest.defaultTestLoader.discover = lambda *a, **k: unittest.TestSuite([Measure()])
    from memory_platform.tests import run_postgres
    run_postgres.main()
