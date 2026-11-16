"""Store mixin: documents, items and read-side queries."""
import hashlib
import base64
import json
import uuid
from datetime import datetime

from .errors import Conflict, MemoryError, NotFound
from .privacy import has_sensitive
from .auth_scope import savepoint
from .store_common import TRIGRAM_FALLBACK_MS, TRIGRAM_THRESHOLD, LexicalResults, as_dict, canonical, digest, fts_match, fts_rank, item_columns, lexical_query, clean, trigram_wanted


INDEXED="""EXISTS(SELECT 1 FROM memory.projection_receipts r JOIN memory.jobs j ON j.id=r.job_id
                    WHERE r.project_id=d.project_id AND r.item_id=d.id AND r.version=d.version
                    AND r.canonical_hash=d.canonical_hash AND r.destination='embed'
                    AND j.resource_type='document' AND j.operation='upsert' AND j.state='succeeded'
                    AND r.receipt->>'verified'='true')"""


def bounded_fallback(c,fetch):
    """Run `fetch()` in a savepoint under the fallback's own statement_timeout; returns (rows, timed_out).

    On timeout the savepoint is rolled back (the transaction stays usable and the timeout setting is restored with it)
    and no fallback rows are returned. On success the transaction's previous statement_timeout is put back.
    """
    from psycopg import errors
    baseline=c.execute("SELECT current_setting('statement_timeout') AS value").fetchone()['value']
    try:
        with savepoint(c):
            c.execute("SELECT set_config('statement_timeout',%s,true)",(str(TRIGRAM_FALLBACK_MS),))
            c.execute("SELECT set_config('pg_trgm.word_similarity_threshold',%s,true)",(str(TRIGRAM_THRESHOLD),))
            rows=fetch()
    except errors.QueryCanceled:
        return [],True
    c.execute("SELECT set_config('statement_timeout',%s,true)",(baseline,))
    return rows,False


# `memory.trigram_key` of the title is computed once per candidate row for the score (LATERAL with OFFSET 0, so the
# planner cannot flatten it and re-substitute the expression); the index recheck is
# bounded by the fallback's statement_timeout. Parameters: q, q (score), projects, q, q (match), filters, limit.
def trigram_items(c,project_ids,q,limit,categories,tags,exclude_categories):
    """Current memory items whose title is close to `q` (pg_trgm, word similarity). Authorization is the caller's.

    Returns (rows, timed_out)."""
    key="memory.trigram_key(i.payload->>'title')"
    return bounded_fallback(c,lambda:c.execute(f"""SELECT {item_columns('i.')},GREATEST(word_similarity(memory.trigram_words(%s),k.tkey),word_similarity(memory.trigram_compact(%s),k.tkey)) AS rank
        FROM memory.memory_items i CROSS JOIN LATERAL (SELECT {key} AS tkey OFFSET 0) k
        WHERE i.project_id=ANY(%s) AND NOT i.deleted AND i.superseded_by IS NULL
        AND ({key} %%> memory.trigram_words(%s) OR {key} %%> memory.trigram_compact(%s))
        AND (%s::text[] IS NULL OR i.payload->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (i.payload->'tags') ?| %s)
        AND NOT (coalesce(i.payload->>'category','')=ANY(%s::text[]))
        ORDER BY rank DESC,i.occurred_at DESC,i.project_id,i.id LIMIT %s""",(q,q,project_ids,q,q,categories,categories,tags,tags,exclude_categories or [],limit)).fetchall())


def trigram_documents(c,project_ids,q,limit,categories,tags,exclude_categories):
    """Same for documents, with the embedding status of each row. Returns (rows, timed_out)."""
    key="memory.trigram_key(d.body->>'title')"
    return bounded_fallback(c,lambda:c.execute(f"""SELECT d.project_id,d.id,d.version,d.canonical_hash,d.body,GREATEST(word_similarity(memory.trigram_words(%s),k.tkey),word_similarity(memory.trigram_compact(%s),k.tkey)) AS rank,
        {INDEXED} AS indexed
        FROM memory.documents d CROSS JOIN LATERAL (SELECT {key} AS tkey OFFSET 0) k
        WHERE d.project_id=ANY(%s) AND NOT d.deleted
        AND ({key} %%> memory.trigram_words(%s) OR {key} %%> memory.trigram_compact(%s))
        AND (%s::text[] IS NULL OR d.body->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (d.body->'tags') ?| %s)
        AND NOT (coalesce(d.body->>'category','')=ANY(%s::text[]))
        ORDER BY rank DESC,d.project_id,d.id LIMIT %s""",(q,q,project_ids,q,q,categories,categories,tags,tags,exclude_categories or [],limit)).fetchall())


