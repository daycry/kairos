"""Retrieval metrics on hand-computed cases (no database needed)."""
import asyncio
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memory_platform.tests.retrieval_eval.fake_embeddings import vectorize
from memory_platform.tests.retrieval_eval.run import (HERE, STRUCTURAL_KEYS, _measure, aggregate, check_dsn, connect_dsn, evaluate_gate, load_dataset,
                                                      mrr, network_observation, recall_at_k, run)


class MetricTests(unittest.TestCase):
    def test_recall_at_k_counts_expected_found_in_the_top_k(self):
        ranked = ['a', 'b', 'c', 'd']
        self.assertEqual(recall_at_k(ranked, ['c'], 1), 0.0)
        self.assertEqual(recall_at_k(ranked, ['c'], 3), 1.0)
        self.assertEqual(recall_at_k(ranked, ['a', 'd', 'z'], 4), 2 / 3)
        self.assertEqual(recall_at_k([], ['a'], 5), 0.0)

    def test_mrr_is_reciprocal_rank_of_first_relevant(self):
        self.assertEqual(mrr(['x', 'y', 'a'], ['a', 'x']), 1.0)
        self.assertEqual(mrr(['x', 'y', 'a'], ['a']), 1 / 3)
        self.assertEqual(mrr(['x'], ['a']), 0.0)

    def test_aggregate_by_subset_and_overall(self):
        rows = [
            {'subset': 'en', 'ranked': ['a', 'b'], 'expected': ['a']},      # r1=1 r5=1 r10=1 rr=1
            {'subset': 'en', 'ranked': ['b', 'a'], 'expected': ['a']},      # r1=0 r5=1 r10=1 rr=.5
            {'subset': 'es', 'ranked': ['b', 'c'], 'expected': ['a']},      # all 0
        ]
        result = aggregate(rows)
        self.assertEqual(result['overall'], {'n': 3, 'recall@1': 0.333333, 'recall@5': 0.666667, 'recall@10': 0.666667, 'mrr': 0.5})
        self.assertEqual(result['subsets']['en'], {'n': 2, 'recall@1': 0.5, 'recall@5': 1.0, 'recall@10': 1.0, 'mrr': 0.75})
        self.assertEqual(result['subsets']['es']['recall@5'], 0.0)

    def test_gate_requires_targets_and_the_subset_gain(self):
        thresholds = {'fused_recall_at_5': 0.8, 'fused_mrr': 0.6, 'subset_gain_points': 15, 'gain_subsets': ['es'], 'max_subset_regression_points': 2}

        def report(r5, mrr_value, es, sha='x'):
            return {'dataset_sha256': sha, 'layers': {'fused': {'overall': {'recall@5': r5, 'mrr': mrr_value}, 'subsets': {'es': {'recall@5': es, 'mrr': mrr_value}}},
                                                      'semantic': {'overall': {'recall@5': 0, 'mrr': 0.1}, 'subsets': {'es': {'recall@5': 0, 'mrr': 0.1}}}}}
        base = report(0.1, 0.1, 0.3)
        self.assertEqual(evaluate_gate(report(0.9, 0.7, 0.5), thresholds, baseline=base), [])
        failed = evaluate_gate(report(0.7, 0.5, 0.4), thresholds, baseline=base)
        self.assertEqual({f['check'] for f in failed}, {'fused_recall_at_5', 'fused_mrr', 'subset:es'})
        # recall@5 above 0.80 is NOT enough on its own: the gain is mandatory (P-06)
        only_absolute = evaluate_gate(report(0.9, 0.7, 0.85), thresholds, baseline=report(0.1, 0.1, 0.8))
        self.assertEqual([f['check'] for f in only_absolute], ['subset:es'])
        self.assertEqual([f['check'] for f in evaluate_gate(report(0.9, 0.7, 0.9), thresholds)], ['baseline_missing'])
        mismatch = evaluate_gate(report(0.9, 0.7, 0.9), thresholds, baseline=report(0.1, 0.1, 0.3, sha='other'))
        self.assertEqual([f['check'] for f in mismatch], ['baseline_dataset_mismatch'])

    def test_ca35_no_subset_may_lose_more_than_the_allowed_points_of_recall_at_5(self):
        thresholds = {'fused_recall_at_5': 0.0, 'fused_mrr': 0.0, 'subset_gain_points': 0, 'gain_subsets': ['es'], 'max_subset_regression_points': 2}

        def report(es, en, sha='x'):
            return {'dataset_sha256': sha, 'layers': {'fused': {'overall': {'recall@5': 1, 'mrr': 1}, 'subsets': {'es': {'recall@5': es, 'mrr': 1}, 'en': {'recall@5': en, 'mrr': 1}}},
                                                      'semantic': {'overall': {'recall@5': 0, 'mrr': 0}, 'subsets': {'es': {'recall@5': 0, 'mrr': 0}, 'en': {'recall@5': 0, 'mrr': 0}}}}}
        base = report(0.5, 0.625)
        self.assertEqual(evaluate_gate(report(0.9, 0.625 - 0.02), thresholds, baseline=base), [])  # exactly the allowed loss
        failed = evaluate_gate(report(0.9, 0.625 - 0.0201), thresholds, baseline=base)
        self.assertEqual([f['check'] for f in failed], ['regression:en'])
        self.assertAlmostEqual(failed[0]['loss_points'], 2.01, places=3)
        # a subset gone from the report is a failure, and so is a gate without the threshold: nothing passes silently
        gone = report(0.9, 0.9)
        del gone['layers']['fused']['subsets']['en']
        self.assertEqual([f['check'] for f in evaluate_gate(gone, thresholds, baseline=base)], ['subset_missing:en'])
        without = {k: v for k, v in thresholds.items() if k != 'max_subset_regression_points'}
        self.assertEqual([f['check'] for f in evaluate_gate(report(0.9, 0.9), without, baseline=base)], ['threshold_missing:max_subset_regression_points'])
        self.assertEqual(json.loads((HERE / 'thresholds.json').read_text(encoding='utf-8'))['max_subset_regression_points'], 2)

    def test_ca18_fused_mrr_must_not_fall_below_the_best_single_layer_overall_or_in_any_subset(self):
        thresholds = {'fused_recall_at_5': 0.0, 'fused_mrr': 0.0, 'subset_gain_points': 0, 'gain_subsets': ['es'], 'max_subset_regression_points': 2}

        def report(fused, semantic, lexical=(0.0, 0.0, 0.0)):
            def layer(overall, es, en):
                return {'overall': {'recall@5': 1, 'mrr': overall}, 'subsets': {'es': {'recall@5': 1, 'mrr': es}, 'en': {'recall@5': 1, 'mrr': en}}}
            return {'dataset_sha256': 'x', 'layers': {'fused': layer(*fused), 'semantic': layer(*semantic), 'episodic': layer(*lexical)}}
        ok = report((0.9, 0.9, 0.9), (0.9, 0.8, 0.9), (0.5, 0.9, 0.1))  # equal to the best layer of each scope still passes
        self.assertEqual(evaluate_gate(ok, thresholds, baseline=ok), [])
        overall = report((0.89, 0.9, 0.9), (0.9, 0.8, 0.9))
        self.assertEqual([f['check'] for f in evaluate_gate(overall, thresholds, baseline=overall)], ['ca18:overall'])
        subset = report((0.9, 0.9, 0.7), (0.8, 0.8, 0.7), (0.5, 0.9, 0.71))  # best of `en` is the lexical layer
        failed = evaluate_gate(subset, thresholds, baseline=subset)
        self.assertEqual([f['check'] for f in failed], ['ca18:en'])
        self.assertEqual(failed[0]['best_single_layer_mrr'], 0.71)
        bonus = report((0.9, 0.9, 0.9), (0.9, 0.9, 0.9))
        del bonus['layers']['semantic'], bonus['layers']['episodic']
        self.assertEqual([f['check'] for f in evaluate_gate(bonus, thresholds, baseline=bonus)], ['ca18_layers_missing'])

    def test_unavailable_backend_fails_with_a_distinguishable_reason(self):
        thresholds = {'fused_recall_at_5': 0.0, 'fused_mrr': 0.0, 'subset_gain_points': 0, 'gain_subsets': ['es'], 'max_subset_regression_points': 2}
        rep = {'dataset_sha256': 'x', 'layers': {'fused': {'overall': {'recall@5': 1, 'mrr': 1}, 'subsets': {'es': {'recall@5': 1, 'mrr': 1}}},
                                                 'semantic': {'overall': {'recall@5': 0, 'mrr': 0}, 'subsets': {'es': {'recall@5': 0, 'mrr': 0}}}},
               'query_backends': [{'id': 'q1', 'episodic': {'backends': {'episodic': 'unavailable'}, 'partial': True}}]}
        self.assertEqual([f['check'] for f in evaluate_gate(rep, thresholds, baseline=rep)], ['backend_unavailable:episodic'])

    def test_measure_records_a_layer_that_raises_instead_of_scoring_recall_zero(self):
        class Retrieval:
            async def search(self, actor, request):
                broken = request['layers'] == ['episodic']
                backends = {request['layers'][0]: {'status': 'unavailable' if broken else 'ok'}}
                return {'items': [], 'backends': backends, 'partial': broken}

        class Store:
            def search_vectors(self, *args):
                raise RuntimeError('vector backend down')

        class Provider:
            async def embed(self, text, query=False):
                return {'embedding': [1.0], 'model': 'm'}
        question = {'id': 'q1', 'subset': 'es', 'q': 'x', 'expected': ['d1']}
        layers, health = asyncio.run(_measure(Store(), {}, 'p', {}, [question], Provider(), None, retrieval=Retrieval()))
        self.assertEqual(health[0]['episodic'], {'backends': {'episodic': 'unavailable'}, 'partial': True})
        self.assertEqual(health[0]['semantic']['backends'], {'semantic': 'unavailable'})
        thresholds = {'fused_recall_at_5': 0.0, 'fused_mrr': 0.0, 'subset_gain_points': 0, 'gain_subsets': ['es'], 'max_subset_regression_points': 2}
        rep = {'dataset_sha256': 'x', 'layers': layers, 'query_backends': health}
        checks = [f['check'] for f in evaluate_gate(rep, thresholds, baseline=rep)]
        self.assertIn('backend_unavailable:episodic', checks)
        self.assertIn('backend_unavailable:semantic', checks)

    def test_determinism_flag_compares_the_structural_keys(self):
        report = {key: key for key in STRUCTURAL_KEYS}
        report.update({'layers': {'fused': {'overall': {'recall@5': 1, 'mrr': 1}, 'subsets': {}}}, 'dataset_sha256': 'x'})
        changed = dict(report, query_backends='different')
        module = 'memory_platform.tests.retrieval_eval.run.'
        with mock.patch(module + 'build_report', side_effect=[report, changed]), mock.patch(module + 'evaluate_gate', return_value=[]):
            result = run(dataset='unused', dsn='d', test_dsn='d')
        self.assertFalse(result['deterministic'])
        self.assertEqual([f['check'] for f in result['gate']['failures']], ['determinism'])
        with mock.patch(module + 'build_report', side_effect=[report, dict(report)]), mock.patch(module + 'evaluate_gate', return_value=[]):
            self.assertTrue(run(dataset='unused', dsn='d', test_dsn='d')['deterministic'])

    def test_fake_embeddings_are_deterministic_and_sized(self):
        self.assertEqual(vectorize('worker lease'), vectorize('worker lease'))
        self.assertEqual(len(vectorize('worker lease')), 768)
        self.assertEqual(len(vectorize('worker lease', 2)), 2)
        self.assertNotEqual(vectorize('worker lease'), vectorize('rotate keys'))
        self.assertTrue(any(vectorize('de la')))

    def test_fake_embeddings_use_character_ngrams_not_only_whole_words(self):
        def cosine(a, b):
            return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
        original = vectorize('authentication')
        typo = cosine(original, vectorize('authentiction'))      # shares no whole word with the original
        other = cosine(original, vectorize('authorization'))
        self.assertGreater(typo, 0.5)
        self.assertGreater(typo, other)

    def test_loader_rejects_invalid_datasets_with_an_explicit_error(self):
        lines = (HERE / 'dataset-v1.jsonl').read_text(encoding='utf-8').splitlines()
        index = next(i for i, line in enumerate(lines) if json.loads(line)['type'] == 'question')
        for expected, text in (([], 'expected'), (['no-such-id'], 'expected')):
            record = dict(json.loads(lines[index]), expected=expected)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'bad.jsonl'
                path.write_text(chr(10).join(lines[:index] + [json.dumps(record)] + lines[index + 1:]) + chr(10), encoding='utf-8')
                with self.assertRaises(SystemExit) as raised:
                    load_dataset(path)
            self.assertIn(text, str(raised.exception))
        self.assertEqual(len(load_dataset(HERE / 'dataset-v1.jsonl')[1]), 64)

    def test_network_observation_is_local_and_reports_what_it_saw(self):
        with mock.patch('os.listdir', return_value=['lo']):
            self.assertEqual(network_observation()['network_interfaces'], ['lo'])
        with mock.patch('os.listdir', return_value=['eth0', 'lo']):
            self.assertIn('other than loopback', network_observation()['network_observation'])
        with mock.patch('os.listdir', side_effect=OSError):
            self.assertIsNone(network_observation()['network_interfaces'])
        self.assertNotIn('network_interfaces', STRUCTURAL_KEYS)

    def test_dsn_guard_accepts_only_the_isolated_harness_database(self):
        ok = 'postgresql://postgres@127.0.0.1:55432/memory_test'
        check_dsn(ok, ok)
        local = 'postgresql://postgres@localhost:55432/memory_test'
        check_dsn(local, local)
        bad = ('postgresql://u:p@db.example.com:5432/memory_test', 'postgresql://postgres@127.0.0.1:55432/memory',
               'postgresql://postgres@localhost:5432/kairos', 'postgresql://postgres@127.0.0.1:5432/memory_test',
               ok + '?host=db.example.com', ok + '?hostaddr=10.0.0.5', ok + '?dbname=kairos', ok + '?service=prod',
               ok + '?port=5432', 'postgresql:///memory_test?host=db.example.com&port=55432',
               'host=127.0.0.1 port=55432 dbname=memory_test options=-ccustom', ok + '?passfile=/x')
        for dsn in bad:
            with self.assertRaises(SystemExit, msg=dsn):
                check_dsn(dsn, dsn)
        with self.assertRaises(SystemExit):
            check_dsn(ok, None)
        with self.assertRaises(SystemExit):
            check_dsn(ok, ok + '?x=1')

    def test_dsn_guard_refuses_libpq_environment_that_redirects_the_connection(self):
        ok = 'postgresql://postgres@127.0.0.1:55432/memory_test'
        check_dsn(ok, ok, environ={'PGPASSWORD': 'x'})
        for name in ('PGHOSTADDR', 'PGHOST', 'PGPORT', 'PGDATABASE', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR'):
            with self.assertRaises(SystemExit, msg=name):
                check_dsn(ok, ok, environ={name: '10.9.9.9'})
        with mock.patch.dict('os.environ', {'PGHOSTADDR': '10.9.9.9'}):
            with self.assertRaises(SystemExit):
                check_dsn(ok, ok)

    def test_connection_dsn_pins_the_numeric_address_to_loopback(self):
        from psycopg.conninfo import conninfo_to_dict
        parts = conninfo_to_dict(connect_dsn('postgresql://postgres@localhost:55432/memory_test'))
        self.assertEqual((parts['hostaddr'], parts['host'], parts['port'], parts['dbname']), ('127.0.0.1', 'localhost', '55432', 'memory_test'))


if __name__ == '__main__':
    unittest.main()
