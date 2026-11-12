"""Language-aware lexical search (Spanish/English with unaccent, `simple` kept) and the trigram fallback."""
import hashlib
import unittest
import uuid

from memory_platform.tests.test_store import create_core, event, extraction_receipt


def document(title, content, tags=None):
    return {'document_id': str(uuid.uuid4()), 'version': 1, 'title': title, 'content': content, 'tags': tags or ['fixture'],
            'source': {'uri': 'fixture://fts', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
            'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}}


def note(pid, title, content, **payload):
    return event(pid, generate=False, payload=dict({'title': title, 'content': content, 'source': {'uri': 'fixture://fts'}}, **payload))


class LanguageSearchTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.pid = create_core()

    def publish(self, title, content, tags=None):
        value = document(title, content, tags)
        self.store.publish_document(self.actor, self.pid, value)
        return value['document_id']

    def remember(self, title, content, **payload):
        value = note(self.pid, title, content, **payload)
        self.store.ingest_event(self.actor, value)
        return value['item_id']

    def test_ca19_spanish_query_without_accent_or_plural_finds_the_document(self):
        target = self.publish('Guía de ajustes', 'La configuración de las canciones se guarda en el servidor.')
        for title in ('Receta de pan', 'Tabla de precios', 'Notas de la reunión', 'Mapa del sitio', 'Registro de cambios', 'Glosario'):
            self.publish(title, f'Texto sin relación alguna número {title}.')
        found = [d['item_id'] for d in self.store.search_documents(self.actor, [self.pid], 'configuracion cancion', 5)]
        self.assertIn(target, found)
        self.assertEqual(found[0], target)

    def test_ca20_english_derived_forms_find_the_memory(self):
        target = self.remember('Release notes', 'Staging deployment failed after the rollout started.')
        for number in range(6):
            self.remember(f'Unrelated note {number}', f'Nothing about that topic here {number}.')
        found = [i['item_id'] for i in self.store.search_items(self.actor, [self.pid], 'deploying fails', 5)]
        self.assertIn(target, found)

    def test_query_with_accents_and_exact_words_keeps_working(self):
        target = self.remember('Configuración', 'La configuración del servidor.')
        self.assertEqual([i['item_id'] for i in self.store.search_items(self.actor, [self.pid], 'configuración servidor', 5)], [target])
        self.assertEqual([i['item_id'] for i in self.store.search_items(self.actor, [self.pid], 'CONFIGURACION', 5)], [target])

    def test_any_mode_uses_the_language_configurations_too(self):
        target = self.publish('Guía', 'La configuración de las canciones.')
        found = self.store.search_documents(self.actor, [self.pid], 'configuracion perros jirafas', 5, match_mode='any')
        self.assertEqual([d['item_id'] for d in found], [target])
        self.assertEqual(self.store.search_documents(self.actor, [self.pid], 'configuracion perros jirafas', 5, match_mode='all'), [])

    def test_results_stay_inside_the_requested_project(self):
        self.remember('Canciones', 'La configuración de las canciones.')
        other = self.pid + '-b'
        self.store.create_project(self.actor, {'id': other, 'title': 'Other'})
        self.store.set_policy(self.actor, other, {'capture_mode': 'summary', 'temporal_projection': False})
        hidden = self.store.ingest_event(self.actor, note(other, 'Canciones', 'Configuración privada de las canciones.'))
        found = self.store.search_items(self.actor, [self.pid], 'configuracion cancion', 5)
        self.assertEqual({i['project_id'] for i in found}, {self.pid})
        self.assertNotIn(hidden['item_id'], [i['item_id'] for i in found])

    def test_native_facts_find_a_query_without_accent(self):
        self.store.extraction_enabled = True  # this test needs the `extract` job: explicit opt-in to MEMORY_EXTRACT_ENABLED
        """CA-23 (native facts): before the change `configuracion` did not match `configuración`."""
        content = 'El servidor guarda la configuración de las canciones'
        original = event(self.pid, payload={'title': 'Servidor', 'content': content, 'source': {'uri': 'fixture://fts'}})
        accepted = self.store.ingest_event(self.actor, original)
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=7,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (accepted['jobs'][0],))
        receipt = extraction_receipt()
        receipt['payload']['facts'] = [{'subject': 'servidor', 'predicate': 'guarda', 'object': 'configuración', 'evidence_quote': content}]
        self.assertTrue(self.store.complete_job(accepted['jobs'][0], 7, receipt))
        self.assertEqual(len(self.store.search_native_facts(self.actor, [self.pid], 'configuracion')), 1)
        self.assertEqual(len(self.store.search_native_facts(self.actor, [self.pid], 'configuración')), 1)
        self.assertEqual(self.store.search_native_facts(self.actor, [self.pid], 'zzzunrelated'), [])

    def test_derived_and_event_items_store_both_language_vectors(self):
        self.store.extraction_enabled = True  # this test needs the `extract` job: explicit opt-in to MEMORY_EXTRACT_ENABLED
        """Both insert paths (events and extraction-derived items) write the language vectors themselves."""
        content = 'El servidor guarda la configuración de las canciones'
        accepted = self.store.ingest_event(self.actor, event(self.pid, payload={'title': 'Servidor', 'content': content, 'source': {'uri': 'fixture://fts'}}))
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=7,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (accepted['jobs'][0],))
            c.execute('ALTER TABLE memory.memory_items DISABLE TRIGGER item_fts_sync')
        try:
            receipt = extraction_receipt()
            receipt['payload']['content'] = 'Las canciones y la configuración'
            receipt['payload']['facts'][0]['evidence_quote'] = 'configuración de las canciones'
            self.assertTrue(self.store.complete_job(accepted['jobs'][0], 7, receipt))
            with self.store.transaction() as c:
                rows = c.execute('SELECT id,search_vector_es IS NOT NULL AS es,search_vector_en IS NOT NULL AS en FROM memory.memory_items WHERE project_id=%s', (self.pid,)).fetchall()
        finally:
            with self.store.transaction() as c:
                c.execute('ALTER TABLE memory.memory_items ENABLE TRIGGER item_fts_sync')
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['es'] and row['en'] for row in rows), rows)


