"""Store mixin: pgvector cosine search (HNSW route and exact SQL route) and index migration."""
import hashlib
import math
import time

from .config import EXACT_CANDIDATE_LIMIT, chunk_settings, HNSW_EF_SEARCH, HNSW_MAX_SCAN_TUPLES, exact_fallback_ms, vector_indexes
from .chunking import embedding_text
from .errors import MemoryError
from .auth_scope import savepoint
from .store_common import canonical


def migrate_vector_indexes(connection):
    """Partial HNSW index per configured (model, dimensions) on `embeddings` and on `embedding_chunks` (once that table exists).

    Caller owns the migration transaction.
    """
    from psycopg import sql
    for table,prefix in (('embeddings','memory_embedding_hnsw_'),('embedding_chunks','memory_chunk_hnsw_')):
        if table=='embedding_chunks' and not connection.execute("SELECT 1 WHERE to_regclass('memory.embedding_chunks') IS NOT NULL").fetchone():
            continue  # a database still in the previous version: the table arrives with schema.sql version 10
        for model, dims in vector_indexes():
            name=prefix+hashlib.sha256(f'{model}:{dims}'.encode('utf-8')).hexdigest()[:16]
            if connection.execute("SELECT 1 FROM pg_indexes WHERE schemaname='memory' AND tablename=%s AND indexname=%s",(table,name)).fetchone():
                continue  # already built: do not even ask for the table lock
            connection.execute(sql.SQL('CREATE INDEX {} ON {} USING hnsw ((embedding::vector({})) vector_cosine_ops) WHERE model={} AND dims={}').format(
                sql.Identifier(name),sql.Identifier('memory',table),sql.SQL(str(dims)),sql.Literal(model),sql.Literal(dims)))


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
CHUNK_COLUMNS = COLUMNS+',e.ordinal,e.char_start,e.char_end'
CHUNK_OVERFETCH = 5  # fragments fetched per requested item at first: several fragments of one item can crowd the top
CHUNK_FETCH_CAP = 2000  # a crowded answer widens the fetch (x4) up to this many fragments; beyond it the answer is reported truncated
# Resources that already have fragments are answered by their fragments only; the item-level row answers the others (not yet backfilled,
# or written by a previous release): `embeddings.chunked` is true when the row was written together with its fragments.
UNCHUNKED = " AND NOT e.chunked"
# Identities (project, item, type) the item route is restricted to; parameters: item ids, projects, item ids, types (see rank_exact `only`).
ONLY_IDENTITIES = " AND e.item_id=ANY(%s) AND EXISTS (SELECT 1 FROM unnest(%s::text[],%s::text[],%s::text[]) AS u(p,i,t) WHERE u.p=e.project_id AND u.i=e.item_id AND u.t=e.resource_type)"
UNCHUNKED_ONLY_LIMIT = 500  # up to this many current resources without fragments are scored by themselves; more and the item route scans the scope
CHUNK_EXACT_FACTOR = 10  # exact route over fragments: up to this many fragments per candidate element (EXACT_CANDIDATE_LIMIT x factor), see docs/operations.md


def chunk_candidate_limit():
    return EXACT_CANDIDATE_LIMIT*CHUNK_EXACT_FACTOR


class FallbackBudget:
    """ONE exact-fallback allowance (MEMORY_VECTOR_EXACT_FALLBACK_MS) for the whole search: the routes share it, they do not each get their own."""
    def __init__(self):
        self.left = exact_fallback_ms()

    def spend(self, started):
        self.left = max(0, self.left-math.ceil((time.monotonic()-started)*1000))


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


