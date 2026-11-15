"""B-02 / CA-15 / CA-18: connections and queries one hybrid search costs, and its latency; BEFORE the pool (T-21) and AFTER it (T-26).

Runs only inside the harness container (the DSN guard of the retrieval evaluation applies first: loopback, port 55432, database memory_test) in a database of
its own that it creates and drops. The vectors are random and the query embedding is a fixed vector: no network, no Ollama. Not part of the regression suite
(its name does not match test_*.py), so it does not change the count.

    docker run --rm --network=none -e MEASURE_CONNECTIONS=1 kairos-test:IMG python -m memory_platform.tests.measure_connections
    docker run --rm --network=none -e MEASURE_CONNECTIONS=1 -e MEASURE_POOL=1 kairos-test:IMG python -m memory_platform.tests.measure_connections

What is counted, per search and after a warm-up of `WARMUP` searches (the measured ones are the next `REPEATS`):
* `connections_per_search`: calls of `psycopg.Connection.connect` (a pool opens its connections through the same call, in its own threads);
* `transactions_per_search`: calls of `Store.transaction()`;
* `queries_per_search`: calls of `psycopg.Cursor.execute` (every statement a transaction sends, BEGIN/COMMIT excluded);
* `latency_ms`: median, p95 and maximum of the whole `Retrieval.search`.
"""
import asyncio
import json
import os
import statistics
import threading
import time
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

import psycopg
from psycopg.conninfo import make_conninfo

from memory_platform import models as m
from memory_platform.auth import hash_password
from memory_platform.config import Settings
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.tests.retrieval_eval.run import check_dsn, connect_dsn

ROWS = int(os.environ.get('MEASURE_ROWS', '300'))  # per table: ROWS documents and ROWS items, every one embedded
WARMUP = int(os.environ.get('MEASURE_WARMUP', '10'))
REPEATS = int(os.environ.get('MEASURE_REPEATS', '40'))
PROJECTS = int(os.environ.get('MEASURE_PROJECTS', '3'))  # the search is over this many projects (B-02: the permission reads grow with them)
MODEL = 'nomic-embed-text'
DIMENSIONS = 768


class Counters:
    def __init__(self):
        self.connections = self.queries = self.transactions = 0
        self.pids = set()
        self._lock = threading.Lock()

    def add(self, name, amount=1):
        with self._lock:
            setattr(self, name, getattr(self, name) + amount)


def instrumented(counters):
    """Patches that count without changing behaviour; the caller enters all of them."""
    real_connect, real_function, real_execute, real_transaction = psycopg.connect, psycopg.Connection.connect.__func__, psycopg.Cursor.execute, Store.transaction

    def direct(*args, **kwargs):  # `psycopg.connect` is bound to the class method at import time: patching the class does not see the direct callers
        counters.add('connections')
        return real_connect(*args, **kwargs)

    def connect(cls, *args, **kwargs):  # the pool opens its connections through the class
        counters.add('connections')
        return real_function(cls, *args, **kwargs)

    def execute(self, query, *args, **kwargs):
        counters.add('queries')
        return real_execute(self, query, *args, **kwargs)

    def transaction(self):
        counters.add('transactions')
        return real_transaction(self)
    return [patch.object(psycopg, 'connect', direct), patch.object(psycopg.Connection, 'connect', classmethod(connect)), patch.object(psycopg.Cursor, 'execute', execute), patch.object(Store, 'transaction', transaction)]


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(share * (len(ordered) - 1))))]


