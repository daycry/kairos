"""Abstention (C-05, M-01, CA-27, CA-29): the search answers `abstained: true` and no items only when the best semantic cosine is below the
threshold of the model AND no lexical layer returned anything. The decision is in `docs/architecture.md` («Abstención: la señal»)."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from memory_platform import models as m
from memory_platform.config import Settings, abstain_from_env
from memory_platform.retrieval import Retrieval

MODEL = 'nomic-embed-text'
ROW = {'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic', 'title': 'Lexical', 'excerpt': 'x', 'validation_status': 'validated'}


def semantic(score, model=MODEL, item='sem'):
    return {'ref': 'episodic:a:%s:1' % item, 'project_id': 'a', 'item_id': item, 'version': 1, 'layer': 'episodic', 'title': 'Semantic', 'excerpt': 'x',
            'validation_status': 'validated', 'score': score, 'embedding_model': model, 'candidates_truncated': False, 'candidate_limit': 10000}


def make(thresholds=None, default=False, lexical=False, scores=(0.2,), vectors=True, truncated=False, model=MODEL):
    store = Mock()
    store.search_items.return_value = [dict(ROW)] if lexical else []
    store.search_documents.return_value = []
    store.search_native_facts.return_value = []
    store.has_vectors.return_value = vectors
    hits = [dict(semantic(score, model, 'sem%d' % number), candidates_truncated=truncated) for number, score in enumerate(scores)]
    store.search_vectors.return_value = hits
    settings = Settings('unused', request_timeout=5, abstain_thresholds=thresholds or {}, abstain_default=default, embedding_model=model)
    return Retrieval(store, settings, Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': model, 'verified': True})))


def ask(retrieval, **extra):
    return asyncio.run(retrieval.search({}, m.Search(project_ids=['a'], q='question', layers=['episodic'], **extra)))


class AbstentionTests(unittest.TestCase):
    def test_below_the_threshold_without_lexical_match_abstains(self):
        answer = ask(make({MODEL: 0.5}), abstain=True)
        self.assertEqual(answer['items'], [])
        self.assertIs(answer['abstained'], True)
        self.assertNotIn('abstention', answer)
        self.assertIn('semantic', answer['backends'])  # the evidence of what ran stays

    def test_at_or_above_the_threshold_answers_and_says_it_did_not_abstain(self):
        for score in (0.5, 0.9):
            answer = ask(make({MODEL: 0.5}, scores=(score,)), abstain=True)
            self.assertEqual([i['item_id'] for i in answer['items']], ['sem0'], score)
            self.assertIs(answer['abstained'], False)

    def test_the_best_of_all_the_semantic_hits_decides(self):
        answer = ask(make({MODEL: 0.5}, scores=(0.1, 0.7, 0.3)), abstain=True)
        self.assertIs(answer['abstained'], False)

    def test_a_lexical_hit_never_abstains(self):
        answer = ask(make({MODEL: 0.99}, lexical=True), abstain=True)
        self.assertIs(answer['abstained'], False)
        self.assertIn('lex', [i['item_id'] for i in answer['items']])

    def test_without_threshold_for_the_model_it_answers_and_says_uncalibrated(self):
        for thresholds in ({}, {'other-model': 0.9}):
            answer = ask(make(thresholds), abstain=True)
            self.assertEqual(answer['abstention'], 'uncalibrated')
            self.assertIs(answer['abstained'], False)
            self.assertEqual([i['item_id'] for i in answer['items']], ['sem0'])

    def test_a_degraded_semantic_layer_never_abstains(self):
        for retrieval in (make({MODEL: 0.99}, vectors=False), make({MODEL: 0.99}, truncated=True)):
            answer = ask(retrieval, abstain=True)
            self.assertIs(answer['abstained'], False)
            self.assertNotIn('abstention', answer)
        broken = make({MODEL: 0.99})
        broken.store.search_vectors.side_effect = RuntimeError('boom')
        answer = ask(broken, abstain=True)
        self.assertEqual(answer['degraded']['reason'], 'store_error')
        self.assertIs(answer['abstained'], False)
        self.assertIs(ask(make({MODEL: 0.99}), abstain=True, semantic=False)['abstained'], False)  # semantic layer not asked for

    def test_without_abstain_and_with_default_off_the_answer_is_the_current_one_field_by_field(self):
        plain = ask(make({MODEL: 0.99}))
        self.assertEqual(plain, ask(make()))  # thresholds configured or not, nothing changes
        self.assertEqual(plain, ask(make({MODEL: 0.99}), abstain=False))
        self.assertTrue(plain['items'])
        self.assertTrue(set(plain) <= {'items', 'backends', 'partial', 'degraded'})

    def test_default_on_abstains_without_the_parameter_and_the_parameter_overrides_it(self):
        retrieval = make({MODEL: 0.5}, default=True)
        self.assertIs(ask(retrieval)['abstained'], True)
        self.assertIs(ask(retrieval, abstain=True)['abstained'], True)
        off = ask(retrieval, abstain=False)
        self.assertNotIn('abstained', off)
        self.assertTrue(off['items'])


class AbstentionSettingsTests(unittest.TestCase):
    def test_defaults_are_off_and_no_thresholds(self):
        self.assertEqual(abstain_from_env({}), (False, {}))
        self.assertEqual((Settings('unused').abstain_default, Settings('unused').abstain_thresholds), (False, {}))

    def test_reads_the_switch_and_the_thresholds_per_model(self):
        self.assertEqual(abstain_from_env({'MEMORY_ABSTAIN_DEFAULT': 'on', 'MEMORY_ABSTAIN_THRESHOLDS': 'nomic-embed-text=0.55, mxbai:large=0.4'}),
                         (True, {'nomic-embed-text': 0.55, 'mxbai:large': 0.4}))
        self.assertEqual(abstain_from_env({'MEMORY_ABSTAIN_DEFAULT': 'OFF'})[0], False)

    def test_invalid_values_fail_at_startup(self):
        for env in ({'MEMORY_ABSTAIN_DEFAULT': 'maybe'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'nomic'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a=x'},
                    {'MEMORY_ABSTAIN_THRESHOLDS': 'a=1.5'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a=nan'}, {'MEMORY_ABSTAIN_THRESHOLDS': '=0.5'},
                    {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5,a=0.6'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                abstain_from_env(env)
        with self.assertRaises(ValueError):
            Settings('unused', abstain_thresholds={'a': 2.0})

    def test_the_request_field_is_optional_and_unset_by_default(self):
        self.assertIsNone(m.Search(project_ids=['a'], q='x').abstain)
        self.assertNotIn('abstain', m.Search(project_ids=['a'], q='x').model_dump(exclude_none=True))


if __name__ == '__main__':
    unittest.main()
