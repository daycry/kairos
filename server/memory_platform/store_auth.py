"""Store mixin: migration, actors, projects, policy, users and keys."""
import secrets
from pathlib import Path

from .config import migration_maintenance_work_mem
from .auth import SCOPES, hash_password, token_hash
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

    def require_permission(self, actor, project_id, permission):
        with self.transaction() as c:
            self._require(c, actor, project_id, permission)

    def _audit(self, c, actor, action, project_id=None, resource_id=None):
        c.execute('INSERT INTO memory.audit_events(actor_id,action,project_id,resource_id) VALUES(%s,%s,%s,%s)', (actor['id'], action, project_id, resource_id))

    def list_projects(self, actor):
        with self.transaction() as c:
            row, key = self._active(c, actor)
            if row['is_admin'] and not key:
                rows = c.execute('SELECT * FROM memory.projects ORDER BY id').fetchall()
            elif row['is_admin']:
                rows = c.execute('SELECT * FROM memory.projects WHERE id=ANY(%s) ORDER BY id', (key['project_ids'],)).fetchall()
            else:
                rows = c.execute('SELECT DISTINCT p.* FROM memory.projects p JOIN memory.project_grants g ON g.project_id=p.id WHERE g.actor_id=%s ORDER BY p.id', (actor['id'],)).fetchall()
                if key:
                    rows = [r for r in rows if r['id'] in key['project_ids']]
            rows = rows[:100]
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

    def create_user(self, actor, user):
        data = as_dict(user)
        password = hash_password(data['password'])
        with self.transaction() as c:
            self._delegate(c, actor, data['project_ids'], data['scopes'])
            if c.execute('SELECT 1 FROM memory.actors WHERE username=%s', (data['username'],)).fetchone():
                raise Conflict('Username already exists')
            aid = new_id()
            c.execute('INSERT INTO memory.actors(id,username,password_hash) VALUES(%s,%s,%s)', (aid, data['username'], password))
            for project in data['project_ids']:
                for scope in data['scopes']:
                    c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (aid, project, scope))
            invalidate_auth(c)
            self._audit(c, actor, 'user.created', resource_id=aid)
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
            self._delegate(c, actor, data['project_ids'], data['scopes'])
            c.execute('INSERT INTO memory.api_keys(id,actor_id,name,token_hash,prefix,project_ids,scopes) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)', (kid, actor['id'], data['name'], token_hash(token), token[:10], canonical(data['project_ids']), canonical(data['scopes'])))
            invalidate_auth(c)
            self._audit(c, actor, 'key.created', resource_id=kid)
        return {'id': kid, 'name': data['name'], 'token': token, 'key': token, 'project_ids': data['project_ids'], 'scopes': data['scopes']}

    def list_keys(self, actor):
        with self.transaction() as c:
            row, key = self._active(c, actor)
            if key and 'admin' not in key['scopes']:
                raise Forbidden()
            if not row['is_admin'] and not c.execute("SELECT 1 FROM memory.project_grants WHERE actor_id=%s AND permission='admin' LIMIT 1",(actor['id'],)).fetchone():
                raise Forbidden()
            if key or not row['is_admin']:
                rows = c.execute('SELECT id,name,prefix,project_ids,scopes,revoked_at,created_at FROM memory.api_keys WHERE actor_id=%s ORDER BY created_at,id', (actor['id'],)).fetchall()
                if key:
                    rows = [r for r in rows if set(r['project_ids']) <= set(key['project_ids']) and set(r['scopes']) <= set(key['scopes'])]
                for r in rows:
                    for p in r['project_ids']:
                        self._require(c, actor, p, 'admin')
            else:
                rows = c.execute('SELECT id,name,prefix,project_ids,scopes,revoked_at,created_at FROM memory.api_keys ORDER BY created_at,id').fetchall()
            return clean(rows)

    def revoke_key(self, actor, key_id):
        with self.transaction() as c:
            self._active(c, actor)
            row = c.execute('SELECT id,project_ids FROM memory.api_keys WHERE id=%s', (key_id,)).fetchone()
            if not row:
                raise NotFound()
            for project in row['project_ids']:
                self._require(c, actor, project, 'admin')
            c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE id=%s', (key_id,))
            invalidate_auth(c)
            self._audit(c, actor, 'key.revoked', resource_id=key_id)
        return {'id': key_id, 'revoked': True}
