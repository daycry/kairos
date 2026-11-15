"""Store mixin: job queue, leases and receipts."""

from .chunking import embedding_text
from .config import CHUNK_MAX_LIMIT
from .errors import MemoryError, NotFound
from .privacy import has_sensitive, sanitize_payload
from .store_common import canonical, digest, clean

DEFAULT_MAX_ATTEMPTS = 3  # the cap of `claim_job` when nobody told the store otherwise; the worker passes MEMORY_MAX_ATTEMPTS (`store.max_attempts`)
LEGACY_EMBED_CHARS = 8000  # what a receipt without `chunks` (a previous worker) embedded: the first 8,000 characters


def vector_literal(values):
    return '['+','.join(repr(v) for v in values)+']'


def invalid_chunks(message):
    return MemoryError('invalid_embedding',message,422)


def chunk_rows(store,receipt,text,vector):
    """Validated fragments of an `embed` receipt: ([(ordinal, char_start, char_end, vector)], truncated).

    A receipt without `chunks` (a previous worker) is ONE fragment over what that worker embedded, the first 8,000 characters.
    With `chunks` they must be consecutive from 0, start at 0, leave no gap between neighbours, stay inside the text and, unless
    the receipt declares `chunks_truncated`, end exactly at its end; every vector has the dimensions of the item vector.
    """
    chunks=receipt.get('chunks')
    if chunks is None:
        return [(0,0,min(len(text),LEGACY_EMBED_CHARS),vector)],None
    if not isinstance(chunks,list) or not 1<=len(chunks)<=CHUNK_MAX_LIMIT:
        raise invalid_chunks('Embedding fragments must be a list of 1 to %d entries'%CHUNK_MAX_LIMIT)
    rows,previous_end=[],None
    for expected,chunk in enumerate(chunks):
        if not isinstance(chunk,dict) or chunk.get('ordinal')!=expected:
            raise invalid_chunks('Embedding fragment ordinals must be consecutive from 0')
        start,end=chunk.get('char_start'),chunk.get('char_end')
        if any(isinstance(v,bool) or not isinstance(v,int) for v in (start,end)) or not 0<=start<end<=len(text):
            raise invalid_chunks('Embedding fragment offsets must lie inside the embedded text')
        if (expected==0 and start!=0) or (previous_end is not None and not rows[-1][1]<start<=previous_end):
            raise invalid_chunks('Embedding fragments must cover the text without gaps')
        values=store._vector(chunk.get('vector'))
        if len(values)!=len(vector):
            raise invalid_chunks('Every fragment vector must have the dimensions of the item vector')
        rows.append((expected,start,end,values))
        previous_end=end
    truncated=receipt.get('chunks_truncated') is True
    if truncated:
        if receipt.get('chunks_covered_chars')!=previous_end or previous_end>=len(text):
            raise invalid_chunks('A truncated receipt must say where its coverage ends, before the end of the text')
    elif previous_end!=len(text):
        raise invalid_chunks('Embedding fragments must reach the end of the text unless the receipt declares chunks_truncated')
    return rows,truncated


def stored_item_vector(store,project_id,item_id,resource_type,version,canonical_hash,model):
    """The item vector already stored for exactly this version, hash and model (or None): the backfill keeps it instead of embedding the whole text again,
    unless its dimensions differ from the fragments' (then the worker embeds the text once more, within the job deadline).

    A module function, not a Store method: the public surface of the store (`store_surface.json`) does not change.
    """
    with store.transaction() as c:
        row=c.execute('SELECT vector FROM memory.embeddings WHERE project_id=%s AND item_id=%s AND resource_type=%s AND version=%s AND model=%s AND canonical_hash=%s AND embedding IS NOT NULL',
                      (project_id,item_id,resource_type,version,model,canonical_hash)).fetchone()
        return list(row['vector']) if row and any(row['vector']) else None


def job_outcome(store,job_id,fence):
    """`{state, error_code}` of the job as the database has it for exactly this fence (None when another claim has taken it over): the worker asks it after a write
    whose answer was lost, to tell a write that landed from one that did not. A module function, not a Store method: `store_surface.json` does not change."""
    with store.transaction() as c:
        return c.execute('SELECT state,error_code FROM memory.jobs WHERE id=%s AND fence=%s',(job_id,fence)).fetchone()


