"""Abstention (C-05, M-01, CA-27, CA-29): the search answers `abstained: true` and no items only when the best semantic cosine is below the
threshold of the model AND no lexical layer returned anything. The decision is in `docs/architecture.md` («Abstención: la señal»)."""
import asyncio
import itertools
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import yaml

from fastapi.testclient import TestClient

from memory_platform import models as m
from memory_platform.app import create_app
from memory_platform.errors import Unauthorized
from memory_platform.config import Settings, abstain_from_env, threshold_for
from memory_platform.retrieval import Retrieval, lexical_complete

MODEL = 'nomic-embed-text'
ROW = {'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic', 'title': 'Lexical', 'excerpt': 'x', 'validation_status': 'validated'}


class TimedOut(list):
    """What the store returns when the trigram fallback ran out of its own time (`fuzzy_timed_out`): the lexical hits are there but incomplete."""
    fuzzy_timed_out = True


def semantic(score, model=MODEL, item='sem'):
    return {'ref': 'episodic:a:%s:1' % item, 'project_id': 'a', 'item_id': item, 'version': 1, 'layer': 'episodic', 'title': 'Semantic', 'excerpt': 'x',
            'validation_status': 'validated', 'score': score, 'embedding_model': model, 'candidates_truncated': False, 'candidate_limit': 10000}


