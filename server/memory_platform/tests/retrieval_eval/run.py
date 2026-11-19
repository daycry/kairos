"""Retrieval quality evaluation: loads the synthetic dataset and measures every retrieval layer.

Safety: it only talks to the isolated harness database (local ``memory_test``) and, by default, uses the offline
embedding provider. It never reads configured user services or the deployed database.

Real embeddings (T-36): MEMORY_RETRIEVAL_EVAL_PROVIDER=ollama plus MEMORY_RETRIEVAL_EVAL_OLLAMA_URL=<endpoint of a disposable Ollama created for the
evaluation>. Only these two variables are read (never MEMORY_OLLAMA_URL), and the deployed Ollama (the `ollama` proxy, `knowledge-graphs-*`
containers, host.docker.internal, loopback and bridge gateways in any spelling) is refused by ``check_ollama_url``. It is a deny list that does
not resolve DNS: the LAN address of the host or a name that resolves to it still passes, so point it only at a disposable container by name. Only embeddings are used: no LLM, no extraction.

Usage (inside the harness): python -m memory_platform.tests.retrieval_eval.run [--report out.json]
Normally invoked by ``memory_platform.tests.run_postgres`` with MEMORY_RETRIEVAL_EVAL=1.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import ipaddress
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from memory_platform.config import Settings, threshold_for

HERE = Path(__file__).parent
LAYERS = ('episodic', 'documental', 'semantic', 'fused')
LIMIT = 10
NAMESPACE = uuid.UUID('6f2c1d0e-6b3a-4d52-9d44-5a1f0c7e9b11')
HARNESS_PORT = '55432'
DSN_KEYS = frozenset({'host', 'port', 'dbname', 'user'})
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
PINNED_HOSTADDR = '127.0.0.1'
LIBPQ_REDIRECT_ENV = ('PGHOSTADDR', 'PGHOST', 'PGPORT', 'PGDATABASE', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR')
PROVIDER_ENV, OLLAMA_URL_ENV = 'MEMORY_RETRIEVAL_EVAL_PROVIDER', 'MEMORY_RETRIEVAL_EVAL_OLLAMA_URL'
DEPLOYED_OLLAMA_HOSTS = ('ollama', 'host.docker.internal', 'gateway.docker.internal')  # the compose proxy and the host's Ollama (by name): the deployed installation
FAKE_LABEL = 'fake-hashed-words-and-char-ngrams'
STRUCTURAL_KEYS = ('query_backends', 'dataset', 'dataset_sha256', 'product_database_accessed', 'embedding_provider', 'model', 'limit', 'layers', 'negatives_sha256', 'abstention')
NEGATIVES_MINIMUM = 20  # the gate refuses to measure abstention over fewer questions without an answer (CA-26)


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
    fused recall@5 by ``subset_gain_points`` over the baseline (both are mandatory). CA-35: no subset of the
    baseline loses more than ``max_subset_regression_points`` of fused recall@5 (a missing threshold or subset is
    itself a failure, never a silent pass). CA-18: the MRR of ``fused`` is at least that of the best single layer, overall (``ca18:overall``)
    and in every subset (``ca18:<subset>``); a report without the single layers fails as ``ca18_layers_missing``. A retrieval backend that is not ``ok`` is reported as
    ``backend_unavailable:<layer>``, never as recall 0.
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
        allowed = thresholds.get('max_subset_regression_points')
        if allowed is None:
            failures.append({'check': 'threshold_missing:max_subset_regression_points', 'value': None, 'required': 'maximum recall@5 loss per subset, in points (CA-35)'})
        else:
            for subset, before in sorted(baseline['layers']['fused']['subsets'].items()):
                current = fused['subsets'].get(subset)
                if current is None:
                    failures.append({'check': 'subset_missing:' + subset, 'value': None, 'required': 'subset of the baseline'})
                    continue
                loss = round((before['recall@5'] - current['recall@5']) * 100, 4)
                if loss > allowed:
                    failures.append({'check': 'regression:' + subset, 'value': current['recall@5'], 'loss_points': loss, 'allowed_loss_points': allowed})
    singles = [layer for layer in LAYERS if layer != 'fused' and layer in report['layers']]
    if not singles:
        failures.append({'check': 'ca18_layers_missing', 'value': None, 'required': 'the single layers of the report, to compare their MRR with the fused one (CA-18)'})
    else:
        scopes = [('overall', fused['overall'], [report['layers'][layer]['overall'] for layer in singles])]
        for subset, row in sorted(fused['subsets'].items()):
            scopes.append((subset, row, [report['layers'][layer]['subsets'][subset] for layer in singles if subset in report['layers'][layer]['subsets']]))
        for name, row, others in scopes:
            best = max((other['mrr'] for other in others), default=0.0)
            if row['mrr'] < best:
                failures.append({'check': 'ca18:' + name, 'value': row['mrr'], 'best_single_layer_mrr': best, 'required': 'fused mrr >= best single layer'})
    return failures


class CachedQueries:
    """Embeds each QUERY text once per run: the evaluation asks every question through several searches, and with a real model each embedding is a CPU run (T-89).

    Only ``embed(text, query=True)`` is remembered; document embeddings (the worker's ``embed_many`` and ``embed`` without ``query``) and every other attribute go to the provider unchanged.
    """

    def __init__(self, provider):
        self._provider, self._queries = provider, {}

    async def embed(self, text, query=False):
        if not query:
            return await self._provider.embed(text, query=query)
        if text not in self._queries:
            self._queries[text] = await self._provider.embed(text, query=True)
        return self._queries[text]

    def __getattr__(self, name):
        return getattr(self._provider, name)


def abstention_threshold(thresholds, model, simulated):
    """The cosine threshold under test for ``model`` (CA-27): ``abstention.simulated.threshold`` with the offline provider, ``abstention.models[<model>]`` with a real one
    (``:latest`` is the same model); None when there is none, which the gate reports as ``threshold_missing:abstention.threshold`` instead of measuring blind."""
    config = thresholds.get('abstention')
    config = config if isinstance(config, dict) else {}
    if simulated:
        return (config.get('simulated') or {}).get('threshold')
    models = config.get('models')
    return threshold_for(models, model) if isinstance(models, dict) else None


def pick_threshold(rows, min_correct, max_false):
    """Calibration (T-89): the threshold in the middle of the widest interval where the correct abstention is >= ``min_correct`` and the false abstention <= ``max_false``.

    ``rows`` are the ``abstention.scores`` of a report (``negative``, ``best`` cosine, ``protected`` = a lexical hit or an incomplete lexical layer prevents abstaining).
    A question abstains at threshold ``t`` when it is not protected and its best cosine is below ``t``; a question with no cosine is protected. Returns
    ``{'threshold', 'low', 'high', 'correct_abstention', 'false_abstention'}`` or None when no threshold reaches both goals.
    """
    negatives, positives = [r for r in rows if r['negative']], [r for r in rows if not r['negative']]
    if not negatives or not positives:
        return None

    def rates(t):
        def rate(group):
            return sum(1 for r in group if not r['protected'] and r.get('best') is not None and r['best'] < t) / len(group)
        return rate(negatives), rate(positives)
    points = sorted({r['best'] for r in rows if r.get('best') is not None})
    candidates = [(a + b) / 2 for a, b in zip(points, points[1:])] + ([points[-1] + 0.001] if points else [])
    good = [i for i, t in enumerate(candidates) if rates(t)[0] >= min_correct and rates(t)[1] <= max_false]
    if not good:
        return None
    runs, current = [], [good[0]]
    for before, after in zip(good, good[1:]):
        if after == before + 1:
            current.append(after)
        else:
            runs.append(current)
            current = [after]
    runs.append(current)
    widest = max(runs, key=lambda run_: candidates[run_[-1]] - candidates[run_[0]])
    low, high = candidates[widest[0]], candidates[widest[-1]]
    # Rounded for reading, but the goals are checked again AT the rounded threshold: a window narrower than the rounding would otherwise report a threshold that misses them (review phase 14, B1).
    for digits in (4, 5, 6, None):
        middle = (low + high) / 2 if digits is None else round((low + high) / 2, digits)
        correct, false = rates(middle)
        if correct >= min_correct and false <= max_false:
            fit = (lambda value: value) if digits is None else (lambda value: round(value, digits))
            return {'threshold': middle, 'low': fit(low), 'high': fit(high), 'correct_abstention': round(correct, 6), 'false_abstention': round(false, 6)}
    return None


def evaluate_abstention(report, thresholds):
    """Failed checks of the abstention goals (CA-27, CA-28; empty = they pass), same discipline as ``evaluate_gate``: a missing goal, threshold or measurement fails, never passes silently.

    ``abstention_correct``: fewer than ``min_correct_rate`` of the questions without an answer got ``abstained: true``; ``abstention_false``: more than ``max_false_rate`` of the questions
    with an answer did; ``abstention_measurement_errors``: a question whose best cosine could not be measured; ``abstention_items``: an abstention that still carried items; ``abstention_negatives_too_few``: the set shrank below 20 questions.
    """
    failures = []
    config = thresholds.get('abstention')
    config = config if isinstance(config, dict) else {}
    if isinstance(report.get('abstention'), dict) and report['abstention'].get('simulated'):
        config = config.get('simulated')  # the offline provider has its own goals (R-07: its cosines are not a real model's); the real model's are the top-level ones
        config = config if isinstance(config, dict) else {}
    for key in ('min_correct_rate', 'max_false_rate'):
        if not isinstance(config.get(key), (int, float)) or isinstance(config.get(key), bool):
            failures.append({'check': 'threshold_missing:abstention.' + key, 'value': None, 'required': 'abstention goal in thresholds.json (CA-27)'})
    measured = report.get('abstention')
    if not isinstance(measured, dict):
        failures.append({'check': 'abstention_missing', 'value': None, 'required': 'abstention measurement over the questions with and without an answer'})
        return failures
    if measured.get('threshold') is None:
        failures.append({'check': 'threshold_missing:abstention.threshold', 'value': None, 'required': 'cosine threshold of the model under test (simulated.threshold or models.<model>)'})
    if measured.get('negatives', {}).get('n', 0) < NEGATIVES_MINIMUM:
        failures.append({'check': 'abstention_negatives_too_few', 'value': measured.get('negatives', {}).get('n', 0), 'required': NEGATIVES_MINIMUM})
    if measured.get('measurement_errors'):
        failures.append({'check': 'abstention_measurement_errors', 'value': measured['measurement_errors'], 'required': 0})
    if measured.get('abstained_with_items'):
        failures.append({'check': 'abstention_items', 'value': measured['abstained_with_items'], 'required': 0})
    if isinstance(config.get('min_correct_rate'), (int, float)) and measured.get('correct_abstention', 0) < config['min_correct_rate']:
        failures.append({'check': 'abstention_correct', 'value': measured.get('correct_abstention', 0), 'required': config['min_correct_rate']})
    if isinstance(config.get('max_false_rate'), (int, float)) and measured.get('false_abstention', 1) > config['max_false_rate']:
        failures.append({'check': 'abstention_false', 'value': measured.get('false_abstention', 1), 'required': config['max_false_rate']})
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


def host_address(host):
    """The IP a host spells (dotted, short `127.1`, integer `2130706433`, hex/octal parts as `inet_aton` reads them, IPv6, `::ffff:` mapped), or None for a name."""
    try:
        return ipaddress.ip_address(host.split('%', 1)[0])
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def refused_address(address):
    """Loopback, unspecified, link-local (the host or the container itself) and the gateway of a Docker bridge network (a private IPv4 ending in `.1`: it is
    the host, and with it the deployed Ollama on 11434). Any other private address is a container of an isolated network, which is what the evaluation needs."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast or address.is_reserved:
        return True
    return isinstance(address, ipaddress.IPv4Address) and address.is_private and int(address) & 0xFF == 1


def check_ollama_url(url):
    """The endpoint of the disposable Ollama of the evaluation, or SystemExit.

    Plain ``http`` without credentials, query or path; never the deployed installation: not the compose proxy (`ollama`), not ``host.docker.internal`` or
    ``gateway.docker.internal``, not a ``knowledge-graphs*`` container, not the host itself (any loopback, unspecified or link-local address, in any spelling, on any port)
    and not the conventional gateway of a Docker bridge network (`172.17.0.1`: the host). The host is lower-cased and loses its trailing dot, and IPs are interpreted
    (`127.1`, `2130706433`, `::ffff:127.0.0.1`), never compared as text. What is accepted is the name of a container of an isolated network (`kairos-rq8-ollama`).
    """
    refuse = SystemExit('retrieval-eval refuses this Ollama endpoint: %s must be the plain http endpoint of a disposable Ollama created for the evaluation, '
                        'never the deployed one (no `ollama` proxy, host.docker.internal, gateway.docker.internal, knowledge-graphs-* container, loopback or bridge gateway address).' % OLLAMA_URL_ENV)
    try:
        parts = urlsplit(url or '')
        host, port = (parts.hostname or '').lower().rstrip('.'), parts.port
    except ValueError:
        raise refuse from None
    if parts.scheme != 'http' or not host or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise refuse
    if host in DEPLOYED_OLLAMA_HOSTS or host.startswith('knowledge-graphs') or host == 'localhost' or host.endswith('.localhost'):
        raise refuse
    address = host_address(host)
    if address is not None and refused_address(address):
        raise refuse
    if address is None and ':' in host:  # an IPv6 form that ipaddress does not read is not worth guessing at
        raise refuse
    return url.rstrip('/')


def make_provider(dsn):
    """(embeddings provider, report label, settings). Simulated unless MEMORY_RETRIEVAL_EVAL_PROVIDER=ollama; never falls back silently."""
    from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
    choice = os.environ.get(PROVIDER_ENV, 'fake').strip().lower()
    if choice == 'fake':
        settings = Settings(dsn, request_timeout=60.0, embedding_query_timeout=30.0)
        return FakeEmbeddings(settings), FAKE_LABEL, settings
    if choice != 'ollama':
        raise SystemExit('retrieval-eval: %s must be `fake` or `ollama`' % PROVIDER_ENV)
    from memory_platform.providers import Embeddings
    # A disposable Ollama on a loaded CPU needs minutes, not the 60 s per batch of a production host, for the long documents (T-89: 4 of 72 embed jobs failed with the defaults).
    settings = Settings(dsn, request_timeout=60.0, embedding_query_timeout=30.0, embedding_worker_timeout=300.0, embedding_batch_timeout=300.0, embedding_job_timeout_max=3000.0,
                        ollama_url=check_ollama_url(os.environ.get(OLLAMA_URL_ENV)))
    return Embeddings(settings), 'ollama:' + settings.embedding_model, settings


def load_dataset(path):
    from memory_platform.tests.retrieval_eval.check_dataset import validate
    raw = Path(path).read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    errors = validate(records)[2]
    if errors:
        raise SystemExit('retrieval-eval refuses an invalid dataset: ' + '; '.join(errors[:5]))
    return records, hashlib.sha256(raw).hexdigest()


def load_negatives(path, corpus_records):
    """The questions without an answer (dataset-v1-negatives.jsonl), validated against the corpus they are asked of, with the SHA-256 of the file."""
    from memory_platform.tests.retrieval_eval.check_dataset import validate_negatives
    raw = Path(path).read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    errors = validate_negatives(records, corpus_records)[2]
    if errors:
        raise SystemExit('retrieval-eval refuses an invalid set of questions without an answer: ' + '; '.join(errors[:5]))
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


async def _measure_abstention(store, actor, project, positives, negatives, provider, settings, threshold, retrieval=None, probe=None):
    """Abstention as a client would ask for it (CA-27): every question with `abstain: true` through ``Retrieval.search`` at ``threshold`` (None = no threshold for the model).

    Returns the ``abstention`` section of the report. ``scores`` keeps, per question, the best semantic cosine and whether something protects it from abstaining
    (``protected``: a lexical hit, or a lexical layer that did not answer complete; read from a second search with the threshold at its maximum, 1.0), which is what
    ``pick_threshold`` needs to calibrate a model without running the whole set once per candidate threshold.
    """
    from dataclasses import replace
    if retrieval is None:
        from memory_platform.retrieval import Retrieval
        retrieval = Retrieval(store, replace(settings, abstain_thresholds={settings.embedding_model: threshold} if threshold is not None else {}), provider)
        probe = Retrieval(store, replace(settings, abstain_thresholds={settings.embedding_model: 1.0}), provider)
    rows, errors = [], 0
    for negative, questions in ((True, negatives), (False, positives)):
        for question in questions:
            request = {'project_ids': [project], 'q': question['q'], 'layers': ['episodic', 'documental'], 'semantic': True, 'limit': LIMIT, 'abstain': True}
            answer, probed = await retrieval.search(actor, request), await probe.search(actor, request)
            try:
                embedded = await provider.embed(question['q'], query=True)
                scores = [float(h['score']) for h in store.search_vectors(actor, [project], embedded['embedding'], embedded['model'], LIMIT) if h.get('score') is not None]
            except Exception:
                scores, errors = [], errors + 1  # counted and reported (`measurement_errors`): a failed cosine is not a question that "does not abstain"
            abstained = answer.get('abstained') is True
            rows.append({'id': question['id'], 'negative': negative, 'near': bool(question.get('near')), 'best': round(max(scores), 6) if scores else None,
                         'protected': probed.get('abstained') is not True, 'abstained': abstained and not answer['items'], 'with_items': abstained and bool(answer['items'])})
    negative_rows, positive_rows = [r for r in rows if r['negative']], [r for r in rows if not r['negative']]

    def rate(group):
        return round(sum(1 for r in group if r['abstained']) / len(group), 6) if group else 0.0
    return {'model': settings.embedding_model, 'threshold': threshold,
            'correct_abstention': rate(negative_rows), 'false_abstention': rate(positive_rows),
            'abstained_with_items': sum(1 for r in rows if r['with_items']), 'measurement_errors': errors,
            'negatives': {'n': len(negative_rows), 'abstained': sum(1 for r in negative_rows if r['abstained']),
                          'near_n': sum(1 for r in negative_rows if r['near']), 'near_abstained': sum(1 for r in negative_rows if r['near'] and r['abstained'])},
            'positives': {'n': len(positive_rows), 'abstained': sum(1 for r in positive_rows if r['abstained'])},
            'scores': [{k: r[k] for k in ('id', 'negative', 'best', 'protected', 'abstained')} for r in rows]}


async def _fused_aggregate(retrieval, actor, project, ids, questions):
    """Aggregate of the fused search alone (what a fusion setting changes), over every question."""
    rows = []
    for question in questions:
        result = await retrieval.search(actor, {'project_ids': [project], 'q': question['q'], 'layers': ['episodic', 'documental'], 'semantic': True, 'limit': LIMIT})
        rows.append({'subset': question['subset'], 'expected': question['expected'], 'ranked': [ids[h['item_id']] for h in result['items'] if h['item_id'] in ids]})
    return aggregate(rows)


def tune(spec, dsn=None, test_dsn=None, dataset=None):
    """Measure the fused search for every combination of ``spec`` = {"bonus": [...], "k": [...], "weights": [{layer: weight}, ...]}.

    The corpus is indexed once; only the fusion settings change between points. It also returns the other layers at the
    default settings so the fused MRR can be compared with the best single layer (CA-18). Same isolation guarantees as the gate.
    """
    from dataclasses import replace
    from itertools import product
    dsn, test_dsn = dsn or os.environ.get('MEMORY_DSN'), test_dsn or os.environ.get('MEMORY_TEST_DSN')
    check_dsn(dsn, test_dsn)
    dsn = connect_dsn(dsn)
    from memory_platform.retrieval import Retrieval
    from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
    records, digest = load_dataset(Path(dataset or HERE / 'dataset-v1.jsonl'))
    store, actor, project = _setup(dsn)
    settings = Settings(dsn, request_timeout=60.0, embedding_query_timeout=30.0)
    provider = FakeEmbeddings(settings)
    ids, _ = _load_corpus(store, actor, project, records)
    questions = [r for r in records if r['type'] == 'question']

    async def go():
        await _index(store, project, provider, settings)
        layers, _health = await _measure(store, actor, project, ids, questions, provider, settings)
        points = []
        for bonus, k, weights in product(spec.get('bonus', [settings.fusion_validated_bonus]), spec.get('k', [settings.fusion_k]), spec.get('weights', [{}])):
            point = replace(settings, fusion_validated_bonus=bonus, fusion_k=k, fusion_weights=weights)
            points.append({'bonus': bonus, 'k': k, 'weights': weights,
                           'fused': await _fused_aggregate(Retrieval(store, point, provider), actor, project, ids, questions)})
        return layers, points
    layers, points = asyncio.run(go())
    return {'dataset_sha256': digest, 'default_settings': {'bonus': settings.fusion_validated_bonus, 'k': settings.fusion_k, 'weights': settings.fusion_weights},
            'layers_at_default': layers, 'grid': points}


def build_report(dsn, test_dsn, dataset_path, negatives_path=None, thresholds=None):
    check_dsn(dsn, test_dsn)
    dsn = connect_dsn(dsn)
    records, digest = load_dataset(dataset_path)
    negatives, negatives_digest = load_negatives(negatives_path or HERE / 'dataset-v1-negatives.jsonl', records)
    provider, label, settings = make_provider(dsn)
    provider = CachedQueries(provider)
    threshold = abstention_threshold(thresholds or {}, settings.embedding_model, label == FAKE_LABEL)
    store, actor, project = _setup(dsn)
    ids, texts = _load_corpus(store, actor, project, records)
    questions = [r for r in records if r['type'] == 'question']

    async def go():
        await _index(store, project, provider, settings)
        layers, query_backends = await _measure(store, actor, project, ids, questions, provider, settings)
        return layers, query_backends, await _measure_abstention(store, actor, project, questions, negatives, provider, settings, threshold)
    layers, query_backends, abstention = asyncio.run(go())
    abstention['simulated'] = label == FAKE_LABEL
    return {'dataset': Path(dataset_path).stem, 'dataset_sha256': digest, 'negatives_sha256': negatives_digest, 'product_database_accessed': False,
            'embedding_provider': label, 'model': settings.embedding_model, 'limit': LIMIT,
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'layers': layers, 'query_backends': query_backends, 'abstention': abstention}


def run(report_path=None, dataset=None, thresholds=None, baseline=None, dsn=None, test_dsn=None, negatives=None):
    """Run the evaluation (twice with the simulated provider, as a determinism check), evaluate the gate and print/write the report."""
    dataset = Path(dataset or HERE / 'dataset-v1.jsonl')
    thresholds = json.loads(Path(thresholds or HERE / 'thresholds.json').read_text(encoding='utf-8'))
    negatives = Path(negatives or HERE / 'dataset-v1-negatives.jsonl')
    baseline_file = Path(baseline) if baseline else HERE / 'baseline.json'
    baseline_report = json.loads(baseline_file.read_text(encoding='utf-8')) if baseline_file.exists() else None
    dsn, test_dsn = dsn or os.environ.get('MEMORY_DSN'), test_dsn or os.environ.get('MEMORY_TEST_DSN')
    first = build_report(dsn, test_dsn, dataset, negatives, thresholds)
    # Determinism is a property of the simulated provider. A real model is evaluated once (indexing the corpus twice on a CPU doubles an already long run, T-89) and `deterministic` is None.
    real = first.get('embedding_provider') != FAKE_LABEL
    second = None if real else build_report(dsn, test_dsn, dataset, negatives, thresholds)
    deterministic = None if real else all(first[k] == second[k] for k in STRUCTURAL_KEYS)
    failures = evaluate_gate(first, thresholds, baseline_report) + evaluate_abstention(first, thresholds)
    if deterministic is False:
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
    parser.add_argument('--negatives')
    args = parser.parse_args(argv)
    report = run(args.report, args.dataset, args.thresholds, args.baseline, negatives=args.negatives)
    if not report['gate']['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
