"""Store mixin: timeline, native facts and graph data."""
import hashlib

from .errors import NotFound
from .store_common import as_dict, clean, fts_inline

FACT_TEXT="concat_ws(' ',f.fact->>'subject',f.fact->>'predicate',f.fact->>'object',f.fact->>'evidence_quote')"


class GraphMixin:
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
            rows=c.execute(f"""SELECT i.project_id,i.id,i.version,i.canonical_hash,i.payload,i.occurred_at,f.fact,f.ordinality FROM memory.memory_items i
                CROSS JOIN LATERAL jsonb_array_elements(COALESCE(i.payload->'facts','[]'::jsonb)) WITH ORDINALITY AS f(fact,ordinality)
                JOIN memory.projects p ON p.id=i.project_id
                WHERE i.project_id=ANY(%s) AND NOT i.deleted AND i.superseded_by IS NULL
                AND COALESCE((p.policy->>'temporal_projection')::boolean,false)
                AND (%s::text[] IS NULL OR i.payload->>'category'=ANY(%s))
                AND (%s::text[] IS NULL OR (i.payload->'tags') ?| %s)
                AND (%s='' OR {fts_inline(FACT_TEXT)})
                ORDER BY (i.payload->>'validation_status'='validated') DESC,i.occurred_at DESC,i.project_id,i.id,f.ordinality LIMIT %s""",(project_ids,categories,categories,tags,tags,q,q,q,q,min(max(limit,1),100))).fetchall()
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
                if item.get('lexical_match'):
                    continue  # graph nodes come from exact lexical matches only; approximate title matches would be unmarked nodes
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