def rank_ann(c,projects,model,dims,unit,categories,tags,size,arm=lambda cap=None:None,skip_chunked=False,budget=None):
    """Top `size` by cosine through the partial HNSW index (iterative scan), same filters as the exact route.

    Returns (rows, candidate_limit, truncated). A short answer is checked with ONE bounded traversal of the
    authorized rows, the exact route (`truncated` there = more than EXACT_CANDIDATE_LIMIT current candidates):
    within the limit its result replaces the index rows (an approximate index can leave heavily duplicated vectors
    unreachable); above it, or when the fallback exhausts its own budget (MEMORY_VECTOR_EXACT_FALLBACK_MS, capped by
    what is left of the deadline), the index rows are returned flagged `truncated` and the caller reports `partial`.
    The fallback runs in a savepoint, so its cancellation leaves the transaction usable. If the GLOBAL deadline is
    what ran out, `semantic_deadline_exceeded` propagates as before.
    """
    from psycopg import errors, sql
    for name,value in (('hnsw.iterative_scan','relaxed_order'),('hnsw.max_scan_tuples',str(HNSW_MAX_SCAN_TUPLES)),('hnsw.ef_search',str(HNSW_EF_SEARCH))):
        c.execute('SELECT set_config(%s,%s,true)',(name,value))
    width=sql.SQL(str(int(dims)))
    distance=sql.SQL('e.embedding::vector({})').format(width)
    query=sql.SQL('SELECT '+COLUMNS+', 1 - ({d} <=> %s::vector({n})) AS score FROM memory.embeddings e WHERE e.model={m} AND e.dims={n} AND e.project_id=ANY(%s) AND vector_norm(e.embedding)>0 AND '+CURRENT_RESOURCE+(UNCHUNKED if skip_chunked else '')+
                  ' ORDER BY {d} <=> %s::vector({n}), e.project_id, '+LAYER+', e.item_id LIMIT %s').format(d=distance,n=width,m=sql.Literal(model))
    text=vector_text(unit)
    arm()
    rows=c.execute(query,[text,projects,categories,categories,tags,tags,categories,categories,tags,tags,text,size]).fetchall()
    if len(rows)>=size:
        return rows,HNSW_MAX_SCAN_TUPLES,False
    budget=budget or FallbackBudget()
    if budget.left<=0:
        return rows,HNSW_MAX_SCAN_TUPLES,True  # another route of this search spent the whole allowance: say so, do not run it again
    started=time.monotonic()
    try:
        with savepoint(c):  # savepoint: a cancelled fallback is rolled back, the transaction stays usable
            exact=rank_exact(c,projects,model,dims,unit,categories,tags,size,lambda:arm(budget.left),**({'skip_chunked':True} if skip_chunked else {}))
    except errors.QueryCanceled:
        budget.spend(started)
        arm()  # the global deadline expired -> semantic_deadline_exceeded; otherwise only the fallback budget did
        return rows,HNSW_MAX_SCAN_TUPLES,True
    budget.spend(started)
    arm()  # drop the fallback's own timeout for the statements that follow
    if exact[2]:
        return rows,HNSW_MAX_SCAN_TUPLES,True
    return exact


def rank_exact(c,projects,model,dims,unit,categories,tags,size,arm=lambda cap=None:None,skip_chunked=False,budget=None,only=None):
    """Exact cosine in SQL over the first EXACT_CANDIDATE_LIMIT current candidates (stable identity order).

    Returns (rows, candidate_limit, truncated); `truncated` means more candidates existed than were scored. `only` restricts it to those
    identities (project_id, item_id, resource_type), the few resources the probe found without fragments.
    """
    query='''WITH cand AS (
        SELECT '''+COLUMNS+''',e.embedding AS emb FROM memory.embeddings e
        WHERE e.model=%s AND e.dims=%s AND e.project_id=ANY(%s) AND '''+CURRENT_RESOURCE+(UNCHUNKED if skip_chunked else '')+(ONLY_IDENTITIES if only else '')+'''
        ORDER BY e.project_id,e.resource_type,e.item_id LIMIT %s),
    numbered AS (SELECT cand.*,row_number() OVER (ORDER BY project_id,resource_type,item_id) AS ordinal FROM cand)
    SELECT project_id,item_id,resource_type,version,canonical_hash,1 - (emb <=> %s::vector) AS score,
        (SELECT count(*) FROM cand)>%s AS truncated
    FROM numbered e WHERE ordinal<=%s AND vector_norm(emb)>0
    ORDER BY emb <=> %s::vector, project_id, '''+LAYER+''', item_id LIMIT %s'''
    text=vector_text(unit)
    arm()
    scope=[[i[1] for i in only],[i[0] for i in only],[i[1] for i in only],[i[2] for i in only]] if only else []
    rows=c.execute(query,[model,dims,projects,categories,categories,tags,tags,categories,categories,tags,tags,*scope,EXACT_CANDIDATE_LIMIT+1,
                          text,EXACT_CANDIDATE_LIMIT,EXACT_CANDIDATE_LIMIT,text,size]).fetchall()
    return rows,EXACT_CANDIDATE_LIMIT,bool(rows and rows[0]['truncated'])


