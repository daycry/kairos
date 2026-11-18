"""Retrieval metrics on hand-computed cases (no database needed)."""
import asyncio
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memory_platform.tests.retrieval_eval.fake_embeddings import vectorize
from memory_platform.tests.retrieval_eval.run import (HERE, STRUCTURAL_KEYS, _measure, _measure_abstention, abstention_threshold, aggregate, check_dsn, connect_dsn,
                                                      evaluate_abstention, evaluate_gate, load_dataset, load_negatives, mrr, network_observation,
                                                      pick_threshold, recall_at_k, run)


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
        with mock.patch(module + 'build_report', side_effect=[report, changed]), mock.patch(module + 'evaluate_gate', return_value=[]), mock.patch(module + 'evaluate_abstention', return_value=[]):
            result = run(dataset='unused', dsn='d', test_dsn='d')
        self.assertFalse(result['deterministic'])
        self.assertEqual([f['check'] for f in result['gate']['failures']], ['determinism'])
        with mock.patch(module + 'build_report', side_effect=[report, dict(report)]), mock.patch(module + 'evaluate_gate', return_value=[]), mock.patch(module + 'evaluate_abstention', return_value=[]):
            self.assertTrue(run(dataset='unused', dsn='d', test_dsn='d')['deterministic'])

    # --- Abstention (C-05, CA-27, CA-28) ---------------------------------------------------------------------------------------------------------------
    GOALS = {'abstention': {'min_correct_rate': 0.70, 'max_false_rate': 0.05, 'simulated': {'threshold': 0.20, 'min_correct_rate': 0.50, 'max_false_rate': 0.05}}}

    @staticmethod
    def abstention_report(correct=0.75, false=0.0, threshold=0.3, negatives=24, with_items=0):
        return {'abstention': {'model': 'm', 'threshold': threshold, 'correct_abstention': correct, 'false_abstention': false, 'abstained_with_items': with_items,
                               'negatives': {'n': negatives}, 'positives': {'n': 72}}}

    def test_abstention_goals_pass_exactly_at_the_limits(self):
        self.assertEqual(evaluate_abstention(self.abstention_report(correct=0.70, false=0.05), self.GOALS), [])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(correct=0.6999), self.GOALS)], ['abstention_correct'])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(false=0.0501), self.GOALS)], ['abstention_false'])

    def test_the_offline_provider_is_judged_by_its_own_goals_and_a_real_model_by_the_top_ones(self):
        simulated = self.abstention_report(correct=0.5, false=0.05)
        simulated['abstention']['simulated'] = True
        self.assertEqual(evaluate_abstention(simulated, self.GOALS), [])
        simulated['abstention']['simulated'] = False
        self.assertEqual([f['check'] for f in evaluate_abstention(simulated, self.GOALS)], ['abstention_correct'])
        simulated['abstention'].update(simulated=True, correct=0.49, correct_abstention=0.49)
        self.assertEqual([f['check'] for f in evaluate_abstention(simulated, self.GOALS)], ['abstention_correct'])
        without = {'abstention': {'min_correct_rate': 0.7, 'max_false_rate': 0.05}}
        self.assertEqual([f['check'] for f in evaluate_abstention(simulated, without)],
                         ['threshold_missing:abstention.min_correct_rate', 'threshold_missing:abstention.max_false_rate'])

    def test_an_absurd_threshold_leaves_the_gate_red(self):
        # 0.99 abstains on almost every question: correct abstention is perfect and the false abstention on questions WITH an answer breaks its cap (CA-28)
        failed = evaluate_abstention(self.abstention_report(correct=1.0, false=0.9, threshold=0.99), self.GOALS)
        self.assertEqual([f['check'] for f in failed], ['abstention_false'])
        # 0.0 never abstains: nothing is a correct abstention
        failed = evaluate_abstention(self.abstention_report(correct=0.0, false=0.0, threshold=0.0), self.GOALS)
        self.assertEqual([f['check'] for f in failed], ['abstention_correct'])

    def test_a_missing_goal_threshold_or_measurement_fails_instead_of_passing(self):
        self.assertEqual([f['check'] for f in evaluate_abstention({}, self.GOALS)], ['abstention_missing'])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(), {})],
                         ['threshold_missing:abstention.min_correct_rate', 'threshold_missing:abstention.max_false_rate'])
        for key in ('min_correct_rate', 'max_false_rate'):
            goals = {'abstention': {k: v for k, v in self.GOALS['abstention'].items() if k != key}}
            self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(), goals)], ['threshold_missing:abstention.' + key])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(threshold=None), self.GOALS)], ['threshold_missing:abstention.threshold'])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(negatives=19), self.GOALS)], ['abstention_negatives_too_few'])
        self.assertEqual([f['check'] for f in evaluate_abstention(self.abstention_report(with_items=1), self.GOALS)], ['abstention_items'])

    def test_the_committed_thresholds_carry_the_agreed_abstention_goals_and_keep_the_existing_gates(self):
        thresholds = json.loads((HERE / 'thresholds.json').read_text(encoding='utf-8'))
        self.assertEqual((thresholds['abstention']['min_correct_rate'], thresholds['abstention']['max_false_rate']), (0.70, 0.05))
        simulated = thresholds['abstention']['simulated']  # R-07: with the offline provider 70 % correct needs 6.9 % false (measured), so it has goals of its own
        self.assertIsInstance(simulated['threshold'], float)
        self.assertLessEqual(simulated['max_false_rate'], 0.05)
        self.assertEqual((thresholds['fused_recall_at_5'], thresholds['fused_mrr'], thresholds['max_subset_regression_points']), (0.80, 0.60, 2))

    def test_run_adds_the_abstention_failures_to_the_gate(self):
        report = {key: key for key in STRUCTURAL_KEYS}
        report.update({'layers': {'fused': {'overall': {'recall@5': 1, 'mrr': 1}, 'subsets': {}}}, 'dataset_sha256': 'x'})
        module = 'memory_platform.tests.retrieval_eval.run.'
        with mock.patch(module + 'build_report', side_effect=[report, dict(report)]), mock.patch(module + 'evaluate_gate', return_value=[]):
            result = run(dataset='unused', dsn='d', test_dsn='d')
        self.assertFalse(result['gate']['passed'])
        self.assertEqual([f['check'] for f in result['gate']['failures']], ['abstention_missing'])

    def test_the_threshold_under_test_comes_from_the_simulated_entry_or_the_model_entry(self):
        config = {'abstention': {'simulated': {'threshold': 0.3}, 'models': {'nomic-embed-text': 0.55}}}
        self.assertEqual(abstention_threshold(config, 'nomic-embed-text', True), 0.3)
        self.assertEqual(abstention_threshold(config, 'nomic-embed-text:latest', False), 0.55)
        self.assertIsNone(abstention_threshold(config, 'other-model', False))
        self.assertIsNone(abstention_threshold({}, 'nomic-embed-text', True))
        self.assertIsNone(abstention_threshold({'abstention': {'simulated': {'threshold': 0.3}}}, 'nomic-embed-text', False))

    def test_pick_threshold_takes_the_middle_of_the_widest_interval_that_meets_both_goals(self):
        def row(negative, best, protected=False):
            return {'negative': negative, 'best': best, 'protected': protected}
        # negatives at .10 .15 .20 .25 and one protected at .05; positives at .40 .50 .60 .70 and a low one (.18) protected by a lexical hit
        rows = [row(True, b) for b in (0.10, 0.15, 0.20, 0.25)] + [row(True, 0.05, True)] + [row(False, b) for b in (0.40, 0.50, 0.60, 0.70)] + [row(False, 0.18, True), row(False, 0.30, True)]
        picked = pick_threshold(rows, 0.70, 0.05)
        self.assertEqual((picked['low'], picked['high']), (0.275, 0.35))
        self.assertEqual(picked['threshold'], 0.3125)
        self.assertEqual((picked['correct_abstention'], picked['false_abstention']), (0.8, 0.0))
        # nothing reaches the goals when a positive without lexical protection sits below every negative
        self.assertIsNone(pick_threshold(rows + [row(False, 0.02)], 0.70, 0.05))
        self.assertIsNone(pick_threshold([row(True, 0.1)], 0.70, 0.05))
        # a question with no cosine at all is protected: it can never abstain
        self.assertIsNone(pick_threshold([row(True, None)] * 3 + [row(False, 0.9)], 0.70, 0.05))

    def test_measure_abstention_counts_correct_and_false_abstentions_from_the_search_answers(self):
        class Search:
            def __init__(self, threshold):
                self.threshold = threshold

            async def search(self, actor, request):
                assert request['abstain'] is True
                best = {'n1': 0.1, 'n2': 0.2, 'p1': 0.9, 'p2': 0.25}[request['q']]
                gone = best < self.threshold and request['q'] != 'p2'  # p2 is protected by a lexical hit
                return {'items': [] if gone else [{'item_id': 'x'}], 'abstained': gone}

        class Store:
            def search_vectors(self, actor, projects, vector, model, limit):
                return [{'score': vector[0]}, {'score': vector[0] / 2}]

        class Provider:
            async def embed(self, text, query=False):
                return {'embedding': [{'n1': 0.1, 'n2': 0.2, 'p1': 0.9, 'p2': 0.25}[text]], 'model': 'm'}
        negatives = [{'id': 'n-1', 'q': 'n1', 'near': False}, {'id': 'n-2', 'q': 'n2', 'near': True}]
        positives = [{'id': 'p-1', 'q': 'p1'}, {'id': 'p-2', 'q': 'p2'}]
        settings = type('S', (), {'embedding_model': 'm'})()
        result = asyncio.run(_measure_abstention(Store(), {}, 'proj', positives, negatives, Provider(), settings, 0.15, retrieval=Search(0.15), probe=Search(1.0)))
        self.assertEqual((result['correct_abstention'], result['false_abstention'], result['abstained_with_items']), (0.5, 0.0, 0))
        self.assertEqual(result['negatives'], {'n': 2, 'abstained': 1, 'near_n': 1, 'near_abstained': 0})
        self.assertEqual({r['id']: (r['best'], r['protected'], r['abstained']) for r in result['scores']},
                         {'n-1': (0.1, False, True), 'n-2': (0.2, False, False), 'p-1': (0.9, False, False), 'p-2': (0.25, True, False)})
        # an abstention that still carries items is reported, never counted as a correct one
        class Leaky(Search):
            async def search(self, actor, request):
                return {'items': [{'item_id': 'x'}], 'abstained': True}
        leaked = asyncio.run(_measure_abstention(Store(), {}, 'proj', positives, negatives, Provider(), settings, 0.15, retrieval=Leaky(0), probe=Search(1.0)))
        self.assertEqual((leaked['correct_abstention'], leaked['abstained_with_items']), (0.0, 4))
        # the calibration of this file picks a threshold that its own scores reproduce
        self.assertEqual(pick_threshold(result['scores'], 0.5, 0.0)['false_abstention'], 0.0)

    def test_negatives_are_loaded_and_validated_against_the_corpus(self):
        corpus, _ = load_dataset(HERE / 'dataset-v1.jsonl')
        records, digest = load_negatives(HERE / 'dataset-v1-negatives.jsonl', corpus)
        self.assertEqual((len(records), len(digest)), (24, 64))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'few.jsonl'
            path.write_text(json.dumps(records[0]) + chr(10), encoding='utf-8')
            with self.assertRaises(SystemExit) as raised:
                load_negatives(path, corpus)
        self.assertIn('without an answer', str(raised.exception))

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


