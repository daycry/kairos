"""Retrieval quality evaluation: loads the synthetic dataset and measures every retrieval layer.

Safety: it only talks to the isolated harness database (local ``memory_test``) and uses the offline
embedding provider. It never reads configured user services or the deployed database.

Usage (inside the harness): python -m memory_platform.tests.retrieval_eval.run [--report out.json]
Normally invoked by ``memory_platform.tests.run_postgres`` with MEMORY_RETRIEVAL_EVAL=1.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from memory_platform.config import Settings

HERE = Path(__file__).parent
LAYERS = ('episodic', 'documental', 'semantic', 'fused')
LIMIT = 10
NAMESPACE = uuid.UUID('6f2c1d0e-6b3a-4d52-9d44-5a1f0c7e9b11')
HARNESS_PORT = '55432'
DSN_KEYS = frozenset({'host', 'port', 'dbname', 'user'})
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
PINNED_HOSTADDR = '127.0.0.1'
LIBPQ_REDIRECT_ENV = ('PGHOSTADDR', 'PGHOST', 'PGPORT', 'PGDATABASE', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR')
STRUCTURAL_KEYS = ('query_backends', 'dataset', 'dataset_sha256', 'product_database_accessed', 'embedding_provider', 'model', 'limit', 'layers')


def network_observation():
    """Local, passive observation (no connection of any kind): the interfaces listed in /sys/class/net.

    Informational only; it says which interfaces exist, not that no traffic could leave the process.
    """
    try:
        interfaces = sorted(os.listdir('/sys/class/net'))
    except OSError:
        return {'network_interfaces': None, 'network_observation': 'unknown: /sys/class/net is not readable'}
    if interfaces == ['lo']:
        return {'network_interfaces': interfaces, 'network_observation': 'only the loopback interface exists'}
    return {'network_interfaces': interfaces, 'network_observation': 'interfaces other than loopback exist'}


def recall_at_k(ranked, expected, k):
    return len(set(ranked[:k]) & set(expected)) / len(set(expected))


def mrr(ranked, expected):
    for position, key in enumerate(ranked, 1):
        if key in expected:
            return 1 / position
    return 0.0


def _summary(rows):
    n = len(rows)

    def mean(fn):
        return round(sum(fn(r) for r in rows) / n, 6) if n else 0.0
    return {'n': n, 'recall@1': mean(lambda r: recall_at_k(r['ranked'], r['expected'], 1)),
            'recall@5': mean(lambda r: recall_at_k(r['ranked'], r['expected'], 5)),
            'recall@10': mean(lambda r: recall_at_k(r['ranked'], r['expected'], 10)),
            'mrr': mean(lambda r: mrr(r['ranked'], r['expected']))}


def aggregate(rows):
    subsets = {name: _summary([r for r in rows if r['subset'] == name]) for name in sorted({r['subset'] for r in rows})}
    return {'overall': _summary(rows), 'subsets': subsets}


def evaluate_gate(report, thresholds, baseline=None):
    """Return the list of failed checks (empty = gate passes).

    Decision P-06: fused recall@5 and MRR reach their targets AND each gain subset improves its
    fused recall@5 by ``subset_gain_points`` over the baseline (both are mandatory). A retrieval
    backend that is not ``ok`` is reported as ``backend_unavailable:<layer>``, never as recall 0.
    """
    fused = report['layers']['fused']
    failures = []
    unavailable = {}
    for entry in report.get('query_backends', []):
        for layer in LAYERS:
            detail = entry.get(layer)
            if detail and (detail.get('partial') or any(status != 'ok' for status in detail['backends'].values())):
                unavailable.setdefault(layer, []).append(entry['id'])
    for layer, queries in sorted(unavailable.items()):
        failures.append({'check': 'backend_unavailable:' + layer, 'value': 'backend not ok or partial result', 'required': 'ok', 'queries': queries})
    for check, metric in (('fused_recall_at_5', 'recall@5'), ('fused_mrr', 'mrr')):
        value = fused['overall'][metric]
        if value < thresholds[check]:
            failures.append({'check': check, 'value': value, 'required': thresholds[check]})
    if baseline is None:
        failures.append({'check': 'baseline_missing', 'value': None, 'required': 'baseline report to measure subset gains'})
    elif baseline.get('dataset_sha256') != report.get('dataset_sha256'):
        failures.append({'check': 'baseline_dataset_mismatch', 'value': report.get('dataset_sha256'), 'required': baseline.get('dataset_sha256')})
    else:
        for subset in thresholds['gain_subsets']:
            value = fused['subsets'][subset]['recall@5']
            gain = round((value - baseline['layers']['fused']['subsets'][subset]['recall@5']) * 100, 4)
            if gain < thresholds['subset_gain_points']:
                failures.append({'check': 'subset:' + subset, 'value': value, 'gain_points': gain, 'required_gain_points': thresholds['subset_gain_points']})
    return failures


def check_dsn(dsn, test_dsn, environ=None):
    """Refuse anything that is not the harness' own temporary database.

    Guarantees: (1) none of the libpq environment variables in ``LIBPQ_REDIRECT_ENV`` is set (libpq would
    apply them to a DSN that omits the key); (2) the DSN equals MEMORY_TEST_DSN and, resolved the way
    psycopg resolves it, carries only host/port/dbname/user with a loopback host, port 55432 and database
    memory_test; (3) callers connect through ``connect_dsn``, which pins ``hostaddr=127.0.0.1``.
    It does not inspect other libpq variables (PGOPTIONS, PGPASSFILE...), which do not select the target.
    """
    from psycopg.conninfo import conninfo_to_dict
    refuse = SystemExit('retrieval-eval refuses to run: MEMORY_DSN must equal MEMORY_TEST_DSN and resolve to the local isolated memory_test database (127.0.0.1:%s).' % HARNESS_PORT)
    environ = os.environ if environ is None else environ
    redirecting = [name for name in LIBPQ_REDIRECT_ENV if name in environ]
    if redirecting:
        raise SystemExit('retrieval-eval refuses to run: libpq environment variables could redirect the connection: ' + ', '.join(redirecting))
    if not dsn or dsn != test_dsn:
        raise refuse
    try:
        parts = conninfo_to_dict(dsn)
    except Exception:
        raise refuse from None
    if set(parts) - DSN_KEYS or parts.get('host') not in LOOPBACK or str(parts.get('port')) != HARNESS_PORT or parts.get('dbname') != 'memory_test':
        raise refuse


def connect_dsn(dsn):
    """The DSN actually used to connect: the validated one with the numeric address pinned to loopback."""
    from psycopg.conninfo import make_conninfo
    return make_conninfo(dsn, hostaddr=PINNED_HOSTADDR)


def load_dataset(path):
    from memory_platform.tests.retrieval_eval.check_dataset import validate
    raw = Path(path).read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    errors = validate(records)[2]
    if errors:
        raise SystemExit('retrieval-eval refuses an invalid dataset: ' + '; '.join(errors[:5]))
    return records, hashlib.sha256(raw).hexdigest()


def _setup(dsn):
    from memory_platform.auth import hash_password
    from memory_platform.store import Store
    store = Store(dsn, embedding_enabled=True)  # the write paths queue the embed jobs that _index runs through the product worker
    store.migrate()
    suffix = uuid.uuid4().hex[:14]
    actor_id = str(uuid.uuid4())
    with store.transaction() as c:
        c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)',
                  (actor_id, 'eval-' + suffix, hash_password('fixture-password-123')))
    actor = {'id': actor_id, 'credential_type': 'bootstrap'}
    project = 'eval-' + suffix
    store.create_project(actor, {'id': project, 'title': 'Retrieval evaluation (synthetic)'})
    store.set_policy(actor, project, {'capture_mode': 'summary', 'temporal_projection': True})
    return store, actor, project


def _load_corpus(store, actor, project, records):
    """Ingest through the product write paths; return {item_id: dataset key} and texts to embed."""
    ids, texts = {}, {}
    for record in records:
        if record['type'] == 'question':
            continue
        key = record['id']
        item_id = str(uuid.uuid5(NAMESPACE, key))
        ids[item_id] = key
        texts[item_id] = (record['type'], record['title'] + '\n' + record['content'])
        if record['type'] == 'memory':
            store.ingest_event(actor, {'event_id': str(uuid.uuid5(NAMESPACE, 'event:' + project + ':' + key)), 'project_id': project,
                                       'session_id': 'retrieval-eval', 'agent_id': 'eval', 'event_type': 'note',
                                       'occurred_at': '2026-11-09T10:00:00Z', 'item_id': item_id, 'version': 1, 'generate': False,
                                       'payload': {'title': record['title'], 'content': record['content'], 'source': {'uri': 'fixture://' + key}}})
        else:
            store.publish_document(actor, project, {
                'document_id': item_id, 'version': 1, 'title': record['title'], 'content': record['content'],
                'source': {'uri': 'fixture://' + key, 'sha256': hashlib.sha256(record['content'].encode('utf-8')).hexdigest()},
                'validation': {'status': 'validated', 'validated_by': 'eval', 'evidence': ['fixture://retrieval-eval']}})
    return ids, texts


async def _index(store, project, provider, settings):
    """Index exactly like production: the queued embed jobs run through the real worker (fragments, batches, atomic completion).

    A job that does not finish is an error of the harness, never a silently missing index.
    """
    from memory_platform.worker import Worker
    worker = Worker(store, settings, {'embed': provider}, worker_id='retrieval-eval')
    while await worker.run_once():
        pass
    with store.transaction() as c:
        states = {row['state']: row['n'] for row in c.execute("SELECT state,count(*) AS n FROM memory.jobs WHERE project_id=%s AND destination='embed' GROUP BY state", (project,)).fetchall()}
    if set(states) != {'succeeded'}:
        raise SystemExit('retrieval-eval could not index the corpus: embed job states ' + json.dumps(states, sort_keys=True))


def _backend_detail(result, expected):
    """Status of every backend the request asked for; a missing one counts as unavailable."""
    reported = result.get('backends', {})
    return {'backends': {name: reported.get(name, {}).get('status', 'unavailable') for name in sorted(expected)},
            'partial': bool(result.get('partial', False))}


async def _measure(store, actor, project, ids, questions, provider, settings, retrieval=None):
    """Return (layer aggregates, per-query backend status). Backend problems are recorded, never hidden."""
    if retrieval is None:
        from memory_platform.retrieval import Retrieval
        retrieval = Retrieval(store, settings, provider)
    rows = {layer: [] for layer in LAYERS}
    query_backends = []
    kinds = {'m': 'episodic', 'd': 'documental'}
    for question in questions:
        text = question['q']
        found, health = {}, {'id': question['id']}
        for layer in ('episodic', 'documental'):
            result = await retrieval.search(actor, {'project_ids': [project], 'q': text, 'layers': [layer], 'semantic': False, 'limit': LIMIT})
            found[layer] = [h['item_id'] for h in result['items']]
            health[layer] = _backend_detail(result, {layer})
        try:
            embedded = await provider.embed(text, query=True)
            found['semantic'] = [h['item_id'] for h in store.search_vectors(actor, [project], embedded['embedding'], embedded['model'], LIMIT)]
            health['semantic'] = {'backends': {'semantic': 'ok'}, 'partial': False}
        except Exception:
            found['semantic'] = []
            health['semantic'] = {'backends': {'semantic': 'unavailable'}, 'partial': True}
        result = await retrieval.search(actor, {'project_ids': [project], 'q': text, 'layers': ['episodic', 'documental'], 'semantic': True, 'limit': LIMIT})
        found['fused'] = [h['item_id'] for h in result['items']]
        health['fused'] = _backend_detail(result, {'episodic', 'documental', 'semantic'})
        query_backends.append(health)
        expected = question['expected']
        for layer in LAYERS:
            # A layer that cannot hold the expected item type is not penalised for it.
            if layer in ('episodic', 'documental') and any(kinds[ref[0]] != layer for ref in expected):
                continue
            rows[layer].append({'subset': question['subset'], 'expected': expected, 'ranked': [ids[i] for i in found[layer] if i in ids]})
    return {layer: aggregate(rows[layer]) for layer in LAYERS}, query_backends


def build_report(dsn, test_dsn, dataset_path):
    check_dsn(dsn, test_dsn)
    dsn = connect_dsn(dsn)
    from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
    records, digest = load_dataset(dataset_path)
    store, actor, project = _setup(dsn)
    settings = Settings(dsn, request_timeout=60.0, embedding_query_timeout=30.0)
    provider = FakeEmbeddings(settings)
    ids, texts = _load_corpus(store, actor, project, records)

    async def go():
        await _index(store, project, provider, settings)
        return await _measure(store, actor, project, ids, [r for r in records if r['type'] == 'question'], provider, settings)
    layers, query_backends = asyncio.run(go())
    return {'dataset': Path(dataset_path).stem, 'dataset_sha256': digest, 'product_database_accessed': False,
            'embedding_provider': 'fake-hashed-words-and-char-ngrams', 'model': settings.embedding_model, 'limit': LIMIT,
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'layers': layers, 'query_backends': query_backends}


def run(report_path=None, dataset=None, thresholds=None, baseline=None, dsn=None, test_dsn=None):
    """Run the evaluation twice (determinism check), evaluate the gate and print/write the report."""
    dataset = Path(dataset or HERE / 'dataset-v1.jsonl')
    thresholds = json.loads(Path(thresholds or HERE / 'thresholds.json').read_text(encoding='utf-8'))
    baseline_file = Path(baseline) if baseline else HERE / 'baseline.json'
    baseline_report = json.loads(baseline_file.read_text(encoding='utf-8')) if baseline_file.exists() else None
    dsn, test_dsn = dsn or os.environ.get('MEMORY_DSN'), test_dsn or os.environ.get('MEMORY_TEST_DSN')
    first = build_report(dsn, test_dsn, dataset)
    second = build_report(dsn, test_dsn, dataset)
    deterministic = all(first[k] == second[k] for k in STRUCTURAL_KEYS)
    failures = evaluate_gate(first, thresholds, baseline_report)
    if not deterministic:
        failures.append({'check': 'determinism', 'value': 'reports differ between two runs', 'required': 'identical'})
    first.update(network_observation())  # observed once, outside the determinism comparison
    first['deterministic'] = deterministic
    first['gate'] = {'passed': not failures, 'failures': failures, 'thresholds': thresholds,
                     'baseline_compared': baseline_report is not None}
    if report_path:
        Path(report_path).write_text(json.dumps(first, sort_keys=True, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('RETRIEVAL_EVAL_RESULT ' + json.dumps(first, sort_keys=True, ensure_ascii=False), flush=True)
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report')
    parser.add_argument('--dataset')
    parser.add_argument('--thresholds')
    parser.add_argument('--baseline')
    args = parser.parse_args(argv)
    report = run(args.report, args.dataset, args.thresholds, args.baseline)
    if not report['gate']['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
