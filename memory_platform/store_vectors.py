"""Store mixin: exact vector candidates and cosine search."""
import math
import bisect
import time
import uuid

from .errors import MemoryError
from .store_common import canonical


class VectorsMixin:
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
