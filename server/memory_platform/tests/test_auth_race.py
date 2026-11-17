"""Check, wait, check (CWE-367): a permission check that comes AFTER waiting for a lock must read the database again, not the answer the transaction cached before the wait.

Each test uses two connections. Transaction A (a thread, the call under test) resolves its permissions, then reaches a statement that waits (an advisory lock, `FOR UPDATE`); transaction B holds
that lock, revokes the key or withdraws a grant and COMMITS. A must answer 401/403 and write nothing. The test hooks the statement of A (`psycopg.Cursor.execute`) and signals before it runs,
so B commits after A's first check and before A's second one in either interleaving (A already blocked, or about to be); no test observes a state with a clock. The same walk of the package
that proves the ORDER (`test_auth_cache.WritersEmptyTheCacheTests`) and these two tests are the pair: remove an `invalidate_auth` after a lock and one of them fails (mutants in the ledger of T-30)."""
import threading
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from memory_platform.errors import Forbidden, Unauthorized
from memory_platform.tests.test_auth_cache import Fixture
from memory_platform.tests.test_store import event

A = 'race-A'


def validated(pid, **changes):
    payload = {'title': 'Validated note', 'content': 'Evidence backed', 'source': {'uri': 'fixture://race'}, 'validation_status': 'validated', 'evidence': ['e']}
    return event(pid, payload=payload, **changes)


class RaceFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.b = psycopg.connect(self.store.dsn, row_factory=dict_row)
        self.addCleanup(self.b.close)

    def race(self, call, waits, hold, revoke):
        """`call()` runs in thread A; `waits(sql, params)` picks the statement of A that waits; `hold(b)` takes the lock on B's connection; `revoke(b)` is B's revocation, committed after A signalled."""
        hold(self.b)
        reached, outcome, real = threading.Event(), {}, psycopg.Cursor.execute

        def execute(cursor, query, params=None, *args, **kwargs):
            if threading.current_thread().name == A and not reached.is_set() and waits(str(query), params):
                reached.set()
            return real(cursor, query, params, *args, **kwargs)

        def run():
            try:
                outcome['result'] = call()
            except BaseException as exc:  # reported by the caller
                outcome['error'] = exc
        with patch.object(psycopg.Cursor, 'execute', execute):
            thread = threading.Thread(target=run, name=A)
            thread.start()
            self.assertTrue(reached.wait(30), 'transaction A never reached the statement that waits')
            revoke(self.b)
            self.b.commit()
            thread.join(60)
        self.assertFalse(thread.is_alive())
        return outcome

    def count(self, sql, *params):
        with psycopg.connect(self.store.dsn, row_factory=dict_row) as c:
            return c.execute(sql, params).fetchone()['n']

    def revoke_key(self, key_id):
        return lambda b: b.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE id=%s', (key_id,))

    def drop_grant(self, user, permission):
        return lambda b: b.execute('DELETE FROM memory.project_grants WHERE actor_id=%s AND permission=%s', (user['id'], permission))

    def lock_advisory(self, name):
        return lambda b: b.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (name,))

    def lock_row(self, table, pid, iid):
        return lambda b: b.execute('SELECT 1 FROM memory.%s WHERE project_id=%%s AND id=%%s FOR UPDATE' % table, (pid, iid))


def item_wait(sql, params):
    return 'pg_advisory_xact_lock' in sql and str(params).startswith("('item:")