def best_per_item(rows,size,fetch):
    """Best fragment per item from fragments in rank order: ([rows], saturated).

    `saturated` means the fetch was filled yet fewer than `size` distinct items came out of it: fragments of a few items may
    have crowded the rest out. The ANN route then widens the fetch; only a saturated fetch at CHUNK_FETCH_CAP is reported truncated.
    """
    seen,best=set(),[]
    for row in rows:
        key=(row['project_id'],str(row['item_id']),row['resource_type'])
        if key in seen:
            continue
        seen.add(key)
        best.append(row)
    return best[:size],len(rows)>=fetch and len(best)<size


def chunk_exact_rows(c,projects,model,dims,unit,categories,tags,size,arm=lambda cap=None:None):
    """Exact cosine over the first `chunk_candidate_limit()` current fragments: (best fragment per item, candidates_truncated, saturated)."""
    fetch=CHUNK_FETCH_CAP
    cap=chunk_candidate_limit()
    query='''WITH cand AS (
        SELECT '''+CHUNK_COLUMNS+''',e.embedding AS emb FROM memory.embedding_chunks e
        WHERE e.model=%s AND e.dims=%s AND e.project_id=ANY(%s) AND '''+CURRENT_RESOURCE+'''
        ORDER BY e.project_id,e.resource_type,e.item_id,e.ordinal LIMIT %s),
    numbered AS (SELECT cand.*,row_number() OVER (ORDER BY project_id,resource_type,item_id,ordinal) AS position FROM cand)
    SELECT project_id,item_id,resource_type,version,canonical_hash,ordinal,char_start,char_end,1 - (emb <=> %s::vector) AS score,
        ((SELECT count(*) FROM cand)>%s OR (SELECT count(DISTINCT (project_id,resource_type,item_id)) FROM cand)>%s) AS truncated
    FROM numbered e WHERE position<=%s AND vector_norm(emb)>0
    ORDER BY emb <=> %s::vector, project_id, '''+LAYER+''', item_id, ordinal LIMIT %s'''
    text=vector_text(unit)
    arm()
    rows=c.execute(query,[model,dims,projects,categories,categories,tags,tags,categories,categories,tags,tags,cap+1,
                          text,cap,EXACT_CANDIDATE_LIMIT,cap,text,fetch]).fetchall()
    best,saturated=best_per_item(rows,size,fetch)
    return best,bool(rows and rows[0]['truncated']),saturated


def rank_chunks_exact(c,projects,model,dims,unit,categories,tags,size,arm=lambda cap=None:None,budget=None):
    """The exact route over fragments. Returns (rows, candidate_limit, truncated); one row per item, its best fragment."""
    rows,candidates_truncated,saturated=chunk_exact_rows(c,projects,model,dims,unit,categories,tags,size,arm)
    return rows,EXACT_CANDIDATE_LIMIT,candidates_truncated or saturated  # reported in elements; the scan itself is bounded in fragments


