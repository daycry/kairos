import uuid

import unittest
from unittest.mock import patch

from memory_platform.auth import Auth, hash_password, verify_password
from memory_platform.errors import Forbidden, MemoryError, NotFound, Unauthorized
from memory_platform.tests.test_store import create_core, event



class AuthTests(unittest.TestCase):

    def test_versioned_scrypt(self):
        first=hash_password('synthetic-password-123')
        second=hash_password('synthetic-password-123')
        assert first!=second
        assert verify_password('synthetic-password-123',first)
        assert not verify_password('wrong',first)


    def test_cookie_csrf_exact_origin_expiry_and_revocation(self):
        store,admin,pid=create_core()
        name='user-'+uuid.uuid4().hex
        store.create_user(admin,{'username':name,'password':'synthetic-password-123','project_ids':[pid],'scopes':['read']})
        auth=Auth(store,['https://memory.example'])
        login=auth.login(name,'synthetic-password-123','192.0.2.8')
        actor=auth.authenticate_session(login['session_token'])
        auth.require_csrf(actor,login['csrf_token'],'https://memory.example')
        for origin in ('https://memory.example.evil','https://memory.example/','null',None):
            with self.assertRaises(Forbidden):
                auth.require_csrf(actor,login['csrf_token'],origin)
        with self.assertRaises(Forbidden):
            auth.require_csrf(actor,'invalid','https://memory.example')
        auth.logout(login['session_token'])
        with self.assertRaises(Unauthorized):
            auth.authenticate_session(login['session_token'])
        with self.assertRaises(Unauthorized):
            store.list_notes(actor,pid)
        second=auth.login(name,'synthetic-password-123','192.0.2.8')
        with store.transaction() as c:
            c.execute("UPDATE memory.web_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(second['actor']['session_id'],))
        with self.assertRaises(Unauthorized):
            auth.authenticate_session(second['session_token'])


    def test_bearer_revocation_primary_and_foreign_scope(self):
        store,admin,pid=create_core()
        key=store.create_key(admin,{'name':'fixture','project_ids':[pid],'scopes':['read']})
        auth=Auth(store)
        actor=auth.authenticate_bearer(key['token'])
        with self.assertRaises(Forbidden):
            store.ingest_event(actor,event(pid))
        with self.assertRaises(NotFound):
            store.list_notes(actor,'foreign-project')
        store.revoke_key(admin,key['id'])
        with self.assertRaises(Unauthorized):
            auth.authenticate_bearer(key['token'])
        with self.assertRaises(Unauthorized):
            store.list_notes(actor,pid)


    def test_login_database_throttle(self):
        store,admin,pid=create_core()
        auth=Auth(store)
        username='missing-'+uuid.uuid4().hex
        ip='synthetic-'+uuid.uuid4().hex
        for _ in range(10):
            with self.assertRaises(Unauthorized):
                auth.login(username,'invalid',ip)
        with self.assertRaises(MemoryError) as caught:
            auth.login(username,'invalid',ip)
        assert caught.exception.status_code==429


class ResolverDelegationTests(unittest.TestCase):
    """The reads that decide an access live in the resolver of `store_auth.py` (CA-38 a, DC-1): the actor of a proven credential, the visible projects and the right to list keys."""

    def test_the_actor_of_a_proven_credential_is_described_by_the_resolver(self):
        store, admin, pid = create_core()
        token = store.create_key(admin, {'name': 'k', 'project_ids': [pid], 'scopes': ['read']})['token']
        with patch.object(store, '_describe', wraps=store._describe) as describe:
            actor = Auth(store).authenticate_bearer(token)
        describe.assert_called_once()
        self.assertEqual((actor['credential_type'], actor['project_ids'], actor['scopes'], actor['is_admin']), ('bearer', [pid], ['read'], False))

    def test_list_projects_asks_the_resolver_which_projects_the_caller_sees(self):
        store, admin, pid = create_core()
        with patch.object(store, '_visible_projects', wraps=store._visible_projects) as visible:
            projects = store.list_projects(admin)
        visible.assert_called_once()
        self.assertIn(pid, [p['id'] for p in projects])

    def test_list_keys_asks_the_resolver_whether_the_caller_administers_somewhere(self):
        store, admin, pid = create_core()
        reader = store.create_user(admin, {'username': 'reader-' + uuid.uuid4().hex[:10], 'password': 'synthetic-password-123', 'project_ids': [pid], 'scopes': ['read']})
        with patch.object(store, '_admin_somewhere', wraps=store._admin_somewhere) as somewhere:
            store.list_keys(admin)
            with self.assertRaises(Forbidden):
                store.list_keys({'id': reader['id'], 'credential_type': 'bootstrap'})
        self.assertEqual(somewhere.call_count, 2)
