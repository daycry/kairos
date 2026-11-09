"""Store mixin: pgvector cosine search (HNSW route and exact SQL route) and index migration."""
import hashlib
import math
import time

from .config import EXACT_CANDIDATE_LIMIT, HNSW_EF_SEARCH, HNSW_MAX_SCAN_TUPLES, vector_indexes
from .errors import MemoryError
from .store_common import canonical


def migrate_vector_indexes(connection):
    """Partial HNSW index per configured (model, dimensions); caller owns the migration transaction."""
    from psycopg import sql
    for model, dims in vector_indexes():
        name='memory_embedding_hnsw_'+hashlib.sha256(f'{model}:{dims}'.encode('utf-8')).hexdigest()[:16]
        if connection.execute("SELECT 1 FROM pg_indexes WHERE schemaname='memory' AND tablename='embeddings' AND indexname=%s",(name,)).fetchone():
            continue  # already built: do not even ask for the table lock
        connection.execute(sql.SQL('CREATE INDEX {} ON memory.embeddings USING hnsw ((embedding::vector({})) vector_cosine_ops) WHERE model={} AND dims={}').format(
            sql.Identifier(name),sql.SQL(str(dims)),sql.Literal(model),sql.Literal(dims)))


# Current resource behind an embedding row: same version and hash, not deleted or superseded, parent still
# current, category/tag filters. Parameters: categories x2, tags x2, categories x2, tags x2.
CURRENT_RESOURCE = """(
    (e.resource_type='item' AND EXISTS (
        SELECT 1 FROM memory.memory_items i LEFT JOIN memory.memory_items p ON p.project_id=i.project_id AND p.id=i.parent_item_id
        WHERE i.project_id=e.project_id AND i.id=e.item_id AND i.version=e.version AND i.canonical_hash=e.canonical_hash
        AND NOT i.deleted AND i.superseded_by IS NULL
        AND (i.parent_item_id IS NULL OR (p.version=i.parent_version AND p.canonical_hash=i.parent_hash AND NOT p.deleted AND p.superseded_by IS NULL))
        AND (%s::text[] IS NULL OR i.payload->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (i.payload->'tags') ?| %s)))
    OR (e.resource_type='document' AND EXISTS (
        SELECT 1 FROM memory.documents d
        WHERE d.project_id=e.project_id AND d.id=e.item_id AND d.version=e.version AND d.canonical_hash=e.canonical_hash AND NOT d.deleted
        AND (%s::text[] IS NULL OR d.body->>'category'=ANY(%s)) AND (%s::text[] IS NULL OR (d.body->'tags') ?| %s))))"""
LAYER = "CASE e.resource_type WHEN 'item' THEN 'episodic' ELSE 'documental' END"
COLUMNS = 'e.project_id,e.item_id,e.resource_type,e.version,e.canonical_hash'


def vector_text(unit):
    return '['+','.join(repr(v) for v in unit)+']'


class VectorResults(list):
    """Hits of one search plus what the hits alone cannot say (an empty answer can still be truncated)."""
    candidate_limit = EXACT_CANDIDATE_LIMIT
    candidates_truncated = False


def vector_results(hits,candidate_limit,truncated):
    results=VectorResults(hits)
    results.candidate_limit,results.candidates_truncated=candidate_limit,truncated
    return results


def rank_ann(c,projects,model,dims,unit,categories,tags,size,arm=lambda:None):
    """Top `size` by cosine through the partial HNSW index (iterative scan), same filters as the exact route.

    Returns (rows, candidate_limit, truncated). A short answer is judged against the AUTHORIZED population only
    (never the volume of other projects): up to EXACT_CANDIDATE_LIMIT embeddings it is recomputed exactly (an
    approximate index can leave heavily duplicated vectors unreachable); above it the answer is returned as
    truncated, because the scan may have stopped at hnsw.max_scan_tuples before filling `size`.
    """
    from psycopg import sql
    for name,value in (('hnsw.iterative_scan','relaxed_order'),('hnsw.max_scan_tuples',str(HNSW_MAX_SCAN_TUPLES)),('hnsw.ef_search',str(HNSW_EF_SEARCH))):
        c.execute('SELECT set_config(%s,%s,true)',(name,value))
    width=sql.SQL(str(int(dims)))
    distance=sql.SQL('e.embedding::vector({})').format(width)
    query=sql.SQL('SELECT '+COLUMNS+', 1 - ({d} <=> %s::vector({n})) AS score FROM memory.embeddings e WHERE e.model={m} AND e.dims={n} AND e.project_id=ANY(%s) AND vector_norm(e.embedding)>0 AND '+CURRENT_RESOURCE+
                  ' ORDER BY {d} <=> %s::vector({n}), e.project_id, '+LAYER+', e.item_id LIMIT %s').format(d=distance,n=width,m=sql.Literal(model))
    text=vector_text(unit)
    arm()
    rows=c.execute(query,[text,projects,categories,categories,tags,tags,categories,categories,tags,tags,text,size]).fetchall()
    truncated=False
    if len(rows)<size:
        arm()
        # Current rows only (same filters as the ranking): old versions and withdrawn items must not push a small
        # corpus over the exact route's limit. project_id leads the index, so the scan stays inside the authorized rows.
        authorized=c.execute('SELECT count(*) AS n FROM (SELECT 1 FROM memory.embeddings e WHERE e.project_id=ANY(%s) AND e.model=%s AND e.dims=%s AND '+CURRENT_RESOURCE+' LIMIT %s) s',
                             [projects,model,dims,categories,categories,tags,tags,categories,categories,tags,tags,EXACT_CANDIDATE_LIMIT+1]).fetchone()['n']
        if authorized<=EXACT_CANDIDATE_LIMIT:
            return rank_exact(c,projects,model,dims,unit,categories,tags,size,arm)
        truncated=True
    return rows,HNSW_MAX_SCAN_TUPLES,truncated