class TrigramFallbackTests(unittest.TestCase):
    """CA-21: `pg_trgm` completes a short lexical answer with titles and identifiers that are close to the query."""

    def setUp(self):
        self.store, self.actor, self.pid = create_core()

    def remember(self, title, content='Texto sin relación.', project=None, **payload):
        value = note(project or self.pid, title, content, **payload)
        self.store.ingest_event(self.actor, value)
        return value['item_id']

    def ids(self, query, limit=5, **kwargs):
        return [i['item_id'] for i in self.store.search_items(self.actor, [self.pid], query, limit, **kwargs)]

    def test_ca21_misspelled_identifier_finds_the_memory(self):
        target = self.remember('pg_advisory_xact_lock', 'Takes a transaction level advisory lock.')
        for number in range(6):
            self.remember(f'Unrelated note {number}')
        found = self.store.search_items(self.actor, [self.pid], 'pg_advisroy_lock', 5)
        self.assertEqual([i['item_id'] for i in found], [target])
        self.assertEqual(found[0]['lexical_match'], 'trigram', 'a fallback hit must say so')

    def test_identifier_written_without_separators_or_in_camel_case_is_found(self):
        code = self.remember('Error code ERR-4471', 'Projection receipt hash mismatch.')
        setting = self.remember('Setting POOL_MAX_CONNS', 'Caps the pool.')
        self.remember('Ticket KB-20931', 'Retention exception.')
        self.assertEqual(self.ids('ERR4471'), [code])
        self.assertEqual(self.ids('PoolMaxConns'), [setting])

    def test_misspelled_words_of_a_title_are_found(self):
        target = self.remember('Kubernetes upgrade window', 'Opens on Tuesday night.')
        for number in range(4):
            self.remember(f'Another topic {number}')
        self.assertEqual(self.ids('kubernets upgarde windw'), [target])

    def test_unrelated_query_finds_nothing(self):
        self.remember('pg_advisory_xact_lock')
        self.assertEqual(self.ids('zzzunrelated'), [])

    def test_fallback_runs_only_when_the_lexical_answer_is_short(self):
        self.remember('advisory lock one', 'Mentions advisory.')
        self.remember('advisory lock two', 'Mentions advisory.')
        near = self.remember('advisery', 'Close to the query by trigram only.')
        full = self.store.search_items(self.actor, [self.pid], 'advisory', 2)
        self.assertEqual(len(full), 2)
        self.assertTrue(all('lexical_match' not in i for i in full), 'the answer was complete: no fallback hit may be added')
        self.assertNotIn(near, [i['item_id'] for i in full])
        short = self.store.search_items(self.actor, [self.pid], 'advisory', 3)
        self.assertEqual(len(short), 3)
        self.assertEqual(short[-1]['item_id'], near)
        self.assertEqual([i.get('lexical_match') for i in short], [None, None, 'trigram'])

    def test_fused_ranks_do_not_duplicate_a_hit_found_by_both_methods(self):
        both = self.remember('advisory lock', 'Mentions advisory locks.')
        found = self.ids('advisory lock', 5)
        self.assertEqual(found, [both])

    def test_fallback_stays_inside_authorized_projects_and_filters(self):
        mine = self.remember('pg_advisory_xact_lock', category='locks')
        self.remember('pg_advisory_lock_shared', category='other')
        other = self.pid + '-b'
        self.store.create_project(self.actor, {'id': other, 'title': 'Other'})
        self.store.set_policy(self.actor, other, {'capture_mode': 'summary', 'temporal_projection': False})
        hidden = self.remember('pg_advisory_xact_lock', project=other)
        found = self.store.search_items(self.actor, [self.pid], 'pg_advisroy_lock', 10)
        self.assertNotIn(hidden, [i['item_id'] for i in found])
        self.assertEqual({i['project_id'] for i in found}, {self.pid})
        self.assertEqual(self.ids('pg_advisroy_lock', 10, categories=['locks']), [mine])
        self.assertEqual(self.ids('pg_advisroy_lock', 10, exclude_categories=['locks', 'other']), [])

    def test_withdrawn_and_superseded_items_are_not_returned_by_the_fallback(self):
        old = note(self.pid, 'pg_advisory_xact_lock', 'Old text.')
        self.store.ingest_event(self.actor, old)
        gone = dict(old, event_id=str(uuid.uuid4()), version=2, event_type='delete')
        self.store.ingest_event(self.actor, gone)
        self.assertEqual(self.ids('pg_advisroy_lock'), [])

    def test_documents_use_the_same_fallback(self):
        value = document('pg_advisory_xact_lock', 'Takes a transaction level advisory lock.')
        self.store.publish_document(self.actor, self.pid, value)
        found = self.store.search_documents(self.actor, [self.pid], 'pg_advisroy_lock', 5)
        self.assertEqual([d['item_id'] for d in found], [value['document_id']])
        self.assertEqual(found[0]['lexical_match'], 'trigram')
        self.assertIn(found[0]['index_status'], ('pending', 'ready'))

    def test_short_words_do_not_trigger_the_fallback(self):
        """A word of 1-2 characters shares a trigram with about half of the titles: no fallback for such queries."""
        self.remember('abc', 'Three letters.')
        self.assertEqual(self.ids('abd'), [self.ids('abd')[0]], 'control: three characters do use the fallback')
        self.assertEqual(self.ids('ab'), [])
        self.assertEqual(self.ids('a b'), [])
        from memory_platform.store_common import trigram_wanted
        self.assertFalse(trigram_wanted('ab cd', 0, 5))
        self.assertFalse(trigram_wanted('', 0, 5))
        self.assertFalse(trigram_wanted('abc', 5, 5))
        self.assertTrue(trigram_wanted('ab abc', 0, 5))

    def test_bounded_fallback_times_out_cleanly_and_restores_the_setting(self):
        from unittest.mock import patch
        from memory_platform import store_documents
        with self.store.transaction() as c:
            before = c.execute("SELECT current_setting('statement_timeout') AS v").fetchone()['v']
            with patch.object(store_documents, 'TRIGRAM_FALLBACK_MS', 50):
                self.assertEqual(store_documents.bounded_fallback(c, lambda: c.execute('SELECT pg_sleep(2)').fetchall()), ([], True))
                self.assertEqual(c.execute("SELECT current_setting('statement_timeout') AS v").fetchone()['v'], before)
                self.assertEqual(store_documents.bounded_fallback(c, lambda: c.execute('SELECT 7 AS n').fetchall()), ([{'n': 7}], False))
                self.assertEqual(c.execute("SELECT current_setting('statement_timeout') AS v").fetchone()['v'], before)

    def test_timeout_returns_the_lexical_rows_and_says_so(self):
        from unittest.mock import patch
        from memory_platform import store_documents
        lexical = self.remember('advisory lock', 'Mentions advisory locks.')
        self.remember('advisery', 'Near by trigram only.')
        slow = lambda c, *args: store_documents.bounded_fallback(c, lambda: c.execute('SELECT pg_sleep(2)').fetchall())
        with patch.object(store_documents, 'TRIGRAM_FALLBACK_MS', 50), patch.object(store_documents, 'trigram_items', slow), patch.object(store_documents, 'trigram_documents', slow):
            items = self.store.search_items(self.actor, [self.pid], 'advisory', 5)
            documents = self.store.search_documents(self.actor, [self.pid], 'advisory', 5)
        self.assertEqual([i['item_id'] for i in items], [lexical])
        self.assertTrue(items.fuzzy_timed_out)
        self.assertTrue(documents.fuzzy_timed_out)
        normal = self.store.search_items(self.actor, [self.pid], 'advisory', 5)
        self.assertEqual(len(normal), 2)
        self.assertFalse(normal.fuzzy_timed_out)

    def test_graph_nodes_never_come_from_the_fallback(self):
        self.remember('pg_advisory_xact_lock', 'Takes a transaction level advisory lock.')
        near = self.store.search_items(self.actor, [self.pid], 'pg_advisroy_lock', 5)
        self.assertEqual([i['lexical_match'] for i in near], ['trigram'])
        graph = self.store.graph_data(self.actor, {'project_ids': [self.pid], 'q': 'pg_advisroy_lock', 'limit': 50})
        self.assertEqual(graph['nodes'], [])

    def test_search_statements_do_not_fetch_the_tsvector_columns(self):
        from contextlib import contextmanager
        self.remember('pg_advisory_xact_lock', 'Takes a lock.')
        self.store.publish_document(self.actor, self.pid, document('pg_advisory_xact_lock', 'Takes a lock.'))
        statements = []
        original = self.store.transaction

        @contextmanager
        def spied():
            with original() as connection:
                class Spy:
                    def execute(_, query, params=None, **kw):
                        statements.append(str(query))
                        return connection.execute(query, params, **kw) if params is not None else connection.execute(query, **kw)

                    def __getattr__(_, name):
                        return getattr(connection, name)
                yield Spy()
        from unittest.mock import patch
        with patch.object(self.store, 'transaction', spied):
            self.store.search_items(self.actor, [self.pid], 'pg_advisroy_lock', 5)
            self.store.search_documents(self.actor, [self.pid], 'pg_advisroy_lock', 5)
        selects = [s for s in statements if 'memory.memory_items' in s or 'memory.documents' in s]
        self.assertGreaterEqual(len(selects), 4)
        for statement in selects:
            projection = statement[:statement.index(' FROM ')]
            self.assertNotIn('*', projection, statement[:120])  # no `SELECT *`/`d.*`: the three tsvectors stay in the database


if __name__ == '__main__':
    unittest.main()
