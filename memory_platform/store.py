"""Transactional Postgres canon. Connections are short-lived; providers never run here."""
import hashlib
import base64
import json
import math
import bisect
import time
import secrets
import uuid
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .auth import SCOPES, hash_password, token_hash
from .errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from .privacy import has_sensitive,sanitize_payload


def as_dict(value):
    return value.model_dump(mode='json', exclude_none=True) if hasattr(value, 'model_dump') else dict(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def new_id():
    return str(uuid.uuid4())

def lexical_query(q, match_mode):
    if match_mode == 'all':
        return 'plainto_tsquery',q
    if match_mode != 'any':
        raise MemoryError('invalid_query_mode','Unsupported lexical query mode',422)
    return 'websearch_to_tsquery',' OR '.join(re.findall(r'\w+',q,flags=re.UNICODE)[:64])


def clean(value):
    """Convert database UUID/datetime values without leaking internal row objects."""
    return json.loads(json.dumps(value, default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)))


class Store:
    def __init__(self, dsn, project_maps=None, embedding_enabled=False):
        self.dsn = dsn
        self.project_maps = project_maps or {}
        self.embedding_enabled = embedding_enabled

    @contextmanager
    def transaction(self):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            with connection.transaction():
                yield connection

    def migrate(self):
        with self.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(688090884123)')
            c.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
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
        return dict(row, scopes=sorted(SCOPES), project_ids=[], credential_type='bootstrap')

    def _active(self, c, actor):
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

    def _global_admin(self, c, actor):
        row, key = self._active(c, actor)
        if not row['is_admin'] or key:
            raise Forbidden()

    def _require(self, c, actor, project_id, permission):
        row, key = self._active(c, actor)
        if key and project_id not in key['project_ids']:
            raise NotFound()
        if row['is_admin'] and not key:
            if not c.execute('SELECT 1 FROM memory.projects WHERE id=%s', (project_id,)).fetchone():
                raise NotFound()
            return
        grants = {r['permission'] for r in c.execute('SELECT permission FROM memory.project_grants WHERE actor_id=%s AND project_id=%s', (actor['id'], project_id)).fetchall()}
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
            self._audit(c, actor, 'key.revoked', resource_id=key_id)
        return {'id': key_id, 'revoked': True}

    def _jobs(self, c, project_id, item_id, version, content_hash, resource_type, destinations, operation, *, embed=True):
        destinations=set(destinations).intersection({'extract','embed'})-({'embed'} if operation=='delete' else set())
        if self.embedding_enabled and embed and operation=='upsert':
            destinations.add('embed')
        ids = []
        for destination in sorted(destinations):
            jid = new_id()
            c.execute('INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)', (jid, project_id, item_id, version, content_hash, resource_type, destination, operation))
            ids.append(jid)
        return sorted(ids)

    def _protect_validated(self,c,actor,project_id,item_id,current):
        protected=bool(current and current['payload'].get('validation_status')=='validated')
        children=c.execute('SELECT payload FROM memory.memory_items WHERE project_id=%s AND parent_item_id=%s AND NOT deleted FOR UPDATE',(project_id,item_id)).fetchall()
        protected=protected or any(child['payload'].get('validation_status')=='validated' for child in children)
        if protected:
            self._require(c,actor,project_id,'validate')

    def _validate_facts(self,payload,source,include_payload_context=True):
        facts=payload.get('facts',[])
        if not isinstance(facts,list) or len(facts)>30:
            raise MemoryError('invalid_facts','At most 30 grounded facts are permitted',422)
        if include_payload_context:
            source='\n'.join([source,payload.get('problem',''),payload.get('correction','')])
        for fact in facts:
            if not isinstance(fact,dict):
                raise MemoryError('invalid_facts','Invalid grounded fact',422)
            for field,limit in (('subject',300),('predicate',200),('object',2000),('evidence_quote',4000)):
                if not isinstance(fact.get(field),str) or not 1<=len(fact[field])<=limit:
                    raise MemoryError('invalid_facts','Invalid grounded fact',422)
            if fact['evidence_quote'] not in source:
                raise MemoryError('invalid_evidence','Fact evidence must quote its source literally',422)
            dates=[]
            for name in ('valid_from','valid_until'):
                value=fact.get(name)
                if value:
                    try:
                        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
                        if parsed.tzinfo is None:
                            raise ValueError()
                    except (ValueError,TypeError):
                        raise MemoryError('invalid_validity','Fact validity requires timezone-aware timestamps',422) from None
                    dates.append(parsed)
            if len(dates)==2 and dates[1]<dates[0]:
                raise MemoryError('invalid_validity','Fact validity interval is reversed',422)

    def _materialize_extract(self,c,row,receipt):
        payload,_=sanitize_payload(dict(receipt.get('payload',{})))
        if has_sensitive(payload):
            raise MemoryError('sensitive_source_requires_review','Generated capture metadata requires privacy review',422)
        if not isinstance(payload.get('title'),str) or not isinstance(payload.get('content'),str) or len(payload['title'])>500 or len(payload['content'])>100000:
            raise MemoryError('invalid_extraction','Extraction must contain a bounded title and content',422)
        parent=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND id=%s FOR SHARE',(row['project_id'],row['item_id'])).fetchone()
        if not parent or parent['deleted'] or parent['superseded_by']:
            return None
        source=parent['payload']
        self._validate_facts(payload,'\n'.join(source.get(name,'') for name in ('content','problem','correction')),False)
        payload.pop('supersedes',None)
        payload.pop('validated_by',None)
        payload['validation_status']='unverified'
        payload['source']=source.get('source',{'uri':f"memory://{row['project_id']}/{row['item_id']}"})
        payload['provenance']={'parent_item_id':row['item_id'],'parent_version':row['version'],'parent_hash':row['canonical_hash'],'input_hash':receipt.get('input_hash'),'model':receipt.get('model'),'prompt_version':receipt.get('prompt_version')}
        derived_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'memory-extract:'+row['project_id']+':'+row['item_id']))
        old=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND id=%s FOR UPDATE',(row['project_id'],derived_id)).fetchone()
        if old and old['parent_item_id']!=row['item_id']:
            raise Conflict('Derived memory identifier is already allocated')
        # A validated derived version cannot be overwritten by a repeated model result.
        if old and old['payload'].get('validation_status')=='validated' and not old['deleted']:
            return derived_id
        version=old['version']+1 if old else 1
        body={'item_id':derived_id,'project_id':row['project_id'],'version':version,'event_type':'learning','session_id':parent['session_id'],'agent_id':parent['agent_id'],'occurred_at':clean(parent['occurred_at']),'payload':payload}
        content_hash=digest(body)
        c.execute("INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,deleted,search_vector,parent_item_id,parent_version,parent_hash) VALUES(%s,%s,%s,%s,'learning',%s::jsonb,%s,%s,%s,false,setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'B'),%s,%s,%s) ON CONFLICT(project_id,id) DO UPDATE SET version=EXCLUDED.version,canonical_hash=EXCLUDED.canonical_hash,payload=EXCLUDED.payload,deleted=false,superseded_by=NULL,occurred_at=EXCLUDED.occurred_at,search_vector=EXCLUDED.search_vector,parent_version=EXCLUDED.parent_version,parent_hash=EXCLUDED.parent_hash",(row['project_id'],derived_id,version,content_hash,canonical(payload),parent['session_id'],parent['agent_id'],parent['occurred_at'],payload['title']+' '+payload.get('problem','')+' '+payload.get('correction',''),payload['content'],row['item_id'],row['version'],row['canonical_hash']))
        c.execute('INSERT INTO memory.item_versions VALUES(%s,%s,%s,%s,%s::jsonb)',(row['project_id'],derived_id,version,content_hash,canonical(body)))
        jobs=self._jobs(c,row['project_id'],derived_id,version,content_hash,'item',[],'upsert')
        generation_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'memory-generation-event:'+row['project_id']+':'+row['item_id']+':'+str(row['version'])))
        generation_body=dict(body,event_id=generation_id,generate=False)
        generation_receipt={'event_id':generation_id,'item_id':derived_id,'version':version,'status':'accepted','jobs':jobs}
        c.execute('INSERT INTO memory.events(id,project_id,canonical_hash,body,receipt) VALUES(%s,%s,%s,%s::jsonb,%s::jsonb)',(generation_id,row['project_id'],digest(generation_body),canonical(generation_body),canonical(generation_receipt)))
        c.execute("INSERT INTO memory.audit_events(action,project_id,resource_id) VALUES('memory.generated',%s,%s)",(row['project_id'],derived_id))
        return derived_id

    def ingest_event(self, actor, event):
        fingerprint_payload = event.payload.model_dump(mode='json',exclude_unset=True,exclude_none=True) if hasattr(event,'model_dump') else event['payload']
        event = as_dict(event)
        event.setdefault('generate',False)
        capture = event.get('capture')
        auto_mode = None
        if capture:
            expected = digest({'project': event['project_id'], 'runtime': event['agent_id'],
                               'session': event['session_id'], 'event': capture['hook_event'], 'payload': fingerprint_payload})
            if capture.get('fingerprint') != expected or capture.get('mode') not in {'summary','full'}:
                raise MemoryError('invalid_capture_fingerprint', 'Automatic capture identity differs from its content', 422)
            auto_mode = capture['mode']
        legacy_modes = {tag.removeprefix('capture:') for tag in event['payload'].get('tags', []) if tag in {'capture:full','capture:summary'}}
        if len(legacy_modes)>1 or auto_mode and legacy_modes and legacy_modes != {auto_mode}:
            raise MemoryError('invalid_capture_mode', 'Automatic capture mode is ambiguous', 422)
        auto_mode = auto_mode or next(iter(legacy_modes),None)
        if auto_mode == 'summary':
            try:
                body = json.loads(event['payload'].get('content',''))
            except (ValueError,TypeError):
                raise MemoryError('invalid_capture_summary','Automatic summaries require structured content',422) from None
            if not isinstance(body,dict) or not body or set(body)-{'tool','status','exit_code','event','source','detail','summary'} or any(isinstance(value,(dict,list)) for value in body.values()):
                raise MemoryError('invalid_capture_summary','Raw automatic input requires full consent',422)
        event['event_id'], event['item_id'] = str(uuid.UUID(str(event['event_id']))), str(uuid.UUID(str(event['item_id'])))
        occurred = datetime.fromisoformat(str(event['occurred_at']).replace('Z', '+00:00'))
        if occurred.tzinfo is None:
            raise MemoryError('invalid_time', 'Timezone is required', 422)
        event['occurred_at'] = occurred.astimezone(timezone.utc).isoformat()
        payload = event['payload'] = dict(event['payload'])
        try:
            payload,redacted=sanitize_payload(payload)
        except MemoryError as exc:
            if payload.get('validation_status')=='validated' and exc.code in {'invalid_private_block','invalid_private_key_block'}:
                raise MemoryError('sensitive_source_requires_review','Validated sources require privacy review before capture',422) from None
            raise
        if redacted and payload.get('validation_status')=='validated':
            raise MemoryError('sensitive_source_requires_review','Validated sources require privacy review before capture',422)
        if has_sensitive(payload):
            raise MemoryError('sensitive_source_requires_review','Sensitive capture metadata requires privacy review',422)
        event['payload']=payload
        if has_sensitive({'session_id':event.get('session_id'),'agent_id':event.get('agent_id')}):
            raise MemoryError('sensitive_source_requires_review','Sensitive capture metadata requires privacy review',422)
        payload.setdefault('facts',[])
        if payload.get('supersedes'):
            payload['supersedes'] = str(uuid.UUID(str(payload['supersedes'])))
        content_hash, pid, iid = digest(event), event['project_id'], event['item_id']
        # Keep the immutable normalized event identical to the bytes hashed above;
        # authenticated enrichment belongs to the current-view payload and audit.
        payload = dict(payload)
        with self.transaction() as c:
            self._require(c, actor, pid, 'write')
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('event:'+event['event_id'],))
            previous = c.execute('SELECT * FROM memory.events WHERE id=%s', (event['event_id'],)).fetchone()
            if previous:
                if previous['project_id'] != pid:
                    raise NotFound()
                if previous['canonical_hash'] != content_hash:
                    raise Conflict()
                return previous['receipt']
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('item:'+pid+':'+iid,))
            project = c.execute('SELECT * FROM memory.projects WHERE id=%s FOR SHARE', (pid,)).fetchone()
            if project['policy']['capture_mode'] == 'off' and event['event_type'] != 'delete':
                raise Forbidden('Capture is disabled for this project')
            if auto_mode == 'full' and project['policy']['capture_mode'] != 'full' and event['event_type'] != 'delete':
                raise Forbidden('Full automatic capture is disabled for this project')
            if payload.get('validation_status') == 'validated':
                self._require(c, actor, pid, 'validate')
                if not payload.get('evidence'):
                    raise MemoryError('evidence_required', 'Validation requires evidence', 422)
                payload['validated_by'] = actor['id']
            current = c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND id=%s FOR UPDATE', (pid, iid)).fetchone()
            self._protect_validated(c,actor,pid,iid,current)
            if event['version'] != (current['version']+1 if current else 1) or (current and current['deleted']):
                raise Conflict()
            supersedes = payload.get('supersedes')
            if supersedes:
                target=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND id=%s AND NOT deleted FOR UPDATE', (pid, supersedes)).fetchone()
                if supersedes == iid or not target:
                    raise Conflict('Correction target must be a live item in the same project')
                self._protect_validated(c,actor,pid,supersedes,target)
                c.execute('UPDATE memory.memory_items SET superseded_by=%s WHERE project_id=%s AND id=%s', (iid, pid, supersedes))
                c.execute('UPDATE memory.memory_items SET deleted=true WHERE project_id=%s AND parent_item_id=%s',(pid,supersedes))
            deleted = event['event_type'] == 'delete'
            self._validate_facts(payload,payload.get('content',''))
            c.execute('UPDATE memory.memory_items SET deleted=true WHERE project_id=%s AND parent_item_id=%s',(pid,iid))
            c.execute("INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,deleted,search_vector) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'B')) ON CONFLICT(project_id,id) DO UPDATE SET version=EXCLUDED.version,canonical_hash=EXCLUDED.canonical_hash,event_type=EXCLUDED.event_type,payload=EXCLUDED.payload,session_id=EXCLUDED.session_id,agent_id=EXCLUDED.agent_id,occurred_at=EXCLUDED.occurred_at,deleted=EXCLUDED.deleted,search_vector=EXCLUDED.search_vector", (pid,iid,event['version'],content_hash,event['event_type'],canonical(payload),event['session_id'],event['agent_id'],occurred,deleted,payload.get('title',''),payload.get('problem','')+' '+payload.get('correction',''),payload.get('content','')))
            c.execute('INSERT INTO memory.item_versions VALUES(%s,%s,%s,%s,%s::jsonb)', (pid,iid,event['version'],content_hash,canonical(event)))
            c.execute('INSERT INTO memory.sessions(project_id,id,agent_id,started_at,ended_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(project_id,id) DO UPDATE SET ended_at=COALESCE(EXCLUDED.ended_at,memory.sessions.ended_at)', (pid,event['session_id'],event['agent_id'],occurred,occurred if event['event_type']=='session_end' else None))
            destinations = ['extract'] if event['generate'] and not deleted else []
            # Summary extraction is explicit policy, never automatic transcript capture.
            technical = bool(capture or auto_mode or payload.get('category') == 'agent-activity')
            jobs = self._jobs(c,pid,iid,event['version'],content_hash,'item',destinations,'delete' if deleted else 'upsert',embed=not technical)
            receipt = {'event_id': event['event_id'], 'item_id': iid, 'version': event['version'], 'status': 'accepted', 'jobs': jobs}
            if capture:
                receipt['capture_hash'] = capture['fingerprint']
            if redacted:
                receipt['redacted']=True
            c.execute('INSERT INTO memory.events(id,project_id,canonical_hash,body,receipt) VALUES(%s,%s,%s,%s::jsonb,%s::jsonb)', (event['event_id'],pid,content_hash,canonical(event),canonical(receipt)))
            self._audit(c,actor,'event.accepted',pid,iid)
        return receipt

    def publish_document(self, actor, project_id, document):
        data = json.loads(canonical(as_dict(document)))
        try:
            sensitive=has_sensitive(data)
        except MemoryError as exc:
            if exc.code in {'invalid_private_block','invalid_private_key_block'}:
                raise MemoryError('sensitive_source_requires_review','Approved sources require privacy review before publication',422) from None
            raise
        if sensitive:
            raise MemoryError('sensitive_source_requires_review','Approved sources require privacy review before publication',422)
        try:
            source_hash=hashlib.sha256(data['content'].encode('utf-8')).hexdigest()
        except (KeyError,AttributeError,UnicodeError):
            raise MemoryError('invalid_source_content','Published content must be valid UTF-8 text',422) from None
        if data.get('source',{}).get('sha256')!=source_hash:
            raise MemoryError('source_hash_mismatch','Source SHA-256 must match the exact UTF-8 content',422)
        iid = data['document_id'] = str(uuid.UUID(str(data['document_id'])))
        if isinstance(data.get('validation'),dict):
            data['validation']['validated_by'] = actor['id']
        content_hash = digest(data)
        with self.transaction() as c:
            self._require(c,actor,project_id,'publish')
            self._require(c,actor,project_id,'validate')
            if not data.get('source',{}).get('sha256') or not data.get('validation',{}).get('evidence'):
                raise MemoryError('evidence_required','Published documents require source hash and validation evidence',422)
            # Authority is authenticated, never taken from caller's claimed validated_by.
            data['validation']['validated_by'] = actor['id']
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('doc:'+project_id+':'+iid,))
            old = c.execute('SELECT * FROM memory.documents WHERE project_id=%s AND id=%s FOR UPDATE',(project_id,iid)).fetchone()
            if old and old['version']==data['version'] and old['canonical_hash']==content_hash:
                jobs = c.execute("SELECT id FROM memory.jobs WHERE project_id=%s AND item_id=%s AND version=%s AND resource_type='document' ORDER BY id",(project_id,iid,data['version'])).fetchall()
                return {'event_id':iid,'item_id':iid,'version':data['version'],'status':'accepted','jobs':[j['id'] for j in jobs]}
            if data['version'] != (old['version']+1 if old else 1) or (old and old['deleted']):
                raise Conflict()
            c.execute('INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(project_id,id) DO UPDATE SET version=EXCLUDED.version,canonical_hash=EXCLUDED.canonical_hash,body=EXCLUDED.body',(project_id,iid,data['version'],content_hash,canonical(data)))
            c.execute('INSERT INTO memory.document_versions VALUES(%s,%s,%s,%s,%s::jsonb)',(project_id,iid,data['version'],content_hash,canonical(data)))
            policy=c.execute('SELECT policy FROM memory.projects WHERE id=%s',(project_id,)).fetchone()['policy']
            destinations=[]
            jobs=self._jobs(c,project_id,iid,data['version'],content_hash,'document',destinations,'upsert')
            self._audit(c,actor,'document.published',project_id,iid)
        return {'event_id':iid,'item_id':iid,'version':data['version'],'status':'accepted','jobs':jobs}

    def delete_document(self, actor, project_id, document_id, version):
        with self.transaction() as c:
            self._require(c,actor,project_id,'publish')
            old=c.execute('SELECT * FROM memory.documents WHERE project_id=%s AND id=%s FOR UPDATE',(project_id,document_id)).fetchone()
            if not old:
                raise NotFound()
            if old['body'].get('validation',{}).get('status')=='validated':
                self._require(c,actor,project_id,'validate')
            if old['deleted'] and old['version']==version:
                jobs=c.execute("SELECT id FROM memory.jobs WHERE project_id=%s AND item_id=%s AND version=%s AND resource_type='document'",(project_id,document_id,version)).fetchall()
                return {'event_id':document_id,'item_id':document_id,'version':version,'status':'accepted','jobs':sorted(j['id'] for j in jobs)}
            if version != old['version']+1:
                raise Conflict()
            body=dict(old['body'], deleted=True, version=version)
            content_hash=digest(body)
            c.execute('UPDATE memory.documents SET version=%s,canonical_hash=%s,deleted=true,body=%s::jsonb WHERE project_id=%s AND id=%s',(version,content_hash,canonical(body),project_id,document_id))
            c.execute('INSERT INTO memory.document_versions VALUES(%s,%s,%s,%s,%s::jsonb)',(project_id,document_id,version,content_hash,canonical(body)))
            destinations=[r['destination'] for r in c.execute("SELECT DISTINCT destination FROM memory.jobs WHERE project_id=%s AND item_id=%s AND resource_type='document'",(project_id,document_id)).fetchall()]
            jobs=self._jobs(c,project_id,document_id,version,content_hash,'document',destinations,'delete')
            self._audit(c,actor,'document.deleted',project_id,document_id)
        return {'event_id':document_id,'item_id':document_id,'version':version,'status':'accepted','jobs':jobs}

    def _item(self,row):
        payload=row['payload']
        result=dict(payload,project_id=row['project_id'],item_id=row['id'],id=row['id'],version=row['version'],canonical_hash=row['canonical_hash'],event_type=row['event_type'],session_id=row['session_id'],agent_id=row['agent_id'],occurred_at=clean(row['occurred_at']),deleted=row['deleted'],superseded=bool(row['superseded_by']),superseded_by=row['superseded_by'],layer='episodic',ref=f"episodic:{row['project_id']}:{row['id']}:{row['version']}",validation_status=payload.get('validation_status','observed'),excerpt=payload.get('content','')[:500])
        result['payload']=payload
        return result

    def search_items(self, actor, project_ids, q='', limit=20, categories=None, tags=None, *, match_mode='all',exclude_categories=None):
        categories,tags=categories or None,tags or None
        query_function,q=lexical_query(q,match_mode)
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return []
        with self.transaction() as c:
            for project in project_ids:
                self._require(c,actor,project,'read')
            rank_sql=f"ts_rank_cd(search_vector,{query_function}('simple',%s))" if q else "0::real"
            rank_args=[q] if q else []
            rows=c.execute(f"SELECT *,{rank_sql} AS rank FROM memory.memory_items WHERE project_id=ANY(%s) AND NOT deleted AND superseded_by IS NULL AND (%s='' OR search_vector @@ {query_function}('simple',%s)) AND (%s::text[] IS NULL OR payload->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (payload->'tags') ?| %s) AND NOT (coalesce(payload->>'category','')=ANY(%s::text[])) ORDER BY (event_type='correction' AND payload->>'validation_status'='validated') DESC,rank DESC,occurred_at DESC,project_id,id LIMIT %s",(*rank_args,project_ids,q,q,categories,categories,tags,tags,exclude_categories or [],min(max(limit,1),100))).fetchall()
            return [self._item(r) for r in rows]

    def get_item(self, actor, project_id, item_id):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            row=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND id=%s AND NOT deleted',(project_id,str(item_id))).fetchone()
            if not row:
                raise NotFound()
            return self._item(row)

    def get_current_items(self,actor,project_id,item_ids=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            rows=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND NOT deleted AND superseded_by IS NULL AND (%s::text[] IS NULL OR id=ANY(%s)) ORDER BY occurred_at DESC,id LIMIT 100',(project_id,item_ids,item_ids)).fetchall()
            return [self._item(r) for r in rows]

    def get_document(self,actor,project_id,document_id):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            row=c.execute('SELECT * FROM memory.documents WHERE project_id=%s AND id=%s AND NOT deleted',(project_id,str(document_id))).fetchone()
            if not row:
                raise NotFound()
            return dict(row['body'],project_id=project_id,item_id=row['id'],canonical_hash=row['canonical_hash'],deleted=False)

    def search_documents(self,actor,project_ids,q='',limit=20,categories=None,tags=None,*,match_mode='all',exclude_categories=None):
        """Search the canonical documents immediately, independently of vector indexing."""
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return []
        categories,tags=categories or None,tags or None
        query_function,q=lexical_query(q,match_mode)
        with self.transaction() as c:
            for project_id in project_ids:
                self._require(c,actor,project_id,'read')
            rows=c.execute(f"""SELECT d.*,
                ts_rank_cd(d.search_vector,{query_function}('simple',%s)) AS rank,
                EXISTS(SELECT 1 FROM memory.projection_receipts r JOIN memory.jobs j ON j.id=r.job_id
                    WHERE r.project_id=d.project_id AND r.item_id=d.id AND r.version=d.version
                    AND r.canonical_hash=d.canonical_hash AND r.destination='embed'
                    AND j.resource_type='document' AND j.operation='upsert' AND j.state='succeeded'
                    AND r.receipt->>'verified'='true') AS indexed
                FROM memory.documents d WHERE d.project_id=ANY(%s) AND NOT d.deleted
                AND (%s='' OR d.search_vector @@ {query_function}('simple',%s))
                AND (%s::text[] IS NULL OR d.body->>'category'=ANY(%s))
                AND (%s::text[] IS NULL OR (d.body->'tags') ?| %s)
                AND NOT (coalesce(d.body->>'category','')=ANY(%s::text[]))
                ORDER BY rank DESC,d.project_id,d.id LIMIT %s""",(q,project_ids,q,q,categories,categories,tags,tags,exclude_categories or [],min(max(limit,1),100))).fetchall()
            return [dict(row['body'],project_id=row['project_id'],item_id=row['id'],document_id=row['id'],version=row['version'],canonical_hash=row['canonical_hash'],layer='documental',ref=f"documental:{row['project_id']}:{row['id']}:{row['version']}",excerpt=row['body'].get('content','')[:500],validation_status=row['body'].get('validation',{}).get('status','unknown'),index_status='ready' if row['indexed'] else 'pending') for row in rows]

    def list_documents(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            rows=c.execute('SELECT * FROM memory.documents WHERE project_id=%s AND NOT deleted AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall()
            return [dict(r['body'],project_id=project_id,item_id=r['id'],canonical_hash=r['canonical_hash']) for r in rows]

    def list_notes(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            rows=c.execute('SELECT * FROM memory.memory_items WHERE project_id=%s AND NOT deleted AND superseded_by IS NULL AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall()
            return [self._item(r) for r in rows]

    def list_sessions(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            return clean(c.execute('SELECT * FROM memory.sessions WHERE project_id=%s AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall())

    def list_jobs(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            return clean(c.execute('SELECT id,project_id,item_id,version,destination,operation,state,attempts,error_code,created_at FROM memory.jobs WHERE project_id=%s AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall())

    def get_event_receipt(self,actor,event_id):
        with self.transaction() as c:
            self._active(c,actor)
            row=c.execute('SELECT project_id FROM memory.events WHERE id=%s',(str(event_id),)).fetchone()
            if not row:
                raise NotFound()
            self._require(c,actor,row['project_id'],'read')
            return c.execute('SELECT receipt FROM memory.events WHERE id=%s',(str(event_id),)).fetchone()['receipt']

    def reconcile_capture(self, actor, project_id, event_id):
        """Explicit absence only within the caller's currently writable project."""
        with self.transaction() as c:
            self._require(c, actor, project_id, 'read')
            self._require(c, actor, project_id, 'write')
            row = c.execute('SELECT receipt FROM memory.events WHERE id=%s AND project_id=%s',
                            (str(event_id), project_id)).fetchone()
            return row['receipt'] if row else None

    def get_job(self,actor,job_id):
        with self.transaction() as c:
            self._active(c,actor)
            row=c.execute('SELECT project_id FROM memory.jobs WHERE id=%s',(str(job_id),)).fetchone()
            if not row:
                raise NotFound()
            self._require(c,actor,row['project_id'],'read')
            return clean(c.execute('SELECT id,project_id,item_id,version,destination,operation,state,attempts,error_code,created_at FROM memory.jobs WHERE id=%s',(str(job_id),)).fetchone())

    def document_status(self,actor,project_id,document_id):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            row=c.execute("SELECT id,version,canonical_hash,deleted,body->'source'->>'sha256' AS source_sha256 FROM memory.documents WHERE project_id=%s AND id=%s",(project_id,str(document_id))).fetchone()
            if not row:
                raise NotFound()
            jobs=c.execute("SELECT id,destination,operation,state,error_code FROM memory.jobs WHERE project_id=%s AND item_id=%s AND resource_type='document' AND version=%s ORDER BY id",(project_id,str(document_id),row['version'])).fetchall()
            return dict(row,project_id=project_id,document_id=row['id'],jobs=jobs)

    def document_manifest(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            size=min(max(limit,1),100)
            rows=c.execute("SELECT id AS document_id,version,canonical_hash,deleted,body->'source' AS source,body->'source'->>'sha256' AS source_sha256 FROM memory.documents WHERE project_id=%s AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s",(project_id,cursor,cursor,size+1)).fetchall()
            items,more=rows[:size],len(rows)>size
            return {'items':items,'next_cursor':items[-1]['document_id'] if more else None,'has_more':more}

    def stats(self,actor,project_id):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            items=c.execute('SELECT count(*) AS count FROM memory.memory_items WHERE project_id=%s AND NOT deleted',(project_id,)).fetchone()['count']
            documents=c.execute('SELECT count(*) AS count FROM memory.documents WHERE project_id=%s AND NOT deleted',(project_id,)).fetchone()['count']
            sessions=c.execute('SELECT count(*) AS count FROM memory.sessions WHERE project_id=%s',(project_id,)).fetchone()['count']
            jobs=c.execute('SELECT state,count(*) AS count FROM memory.jobs WHERE project_id=%s GROUP BY state',(project_id,)).fetchall()
            return {'project_id':project_id,'items':items,'notes':items,'documents':documents,'sessions':sessions,'jobs':{r['state']:r['count'] for r in jobs}}

    def history(self,actor,project_id,limit=20,cursor=None):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            return clean(c.execute('SELECT id AS event_id,body,created_at FROM memory.events WHERE project_id=%s AND (%s::text IS NULL OR id>%s) ORDER BY id LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall())

    def list_activity(self,actor,project_id,cursor=None,limit=50):
        """Project-scoped metadata feed; no captured text or provider calls."""
        def encode(occurred,event_id):
            value={'v':1,'kind':'activity','pid':project_id,'at':occurred.isoformat(),'id':event_id}
            return base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip('=')
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            after_time,after_id=None,None
            if cursor:
                try:
                    if not isinstance(cursor,str) or len(cursor)>2048:
                        raise ValueError()
                    decoded=json.loads(base64.b64decode(cursor+'='*((-len(cursor))%4),altchars=b'-_',validate=True))
                    if decoded.get('v')!=1 or decoded.get('kind')!='activity' or decoded.get('pid')!=project_id:
                        raise ValueError()
                    after_time=datetime.fromisoformat(decoded['at'])
                    after_id=str(uuid.UUID(decoded['id']))
                    if after_time.tzinfo is None:
                        raise ValueError()
                except (ValueError,KeyError,TypeError,AttributeError,RecursionError):
                    raise MemoryError('invalid_cursor','Activity cursor does not match this project',422) from None
            size=min(max(limit,1),100)
            rows=c.execute("SELECT id,created_at,body->>'event_type' AS event_type,body->>'item_id' AS item_id,body->>'version' AS version FROM memory.events WHERE project_id=%s AND (%s::timestamptz IS NULL OR (created_at,id)>(%s::timestamptz,%s)) ORDER BY created_at,id LIMIT %s",(project_id,after_time,after_time,after_id,size+1)).fetchall()
            items=[{'id':row['id'],'event_id':row['id'],'project_id':project_id,'event_type':row['event_type'],'ref':f"episodic:{project_id}:{row['item_id']}:{row['version']}",'created_at':row['created_at'].isoformat(),'cursor':encode(row['created_at'],row['id'])} for row in rows[:size]]
            return {'items':items,'next_cursor':items[-1]['cursor'] if items else cursor,'has_more':len(rows)>size}

    def native_history(self,actor,project_id,limit=20,cursor=None):
        """Version history describes recording order; validity is only source-declared."""
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            rows=c.execute('SELECT v.*,i.version AS current_version,i.superseded_by FROM memory.item_versions v JOIN memory.memory_items i ON i.project_id=v.project_id AND i.id=v.item_id WHERE v.project_id=%s AND NOT i.deleted AND (%s::text IS NULL OR v.item_id>%s) ORDER BY v.item_id,v.version DESC LIMIT %s',(project_id,cursor,cursor,min(limit,100))).fetchall()
            return [dict(clean(r['body']),canonical_hash=r['canonical_hash'],superseded=r['version']!=r['current_version'] or bool(r['superseded_by']),validity='declared' if any(f.get('valid_from') or f.get('valid_until') for f in r['body'].get('payload',{}).get('facts',[])) else 'unknown') for r in rows]

    def timeline(self,actor,request):
        request=as_dict(request)
        projects=request['project_ids']
        limit=min(max(request.get('limit',20),1),100)
        anchor=request.get('anchor')
        with self.transaction() as c:
            for pid in projects:
                self._require(c,actor,pid,'read')
            anchor_time=None
            if anchor:
                if anchor['project_id'] not in projects:
                    raise NotFound()
                found=c.execute('SELECT occurred_at,version FROM memory.memory_items WHERE project_id=%s AND id=%s AND NOT deleted',(anchor['project_id'],anchor['item_id'])).fetchone()
                if not found or found['version']!=anchor['version']:
                    raise NotFound()
                anchor_time=found['occurred_at']
            rows=c.execute('SELECT * FROM memory.memory_items WHERE project_id=ANY(%s) AND NOT deleted AND (%s::timestamptz IS NULL OR occurred_at<%s::timestamptz) AND (%s::timestamptz IS NULL OR occurred_at>%s::timestamptz) ORDER BY abs(EXTRACT(epoch FROM occurred_at-COALESCE(%s::timestamptz,clock_timestamp()))),occurred_at DESC,project_id,id LIMIT %s',(projects,request.get('before'),request.get('before'),request.get('after'),request.get('after'),anchor_time,limit)).fetchall()
            items=[self._item(row) for row in rows]
            items.sort(key=lambda item:(item['occurred_at'],item['project_id'],item['item_id']))
            return {'items':items,'anchor':anchor,'partial':False,'ordering':'recorded_time','validity':'source_declared_only'}

    def search_native_facts(self,actor,project_ids,q='',limit=20,categories=None,tags=None):
        categories,tags=categories or None,tags or None
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        with self.transaction() as c:
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            rows=c.execute("""SELECT i.*,f.fact,f.ordinality FROM memory.memory_items i
                CROSS JOIN LATERAL jsonb_array_elements(COALESCE(i.payload->'facts','[]'::jsonb)) WITH ORDINALITY AS f(fact,ordinality)
                JOIN memory.projects p ON p.id=i.project_id
                WHERE i.project_id=ANY(%s) AND NOT i.deleted AND i.superseded_by IS NULL
                AND COALESCE((p.policy->>'temporal_projection')::boolean,false)
                AND (%s::text[] IS NULL OR i.payload->>'category'=ANY(%s))
                AND (%s::text[] IS NULL OR (i.payload->'tags') ?| %s)
                AND (%s='' OR to_tsvector('simple',concat_ws(' ',f.fact->>'subject',f.fact->>'predicate',f.fact->>'object',f.fact->>'evidence_quote')) @@ plainto_tsquery('simple',%s))
                ORDER BY (i.payload->>'validation_status'='validated') DESC,i.occurred_at DESC,i.project_id,i.id,f.ordinality LIMIT %s""",(project_ids,categories,categories,tags,tags,q,q,min(max(limit,1),100))).fetchall()
            return [self._native_fact(row) for row in rows]

    def _native_fact(self,row):
        fact=row['fact']
        return dict(fact,ref=f"native:{row['project_id']}:{row['id']}:{row['version']}:{row['ordinality']}",project_id=row['project_id'],item_id=row['id'],version=row['version'],canonical_hash=row['canonical_hash'],title=row['payload'].get('title',''),category=row['payload'].get('category',''),tags=row['payload'].get('tags',[]),source=row['payload'].get('source'),validation_status=row['payload'].get('validation_status','unverified'),evidence=fact['evidence_quote'],superseded=False,validity='declared' if fact.get('valid_from') or fact.get('valid_until') else 'unknown',recorded_at=clean(row['occurred_at']))

    def get_native_fact(self,actor,project_id,item_id,version,ordinal):
        with self.transaction() as c:
            self._require(c,actor,project_id,'read')
            row=c.execute("""SELECT i.*,f.fact,f.ordinality FROM memory.memory_items i
                CROSS JOIN LATERAL jsonb_array_elements(COALESCE(i.payload->'facts','[]'::jsonb)) WITH ORDINALITY AS f(fact,ordinality)
                JOIN memory.projects p ON p.id=i.project_id
                WHERE i.project_id=%s AND i.id=%s AND i.version=%s AND f.ordinality=%s
                AND NOT i.deleted AND i.superseded_by IS NULL
                AND COALESCE((p.policy->>'temporal_projection')::boolean,false)""",(project_id,str(item_id),version,ordinal)).fetchone()
            if not row:
                raise NotFound()
            return self._native_fact(row)

    def graph_data(self,actor,request):
        request=as_dict(request)
        projects=request['project_ids']
        q=request.get('q','')
        limit=min(max(request.get('limit',100),1),100)
        layers=request.get('layers',['episodic','documental','temporal'])
        nodes,links={},[]
        def node(value):
            if value['id'] in nodes or len(nodes)<limit:
                nodes[value['id']]=value
                return True
            return False
        for pid in projects:
            self.require_permission(actor,pid,'read')
        if 'episodic' in layers:
            for item in self.search_items(actor,projects,q,limit,request.get('categories'),request.get('tags')):
                node({'id':item['ref'],'name':item.get('title',''),'type':'memory','project_id':item['project_id'],'category':item.get('category',''),'tags':item.get('tags',[]),'ref':item['ref'],'validation_status':item['validation_status']})
        if 'documental' in layers:
            for pid in projects:
                for doc in self.list_documents(actor,pid,limit):
                    if q and q.casefold() not in (doc.get('title','')+' '+doc.get('content','')).casefold():
                        continue
                    if request.get('categories') and doc.get('category') not in request['categories']:
                        continue
                    if request.get('tags') and not set(doc.get('tags',[])).intersection(request['tags']):
                        continue
                    ref=f"documental:{pid}:{doc['document_id']}:{doc['version']}"
                    node({'id':ref,'name':doc['title'],'type':'document','project_id':pid,'category':doc.get('category',''),'tags':doc.get('tags',[]),'ref':ref,'validation_status':'validated'})
        if 'temporal' in layers:
            for fact in self.search_native_facts(actor,projects,q,100,request.get('categories'),request.get('tags')):
                ids=[]
                for value in (fact['subject'],fact['object']):
                    nid='entity:'+fact['project_id']+':'+hashlib.sha256(value.casefold().encode()).hexdigest()[:24]
                    ids.append(nid)
                    node({'id':nid,'name':value,'type':'entity','project_id':fact['project_id'],'category':'','tags':[],'ref':f"episodic:{fact['project_id']}:{fact['item_id']}:{fact['version']}",'validation_status':fact['validation_status']})
                if all(nid in nodes for nid in ids) and len(links)<100:
                    links.append({'source':ids[0],'target':ids[1],'label':fact['predicate'],'project_id':fact['project_id'],'evidence_refs':[fact['ref']],'evidence_quote':fact['evidence_quote'],'valid_from':fact.get('valid_from'),'valid_until':fact.get('valid_until')})
        return {'nodes':list(nodes.values()),'links':links,'stats':{'nodes':len(nodes),'links':len(links),'project_ids':projects},'partial':False}

    def retry_job(self,actor,job_id):
        with self.transaction() as c:
            self._active(c,actor)
            row=c.execute('SELECT * FROM memory.jobs WHERE id=%s FOR UPDATE',(job_id,)).fetchone()
            if not row:
                raise NotFound()
            self._require(c,actor,row['project_id'],'write')
            if row['state']!='succeeded':
                # Unknown requires reconciliation by worker before a new remote invocation.
                c.execute("UPDATE memory.jobs SET state=CASE WHEN state='unknown' THEN 'unknown' ELSE 'pending' END,available_at=clock_timestamp() WHERE id=%s AND state<>'running'",(job_id,))
            return {'id':job_id,'state':row['state'] if row['state'] in {'succeeded','unknown','running'} else 'pending'}

    def _job_payload(self,c,row):
        table='memory.documents' if row['resource_type']=='document' else 'memory.memory_items'
        current=c.execute('SELECT * FROM '+table+' WHERE project_id=%s AND id=%s',(row['project_id'],row['item_id'])).fetchone()
        project=c.execute('SELECT * FROM memory.projects WHERE id=%s',(row['project_id'],)).fetchone()
        result=clean(row)
        result.update(payload=current['body'] if row['resource_type']=='document' else self._item(current),policy=project['policy'])
        result['needs_reconciliation']=row['state']=='unknown' or row['attempts']>1
        return result

    def claim_job(self,worker_id,lease_seconds=120):
        with self.transaction() as c:
            while True:
                row=c.execute("SELECT * FROM memory.jobs WHERE (state IN ('pending','unknown') AND available_at<=clock_timestamp()) OR (state='running' AND lease_until<clock_timestamp()) ORDER BY available_at,created_at,id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
                if not row:
                    return None
                if row['destination'] not in {'extract','embed'}:
                    c.execute("UPDATE memory.jobs SET state='failed',error_code='destination_retired',lease_until=NULL WHERE id=%s",(row['id'],))
                    continue
                table='memory.documents' if row['resource_type']=='document' else 'memory.memory_items'
                extra=',NULL::text AS superseded_by' if row['resource_type']=='document' else ',superseded_by'
                current=c.execute('SELECT version,canonical_hash,deleted'+extra+' FROM '+table+' WHERE project_id=%s AND id=%s',(row['project_id'],row['item_id'])).fetchone()
                if current and current['version']==row['version'] and current['canonical_hash']==row['canonical_hash'] and not current['superseded_by'] and (not current['deleted'] or row['operation']=='delete'):
                    break
                c.execute("UPDATE memory.jobs SET state='failed',error_code='superseded',lease_until=NULL WHERE id=%s",(row['id'],))
            needs_reconciliation=row['state']=='unknown' or row['state']=='running' or row['attempts']>0
            updated=c.execute("UPDATE memory.jobs SET state='running',attempts=attempts+1,fence=fence+1,worker_id=%s,lease_until=clock_timestamp()+(%s * interval '1 second') WHERE id=%s RETURNING *",(worker_id,lease_seconds,row['id'])).fetchone()
            result=self._job_payload(c,updated)
            result['needs_reconciliation']=needs_reconciliation
            return result

    def renew_lease(self,job_id,fence,lease_seconds=120):
        with self.transaction() as c:
            return c.execute("UPDATE memory.jobs SET lease_until=clock_timestamp()+(%s * interval '1 second') WHERE id=%s AND fence=%s AND state='running' AND lease_until>clock_timestamp() RETURNING id",(lease_seconds,job_id,fence)).fetchone() is not None

    def _current_job(self,c,job_id,fence):
        row=c.execute("SELECT * FROM memory.jobs WHERE id=%s AND fence=%s AND state='running' AND lease_until>clock_timestamp() FOR UPDATE",(job_id,fence)).fetchone()
        if not row:
            return None
        table='memory.documents' if row['resource_type']=='document' else 'memory.memory_items'
        current=c.execute('SELECT * FROM '+table+' WHERE project_id=%s AND id=%s FOR SHARE',(row['project_id'],row['item_id'])).fetchone()
        live=bool(current and (not current['deleted'] or row['operation']=='delete') and not current.get('superseded_by'))
        if live and current.get('parent_item_id'):
            parent=c.execute('SELECT version,canonical_hash,deleted,superseded_by FROM memory.memory_items WHERE project_id=%s AND id=%s',(row['project_id'],current['parent_item_id'])).fetchone()
            live=bool(parent and not parent['deleted'] and not parent['superseded_by'] and parent['version']==current['parent_version'] and parent['canonical_hash']==current['parent_hash'])
        if not live or current['version']!=row['version'] or current['canonical_hash']!=row['canonical_hash']:
            c.execute("UPDATE memory.jobs SET state='failed',error_code='superseded',lease_until=NULL WHERE id=%s",(job_id,))
            return None
        return row

    def complete_job(self,job_id,fence,receipt):
        with self.transaction() as c:
            row=self._current_job(c,job_id,fence)
            if not row:
                return False
            if row['destination']=='extract':
                sanitized,_=sanitize_payload(dict(receipt.get('payload',{})))
                sanitized['validation_status']='unverified'
                sanitized.pop('validated_by',None)
                sanitized.pop('supersedes',None)
                if has_sensitive(sanitized):
                    raise MemoryError('sensitive_source_requires_review','Generated capture metadata requires privacy review',422)
                receipt=dict(receipt,payload=sanitized)
                derived_id=self._materialize_extract(c,row,receipt)
                if not derived_id:
                    c.execute("UPDATE memory.jobs SET state='failed',error_code='superseded',lease_until=NULL WHERE id=%s",(job_id,))
                    return False
                receipt=dict(receipt,derived_item_id=derived_id)
            elif row['destination']=='embed':
                vector=self._vector(receipt.get('vector'))
                model=receipt.get('model')
                if not isinstance(model,str) or not 1<=len(model)<=200:
                    raise MemoryError('invalid_embedding','Embedding model is required',422)
                if receipt.get('verified') is not True:
                    raise MemoryError('invalid_embedding','Embedding provider did not verify its result',422)
                if receipt.get('canonical_hash',row['canonical_hash'])!=row['canonical_hash']:
                    raise MemoryError('invalid_embedding','Embedding source hash does not match the current job',422)
                c.execute('INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(project_id,item_id,resource_type,version,model) DO UPDATE SET canonical_hash=EXCLUDED.canonical_hash,vector=EXCLUDED.vector,created_at=clock_timestamp()',(row['project_id'],row['item_id'],row['resource_type'],row['version'],row['canonical_hash'],model,vector))
                receipt={'model':model,'dimensions':len(vector),'hash':digest(vector),'status':'verified','verified':True}
            c.execute('INSERT INTO memory.projection_receipts(job_id,project_id,item_id,version,canonical_hash,destination,receipt) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(job_id) DO UPDATE SET receipt=EXCLUDED.receipt,recorded_at=clock_timestamp()',(job_id,row['project_id'],row['item_id'],row['version'],row['canonical_hash'],row['destination'],canonical(receipt)))
            c.execute("UPDATE memory.jobs SET state='succeeded',lease_until=NULL,error_code=NULL WHERE id=%s",(job_id,))
            return True

    def fail_job(self,job_id,fence,code,retry_at=None,unknown=False):
        # Only safe public error identifiers are persisted; never provider exception strings.
        safe=code if isinstance(code,str) and code.replace('_','').isalnum() and len(code)<80 else 'provider_error'
        with self.transaction() as c:
            row=self._current_job(c,job_id,fence)
            if not row:
                return False
            state='unknown' if unknown else ('pending' if retry_at else 'failed')
            c.execute('UPDATE memory.jobs SET state=%s,error_code=%s,lease_until=NULL,available_at=COALESCE(%s::timestamptz,clock_timestamp()) WHERE id=%s',(state,safe,retry_at,job_id))
            return True



    def _vector(self,value,allow_zero=False):
        if not isinstance(value,(list,tuple)) or not 1<=len(value)<=4096 or any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in value):
            raise MemoryError('invalid_embedding','Embedding must contain 1 to 4096 finite numbers',422)
        try:
            result=[float(v) for v in value]
        except (OverflowError,ValueError):
            raise MemoryError('invalid_embedding','Embedding must contain finite numbers',422) from None
        if not all(math.isfinite(v) for v in result):
            raise MemoryError('invalid_embedding','Embedding must contain finite numbers',422)
        if not allow_zero and not any(result):
            raise MemoryError('invalid_embedding','Embedding norm must be positive',422)
        return result

    def _unit(self,vector):
        scale=max(abs(v) for v in vector)
        if not scale:
            return None
        scaled=[v/scale for v in vector]
        norm=math.sqrt(sum(v*v for v in scaled))
        return [v/norm for v in scaled]

    def _vector_candidates(self,c,projects,model,categories,tags,limit,*,stream=False,identities=None):
        columns='e.*' if stream else 'e.*,r.payload,r.current_row'
        selection=''
        params=[projects,projects,model,categories,categories,tags,tags]
        if identities is not None:
            selection=''' AND EXISTS (SELECT 1 FROM jsonb_to_recordset(%s::jsonb)
                AS wanted(project_id text,item_id text,resource_type text)
                WHERE wanted.project_id=e.project_id AND wanted.item_id=e.item_id::text
                AND wanted.resource_type=e.resource_type)'''
            params.append(canonical(identities))
        params.append(limit)
        query="""WITH current_resources AS (
            SELECT i.project_id,i.id,i.version,i.canonical_hash,'item'::text AS resource_type,i.payload,to_jsonb(i) AS current_row
            FROM memory.memory_items i LEFT JOIN memory.memory_items p ON p.project_id=i.project_id AND p.id=i.parent_item_id
            WHERE i.project_id=ANY(%s) AND NOT i.deleted AND i.superseded_by IS NULL
            AND (i.parent_item_id IS NULL OR (p.version=i.parent_version AND p.canonical_hash=i.parent_hash AND NOT p.deleted AND p.superseded_by IS NULL))
            UNION ALL
            SELECT d.project_id,d.id,d.version,d.canonical_hash,'document'::text,d.body,to_jsonb(d)
            FROM memory.documents d WHERE d.project_id=ANY(%s) AND NOT d.deleted
        ) SELECT """+columns+""" FROM current_resources r JOIN memory.embeddings e
            ON e.project_id=r.project_id AND e.item_id=r.id AND e.resource_type=r.resource_type
            AND e.version=r.version AND e.canonical_hash=r.canonical_hash
            WHERE e.model=%s AND (%s::text[] IS NULL OR r.payload->>'category'=ANY(%s))
            AND (%s::text[] IS NULL OR (r.payload->'tags') ?| %s)
            """+selection+""" ORDER BY e.project_id,e.resource_type,e.item_id LIMIT %s"""
        if stream:
            cursor=c.cursor(name='vectors_'+uuid.uuid4().hex)
            cursor.itersize=128
            cursor.execute(query,params)
            return cursor
        return c.execute(query,params).fetchall()

    def has_vectors(self,actor,project_ids,model):
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return False
        with self.transaction() as c:
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            return bool(self._vector_candidates(c,project_ids,model,None,None,1))

    def search_vectors(self,actor,project_ids,vector,model,limit=20,categories=None,tags=None,*,deadline=None):
        """Exact cosine over at most 10,000 authorized current candidates; no ANN claim."""
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return []
        def remaining():
            if deadline is None:
                return None
            seconds=deadline-time.monotonic()
            if seconds<=0:
                raise MemoryError('semantic_deadline_exceeded','Semantic query exceeded its time budget',503)
            return max(1,math.ceil(seconds*1000))
        remaining()
        with self.transaction() as c:
            if deadline is not None:
                c.execute("SELECT set_config('statement_timeout',%s,true)",(str(remaining()),))
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            query=self._unit(self._vector(vector,allow_zero=True))
            if query is None:
                return []
            # Only one cursor batch and at most 100 identities live in Python.
            # Fetch payloads after ranking, never for the full candidate corpus.
            winners=[]
            truncated=False
            size=min(max(limit,1),100)
            with self._vector_candidates(c,project_ids,model,categories or None,tags or None,10001,stream=True) as candidates:
                for ordinal,candidate in enumerate(candidates):
                    if ordinal%128==0:
                        remaining()
                    if ordinal==10000:
                        truncated=True
                        break
                    if len(candidate['vector'])!=len(query):
                        continue
                    unit=self._unit(candidate['vector'])
                    if unit is None:
                        continue
                    score=max(-1.0,min(1.0,sum(a*b for a,b in zip(query,unit))))
                    layer='episodic' if candidate['resource_type']=='item' else 'documental'
                    key=(-score,candidate['project_id'],layer,str(candidate['item_id']))
                    identity={key:candidate[key] for key in ('project_id','item_id','resource_type','version','canonical_hash')}
                    bisect.insort(winners,(key,identity),key=lambda entry:entry[0])
                    if len(winners)>size:
                        winners.pop()
            if not winners:
                return []
            # Recheck current authorization and current versions at payload fetch.
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            identities=[{key:str(value[key]) for key in ('project_id','item_id','resource_type')} for _,value in winners]
            current=self._vector_candidates(c,project_ids,model,categories or None,tags or None,size,identities=identities)
        by_id={(row['project_id'],str(row['item_id']),row['resource_type']):row for row in current}
        ranked=[]
        for key,identity in winners:
            candidate=by_id.get((identity['project_id'],str(identity['item_id']),identity['resource_type']))
            if not candidate or any(candidate[field]!=identity[field] for field in ('version','canonical_hash')):
                continue
            score=-key[0]
            if candidate['resource_type']=='item':
                hit=self._item(candidate['current_row'])
            else:
                hit=dict(candidate['payload'],project_id=candidate['project_id'],item_id=candidate['item_id'],document_id=candidate['item_id'],version=candidate['version'],canonical_hash=candidate['canonical_hash'],layer='documental',ref=f"documental:{candidate['project_id']}:{candidate['item_id']}:{candidate['version']}",excerpt=candidate['payload'].get('content','')[:500],validation_status=candidate['payload'].get('validation',{}).get('status','unknown'),index_status='ready')
            hit.update(score=score,embedding_model=model,candidate_limit=10000,candidates_truncated=truncated)
            ranked.append(hit)
        return ranked
