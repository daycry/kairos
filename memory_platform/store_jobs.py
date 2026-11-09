"""Store mixin: job queue, leases and receipts."""

from .errors import MemoryError, NotFound
from .privacy import has_sensitive, sanitize_payload
from .store_common import canonical, digest, clean


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