def rank_exact(c,projects,model,dims,unit,categories,tags,size,arm=lambda:None):
    """Exact cosine in SQL over the first EXACT_CANDIDATE_LIMIT current candidates (stable identity order).

    Returns (rows, candidate_limit, truncated); `truncated` means more candidates existed than were scored.
    """
    query='''WITH cand AS (
        SELECT '''+COLUMNS+''',e.embedding AS emb FROM memory.embeddings e
        WHERE e.model=%s AND e.dims=%s AND e.project_id=ANY(%s) AND '''+CURRENT_RESOURCE+'''
        ORDER BY e.project_id,e.resource_type,e.item_id LIMIT %s),
    numbered AS (SELECT cand.*,row_number() OVER (ORDER BY project_id,resource_type,item_id) AS ordinal FROM cand)
    SELECT project_id,item_id,resource_type,version,canonical_hash,1 - (emb <=> %s::vector) AS score,
        (SELECT count(*) FROM cand)>%s AS truncated
    FROM numbered e WHERE ordinal<=%s AND vector_norm(emb)>0
    ORDER BY emb <=> %s::vector, project_id, '''+LAYER+''', item_id LIMIT %s'''
    text=vector_text(unit)
    arm()
    rows=c.execute(query,[model,dims,projects,categories,categories,tags,tags,categories,categories,tags,tags,EXACT_CANDIDATE_LIMIT+1,
                          text,EXACT_CANDIDATE_LIMIT,EXACT_CANDIDATE_LIMIT,text,size]).fetchall()
    return rows,EXACT_CANDIDATE_LIMIT,bool(rows and rows[0]['truncated'])


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
        """Current embedded resources (with payload) for `model`; used by readiness and the final payload fetch.

        `stream` is accepted and ignored: it kept the private surface (CA-05) unchanged when the cursor went away.
        """
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
        ) SELECT """+COLUMNS+""",r.payload,r.current_row FROM current_resources r JOIN memory.embeddings e
            ON e.project_id=r.project_id AND e.item_id=r.id AND e.resource_type=r.resource_type
            AND e.version=r.version AND e.canonical_hash=r.canonical_hash
            WHERE e.model=%s AND (%s::text[] IS NULL OR r.payload->>'category'=ANY(%s))
            AND (%s::text[] IS NULL OR (r.payload->'tags') ?| %s)
            """+selection+""" ORDER BY e.project_id,e.resource_type,e.item_id LIMIT %s"""
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
        """Cosine top-k over authorized current embeddings.

        Indexed (model, dimensions) from MEMORY_VECTOR_INDEXES use the partial HNSW index with iterative scan;
        any other model or dimension uses the exact SQL route (first 10,000 candidates). Both apply the same
        permission, current-version and hash filters, and the final payload fetch re-checks authorization.
        """
        if isinstance(project_ids,str):
            project_ids=[project_ids]
        if not project_ids:
            return VectorResults()
        def remaining():
            if deadline is None:
                return None
            seconds=deadline-time.monotonic()
            if seconds<=0:
                raise MemoryError('semantic_deadline_exceeded','Semantic query exceeded its time budget',503)
            return max(1,math.ceil(seconds*1000))
        remaining()
        def arm():
            # Re-armed before every statement: what is left of the deadline, never the whole budget again.
            if deadline is not None:
                c.execute("SELECT set_config('statement_timeout',%s,true)",(str(remaining()),))
        with self.transaction() as c:
            arm()
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            query=self._unit(self._vector(vector,allow_zero=True))
            if query is None:
                return VectorResults()
            size=min(max(limit,1),100)
            route=rank_ann if (model,len(query)) in vector_indexes() else rank_exact
            winners,candidate_limit,truncated=route(c,project_ids,model,len(query),query,categories or None,tags or None,size,arm)
            if not winners:
                return vector_results([],candidate_limit,truncated)
            # Recheck current authorization and current versions at payload fetch.
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            identities=[{key:str(value[key]) for key in ('project_id','item_id','resource_type')} for value in winners]
            arm()
            current=self._vector_candidates(c,project_ids,model,categories or None,tags or None,size,identities=identities)
        by_id={(row['project_id'],str(row['item_id']),row['resource_type']):row for row in current}
        ranked=vector_results([],candidate_limit,truncated)
        for winner in winners:
            candidate=by_id.get((winner['project_id'],str(winner['item_id']),winner['resource_type']))
            if not candidate or any(candidate[field]!=winner[field] for field in ('version','canonical_hash')):
                continue
            score=max(-1.0,min(1.0,float(winner['score'])))
            if candidate['resource_type']=='item':
                hit=self._item(candidate['current_row'])
            else:
                hit=dict(candidate['payload'],project_id=candidate['project_id'],item_id=candidate['item_id'],document_id=candidate['item_id'],version=candidate['version'],canonical_hash=candidate['canonical_hash'],layer='documental',ref=f"documental:{candidate['project_id']}:{candidate['item_id']}:{candidate['version']}",excerpt=candidate['payload'].get('content','')[:500],validation_status=candidate['payload'].get('validation',{}).get('status','unknown'),index_status='ready')
            hit.update(score=score,embedding_model=model,candidate_limit=candidate_limit,candidates_truncated=truncated)
            ranked.append(hit)
        return ranked