class Measure(unittest.TestCase):
    def runTest(self):
        base = os.environ['MEMORY_TEST_DSN']
        check_dsn(os.environ.get('MEMORY_DSN'), base)
        base = connect_dsn(base)
        name = 'conn_' + uuid.uuid4().hex[:10]
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        dsn = make_conninfo(base, dbname=name)
        pooled = os.environ.get('MEASURE_POOL') == '1'
        report = {'rows_per_table': ROWS, 'projects': PROJECTS, 'warmup': WARMUP, 'repeats': REPEATS, 'pool': pooled, 'postgres': 'isolated container build'}
        store = Store(dsn, embedding_enabled=True)
        try:
            store.migrate()
            actor_id = str(uuid.uuid4())
            with store.transaction() as c:
                c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (actor_id, 'm-' + actor_id[:8], hash_password('fixture-password-123')))
            actor = {'id': actor_id, 'credential_type': 'bootstrap'}
            projects = ['p%d' % number for number in range(PROJECTS)]
            for project in projects:
                store.create_project(actor, {'id': project, 'title': 'Project ' + project})
            with psycopg.connect(dsn) as c:
                body = "jsonb_build_object('title','Documento '||n,'content',repeat('contenido de ejemplo del despliegue ',20),'source',jsonb_build_object('uri','fixture://'||n))"
                for project in projects:
                    c.execute(f"INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) SELECT '{project}','d'||n,1,repeat('a',64),{body} FROM generate_series(1,{ROWS}) n")
                    c.execute(f"""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector)
                                  SELECT '{project}','i'||n,1,repeat('b',64),'note',jsonb_build_object('title','Nota '||n,'content',repeat('contenido de ejemplo de la nota ',20)),'s','a',clock_timestamp(),
                                  to_tsvector('simple','contenido ejemplo nota despliegue') FROM generate_series(1,{ROWS}) n""")
                    for table, rtype in (('documents', 'document'), ('memory_items', 'item')):
                        c.execute(f"INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) SELECT '{project}',id,%s,1,canonical_hash,%s,"
                                  f"ARRAY(SELECT random()+0.01 FROM generate_series(1,{DIMENSIONS})) FROM memory.{table} WHERE project_id='{project}'", (rtype, MODEL))
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute('ANALYZE')
            if pooled:
                from memory_platform.store_pool import attach_pool
                attach_pool(store, Settings(dsn), 'api')
            embeddings = Mock(embed=AsyncMock(return_value={'embedding': [0.5] * DIMENSIONS, 'model': MODEL, 'verified': True}))
            retrieval = Retrieval(store, Settings(dsn, request_timeout=30), embeddings)
            request = m.Search(project_ids=projects, q='contenido ejemplo', layers=['episodic', 'documental'], semantic=True, limit=10)
            counters = Counters()

            lexical = m.Search(project_ids=projects, q='contenido ejemplo', layers=['episodic', 'documental'], semantic=False, limit=10)

            async def one(asked=request):
                started = time.perf_counter()
                answer = await retrieval.search(actor, asked)
                return (time.perf_counter() - started) * 1000, answer

            async def run():
                for _ in range(WARMUP):
                    await one()
                samples, before = [], (counters.connections, counters.transactions, counters.queries)
                for _ in range(REPEATS):
                    elapsed, answer = await one()
                    samples.append(elapsed)
                    self.assertFalse(answer['partial'], answer['backends'])
                after = (counters.connections, counters.transactions, counters.queries)
                lexical_samples = [(await one(lexical))[0] for _ in range(REPEATS)]
                return samples, before, after, lexical_samples

            patches = instrumented(counters)
            for active in patches:
                active.start()
            try:
                samples, before, after, lexical_samples = asyncio.run(run())
            finally:
                for active in reversed(patches):
                    active.stop()
            report['connections_per_search'] = round((after[0] - before[0]) / REPEATS, 2)
            report['transactions_per_search'] = round((after[1] - before[1]) / REPEATS, 2)
            report['queries_per_search'] = round((after[2] - before[2]) / REPEATS, 2)
            report['connections_total_including_warmup'] = counters.connections
            report['latency_lexical_only_ms'] = {'median': round(statistics.median(lexical_samples), 2), 'p95': round(percentile(lexical_samples, 0.95), 2)}
            report['latency_lexical_only_ms'] = {'median': round(statistics.median(lexical_samples), 2), 'p95': round(percentile(lexical_samples, 0.95), 2)}
            report['latency_ms'] = {'median': round(statistics.median(samples), 2), 'p95': round(percentile(samples, 0.95), 2), 'max': round(max(samples), 2)}
            report['hits'] = len(asyncio.run(retrieval.search(actor, request))['items'])
        finally:
            closer = getattr(getattr(store, 'pool', None), 'close', None)
            if closer:
                closer()
            with psycopg.connect(base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        print('MEASURE_CONNECTIONS ' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    if os.environ.get('MEASURE_CONNECTIONS') != '1':
        raise SystemExit('Set MEASURE_CONNECTIONS=1: this script only runs inside the isolated harness container.')
    unittest.defaultTestLoader.discover = lambda *a, **k: unittest.TestSuite([Measure()])
    from memory_platform.tests import run_postgres
    run_postgres.main()