def rank_chunks_ann(c,projects,model,dims,unit,categories,tags,size,arm=lambda cap=None:None,budget=None):
    """Top fragments through the partial HNSW index of `embedding_chunks`, aggregated to the best fragment of each item.

    Same contract and same bounded exact fallback as `rank_ann` (a short index answer is re-checked with ONE exact traversal in a
    savepoint under its own statement_timeout); the fetch starts at `size * CHUNK_OVERFETCH` fragments and widens while fragments of a few items crowd it.
    """
    from psycopg import errors, sql
    for name,value in (('hnsw.iterative_scan','relaxed_order'),('hnsw.max_scan_tuples',str(HNSW_MAX_SCAN_TUPLES)),('hnsw.ef_search',str(HNSW_EF_SEARCH))):
        c.execute('SELECT set_config(%s,%s,true)',(name,value))
    width=sql.SQL(str(int(dims)))
    distance=sql.SQL('e.embedding::vector({})').format(width)
    query=sql.SQL('SELECT '+CHUNK_COLUMNS+', 1 - ({d} <=> %s::vector({n})) AS score FROM memory.embedding_chunks e WHERE e.model={m} AND e.dims={n} AND e.project_id=ANY(%s) AND vector_norm(e.embedding)>0 AND '+CURRENT_RESOURCE+
                  ' ORDER BY {d} <=> %s::vector({n}), e.project_id, '+LAYER+', e.item_id, e.ordinal LIMIT %s').format(d=distance,n=width,m=sql.Literal(model))
    text=vector_text(unit)
    fetch=min(size*CHUNK_OVERFETCH,CHUNK_FETCH_CAP)
    while True:
        arm()
        raw=c.execute(query,[text,projects,categories,categories,tags,tags,categories,categories,tags,tags,text,fetch]).fetchall()
        index_rows,saturated=best_per_item(raw,size,fetch)
        if not saturated or fetch>=CHUNK_FETCH_CAP:
            break
        fetch=min(fetch*4,CHUNK_FETCH_CAP)  # fragments of a few items filled the fetch: look further before saying anything
    if len(raw)>=fetch:
        return index_rows,HNSW_MAX_SCAN_TUPLES,saturated
    budget=budget or FallbackBudget()
    if budget.left<=0:
        return index_rows,HNSW_MAX_SCAN_TUPLES,True
    started=time.monotonic()
    try:
        with savepoint(c):
            exact,candidates_truncated,exact_saturated=chunk_exact_rows(c,projects,model,dims,unit,categories,tags,size,lambda:arm(budget.left))
    except errors.QueryCanceled:
        budget.spend(started)
        arm()
        return index_rows,HNSW_MAX_SCAN_TUPLES,True
    budget.spend(started)
    arm()
    if candidates_truncated:
        return index_rows,HNSW_MAX_SCAN_TUPLES,True
    return exact,EXACT_CANDIDATE_LIMIT,exact_saturated


