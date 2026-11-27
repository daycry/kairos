"""Store mixin: migration, actors, projects, policy, users and keys."""
import secrets
from contextlib import nullcontext
from pathlib import Path

from psycopg import errors as pg_errors

from .config import migration_maintenance_work_mem
from .auth import KEY_EXPIRY_MAX, SCOPES, token_hash
from .passwords import check_length, hash_password
from .errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from .auth_scope import _cached, _identity, invalidate_auth
from .store_common import as_dict, canonical, new_id, clean


def _load_active(c, actor):
    if not actor or not actor.get('id'):
        raise Unauthorized()
    row = c.execute('SELECT * FROM memory.actors WHERE id=%s AND NOT disabled', (actor['id'],)).fetchone()
    if not row:
        raise Unauthorized()
    kind = actor.get('credential_type')
    if kind == 'bearer':
        key = c.execute('SELECT * FROM memory.api_keys WHERE id=%s AND actor_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())', (actor.get('key_id'), actor['id'])).fetchone()
        if not key:
            raise Unauthorized()
        return row, key
    if kind == 'session':
        if not c.execute('SELECT 1 FROM memory.web_sessions WHERE id=%s AND actor_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (actor.get('session_id'), actor['id'])).fetchone():
            raise Unauthorized()
    elif kind != 'bootstrap':
        raise Unauthorized()
    return row, None


class AuthMixin:
    def migrate(self):
        with self.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(688090884123)')
            # HNSW builds need memory; parallel builds need /dev/shm (64 MB in a default container), so build serially.
            c.execute("SELECT set_config('maintenance_work_mem',%s,true), set_config('max_parallel_maintenance_workers','0',true)",(migration_maintenance_work_mem(),))
            c.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
            from .store_vectors import migrate_vector_indexes
            migrate_vector_indexes(c)
            from .agent_store import migrate_agent_schema
            migrate_agent_schema(c)
            from .extended_store import migrate_extended_schema
            migrate_extended_schema(c)
            from .corpus_answers import migrate_corpus_answers
            migrate_corpus_answers(c)

    def bootstrap_user(self, username, password):
        hashed = hash_password(password)
        with self.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(688090884124)')
            if c.execute('SELECT 1 FROM memory.actors LIMIT 1').fetchone():
                raise Conflict('Bootstrap has already been completed')
            row = c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true) RETURNING id,username,is_admin', (new_id(), username, hashed)).fetchone()
            invalidate_auth(c)
        return dict(row, scopes=sorted(SCOPES), project_ids=[], credential_type='bootstrap')

    def _active(self, c, actor):
        if not actor or not actor.get('id'):
            raise Unauthorized()
        return _cached(c, ('active',) + _identity(actor), lambda: _load_active(c, actor))

    def _global_admin(self, c, actor):
        row, key = self._active(c, actor)
        if not row['is_admin'] or key:
            raise Forbidden()

    def _require(self, c, actor, project_id, permission):
        row, key = self._active(c, actor)
        if key and project_id not in key['project_ids']:
            raise NotFound()
        if row['is_admin'] and not key:
            if not _cached(c, ('exists', project_id), lambda: c.execute('SELECT 1 FROM memory.projects WHERE id=%s', (project_id,)).fetchone() is not None):
                raise NotFound()
            return
        grants = set(_cached(c, ('grants', actor['id'], project_id), lambda: frozenset(r['permission'] for r in c.execute('SELECT permission FROM memory.project_grants WHERE actor_id=%s AND project_id=%s', (actor['id'], project_id)).fetchall())))
        # A key issued by the bootstrap actor is bounded by its explicit scope/project list.
        if row['is_admin'] and key:
            grants = set(SCOPES)
        if not grants:
            raise NotFound()
        allowed = grants if not key else grants.intersection(key['scopes'])
        if permission not in allowed and 'admin' not in allowed:
            raise Forbidden()

    def _describe(self, c, row, credential_type, credential_id=None):
        """The actor of a credential just proven (`Auth` calls it after finding the token): its permissions and projects."""
        grants = c.execute('SELECT project_id,permission FROM memory.project_grants WHERE actor_id=%s', (row['id'],)).fetchall()
        actor = {'id': row['id'], 'username': row['username'], 'is_admin': row['is_admin'], 'credential_type': credential_type,
                 'scopes': sorted(SCOPES if row['is_admin'] else {g['permission'] for g in grants}),
                 'project_ids': sorted({g['project_id'] for g in grants}), 'grants': grants}
        if credential_type == 'bearer':
            key = c.execute('SELECT * FROM memory.api_keys WHERE id=%s', (credential_id,)).fetchone()
            actor.update(is_admin=False, key_id=credential_id, scopes=key['scopes'], project_ids=key['project_ids'],
                         key={'id': key['id'], 'name': key['name'], 'prefix': key['prefix'], 'expires_at': key['expires_at'].isoformat() if key['expires_at'] else None})
        else:
            actor['session_id'] = credential_id
        actor['permissions'] = actor['scopes']
        return actor

    def _visible_projects(self, c, actor):
        """The project rows the caller sees (before the page limit): all of them for an administrator without key, the key's for an administrator's key, else the granted ones."""
        row, key = self._active(c, actor)
        if row['is_admin'] and not key:
            return c.execute('SELECT * FROM memory.projects ORDER BY id').fetchall()
        if row['is_admin']:
            return c.execute('SELECT * FROM memory.projects WHERE id=ANY(%s) ORDER BY id', (key['project_ids'],)).fetchall()
        rows = c.execute('SELECT DISTINCT p.* FROM memory.projects p JOIN memory.project_grants g ON g.project_id=p.id WHERE g.actor_id=%s ORDER BY p.id', (actor['id'],)).fetchall()
        return [r for r in rows if r['id'] in key['project_ids']] if key else rows

    def _admin_somewhere(self, c, actor):
        """Whether the caller may list keys: raises Forbidden unless it administers a project. Returns (key, every_key): `every_key` is true for an administrator without key."""
        row, key = self._active(c, actor)
        if key and 'admin' not in key['scopes']:
            raise Forbidden()
        if not row['is_admin'] and not c.execute("SELECT 1 FROM memory.project_grants WHERE actor_id=%s AND permission='admin' LIMIT 1", (actor['id'],)).fetchone():
            raise Forbidden()
        return key, bool(row['is_admin']) and not key

    def require_permission(self, actor, project_id, permission):
        with self.transaction() as c:
            self._require(c, actor, project_id, permission)

    def _audit(self, c, actor, action, project_id=None, resource_id=None):
        c.execute('INSERT INTO memory.audit_events(actor_id,action,project_id,resource_id) VALUES(%s,%s,%s,%s)', (actor['id'], action, project_id, resource_id))

    def list_projects(self, actor):
        with self.transaction() as c:
            rows = self._visible_projects(c, actor)[:100]
            metadata = c.execute("""SELECT p.id,
                (SELECT count(*) FROM memory.memory_items i WHERE i.project_id=p.id AND NOT i.deleted AND i.superseded_by IS NULL) AS notes,
                (SELECT count(*) FROM memory.documents d WHERE d.project_id=p.id AND NOT d.deleted) AS documents,
                (SELECT count(*) FROM memory.sessions s WHERE s.project_id=p.id) AS sessions,
                (SELECT count(*) FROM memory.jobs j WHERE j.project_id=p.id) AS jobs,
                ARRAY(SELECT category FROM (
                    SELECT i.payload->>'category' AS category FROM memory.memory_items i WHERE i.project_id=p.id AND NOT i.deleted AND i.superseded_by IS NULL
                    UNION SELECT d.body->>'category' AS category FROM memory.documents d WHERE d.project_id=p.id AND NOT d.deleted
                ) categories WHERE category IS NOT NULL AND category<>'' ORDER BY category LIMIT 100) AS categories
                FROM memory.projects p WHERE p.id=ANY(%s)""",([r['id'] for r in rows],)).fetchall()
            indexed = {m['id']:m for m in metadata}
        return [dict(id=r['id'],title=r['title'],categories=indexed[r['id']]['categories'],counts={name:indexed[r['id']][name] for name in ('notes','documents','sessions','jobs')},**r['policy']) for r in rows]

    def create_project(self, actor, project):
        p = as_dict(project)
        with self.transaction() as c:
            self._global_admin(c, actor)
            if c.execute('SELECT 1 FROM memory.projects WHERE id=%s', (p['id'],)).fetchone():
                raise Conflict('Project already exists')
            policy = {'capture_mode': 'off', 'temporal_projection': False}
            c.execute('INSERT INTO memory.projects(id,title,policy,mapping) VALUES(%s,%s,%s::jsonb,%s::jsonb)', (p['id'], p['title'], canonical(policy), '{}'))
            invalidate_auth(c)
            self._audit(c, actor, 'project.created', p['id'])
        return dict(id=p['id'], title=p['title'], **policy)

    def get_policy(self, actor, project_id):
        with self.transaction() as c:
            self._require(c, actor, project_id, 'read')
            return c.execute('SELECT policy FROM memory.projects WHERE id=%s', (project_id,)).fetchone()['policy']

    def capture_policy(self, actor, project_id):
        """One read transaction checks current access and capture consent."""
        with self.transaction() as c:
            self._require(c, actor, project_id, 'read')
            allowed = True
            try:
                self._require(c, actor, project_id, 'write')
            except (Forbidden, NotFound):
                allowed = False
            policy = c.execute('SELECT policy FROM memory.projects WHERE id=%s FOR SHARE', (project_id,)).fetchone()['policy']
            return {'project_id': project_id, 'capture_mode': policy['capture_mode'],
                    'capture_allowed': allowed and policy['capture_mode'] != 'off'}

    def set_policy(self, actor, project_id, policy):
        policy = as_dict(policy)
        if policy.get('capture_mode') not in {'off', 'summary', 'full'} or not isinstance(policy.get('temporal_projection'), bool):
            raise MemoryError('invalid_policy', 'Invalid capture policy', 422)
        with self.transaction() as c:
            self._require(c, actor, project_id, 'admin')
            c.execute('UPDATE memory.projects SET policy=%s::jsonb WHERE id=%s', (canonical(policy), project_id))
            invalidate_auth(c)
            self._audit(c, actor, 'policy.updated', project_id)
        return policy


    def _delegate(self, c, actor, projects, scopes):
        if not projects or not scopes or not set(scopes) <= SCOPES:
            raise Forbidden('Explicit projects and valid scopes are required')
        row, key = self._active(c, actor)
        if key and not set(scopes) <= set(key['scopes']):
            raise Forbidden('Cannot delegate scopes absent from this credential')
        for project in projects:
            self._require(c, actor, project, 'admin')
            for scope in scopes:
                self._require(c, actor, project, scope)

    def create_user(self, actor, user, slot=None):
        """Order of DC-5 / fix1 of the review of phase 2 (gap 2): 1) authorize and refuse a duplicate, in a transaction that derives nothing; 2) the slot of the gate (`slot`, a callable that
        returns a context manager: the route gives `passwords.GATE.hold(ip)`) and the derivation of the password, OUTSIDE any transaction; 3) the insert, in a transaction that authorizes and checks the
        duplicate AGAIN, because the permissions of the credential (or the username) may have changed while the password was derived. A credential that may not create users, or a taken name,
        costs no derivation and no slot of the gate."""
        data = as_dict(user)

        def may_create(c):  # 403/401 for a credential that may not delegate this, 409 for a username that exists; no derivation
            self._delegate(c, actor, data['project_ids'], data['scopes'])
            if c.execute('SELECT 1 FROM memory.actors WHERE username=%s', (data['username'],)).fetchone():
                raise Conflict('Username already exists')
        with self.transaction() as c:
            may_create(c)
        check_length(data['password'])
        with (slot or nullcontext)():
            password = hash_password(data['password'])
        try:
            with self.transaction() as c:
                # The row of the delegate is locked BEFORE it is authorized again (fix1 of the review of phase 3, gap 1; the pattern of `create_key`): a disabling of the delegate or a
                # replacement of its grants holds that row until it commits, so this waits for it and the check that follows (with the cache emptied) sees it: 401 or 403, nothing created.
                # If this creation gets there first, they wait for it and come after it; the user created stays (it was authorized when it committed; disabling the delegate or taking its
                # grants away does not undo the users it created), and the audit shows `user.created` before their event.
                if actor and actor.get('id'):
                    c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR SHARE', (actor['id'],))
                    invalidate_auth(c)
                may_create(c)
                aid = new_id()
                c.execute('INSERT INTO memory.actors(id,username,password_hash) VALUES(%s,%s,%s)', (aid, data['username'], password))
                for project in data['project_ids']:
                    for scope in data['scopes']:
                        c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (aid, project, scope))
                invalidate_auth(c)
                self._audit(c, actor, 'user.created', resource_id=aid)
        except pg_errors.UniqueViolation:  # two creations of the same name at once: the one that lost is a 409 as well
            raise Conflict('Username already exists') from None
        return {'id': aid, 'username': data['username'], 'project_ids': data['project_ids'], 'scopes': data['scopes']}

    def list_users(self, actor):
        with self.transaction() as c:
            self._global_admin(c, actor)
            users = c.execute('SELECT id,username FROM memory.actors ORDER BY username').fetchall()
            for user in users:
                grants = c.execute('SELECT project_id,permission FROM memory.project_grants WHERE actor_id=%s', (user['id'],)).fetchall()
                user.update(project_ids=sorted({g['project_id'] for g in grants}), scopes=sorted({g['permission'] for g in grants}))
            return users

    def create_key(self, actor, key):
        data = as_dict(key)
        token, kid = 'mp_'+secrets.token_urlsafe(48), new_id()
        with self.transaction() as c:
            # The row of the owner is locked BEFORE the credential is checked (fix2 of the review of phase 2, gap 1): the INSERT of the key only takes `FOR KEY SHARE` on it, which does not
            # conflict with the `UPDATE` of `admin set-password --revoke-keys`, so a key made in parallel would escape its `UPDATE api_keys`. `FOR SHARE` waits for that transaction and, once it
            # commits, the check below (a new statement, with the cache emptied) sees the session or the key revoked: 401. If this creation wins, `set-password` waits for it and revokes the new key.
            if actor and actor.get('id'):
                c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR SHARE', (actor['id'],))
                invalidate_auth(c)
            self._delegate(c, actor, data['project_ids'], data['scopes'])
            # An expiry is optional (P-03: without it the key never expires), must be in the future by the clock of the database and not later than KEY_EXPIRY_MAX (fix1 of the review of
            # phase 4, gap 5: it is judged before the value is loaded); it is judged AFTER the caller is authorized (403 first).
            judged = c.execute('SELECT %s::timestamptz<=clock_timestamp() AS past, %s::timestamptz>%s::timestamptz AS late', (data.get('expires_at'), data.get('expires_at'), KEY_EXPIRY_MAX)).fetchone()
            if judged['past']:
                raise MemoryError('invalid_key_expiry', 'The expiry of a key must be in the future', 422)
            if judged['late']:
                raise MemoryError('invalid_key_expiry', 'The expiry of a key must not be later than %s' % KEY_EXPIRY_MAX, 422)
            expires = c.execute('SELECT %s::timestamptz AS at', (data.get('expires_at'),)).fetchone()
            c.execute('INSERT INTO memory.api_keys(id,actor_id,name,token_hash,prefix,project_ids,scopes,expires_at) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)', (kid, actor['id'], data['name'], token_hash(token), token[:10], canonical(data['project_ids']), canonical(data['scopes']), expires['at']))
            invalidate_auth(c)
            self._audit(c, actor, 'key.created', resource_id=kid)
        return {'id': kid, 'name': data['name'], 'token': token, 'key': token, 'project_ids': data['project_ids'], 'scopes': data['scopes'],
                'expires_at': expires['at'].isoformat() if expires['at'] else None}

    def list_keys(self, actor):
        with self.transaction() as c:
            key, every_key = self._admin_somewhere(c, actor)
            if not every_key:
                rows = c.execute('SELECT id,name,prefix,project_ids,scopes,revoked_at,created_at,expires_at,last_used_at FROM memory.api_keys WHERE actor_id=%s ORDER BY created_at,id', (actor['id'],)).fetchall()
                if key:
                    rows = [r for r in rows if set(r['project_ids']) <= set(key['project_ids']) and set(r['scopes']) <= set(key['scopes'])]
                for r in rows:
                    for p in r['project_ids']:
                        self._require(c, actor, p, 'admin')
            else:
                rows = c.execute('SELECT id,name,prefix,project_ids,scopes,revoked_at,created_at,expires_at,last_used_at FROM memory.api_keys ORDER BY created_at,id').fetchall()
            return clean(rows)

    def revoke_key(self, actor, key_id):
        with self.transaction() as c:
            self._active(c, actor)
            row = c.execute('SELECT id,actor_id,project_ids FROM memory.api_keys WHERE id=%s', (key_id,)).fetchone()
            if not row:
                raise NotFound()
            # The caller is authorized WITHOUT any lock first (fix1 of the review of phase 4, gap 4): one that may not revoke the key never waits for, nor makes wait, the rows of its
            # owner. The 404 of an unknown id before the 403 of a key the caller may not revoke stays (gap 3: the policy of `revoke_key` does not change; the ids are random UUIDs).
            for project in row['project_ids']:
                self._require(c, actor, project, 'admin')
            # The rows of the OWNER of the key and of the caller, in the order of their ids (T-22; revision of phase 3, attempt 2, gap 1). `create_key`, `create_user` and
            # `rotate_key` take `FOR SHARE` on the row of their actor before they check the credential again: a creation in progress with this key makes the revocation wait
            # for it (what it created stays, it was authorized when it committed), and a creation that comes after the revocation waits for it and is refused with 401. The row of
            # the caller: the end of its own credential (a logout, a revocation, a disabling) waits for this revocation, or makes it wait and then refuse it with 401 (gap 6).
            c.execute('SELECT id FROM memory.actors WHERE id=ANY(%s) ORDER BY id FOR NO KEY UPDATE', ([actor['id'], row['actor_id']],))
            invalidate_auth(c)
            for project in row['project_ids']:  # again, after the waits
                self._require(c, actor, project, 'admin')
            c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE id=%s', (key_id,))
            invalidate_auth(c)
            self._audit(c, actor, 'key.revoked', resource_id=key_id)
        return {'id': key_id, 'revoked': True}