class JobsMixin:
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
        # `store.max_attempts` is set by the worker (MEMORY_MAX_ATTEMPTS) and is not a parameter: the signature of the store is frozen (store_surface.json).
        max_attempts=getattr(self,'max_attempts',None)
        if max_attempts is None:  # only "nobody said": a 0 is not turned into the default (MEMORY_MAX_ATTEMPTS is validated to be 1 or more in config.py)
            max_attempts=DEFAULT_MAX_ATTEMPTS
        with self.transaction() as c:
            # Every poisoned job (its lease expired, every attempt it was allowed has been charged) is failed by ONE statement for the whole set, before the choice
            # of the job to claim: the rows are locked by this transaction (SKIP LOCKED: one that another transaction holds is left to it), so nothing sits between the
            # judgement and the write, and the cost does not grow with how many are ahead in the queue. Retired destinations keep their own code below.
            c.execute("UPDATE memory.jobs SET state='failed',error_code='attempts_exhausted',lease_until=NULL WHERE id IN (SELECT id FROM memory.jobs WHERE state='running' AND lease_until<clock_timestamp() AND attempts>=%s AND destination IN ('extract','embed') FOR UPDATE SKIP LOCKED) AND state='running'",(max_attempts,))
            while True:
                row=c.execute("SELECT * FROM memory.jobs WHERE (state IN ('pending','unknown') AND available_at<=clock_timestamp()) OR (state='running' AND lease_until<clock_timestamp()) ORDER BY priority,available_at,created_at,id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
                if not row:
                    return None
                if row['destination'] not in {'extract','embed'}:
                    c.execute("UPDATE memory.jobs SET state='failed',error_code='destination_retired',lease_until=NULL WHERE id=%s",(row['id'],))
                    continue
                if row['state']=='running' and row['attempts']>=max_attempts:
                    # Safety net for a lease that expired BETWEEN the statement above and this choice (microseconds): the same judgement, on the row this transaction
                    # holds locked, instead of claiming it one more time. `retry_job` brings it back. `unknown` and `pending` jobs are not touched: reconciliation and
                    # the retry of a failed job keep their semantics.
                    c.execute("UPDATE memory.jobs SET state='failed',error_code='attempts_exhausted',lease_until=NULL WHERE id=%s AND state='running' AND attempts>=%s",(row['id'],max_attempts))
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
                # The whole receipt is validated BEFORE the first write, and every write below shares this transaction: the item vector and
                # all fragments appear together or not at all.
                table='memory.documents' if row['resource_type']=='document' else 'memory.memory_items'
                column='body' if row['resource_type']=='document' else 'payload'
                source=c.execute('SELECT '+column+' AS source FROM '+table+' WHERE project_id=%s AND id=%s',(row['project_id'],row['item_id'])).fetchone()['source']
                incoming=receipt
                fragments,truncated=chunk_rows(self,receipt,embedding_text(source.get('title',''),source.get('content','')),vector)
                # Double write: `vector` (double precision[]) stays authoritative for rollback; `embedding` serves pgvector.
                # An item vector that already exists for this version, hash and model is the embedding of the same text: it is kept as it is
                # (no rewrite of `vector`/`embedding`); only the flag changes. A different one replaces it.
                c.execute('INSERT INTO memory.embeddings AS e(project_id,item_id,resource_type,version,canonical_hash,model,vector,embedding,chunked) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::vector,true) ON CONFLICT(project_id,item_id,resource_type,version,model) DO UPDATE SET canonical_hash=EXCLUDED.canonical_hash,vector=CASE WHEN e.vector=EXCLUDED.vector AND e.embedding IS NOT NULL THEN e.vector ELSE EXCLUDED.vector END,embedding=CASE WHEN e.vector=EXCLUDED.vector AND e.embedding IS NOT NULL THEN e.embedding ELSE EXCLUDED.embedding END,chunked=true,created_at=CASE WHEN e.vector=EXCLUDED.vector THEN e.created_at ELSE clock_timestamp() END',(row['project_id'],row['item_id'],row['resource_type'],row['version'],row['canonical_hash'],model,vector,vector))
                # The item vectors of older versions are no longer current for anybody: flag them so the partial index of unchunked rows holds only live work.
                c.execute('UPDATE memory.embeddings SET chunked=true WHERE project_id=%s AND item_id=%s AND resource_type=%s AND version<%s AND NOT chunked',(row['project_id'],row['item_id'],row['resource_type'],row['version']))
                # Fragments of this version are replaced as a set; those of older versions of the item are derived data nobody can read any more.
                c.execute('DELETE FROM memory.embedding_chunks WHERE project_id=%s AND item_id=%s AND resource_type=%s AND model=%s AND version<=%s',(row['project_id'],row['item_id'],row['resource_type'],model,row['version']))
                with c.cursor() as cursor:
                    cursor.executemany('INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)',
                        [(row['project_id'],row['item_id'],row['resource_type'],row['version'],row['canonical_hash'],model,ordinal,start,end,vector_literal(values)) for ordinal,start,end,values in fragments])
                receipt={'model':model,'dimensions':len(vector),'hash':digest(vector),'status':'verified','verified':True}
                if incoming.get('chunks') is not None:
                    receipt['chunks']=len(fragments)
                    if truncated:
                        receipt.update(chunks_truncated=True,chunks_covered_chars=fragments[-1][2])
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