def fill_up(found,fallback,limit):
    """Rows of `fallback` that are not in `found`, as many as still fit under `limit` (a project's id is unique)."""
    seen={(row['project_id'],row['id']) for row in found}
    return [row for row in fallback if (row['project_id'],row['id']) not in seen][:limit-len(found)]


class DocumentsMixin:
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
        asked=q
        query_function,q=lexical_query(q,match_mode)
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return []
        with self.transaction() as c:
            for project in project_ids:
                self._require(c,actor,project,'read')
            rank_sql=fts_rank(query_function) if q else "0::real"
            rank_args=[q]*3 if q else []
            rows=c.execute(f"SELECT {item_columns()},{rank_sql} AS rank FROM memory.memory_items WHERE project_id=ANY(%s) AND NOT deleted AND superseded_by IS NULL AND (%s='' OR {fts_match(query_function)}) AND (%s::text[] IS NULL OR payload->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (payload->'tags') ?| %s) AND NOT (coalesce(payload->>'category','')=ANY(%s::text[])) ORDER BY (event_type='correction' AND payload->>'validation_status'='validated') DESC,rank DESC,occurred_at DESC,project_id,id LIMIT %s",(*rank_args,project_ids,q,q,q,q,categories,categories,tags,tags,exclude_categories or [],min(max(limit,1),100))).fetchall()
            items=[self._item(r) for r in rows]
            timed_out=False
            wanted=min(max(limit,1),100)
            if trigram_wanted(asked,len(rows),wanted):
                # The lexical answer is short: complete it with titles close to the query. Marked, never silent.
                found,timed_out=trigram_items(c,project_ids,asked[:200],wanted+len(rows),categories,tags,exclude_categories)
                items+=[dict(self._item(r),lexical_match='trigram') for r in fill_up(rows,found,wanted)]
            items=LexicalResults(items)
            items.fuzzy_timed_out=timed_out
            return items

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
        asked=q
        query_function,q=lexical_query(q,match_mode)
        with self.transaction() as c:
            for project_id in project_ids:
                self._require(c,actor,project_id,'read')
            rows=c.execute(f"""SELECT d.project_id,d.id,d.version,d.canonical_hash,d.body,
                {fts_rank(query_function,'d.search_vector')} AS rank,
                {INDEXED} AS indexed
                FROM memory.documents d WHERE d.project_id=ANY(%s) AND NOT d.deleted
                AND (%s='' OR {fts_match(query_function,'d.search_vector')})
                AND (%s::text[] IS NULL OR d.body->>'category'=ANY(%s))
                AND (%s::text[] IS NULL OR (d.body->'tags') ?| %s)
                AND NOT (coalesce(d.body->>'category','')=ANY(%s::text[]))
                ORDER BY rank DESC,d.project_id,d.id LIMIT %s""",(q,q,q,project_ids,q,q,q,q,categories,categories,tags,tags,exclude_categories or [],min(max(limit,1),100))).fetchall()
            def hit(row):
                return dict(row['body'],project_id=row['project_id'],item_id=row['id'],document_id=row['id'],version=row['version'],canonical_hash=row['canonical_hash'],layer='documental',ref=f"documental:{row['project_id']}:{row['id']}:{row['version']}",excerpt=row['body'].get('content','')[:500],validation_status=row['body'].get('validation',{}).get('status','unknown'),index_status='ready' if row['indexed'] else 'pending')
            wanted=min(max(limit,1),100)
            documents=[hit(row) for row in rows]
            timed_out=False
            if trigram_wanted(asked,len(rows),wanted):
                # The lexical answer is short: complete it with titles close to the query. Marked, never silent.
                found,timed_out=trigram_documents(c,project_ids,asked[:200],wanted+len(rows),categories,tags,exclude_categories)
                documents+=[dict(hit(row),lexical_match='trigram') for row in fill_up(rows,found,wanted)]
            documents=LexicalResults(documents)
            documents.fuzzy_timed_out=timed_out
            return documents

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
