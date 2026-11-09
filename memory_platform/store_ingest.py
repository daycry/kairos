"""Store mixin: event ingestion and fact materialization."""
import json
import uuid
from datetime import datetime, timezone

from .errors import Conflict, Forbidden, MemoryError, NotFound
from .privacy import has_sensitive, sanitize_payload
from .store_common import as_dict, canonical, digest, new_id, clean


class IngestMixin:
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
        heading=payload['title']+' '+payload.get('problem','')+' '+payload.get('correction','')  # weight A; the content weighs B
        c.execute("INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,deleted,search_vector,search_vector_es,search_vector_en,parent_item_id,parent_version,parent_hash) VALUES(%s,%s,%s,%s,'learning',%s::jsonb,%s,%s,%s,false,setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'B'),memory.item_fts('spanish',%s,%s),memory.item_fts('english',%s,%s),%s,%s,%s) ON CONFLICT(project_id,id) DO UPDATE SET version=EXCLUDED.version,canonical_hash=EXCLUDED.canonical_hash,payload=EXCLUDED.payload,deleted=false,superseded_by=NULL,occurred_at=EXCLUDED.occurred_at,search_vector=EXCLUDED.search_vector,search_vector_es=EXCLUDED.search_vector_es,search_vector_en=EXCLUDED.search_vector_en,parent_version=EXCLUDED.parent_version,parent_hash=EXCLUDED.parent_hash",(row['project_id'],derived_id,version,content_hash,canonical(payload),parent['session_id'],parent['agent_id'],parent['occurred_at'],*3*(heading,payload['content']),row['item_id'],row['version'],row['canonical_hash']))
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
            c.execute("INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,deleted,search_vector,search_vector_es,search_vector_en) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'B'),memory.item_fts('spanish',%s,%s),memory.item_fts('english',%s,%s)) ON CONFLICT(project_id,id) DO UPDATE SET version=EXCLUDED.version,canonical_hash=EXCLUDED.canonical_hash,event_type=EXCLUDED.event_type,payload=EXCLUDED.payload,session_id=EXCLUDED.session_id,agent_id=EXCLUDED.agent_id,occurred_at=EXCLUDED.occurred_at,deleted=EXCLUDED.deleted,search_vector=EXCLUDED.search_vector,search_vector_es=EXCLUDED.search_vector_es,search_vector_en=EXCLUDED.search_vector_en", (pid,iid,event['version'],content_hash,event['event_type'],canonical(payload),event['session_id'],event['agent_id'],occurred,deleted,payload.get('title',''),payload.get('problem','')+' '+payload.get('correction',''),payload.get('content',''),*2*(payload.get('title','')+' '+payload.get('problem','')+' '+payload.get('correction',''),payload.get('content',''))))
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
