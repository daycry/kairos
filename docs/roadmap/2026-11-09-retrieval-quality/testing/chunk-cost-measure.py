"""Cost of schema version 10, `admin backfill-chunks`, the fragment tables and the STEADY STATE (every resource chunked), in an isolated PostgreSQL.

Runs only inside the harness container: the DSN guard of the retrieval evaluation (loopback, port 55432, database memory_test) applies first and
the script then works in a database of its own that it creates and drops. Embeddings come from a local simulated provider; no network."""
import hashlib
import json
import os
import random
import time
import unittest
import uuid
from pathlib import Path

import asyncio
import multiprocessing

import psycopg
from psycopg.conninfo import make_conninfo

from memory_platform.admin import backfill_chunks
from memory_platform.chunking import chunk_text, embedding_text
from memory_platform.config import Settings
from memory_platform.store import Store
from memory_platform.tests.retrieval_eval.run import check_dsn, connect_dsn
from memory_platform.worker import Worker

SCHEMA = Path('/app/memory_platform/schema.sql')
MARKER = '-- embedding-chunks (schema version 10)'
ROWS = int(os.environ.get('COST_ROWS', '20000'))
DOCS = int(os.environ.get('COST_DOCS', '300'))
MODEL = 'nomic-embed-text'


def size(c, relation):
    return c.execute('SELECT pg_total_relation_size(%s::regclass)', (relation,)).fetchone()[0]


def drain_process(dsn):
    """One OS process: its own Store and Worker (the real worker loop) with a simulated provider; returns the jobs it completed."""
    generator = random.Random(os.getpid())
    pool = [[generator.random() + 0.01 for _ in range(768)] for _ in range(64)]

    def vector():
        # a distinct vector per call (a handful of coordinates of a pooled one move): HNSW over a few dozen duplicated points is not representative
        value = list(pool[generator.randrange(64)])
        for _ in range(8):
            value[generator.randrange(768)] += generator.random()
        return value

    class Simulated:
        async def embed(self, text, query=False):
            return {'embedding': vector(), 'model': MODEL, 'verified': True}

        async def embed_many(self, texts, query=False):
            return {'embeddings': [vector() for _ in texts], 'model': MODEL, 'verified': True}
    worker = Worker(Store(dsn, embedding_enabled=True), Settings(dsn, lease_seconds=120), {'embed': Simulated()}, worker_id='cost-%d' % os.getpid())

    async def loop():
        done = 0
        while await worker.run_once():
            done += 1
        return done
    return asyncio.run(loop())