class NegativeDatasetTests(unittest.TestCase):
    """T-87 (CA-26): the questions without an answer live in their own file; dataset-v1.jsonl stays frozen."""

    def records(self):
        return [json.loads(line) for line in (HERE / 'dataset-v1-negatives.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]

    def test_the_negative_file_is_valid_bilingual_and_has_questions_close_to_existing_topics(self):
        from memory_platform.tests.retrieval_eval.check_dataset import validate_negatives
        records = self.records()
        self.assertEqual(validate_negatives(records, load_dataset(HERE / 'dataset-v1.jsonl')[0])[2], [])
        self.assertGreaterEqual(len(records), 20)
        self.assertTrue(all(r['expected'] == [] for r in records))
        self.assertGreaterEqual(sum(r['lang'] == 'es' for r in records), 8)
        self.assertGreaterEqual(sum(r['lang'] == 'en' for r in records), 8)
        self.assertGreaterEqual(sum(r['near'] for r in records), 8)

    def test_validate_negatives_refuses_what_would_weaken_the_set(self):
        from memory_platform.tests.retrieval_eval.check_dataset import validate_negatives
        corpus = load_dataset(HERE / 'dataset-v1.jsonl')[0]
        good = self.records()
        def errors(records):
            return validate_negatives(records, corpus)[2]
        self.assertTrue(errors(good[:19]))                                                  # fewer than 20
        self.assertTrue(errors([dict(good[0], expected=['m-en-01'])] + good[1:]))           # it has an answer
        self.assertTrue(errors([dict(good[0], subset='es')] + good[1:]))                    # not a negative subset
        self.assertTrue(errors([dict(good[0], near='yes')] + good[1:]))                     # near must be a boolean
        self.assertTrue(errors([dict(good[0], id=good[1]['id'])] + good[1:]))               # duplicate id
        self.assertTrue(errors([dict(good[0], id='q-001')] + good[1:]))                     # id of a question of dataset-v1
        self.assertTrue(errors([dict(r, near=False) for r in good]))                        # none close to a topic
        self.assertTrue(errors([dict(r, lang='en') for r in good]))                         # one language only
        self.assertTrue(errors([dict(good[0], type='memory')] + good[1:]))                  # a corpus record in the negative set
        self.assertTrue(errors([dict(good[0], q=' ')] + good[1:]))

    def test_dataset_v1_is_frozen(self):
        from memory_platform.tests.retrieval_eval.check_dataset import load
        records, digest = load(HERE / 'dataset-v1.jsonl')
        self.assertEqual(digest, json.loads((HERE / 'baseline.json').read_text(encoding='utf-8'))['dataset_sha256'])
        self.assertEqual(sum(r['type'] == 'question' for r in records), 72)


class ProviderSelectionTests(unittest.TestCase):
    """T-36: the gate can run with a real Ollama, but only one that the operator names for the evaluation and never the deployed one."""

    def test_the_default_provider_is_the_simulated_one(self):
        from memory_platform.config import Settings
        from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
        from memory_platform.tests.retrieval_eval.run import make_provider
        with mock.patch.dict('os.environ', {}, clear=True):
            provider, label, settings = make_provider('postgresql://postgres@127.0.0.1:55432/memory_test')
        self.assertIsInstance(provider, FakeEmbeddings)
        self.assertEqual(label, 'fake-hashed-words-and-char-ngrams')
        self.assertIsInstance(settings, Settings)

    def test_ollama_needs_its_own_endpoint_variable_and_an_explicit_choice(self):
        from memory_platform.tests.retrieval_eval.run import make_provider
        dsn = 'postgresql://postgres@127.0.0.1:55432/memory_test'
        with mock.patch.dict('os.environ', {'MEMORY_RETRIEVAL_EVAL_PROVIDER': 'ollama'}, clear=True):
            with self.assertRaises(SystemExit):
                make_provider(dsn)  # no endpoint: it never falls back to MEMORY_OLLAMA_URL or the simulated provider
        with mock.patch.dict('os.environ', {'MEMORY_RETRIEVAL_EVAL_PROVIDER': 'ollama', 'MEMORY_OLLAMA_URL': 'http://kairos-rq8-ollama:11434'}, clear=True):
            with self.assertRaises(SystemExit):
                make_provider(dsn)  # MEMORY_OLLAMA_URL is the service's variable: not read here
        with mock.patch.dict('os.environ', {'MEMORY_RETRIEVAL_EVAL_PROVIDER': 'unknown'}, clear=True):
            with self.assertRaises(SystemExit):
                make_provider(dsn)

    def test_ollama_is_built_with_the_named_endpoint_and_labelled(self):
        from memory_platform.providers import Embeddings
        from memory_platform.tests.retrieval_eval.run import make_provider
        env = {'MEMORY_RETRIEVAL_EVAL_PROVIDER': 'ollama', 'MEMORY_RETRIEVAL_EVAL_OLLAMA_URL': 'http://kairos-rq8-ollama:11434/'}
        with mock.patch.dict('os.environ', env, clear=True):
            provider, label, settings = make_provider('postgresql://postgres@127.0.0.1:55432/memory_test')
        self.assertIsInstance(provider, Embeddings)
        self.assertEqual(settings.ollama_url, 'http://kairos-rq8-ollama:11434')
        self.assertEqual(label, 'ollama:nomic-embed-text')

    def test_the_deployed_ollama_and_anything_unsafe_is_refused(self):
        from memory_platform.tests.retrieval_eval.run import check_ollama_url
        for url in ('http://127.0.0.1:11434', 'http://localhost:11434/', 'http://[::1]:11434', 'http://ollama:11434', 'http://ollama', 'http://host.docker.internal:11434',
                    'http://host.docker.internal:11535', 'http://knowledge-graphs-ollama-1:11434', 'http://Knowledge-Graphs-Ollama-1:11434',
                    'https://kairos-rq8-ollama:11434', 'http://user:pw@kairos-rq8-ollama:11434', 'http://kairos-rq8-ollama:11434/api?x=1', 'ftp://x', '', None,
                    'http://kairos-rq8-ollama:11434/#frag', 'http://127.0.0.1:11434/api'):
            with self.assertRaises(SystemExit, msg=url):
                check_ollama_url(url)
        for url in ('http://kairos-rq8-ollama:11434', 'http://my-eval-ollama:11434', 'http://kairos-rq8-ollama.:11434', 'http://172.17.0.2:11434', 'http://10.20.0.5:11434'):
            self.assertEqual(check_ollama_url(url), url.rstrip('/'))

    def test_gap2_every_spelling_of_the_host_or_the_deployed_services_is_refused(self):
        """Gap 2 (CWE-184): the exclusion list was bypassable by spelling; hosts are normalised and IPs interpreted, not compared as text."""
        from memory_platform.tests.retrieval_eval.run import check_ollama_url
        for url in ('http://0.0.0.0:11434', 'http://127.0.0.2:11434', 'http://127.1:11434', 'http://2130706433:11434', 'http://0x7f.0.0.1:11434', 'http://0177.0.0.1:11434',
                    'http://localhost.:11434', 'http://LOCALHOST.:11434', 'http://foo.localhost:11434', 'http://[::ffff:127.0.0.1]:11434', 'http://[::ffff:7f00:1]:11434',
                    'http://[::]:11434', 'http://[::1]:11535', 'http://127.0.0.1:11535', 'http://localhost:11535/', 'http://169.254.169.254:11434', 'http://[fe80::1]:11434',
                    'http://ollama.:11434', 'http://OLLAMA:11434', 'http://host.docker.internal.:11434', 'http://gateway.docker.internal:11434',
                    'http://Gateway.Docker.Internal.:11434', 'http://knowledge-graphs-ollama-1.:11434', 'http://172.17.0.1:11434', 'http://192.168.1.1:11434',
                    'http://10.0.0.1:11434', 'http://[::ffff:172.17.0.1]:11434', 'http://172.17.0.1.:11434'):
            with self.assertRaises(SystemExit, msg=url):
                check_ollama_url(url)


if __name__ == '__main__':
    unittest.main()