def make(thresholds=None, default=False, lexical=False, scores=(0.2,), vectors=True, truncated=False, model=MODEL, error=False):
    store = Mock()
    store.search_items.return_value = [dict(ROW)] if lexical else []
    store.search_documents.return_value = []
    store.search_native_facts.return_value = []
    store.has_vectors.return_value = vectors
    hits = [dict(semantic(score, model, 'sem%d' % number), candidates_truncated=truncated) for number, score in enumerate(scores)]
    store.search_vectors.return_value = hits
    if error:
        store.search_vectors.side_effect = RuntimeError('boom')
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

    def test_a_lexical_layer_that_failed_or_ran_out_of_time_never_abstains(self):
        # Without the lexical signal the absence of a match proves nothing: the same request answers with what the semantic layer found.
        down = make({MODEL: 0.5})
        down.store.search_items.side_effect = RuntimeError('lexical down')
        slow = make({MODEL: 0.5})
        slow.store.search_items.return_value = TimedOut()
        for name, retrieval in (('unavailable', down), ('fuzzy_timeout', slow)):
            answer = ask(retrieval, abstain=True)
            self.assertIs(answer['abstained'], False, name)
            self.assertEqual([i['item_id'] for i in answer['items']], ['sem0'], name)
        documental = make({MODEL: 0.5})
        documental.store.search_documents.side_effect = RuntimeError('documental down')
        answer = asyncio.run(documental.search({}, m.Search(project_ids=['a'], q='question', layers=['episodic', 'documental'], abstain=True)))
        self.assertIs(answer['abstained'], False)  # one layer down is enough, even if the other answered "nothing"
        self.assertEqual([i['item_id'] for i in answer['items']], ['sem0'])

    def test_the_lexical_state_is_complete_only_with_every_layer_and_provider_ok(self):
        self.assertTrue(lexical_complete({'status': 'ok', 'count': 0}))
        self.assertTrue(lexical_complete({'status': 'ok', 'providers': {'native': {'status': 'ok', 'fuzzy_matches': 2}}}))
        for status in ({'status': 'unavailable'}, {'status': 'partial'}, {'status': 'off'}, {'status': 'degraded'}, {}, {'status': 'ok', 'fuzzy_timeout': True},
                       {'status': 'ok', 'providers': {'native': {'status': 'ok', 'fuzzy_timeout': True}}},
                       {'status': 'ok', 'providers': {'a': {'status': 'ok'}, 'b': {'status': 'unavailable'}}}):
            self.assertFalse(lexical_complete(status), status)

    def test_without_threshold_it_says_uncalibrated_also_with_a_complete_semantic_layer_and_no_hits(self):
        answer = ask(make({}, scores=()), abstain=True)
        self.assertEqual((answer['abstained'], answer['abstention'], answer['items']), (False, 'uncalibrated', []))
        # No signal at all (layer off, degraded, truncated or not asked for) is not a calibration question: no `abstention`, just `abstained: false`.
        for retrieval, extra in ((make({}, vectors=False), {}), (make({}, truncated=True), {}), (make({}, error=True), {}), (make({}), {'semantic': False})):
            answer = ask(retrieval, abstain=True, **extra)
            self.assertIs(answer['abstained'], False)
            self.assertNotIn('abstention', answer)

    def test_the_latest_tag_is_the_same_model_on_both_sides(self):
        self.assertIs(ask(make({'nomic-embed-text': 0.5}, model='nomic-embed-text:latest'), abstain=True)['abstained'], True)
        self.assertIs(ask(make({'nomic-embed-text:latest': 0.5}, model='nomic-embed-text'), abstain=True)['abstained'], True)
        self.assertNotIn('abstention', ask(make({'nomic-embed-text': 0.5}, model='nomic-embed-text:latest'), abstain=True))
        self.assertEqual(threshold_for({'a': 0.1, 'b:v2': 0.2}, 'a:latest'), 0.1)
        self.assertEqual(threshold_for({'a': 0.1, 'b:v2': 0.2}, 'b:v2'), 0.2)
        self.assertIsNone(threshold_for({'a': 0.1}, 'b'))
        self.assertIsNone(threshold_for({'a': 0.1, 'b:v2': 0.2}, 'b'))  # another tag is another model


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
                    {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5,a=0.6'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5;b=0.2'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5 b=0.2'},
                    {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5:b=0.2'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a==0.5'}, {'MEMORY_ABSTAIN_THRESHOLDS': 'a b=0.5'},
                    {'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5,a:latest=0.6'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                abstain_from_env(env)
        for models in ({'a': 2.0}, {'a=0.5;b': 0.2}, {'a;b': 0.2}, {'a b': 0.2}, {'a=b': 0.2}, {'a': 0.1, 'a:latest': 0.2}):
            with self.subTest(models=models), self.assertRaises(ValueError):
                Settings('unused', abstain_thresholds=models)

    def test_a_misspelt_separator_is_named_without_echoing_the_values(self):
        with self.assertRaises(ValueError) as caught:
            abstain_from_env({'MEMORY_ABSTAIN_THRESHOLDS': 'a=0.5;b=0.2'})
        self.assertIn('MEMORY_ABSTAIN_THRESHOLDS', str(caught.exception))
        self.assertNotIn('0.5', str(caught.exception))
        self.assertNotIn('0.2', str(caught.exception))

    def test_real_model_names_are_accepted(self):
        env = {'MEMORY_ABSTAIN_THRESHOLDS': 'nomic-embed-text=0.5,mxbai-embed-large:335m=0.4,hf.co/org/model_x:Q4_K_M=0.3,registry.local:5000/lib/m@v1=0.2'}
        self.assertEqual(len(abstain_from_env(env)[1]), 4)

    def test_the_request_field_is_optional_and_unset_by_default(self):
        self.assertIsNone(m.Search(project_ids=['a'], q='x').abstain)
        self.assertNotIn('abstain', m.Search(project_ids=['a'], q='x').model_dump(exclude_none=True))


THRESHOLD = 0.5
# The class, in full: model with/without threshold x state of the semantic layer x lexical hit x how abstention is asked for.
MODELS = {'threshold': {MODEL: THRESHOLD}, 'no-threshold': {'another-model': THRESHOLD}}
SEMANTIC = {'low': {}, 'high': {'scores': (0.9,)}, 'empty': {'scores': ()}, 'no_vectors': {'vectors': False}, 'truncated': {'truncated': True}, 'store_error': {'error': True}, 'not_asked': {'semantic': False}}
LEXICAL = (False, True)
# What the lexical layers did: `ok` (the layers asked for all answered in time) or one of them failed (`_down`) or ran out of its trigram time (`_slow`).
LEXSTATE = {'ok': ['episodic'], 'episodic_down': ['episodic'], 'episodic_slow': ['episodic'], 'documental_down': ['episodic', 'documental'],
            'documental_slow': ['episodic', 'documental'], 'temporal_down': ['episodic', 'temporal'], 'two_down': ['episodic', 'documental', 'temporal']}
ASKED = {'explicit-true': (True, False), 'explicit-false': (False, True), 'default-on': (None, True), 'default-off': (None, False)}


def expected(thresholds, semantic, lexical, asked, lexstate='ok'):
    """The rule written from the decision, not from the code: (active, abstained, uncalibrated)."""
    explicit, default = ASKED[asked]
    active = default if explicit is None else explicit
    complete = semantic in ('low', 'high', 'empty')
    calibrated = MODEL in MODELS[thresholds]
    abstained = active and complete and calibrated and semantic == 'low' and not lexical and lexstate == 'ok'
    return active, abstained, bool(active and complete and not calibrated)


def combos():
    # A lexical hit comes from the episodic layer, which cannot also be the one that is down.
    return [c for c in itertools.product(MODELS, SEMANTIC, LEXICAL, ASKED, LEXSTATE) if not (c[2] and c[4] == 'episodic_down')]


def build(thresholds, semantic, lexical, asked, lexstate='ok'):
    options = dict(SEMANTIC[semantic])
    options.pop('semantic', None)
    retrieval = make(MODELS[thresholds], default=ASKED[asked][1], lexical=lexical, **options)
    store = retrieval.store
    if lexstate == 'episodic_down':
        store.search_items.side_effect = RuntimeError('episodic down')
    elif lexstate == 'episodic_slow':
        store.search_items.return_value = TimedOut(store.search_items.return_value)
    elif lexstate == 'documental_down':
        store.search_documents.side_effect = RuntimeError('documental down')
    elif lexstate == 'documental_slow':
        store.search_documents.return_value = TimedOut()
    elif lexstate == 'temporal_down':
        store.search_native_facts.side_effect = RuntimeError('temporal down')
    elif lexstate == 'two_down':
        store.search_documents.side_effect = RuntimeError('documental down')
        store.search_native_facts.side_effect = RuntimeError('temporal down')
    return retrieval


def request(semantic, asked, lexstate='ok'):
    explicit = ASKED[asked][0]
    return dict(({} if explicit is None else {'abstain': explicit}), layers=LEXSTATE[lexstate], **({'semantic': False} if semantic == 'not_asked' else {}))


def check(test, body, thresholds, semantic, lexical, asked, lexstate='ok'):
    active, abstained, uncalibrated = expected(thresholds, semantic, lexical, asked, lexstate)
    if not active:
        test.assertFalse({'abstained', 'abstention'} & set(body))
    else:
        test.assertIs(body['abstained'], abstained)
        test.assertEqual(body.get('abstention'), 'uncalibrated' if uncalibrated else None)
    ids = [item['item_id'] for item in body['items']]
    if abstained:
        test.assertEqual(ids, [])
    else:
        test.assertEqual(bool(ids), lexical or semantic in ('low', 'high', 'truncated'), 'a question that is not abstained keeps whatever the layers found')
        test.assertEqual('lex' in ids, lexical)
    if semantic in ('no_vectors', 'store_error') and not lexstate.endswith('_down') and lexstate != 'two_down':
        test.assertIn('degraded', body)  # the degradation is still reported next to the plain answer (only when no other layer is down: those show in `backends`/`partial`)
    else:
        test.assertNotIn('degraded', body)


def client_for(retrieval):
    auth = Mock()
    auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer'}
    auth.authenticate_session.side_effect = Unauthorized()
    return TestClient(create_app(retrieval.settings, retrieval.store, auth, retrieval))


HEADERS = {'Authorization': 'Bearer fixture'}


class AbstentionClassTests(unittest.TestCase):
    def test_every_combination_at_service_level(self):
        count = 0
        for thresholds, semantic, lexical, asked, lexstate in combos():
            with self.subTest(thresholds=thresholds, semantic=semantic, lexical=lexical, asked=asked, lexstate=lexstate):
                answer = asyncio.run(build(thresholds, semantic, lexical, asked, lexstate).search({}, m.Search(project_ids=['a'], q='question', **request(semantic, asked, lexstate))))
                check(self, answer, thresholds, semantic, lexical, asked, lexstate)
            count += 1
        self.assertEqual(count, 2 * 7 * 4 * (2 * 7 - 1))

    def test_every_combination_end_to_end_over_the_api_search_and_context(self):
        shared = build('threshold', 'low', False, 'default-off')  # one app: each combination only swaps what the retrieval reads
        with client_for(shared) as client:
            for thresholds, semantic, lexical, asked, lexstate in combos():
                other = build(thresholds, semantic, lexical, asked, lexstate)
                shared.store, shared.settings, shared.embeddings = other.store, other.settings, other.embeddings
                for path in ('/v1/search', '/v1/context'):
                    with self.subTest(path=path, thresholds=thresholds, semantic=semantic, lexical=lexical, asked=asked, lexstate=lexstate):
                        body = {'project_ids': ['a'], 'q': 'question', 'layers': LEXSTATE[lexstate], **({'semantic': False} if semantic == 'not_asked' else {})}
                        if path == '/v1/search':
                            body.update(request(semantic, asked, lexstate))
                        response = client.post(path, json=body, headers=HEADERS)
                        self.assertEqual(response.status_code, 200, response.text)
                        answer = response.json()
                        if path == '/v1/search':
                            check(self, answer, thresholds, semantic, lexical, asked, lexstate)
                        else:  # `context` has no `abstain` of its own: only the server default applies to it
                            check(self, answer, thresholds, semantic, lexical, 'default-on' if ASKED[asked][1] else 'default-off', lexstate)
                            if answer.get('abstained'):
                                self.assertEqual(answer['context'], '')

    def test_the_api_refuses_a_non_boolean_abstain_and_accepts_null_as_unset(self):
        with client_for(make({MODEL: THRESHOLD})) as client:
            for bad in ('maybe', 2, [], {}):
                self.assertEqual(client.post('/v1/search', json={'project_ids': ['a'], 'q': 'x', 'abstain': bad}, headers=HEADERS).status_code, 422, bad)
            plain = client.post('/v1/search', json={'project_ids': ['a'], 'q': 'x', 'layers': ['episodic']}, headers=HEADERS).json()
            null = client.post('/v1/search', json={'project_ids': ['a'], 'q': 'x', 'layers': ['episodic'], 'abstain': None}, headers=HEADERS).json()
            self.assertEqual(plain, null)
            self.assertNotIn('abstained', plain)

    def test_the_rule_of_the_table_itself_is_not_vacuous(self):
        # Some combinations abstain, some are uncalibrated, some are inactive, and none abstains while protected by a lexical hit or without a complete signal.
        outcomes = [(combo, expected(*combo)) for combo in combos()]
        self.assertTrue(any(abstained for _, (_, abstained, _) in outcomes))
        self.assertTrue(any(uncalibrated for _, (_, _, uncalibrated) in outcomes))
        self.assertTrue(any(not active for _, (active, _, _) in outcomes))
        self.assertFalse(any(abstained and (combo[2] or combo[1] != 'low' or combo[4] != 'ok') for combo, (_, abstained, _) in outcomes))
        self.assertTrue(any(combo[4] != 'ok' and combo[1] == 'low' and not combo[2] and expected(*combo)[0] for combo, _ in outcomes))  # the lexical-failure cases are in the table


ROOT = Path(__file__).resolve().parents[3]


class AbstentionDeploymentTests(unittest.TestCase):
    """The variables reach the containers (the operator sets them in `.env`) and the manual lists them, as the other `MEMORY_*` of the search."""

    def test_compose_passes_both_variables_with_the_server_defaults_to_every_service_that_runs_the_search(self):
        compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
        shared = compose['x-memory-environment']
        self.assertEqual(shared['MEMORY_ABSTAIN_THRESHOLDS'], '${MEMORY_ABSTAIN_THRESHOLDS:-}')
        self.assertEqual(shared['MEMORY_ABSTAIN_DEFAULT'], '${MEMORY_ABSTAIN_DEFAULT:-off}')
        self.assertEqual(abstain_from_env({'MEMORY_ABSTAIN_THRESHOLDS': '', 'MEMORY_ABSTAIN_DEFAULT': 'off'}), (False, {}))  # the compose defaults are the code's
        api = compose['services']['memory-api']
        for name in ('MEMORY_ABSTAIN_THRESHOLDS', 'MEMORY_ABSTAIN_DEFAULT'):
            self.assertIn(name, api['environment'], 'memory-api runs the search')

    def test_the_manual_lists_them_with_the_latest_rule_and_the_uncalibrated_answer(self):
        manual = (ROOT / 'docs/configuration.md').read_text(encoding='utf-8')
        for name in ('MEMORY_ABSTAIN_THRESHOLDS', 'MEMORY_ABSTAIN_DEFAULT', ':latest', 'uncalibrated'):
            self.assertIn(name, manual)


if __name__ == '__main__':
    unittest.main()