class IngestRaceTests(RaceFixture):
    def test_validated_ingest_that_waits_for_the_item_lock_sees_the_key_revoked_meanwhile(self):
        created, actor = self.key(scopes=('read', 'write', 'validate'))
        item = str(uuid.uuid4())
        outcome = self.race(lambda: self.store.ingest_event(actor, validated(self.pid, item_id=item)), item_wait,
                            self.lock_advisory('item:%s:%s' % (self.pid, item)), self.revoke_key(created['id']))
        self.assertIsInstance(outcome.get('error'), Unauthorized, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 0)

    def test_validated_ingest_that_waits_for_the_item_lock_sees_validate_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'write', 'validate'))
        item = str(uuid.uuid4())
        outcome = self.race(lambda: self.store.ingest_event(user, validated(self.pid, item_id=item)), item_wait,
                            self.lock_advisory('item:%s:%s' % (self.pid, item)), self.drop_grant(user, 'validate'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 0)

    def test_ingest_that_waits_for_the_item_lock_sees_write_revoked_meanwhile(self):
        created, actor = self.key(scopes=('read', 'write'))  # a plain event: no `validate` check follows, only the `write` of the start
        item = str(uuid.uuid4())
        outcome = self.race(lambda: self.store.ingest_event(actor, event(self.pid, item_id=item)), item_wait,
                            self.lock_advisory('item:%s:%s' % (self.pid, item)), self.revoke_key(created['id']))
        self.assertIsInstance(outcome.get('error'), Unauthorized, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 0)

    def test_ingest_that_waits_for_the_item_lock_sees_the_write_grant_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'write'))
        item = str(uuid.uuid4())
        outcome = self.race(lambda: self.store.ingest_event(user, event(self.pid, item_id=item)), item_wait,
                            self.lock_advisory('item:%s:%s' % (self.pid, item)), self.drop_grant(user, 'write'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 0)

    def seed(self):
        item = str(uuid.uuid4())
        self.store.ingest_event(self.admin, validated(self.pid, item_id=item))
        return item

    def test_an_update_of_a_validated_item_that_waits_for_its_row_sees_validate_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'write', 'validate'))
        item = self.seed()
        plain = event(self.pid, item_id=item, version=2)  # not marked validated: only `_protect_validated` asks for `validate`, after the row lock

        def waits(sql, params):
            return 'FROM memory.memory_items' in sql and 'FOR UPDATE' in sql and 'parent_item_id' not in sql
        outcome = self.race(lambda: self.store.ingest_event(user, plain), waits, self.lock_row('memory_items', self.pid, item), self.drop_grant(user, 'validate'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT version AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 1)

    def test_a_correction_whose_target_row_is_locked_sees_validate_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'write', 'validate'))
        target = self.seed()
        item = str(uuid.uuid4())
        # validated itself: the first `validate` check (cached) comes BEFORE the wait, `_protect_validated` of the target asks again AFTER it
        correction = validated(self.pid, item_id=item)
        correction['payload']['supersedes'] = target

        def waits(sql, params):
            return 'FOR UPDATE' in sql and 'NOT deleted' in sql and 'parent_item_id' not in sql
        outcome = self.race(lambda: self.store.ingest_event(user, correction), waits, self.lock_row('memory_items', self.pid, target), self.drop_grant(user, 'validate'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND id=%s', self.pid, item), 0)


class DocumentRaceTests(RaceFixture):
    def document(self, **changes):
        import hashlib
        return {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'T', 'content': 'C', 'source': {'uri': 'fixture://race', 'sha256': hashlib.sha256(b'C').hexdigest()},
                'validation': {'status': 'validated', 'evidence': ['e'], 'validated_by': 't'}, **changes}

    def test_publish_that_waits_for_the_document_lock_sees_validate_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'publish', 'validate'))
        data = self.document()
        outcome = self.race(lambda: self.store.publish_document(user, self.pid, data), lambda sql, params: 'pg_advisory_xact_lock' in sql,
                            self.lock_advisory('doc:%s:%s' % (self.pid, data['document_id'])), self.drop_grant(user, 'validate'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.documents WHERE project_id=%s AND id=%s', self.pid, data['document_id']), 0)

    def test_publish_that_waits_for_the_document_lock_sees_the_key_revoked_meanwhile(self):
        created, actor = self.key(scopes=('read', 'publish', 'validate'))
        data = self.document()
        outcome = self.race(lambda: self.store.publish_document(actor, self.pid, data), lambda sql, params: 'pg_advisory_xact_lock' in sql,
                            self.lock_advisory('doc:%s:%s' % (self.pid, data['document_id'])), self.revoke_key(created['id']))
        self.assertIsInstance(outcome.get('error'), Unauthorized, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.documents WHERE project_id=%s AND id=%s', self.pid, data['document_id']), 0)

    def test_delete_that_waits_for_the_document_row_sees_validate_withdrawn_meanwhile(self):
        user = self.user([self.pid], ('read', 'publish', 'validate'))
        data = self.document()
        self.store.publish_document(user, self.pid, data)

        def waits(sql, params):
            return 'FROM memory.documents' in sql and 'FOR UPDATE' in sql
        outcome = self.race(lambda: self.store.delete_document(user, self.pid, data['document_id'], 2), waits,
                            self.lock_row('documents', self.pid, data['document_id']), self.drop_grant(user, 'validate'))
        self.assertIsInstance(outcome.get('error'), Forbidden, outcome)
        self.assertEqual(self.count('SELECT count(*) AS n FROM memory.documents WHERE project_id=%s AND id=%s AND NOT deleted', self.pid, data['document_id']), 1)


class JobRaceTests(RaceFixture):
    def test_retry_that_waits_for_the_job_row_sees_the_key_revoked_meanwhile(self):
        created, actor = self.key(scopes=('read', 'write'))  # `_active` is resolved BEFORE the row lock (the cached answer), the grants only after it
        self.store.embedding_enabled = True
        jobs = self.store.ingest_event(self.admin, event(self.pid))['jobs']
        self.assertTrue(jobs)

        def lock(b):
            b.execute('SELECT 1 FROM memory.jobs WHERE id=%s FOR UPDATE', (jobs[0],))
        outcome = self.race(lambda: self.store.retry_job(actor, jobs[0]), lambda sql, params: 'FROM memory.jobs' in sql and 'FOR UPDATE' in sql, lock, self.revoke_key(created['id']))
        self.assertIsInstance(outcome.get('error'), Unauthorized, outcome)


if __name__ == '__main__':
    unittest.main()