class Measure(unittest.TestCase):
    def runTest(self):
        base = os.environ['MEMORY_TEST_DSN']
        check_dsn(os.environ.get('MEMORY_DSN'), base)  # same guard as retrieval-eval: never anything but the harness' own temporary database
        base = connect_dsn(base)  # hostaddr pinned to loopback, as the retrieval evaluation does
        name = 'cost_' + uuid.uuid4().hex[:10]
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        dsn = make_conninfo(base, dbname=name)
        report = {'rows_per_table': ROWS, 'postgres': 'isolated container build', 'maintenance_work_mem': '256MB (migration default)'}
        try:
            text = SCHEMA.read_text(encoding='utf-8')
            from memory_platform.agent_store import migrate_agent_schema
            from memory_platform.corpus_answers import migrate_corpus_answers
            from memory_platform.extended_store import migrate_extended_schema
            from memory_platform.store_vectors import migrate_vector_indexes
            started = time.monotonic()
            with psycopg.connect(dsn) as c:
                c.execute(text[:text.index(MARKER)])
                migrate_vector_indexes(c)
                migrate_agent_schema(c)
                migrate_extended_schema(c)
                migrate_corpus_answers(c)
                c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
                body = "jsonb_build_object('title','Documento '||n,'content',repeat('contenido de ejemplo del despliegue ',70),'source',jsonb_build_object('uri','fixture://'||n))"
                c.execute(f"INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) SELECT 'p1','d'||n,1,repeat('a',64),{body} FROM generate_series(1,{ROWS}) n")
                c.execute(f"""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector)
                              SELECT 'p1','i'||n,1,repeat('b',64),'note',jsonb_build_object('title','Nota '||n,'content',repeat('contenido de ejemplo de la nota ',70)),'s','a',clock_timestamp(),to_tsvector('simple','x') FROM generate_series(1,{ROWS}) n""")
                for table, rtype, column, prefix in (('documents', 'document', 'id', 'd'), ('memory_items', 'item', 'id', 'i')):
                    c.execute(f"INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state) SELECT gen_random_uuid()::text,'p1',{column},1,canonical_hash,%s,'embed','upsert','succeeded' FROM memory.{table}", (rtype,))
                    c.execute(f"INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) SELECT 'p1',{column},%s,1,canonical_hash,%s,ARRAY(SELECT random()+0.01 FROM generate_series(1,768)) FROM memory.{table}", (rtype, MODEL))
            report['seed_seconds'] = round(time.monotonic() - started, 1)
            with psycopg.connect(dsn) as c:
                report['before'] = {name: size(c, 'memory.' + name) for name in ('documents', 'memory_items', 'embeddings', 'jobs')}
            store = Store(dsn, embedding_enabled=True)
            started = time.monotonic()
            store.migrate()
            report['migrate_v9_to_v10_seconds'] = round(time.monotonic() - started, 3)
            started = time.monotonic()
            store.migrate()
            report['migrate_repeat_seconds'] = round(time.monotonic() - started, 3)
            with psycopg.connect(dsn) as c:
                report['chunk_table_empty_bytes'] = size(c, 'memory.embedding_chunks')
            # Backfill: every resource is a candidate (embedded by the previous release, no fragments).
            started = time.monotonic()
            first = backfill_chunks(store, MODEL, batch=200)
            report['backfill_seconds'] = round(time.monotonic() - started, 2)
            report['backfill_first_run'] = first
            started = time.monotonic()
            second = backfill_chunks(store, MODEL, batch=200)
            report['backfill_second_run'] = dict(second, seconds=round(time.monotonic() - started, 3))
            with psycopg.connect(dsn) as c:
                report['after'] = {name: size(c, 'memory.' + name) for name in ('documents', 'memory_items', 'embeddings', 'jobs')}
                report['jobs_pending'] = c.execute("SELECT count(*) FROM memory.jobs WHERE state='pending'").fetchone()[0]
                # one batch of the candidate query on its own (it is re-run for every batch)
                from memory_platform.admin import backfill_query
                started = time.monotonic()
                for kind in ('document', 'item'):
                    c.execute(backfill_query(kind), {'project': None, 'model': MODEL, 'retry_failed': False, 'after_project': None, 'after_item': None, 'limit': 200}).fetchall()
                report['one_pass_over_both_tables_when_nothing_is_left_seconds'] = round(time.monotonic() - started, 3)
            # STEADY STATE: the real Worker drains every job of the backfill (all 40,000 resources get their fragments) with a simulated provider.
            generator = random.Random(7)
            pool = [[generator.random() + 0.01 for _ in range(768)] for _ in range(64)]

            WORKERS = int(os.environ.get('COST_WORKERS', '8'))  # processes: the job claim is SKIP LOCKED, so several workers only drain the same queue faster
            context = multiprocessing.get_context('fork')
            started = time.monotonic()
            # (the drain itself runs below, after the indexes are dropped)
            # The HNSW indexes are dropped for the drain and rebuilt in bulk afterwards (an incremental HNSW insert costs ~0.1 s of CPU and 40,000 jobs
            # would take over an hour here; the steady state, every resource chunked, is the same). The rebuild is timed and reported.
            with psycopg.connect(dsn, autocommit=True) as c:
                names = [row[0] for row in c.execute("SELECT indexname FROM pg_indexes WHERE schemaname='memory' AND indexname LIKE 'memory_%hnsw_%'").fetchall()]
                for name in names:
                    c.execute('DROP INDEX memory.' + name)
            report['hnsw_indexes_dropped_for_the_drain'] = len(names)
            started = time.monotonic()
            with context.Pool(WORKERS) as pool:
                report['worker_jobs_drained'] = sum(pool.map(drain_process, [dsn] * WORKERS))
            report['worker_concurrency'] = WORKERS
            report['worker_drain_seconds'] = round(time.monotonic() - started, 1)
            with psycopg.connect(dsn) as c:
                report['after_drain'] = {'chunks': c.execute('SELECT count(*) FROM memory.embedding_chunks').fetchone()[0],
                                         'embeddings_chunked': c.execute('SELECT count(*) FILTER (WHERE chunked) FROM memory.embeddings').fetchone()[0],
                                         'embeddings': c.execute('SELECT count(*) FROM memory.embeddings').fetchone()[0],
                                         'jobs_pending': c.execute("SELECT count(*) FROM memory.jobs WHERE state<>'succeeded'").fetchone()[0]}
            started = time.monotonic()
            with psycopg.connect(dsn) as c:
                c.execute('SET max_parallel_maintenance_workers=0')  # parallel builds need /dev/shm segments the 64 MB container default cannot give
                c.execute("SET maintenance_work_mem='1GB'")  # the graph of 100k x 768 does not fit the 256 MB migration default (docs/operations.md)
                from memory_platform.store_vectors import migrate_vector_indexes
                migrate_vector_indexes(c)
            report['hnsw_rebuild_seconds'] = round(time.monotonic() - started, 1)
            third = backfill_chunks(store, MODEL, batch=200)
            report['backfill_after_drain'] = third
            # Fragment tables: worker output of DOCS documents of 20,000 characters and one of 200,000, through complete_job.
            def content(n):
                words = ['servidor', 'cluster', 'despliegue', 'copia', 'archivo', 'registro', 'cola', 'proceso', 'memoria', 'tarea']
                return ' '.join(generator.choice(words) for _ in range(n // 8))[:n]
            started_size = None
            totals = {'documents': 0, 'chunks': 0, 'complete_job_seconds': 0.0}
            samples = []
            for number in range(DOCS + 1):
                length = 200000 if number == DOCS else 20000
                text_body = content(length)
                doc_id = f'long-{number}'
                title = f'Largo {number}'
                full = embedding_text(title, text_body)
                chunks = chunk_text(full)
                with psycopg.connect(dsn) as c:
                    c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES('p1',%s,1,%s,%s::jsonb)", (doc_id, hashlib.sha256(full.encode()).hexdigest(), json.dumps({'title': title, 'content': text_body})))
                    c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,fence,lease_until) SELECT %s,'p1',%s,1,canonical_hash,'document','embed','upsert','running',1,clock_timestamp()+interval '1 hour' FROM memory.documents WHERE project_id='p1' AND id=%s", (str(uuid.uuid4()), doc_id, doc_id))
                    job = c.execute("SELECT id,canonical_hash FROM memory.jobs WHERE project_id='p1' AND item_id=%s", (doc_id,)).fetchone()
                vectors = [[generator.random() + 0.01 for _ in range(768)] for _ in chunks]
                receipt = {'vector': vectors[0], 'model': MODEL, 'verified': True, 'canonical_hash': job[1],
                           'chunks': [{'ordinal': ch.ordinal, 'char_start': ch.char_start, 'char_end': ch.char_end, 'vector': v} for ch, v in zip(chunks, vectors)]}
                started = time.monotonic()
                assert store.complete_job(job[0], 1, receipt)
                elapsed = time.monotonic() - started
                totals['complete_job_seconds'] += elapsed
                totals['documents'] += 1
                totals['chunks'] += len(chunks)
                if number in (0, DOCS):
                    samples.append({'characters': length, 'chunks': len(chunks), 'complete_job_seconds': round(elapsed, 3)})
            with psycopg.connect(dsn) as c:
                heap = c.execute("SELECT pg_table_size('memory.embedding_chunks'), pg_indexes_size('memory.embedding_chunks')").fetchone()
                hnsw = c.execute("SELECT sum(pg_relation_size(indexrelid)) FROM pg_index WHERE indrelid='memory.embedding_chunks'::regclass AND indexrelid::regclass::text LIKE 'memory.memory_chunk_hnsw_%'").fetchone()[0]
                report['fragments'] = {'documents_20k_plus_one_200k': totals['documents'], 'chunks': totals['chunks'], 'table_with_toast_bytes': heap[0], 'indexes_bytes': heap[1], 'hnsw_bytes': int(hnsw or 0),
                                       'bytes_per_chunk_table_with_toast': round(heap[0] / totals['chunks']), 'bytes_per_chunk_with_indexes': round((heap[0] + heap[1]) / totals['chunks']),
                                       'complete_job_seconds_total': round(totals['complete_job_seconds'], 2), 'samples': samples}
                report['plan_uses_chunk_hnsw'] = None
                query = [random.Random(3).random() for _ in range(768)]
                admin_actor = None
            # Search latency in the steady state (every resource chunked), 30 queries: the fragment route only.
            with psycopg.connect(dsn) as c:
                from memory_platform.auth import hash_password
                actor_id = str(uuid.uuid4())
                c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (actor_id, 'cost', hash_password('fixture-password-123')))
            actor = {'id': actor_id, 'credential_type': 'bootstrap'}
            queries = [[random.Random(n).random() for _ in range(768)] for n in range(30)]
            store.search_vectors(actor, ['p1'], queries[0], MODEL, limit=10)  # warm-up (plan/buffers)
            started = time.monotonic()
            truncated = 0
            for vector in queries:
                found = store.search_vectors(actor, ['p1'], vector, MODEL, limit=10)
                truncated += bool(found.candidates_truncated)
            report['search_steady_state_ms_avg'] = round((time.monotonic() - started) / len(queries) * 1000, 1)
            report['search_steady_state'] = {'queries': len(queries), 'queries_with_candidates_truncated': truncated, 'last_hits': len(found),
                                             'last_with_matched_chunk': sum('matched_chunk' in h for h in found)}
            # One exact scan over ALL fragments, without a timeout: what the exact route costs per fragment (it is bounded by 10 fragments per candidate element).
            from memory_platform import store_vectors
            with psycopg.connect(dsn) as c:
                fragments = c.execute('SELECT count(*) FROM memory.embedding_chunks').fetchone()[0]
            from psycopg.rows import dict_row
            unit = store._unit(queries[1])
            with psycopg.connect(dsn, row_factory=dict_row) as c:
                started = time.monotonic()
                best, candidates_truncated, saturated = store_vectors.chunk_exact_rows(c, ['p1'], MODEL, 768, unit, None, None, 10)
                scan_ms = round((time.monotonic() - started) * 1000)
            report['chunk_exact_scan'] = {'fragments': fragments, 'cap': store_vectors.chunk_candidate_limit(), 'ms': scan_ms, 'ms_per_10k_fragments': round(scan_ms / max(1, min(fragments, store_vectors.chunk_candidate_limit())) * 10000, 1),
                                          'candidates_truncated': candidates_truncated, 'fallback_budget_ms': 1500}
            # Baseline of the previous design: no fragments at all, every resource answered by its item vector (as the earlier 989 ms measure).
            with psycopg.connect(dsn) as c:
                c.execute('TRUNCATE memory.embedding_chunks')
                c.execute('UPDATE memory.embeddings SET chunked=false')
            started = time.monotonic()
            truncated = 0
            for vector in queries:
                found = store.search_vectors(actor, ['p1'], vector, MODEL, limit=10)
                truncated += bool(found.candidates_truncated)
            report['search_item_vectors_only_ms_avg'] = round((time.monotonic() - started) / len(queries) * 1000, 1)
            report['search_item_vectors_only'] = {'queries_with_candidates_truncated': truncated}
        finally:
            with psycopg.connect(base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        print('CHUNK_COST_RESULT ' + json.dumps(report, sort_keys=True), flush=True)


unittest.defaultTestLoader.discover = lambda *a, **k: unittest.TestSuite([Measure()])
from memory_platform.tests import run_postgres
run_postgres.main()