def chunk_view(payload,winner):
    """(matched_chunk, excerpt) of a winning fragment, or None when it adds nothing (the fragment is the whole embedded text).

    Fragments store offsets, not text, so the text is recomputed from the current resource. The excerpt is the fragment without the
    title (the title is already shown next to it), at most MEMORY_CHUNK_CHARS: also for receipts of a previous worker, whose single
    fragment spans up to 8,000 characters. Offsets are Unicode code points (Python `str` indexes) of title + newline + content.
    """
    title=payload.get('title','')
    title='' if title is None else str(title)
    text=embedding_text(title,payload.get('content',''))
    start,end=winner['char_start'],winner['char_end']
    if start==0 and end>=len(text):
        return None
    body=text[max(start,len(title)+1):end].strip()[:chunk_settings()[0]]
    return {'ordinal':winner['ordinal'],'char_start':start,'char_end':end},(body or None)


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
        selection,wanted_items,wanted_documents='','',''
        params=[projects]
        if identities is not None:
            # The rows to serialize (`to_jsonb`) are chosen by identity first: the winners' ids, not every current resource of the projects (B-09).
            ids=sorted({str(identity['item_id']) for identity in identities})
            wanted_items,wanted_documents=' AND i.id=ANY(%s)',' AND d.id=ANY(%s)'
            params.append(ids)
        params.append(projects)
        if identities is not None:
            params.append(ids)
        params.extend([model,categories,categories,tags,tags])
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
            WHERE i.project_id=ANY(%s)"""+wanted_items+""" AND NOT i.deleted AND i.superseded_by IS NULL
            AND (i.parent_item_id IS NULL OR (p.version=i.parent_version AND p.canonical_hash=i.parent_hash AND NOT p.deleted AND p.superseded_by IS NULL))
            UNION ALL
            SELECT d.project_id,d.id,d.version,d.canonical_hash,'document'::text,d.body,to_jsonb(d)
            FROM memory.documents d WHERE d.project_id=ANY(%s)"""+wanted_documents+""" AND NOT d.deleted
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
            # A probe, not a candidate query: no row of any resource is serialized to answer "is there anything embedded in scope" (B-09).
            return c.execute('SELECT EXISTS (SELECT 1 FROM memory.embeddings e WHERE e.project_id=ANY(%s) AND e.model=%s AND '+CURRENT_RESOURCE+') AS found',
                             (project_ids,model,None,None,None,None,None,None,None,None)).fetchone()['found']

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
        baseline=[]
        def arm(cap=None):
            # Re-armed before every statement: what is left of the deadline (never the whole budget again), further
            # capped by `cap` (the exact fallback's own budget) when one is given.
            milliseconds=remaining()
            if cap is not None:
                milliseconds=cap if milliseconds is None else min(milliseconds,cap)
                if deadline is None and not baseline:
                    baseline.append(c.execute("SELECT current_setting('statement_timeout') AS value").fetchone()['value'])
            elif milliseconds is None and baseline:
                c.execute("SELECT set_config('statement_timeout',%s,true)",(baseline[0],))  # back to what the session had
                return
            if milliseconds is not None:
                c.execute("SELECT set_config('statement_timeout',%s,true)",(str(milliseconds),))
        with self.transaction() as c:
            arm()
            for pid in project_ids:
                self._require(c,actor,pid,'read')
            query=self._unit(self._vector(vector,allow_zero=True))
            if query is None:
                return VectorResults()
            size=min(max(limit,1),100)
            indexed=(model,len(query)) in vector_indexes()
            route=rank_ann if indexed else rank_exact
            cats,tgs=categories or None,tags or None
            # Fragments exist for this scope only after the worker (or `admin backfill-chunks`) wrote them. Each route runs only when it has
            # something to answer, probed through an index: the fragment route when any fragment exists, the item-vector route (rows not
            # written with fragments: not backfilled yet, or written by a previous release) when any current resource still lacks them. Once
            # everything is chunked the item route never runs, so it never pays an index traversal that cannot return anything.
            chunked=c.execute('SELECT 1 FROM memory.embedding_chunks WHERE project_id=ANY(%s) AND model=%s AND dims=%s LIMIT 1',(project_ids,model,len(query))).fetchone() is not None
            # The probe also names (up to a cap) the resources without fragments: while there are few the item route scores only those.
            pending=c.execute('SELECT e.project_id,e.item_id,e.resource_type FROM memory.embeddings e WHERE e.project_id=ANY(%s) AND e.model=%s AND e.dims=%s AND NOT e.chunked AND '+CURRENT_RESOURCE+' LIMIT %s',
                              (project_ids,model,len(query),cats,cats,tgs,tgs,cats,cats,tgs,tgs,UNCHUNKED_ONLY_LIMIT+1)).fetchall()
            unchunked=bool(pending)
            few=[(row['project_id'],str(row['item_id']),row['resource_type']) for row in pending] if chunked and 0<len(pending)<=UNCHUNKED_ONLY_LIMIT else None
            budget=FallbackBudget()  # ONE exact-fallback allowance for both routes
            winners,candidate_limit,truncated=[],EXACT_CANDIDATE_LIMIT,False
            if unchunked:
                if few:  # a handful of resources without fragments (e.g. a failed job) must not cost the whole scope an item-vector scan
                    winners,candidate_limit,truncated=rank_exact(c,project_ids,model,len(query),query,cats,tgs,size,arm,budget=budget,skip_chunked=True,only=few)
                else:
                    winners,candidate_limit,truncated=route(c,project_ids,model,len(query),query,cats,tgs,size,arm,budget=budget,**({'skip_chunked':True} if chunked else {}))
            if chunked:
                fragments,fragment_limit,fragment_truncated=(rank_chunks_ann if indexed else rank_chunks_exact)(c,project_ids,model,len(query),query,cats,tgs,size,arm,budget=budget)
                best={}
                for row in [*winners,*fragments]:  # one hit per element: its best row, whichever route found it
                    key=(row['project_id'],str(row['item_id']),row['resource_type'])
                    if key not in best or float(row['score'])>float(best[key]['score']):
                        best[key]=row
                winners=sorted(best.values(),key=lambda row:(-float(row['score']),row['project_id'],'episodic' if row['resource_type']=='item' else 'documental',str(row['item_id'])))[:size]
                candidate_limit,truncated=(max(candidate_limit,fragment_limit) if unchunked else fragment_limit),truncated or fragment_truncated
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
            if winner.get('ordinal') is not None:
                view=chunk_view(candidate['payload'],winner)
                if view:
                    hit['matched_chunk']=view[0]
                    if view[1]:
                        hit['excerpt']=view[1]
            hit.update(score=score,embedding_model=model,candidate_limit=candidate_limit,candidates_truncated=truncated)
            ranked.append(hit)
        return ranked
