CREATE SCHEMA IF NOT EXISTS memory;
CREATE TABLE IF NOT EXISTS memory.schema_versions(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE IF NOT EXISTS memory.actors(id text PRIMARY KEY, username text UNIQUE NOT NULL, password_hash text NOT NULL, is_admin boolean NOT NULL DEFAULT false, disabled boolean NOT NULL DEFAULT false);
CREATE TABLE IF NOT EXISTS memory.projects(id text PRIMARY KEY, title text NOT NULL, policy jsonb NOT NULL DEFAULT '{"capture_mode":"off","temporal_projection":false}', mapping jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS memory.project_grants(actor_id text NOT NULL REFERENCES memory.actors(id), project_id text NOT NULL REFERENCES memory.projects(id), permission text NOT NULL CHECK(permission IN ('read','write','publish','validate','admin')), PRIMARY KEY(actor_id,project_id,permission));
CREATE TABLE IF NOT EXISTS memory.api_keys(id text PRIMARY KEY, actor_id text NOT NULL REFERENCES memory.actors(id), name text NOT NULL, token_hash text UNIQUE NOT NULL, prefix text NOT NULL, project_ids jsonb NOT NULL, scopes jsonb NOT NULL, expires_at timestamptz, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE IF NOT EXISTS memory.web_sessions(id text PRIMARY KEY, actor_id text NOT NULL REFERENCES memory.actors(id), token_hash text UNIQUE NOT NULL, csrf_hash text NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz);
CREATE TABLE IF NOT EXISTS memory.login_attempts(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, username text NOT NULL, client_ip text NOT NULL, happened_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE INDEX IF NOT EXISTS login_attempt_time ON memory.login_attempts(happened_at);
CREATE TABLE IF NOT EXISTS memory.audit_events(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, actor_id text, action text NOT NULL, project_id text, resource_id text, happened_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE IF NOT EXISTS memory.events(id text PRIMARY KEY, project_id text NOT NULL REFERENCES memory.projects(id), canonical_hash text NOT NULL, body jsonb NOT NULL, receipt jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE IF NOT EXISTS memory.sessions(project_id text NOT NULL REFERENCES memory.projects(id), id text NOT NULL, agent_id text NOT NULL, started_at timestamptz NOT NULL, ended_at timestamptz, PRIMARY KEY(project_id,id));
CREATE TABLE IF NOT EXISTS memory.memory_items(project_id text NOT NULL REFERENCES memory.projects(id), id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, event_type text NOT NULL, payload jsonb NOT NULL, session_id text NOT NULL, agent_id text NOT NULL, occurred_at timestamptz NOT NULL, deleted boolean NOT NULL DEFAULT false, superseded_by text, search_vector tsvector NOT NULL, PRIMARY KEY(project_id,id));
CREATE INDEX IF NOT EXISTS memory_item_search ON memory.memory_items USING gin(search_vector);
CREATE TABLE IF NOT EXISTS memory.item_versions(project_id text NOT NULL, item_id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, body jsonb NOT NULL, PRIMARY KEY(project_id,item_id,version));
CREATE TABLE IF NOT EXISTS memory.documents(project_id text NOT NULL REFERENCES memory.projects(id), id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, body jsonb NOT NULL, deleted boolean NOT NULL DEFAULT false, PRIMARY KEY(project_id,id));
CREATE TABLE IF NOT EXISTS memory.document_versions(project_id text NOT NULL, document_id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, body jsonb NOT NULL, PRIMARY KEY(project_id,document_id,version));
CREATE TABLE IF NOT EXISTS memory.jobs(id text PRIMARY KEY, project_id text NOT NULL REFERENCES memory.projects(id), item_id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, resource_type text NOT NULL, destination text NOT NULL, operation text NOT NULL, state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','succeeded','failed','unknown')), attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT clock_timestamp(), lease_until timestamptz, worker_id text, fence bigint NOT NULL DEFAULT 0, error_code text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(project_id,item_id,version,resource_type,destination,operation));
CREATE INDEX IF NOT EXISTS memory_job_queue ON memory.jobs(state,available_at);
CREATE TABLE IF NOT EXISTS memory.projection_receipts(job_id text PRIMARY KEY REFERENCES memory.jobs(id), project_id text NOT NULL, item_id text NOT NULL, version integer NOT NULL, canonical_hash text NOT NULL, destination text NOT NULL, receipt jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp());
INSERT INTO memory.schema_versions(version) VALUES (1) ON CONFLICT DO NOTHING;
ALTER TABLE memory.memory_items ADD COLUMN IF NOT EXISTS parent_item_id text;
ALTER TABLE memory.memory_items ADD COLUMN IF NOT EXISTS parent_version integer;
ALTER TABLE memory.memory_items ADD COLUMN IF NOT EXISTS parent_hash text;
CREATE INDEX IF NOT EXISTS memory_item_parent ON memory.memory_items(project_id,parent_item_id);
INSERT INTO memory.schema_versions(version) VALUES (2) ON CONFLICT DO NOTHING;
ALTER TABLE memory.documents ADD COLUMN IF NOT EXISTS search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('simple'::regconfig,COALESCE(body->>'title','')),'A') ||
    setweight(to_tsvector('simple'::regconfig,COALESCE(body->>'tags','')),'B') ||
    setweight(to_tsvector('simple'::regconfig,COALESCE(body->>'content','')),'C')
) STORED;
CREATE INDEX IF NOT EXISTS memory_document_search ON memory.documents USING gin(search_vector) WHERE NOT deleted;
INSERT INTO memory.schema_versions(version) VALUES (3) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS memory.embeddings(
    project_id text NOT NULL REFERENCES memory.projects(id),
    item_id text NOT NULL,
    resource_type text NOT NULL CHECK(resource_type IN ('item','document')),
    version integer NOT NULL,
    canonical_hash text NOT NULL,
    model text NOT NULL,
    vector double precision[] NOT NULL CHECK(array_ndims(vector)=1 AND array_length(vector,1) BETWEEN 1 AND 4096),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(project_id,item_id,resource_type,version,model)
);
CREATE INDEX IF NOT EXISTS memory_embedding_scope ON memory.embeddings(project_id,model,resource_type,item_id,version);
INSERT INTO memory.schema_versions(version) VALUES (4) ON CONFLICT DO NOTHING;

-- Project-scoped cursor feeds and current projection lookup. Additive only.
SET LOCAL lock_timeout = '5s';
CREATE INDEX IF NOT EXISTS memory_events_activity ON memory.events(project_id,created_at,id);
CREATE INDEX IF NOT EXISTS memory_events_history ON memory.events(project_id,id);
CREATE INDEX IF NOT EXISTS memory_receipts_current ON memory.projection_receipts(project_id,item_id,version,canonical_hash,destination);
CREATE INDEX IF NOT EXISTS memory_items_recent ON memory.memory_items(project_id,
    (event_type='correction' AND payload->>'validation_status'='validated') DESC,occurred_at DESC,id)
    WHERE NOT deleted AND superseded_by IS NULL;
INSERT INTO memory.schema_versions(version) VALUES (5) ON CONFLICT DO NOTHING;

-- pgvector (schema version 8; 6 and 7 are taken by the extended and corpus-answer migrations). Additive: `vector double precision[]` stays authoritative so a previous release keeps working.
-- The extension lives in `public` on purpose: without WITH SCHEMA it would land in the first schema of the search path,
-- which for the role `memory` is the schema `memory` itself. Needs a role allowed to create the extension (the bootstrap superuser of the PostgreSQL image). The partial
-- HNSW indexes are created by Store.migrate() because the indexed model/dimensions come from MEMORY_VECTOR_INDEXES.
SET LOCAL lock_timeout = '5s';
-- The whole block is skipped once version 8 is registered and its columns exist: a repeated `admin migrate` takes
-- no ACCESS EXCLUSIVE lock and does not walk the table. The first run rewrites the table (generated `dims`),
-- backfills `embedding` and builds the HNSW indexes; see docs/operations.md for cost and lock window.
DO $pgvector$
BEGIN
    IF EXISTS (SELECT 1 FROM memory.schema_versions WHERE version = 8)
       AND (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'memory' AND table_name = 'embeddings' AND column_name IN ('embedding', 'dims')) = 2 THEN
        RETURN;
    END IF;
    CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
    ALTER TABLE memory.embeddings ADD COLUMN IF NOT EXISTS embedding vector;
    ALTER TABLE memory.embeddings ADD COLUMN IF NOT EXISTS dims integer GENERATED ALWAYS AS (array_length(vector,1)) STORED;
    CREATE OR REPLACE FUNCTION memory.embedding_sync() RETURNS trigger LANGUAGE plpgsql AS $function$
    BEGIN
        -- Rows written by code that only knows `vector` (a previous release, direct SQL) get their `embedding`.
        IF NEW.embedding IS NULL OR (TG_OP = 'UPDATE' AND NEW.vector IS DISTINCT FROM OLD.vector AND NEW.embedding IS NOT DISTINCT FROM OLD.embedding) THEN
            NEW.embedding := NEW.vector::vector;
        END IF;
        RETURN NEW;
    END
    $function$;
    CREATE OR REPLACE TRIGGER embedding_sync BEFORE INSERT OR UPDATE ON memory.embeddings
        FOR EACH ROW EXECUTE FUNCTION memory.embedding_sync();
    UPDATE memory.embeddings SET embedding = vector::vector WHERE embedding IS NULL;
    INSERT INTO memory.schema_versions(version) VALUES (8) ON CONFLICT DO NOTHING;
END
$pgvector$;

-- fts-language (schema version 9)
-- Spanish and English full-text vectors with `unaccent`, plus `pg_trgm` for typo/identifier fallback. Additive: the `simple`
-- `search_vector` columns and their indexes stay, and a previous release keeps working (documents: generated columns;
-- memory_items: a trigger completes rows written by code that only knows `search_vector`).
-- Extensions live in `public` (see the pgvector note above). `unaccent` and `pg_trgm` are trusted extensions.
-- The block is skipped once version 9 is registered and its columns exist, so a repeated `admin migrate` takes no
-- ACCESS EXCLUSIVE/SHARE lock and does not walk the tables. The first run rewrites `documents` (generated columns),
-- adds columns to `memory_items`, backfills it, creates a trigger and builds six indexes. Store.migrate() runs ALL of schema.sql in ONE
-- transaction, so the strongest lock taken on each table (ACCESS EXCLUSIVE from the ALTER TABLEs, on BOTH `documents` and
-- `memory_items`) is held until the COMMIT of the whole migration: reads and writes of those two tables by other sessions
-- wait for the entire run, not only for the statement that took the lock. Cost, window and mitigation: docs/operations.md.
-- The new indexes are not partial on purpose: they cover every row, so no predicate has to be kept in step with the queries.
SET LOCAL lock_timeout = '5s';
DO $fts$
BEGIN
    IF EXISTS (SELECT 1 FROM memory.schema_versions WHERE version = 9)
       AND (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'memory'
            AND table_name IN ('documents', 'memory_items') AND column_name IN ('search_vector_es', 'search_vector_en')) = 4 THEN
        RETURN;
    END IF;
    CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;
    CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
    -- `unaccent` is only STABLE; the wrapper pins the dictionary so generated columns and indexes may use it.
    CREATE OR REPLACE FUNCTION memory.kairos_unaccent(text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $f$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $f$;
    -- Heading text weighs A, body text B (same weights as the `simple` vectors of memory_items).
    CREATE OR REPLACE FUNCTION memory.item_fts(config regconfig, heading text, body text) RETURNS tsvector LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $f$ SELECT setweight(to_tsvector(config, memory.kairos_unaccent(COALESCE(heading, ''))), 'A')
                   || setweight(to_tsvector(config, memory.kairos_unaccent(COALESCE(body, ''))), 'B') $f$;
    -- Trigram keys: words (lowercase, no accents) and the same string without separators for identifiers (ERR-4471 / err4471).
    CREATE OR REPLACE FUNCTION memory.trigram_words(text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $f$ SELECT lower(memory.kairos_unaccent($1)) $f$;
    CREATE OR REPLACE FUNCTION memory.trigram_compact(text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $f$ SELECT regexp_replace(lower(memory.kairos_unaccent($1)), '[^[:alnum:]]', '', 'g') $f$;
    CREATE OR REPLACE FUNCTION memory.trigram_key(text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $f$ SELECT memory.trigram_words($1) || ' ' || memory.trigram_compact($1) $f$;
    ALTER TABLE memory.documents
        ADD COLUMN IF NOT EXISTS search_vector_es tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('spanish'::regconfig, memory.kairos_unaccent(COALESCE(body->>'title', ''))), 'A') ||
            setweight(to_tsvector('spanish'::regconfig, memory.kairos_unaccent(COALESCE(body->>'tags', ''))), 'B') ||
            setweight(to_tsvector('spanish'::regconfig, memory.kairos_unaccent(COALESCE(body->>'content', ''))), 'C')) STORED,
        ADD COLUMN IF NOT EXISTS search_vector_en tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, memory.kairos_unaccent(COALESCE(body->>'title', ''))), 'A') ||
            setweight(to_tsvector('english'::regconfig, memory.kairos_unaccent(COALESCE(body->>'tags', ''))), 'B') ||
            setweight(to_tsvector('english'::regconfig, memory.kairos_unaccent(COALESCE(body->>'content', ''))), 'C')) STORED;
    ALTER TABLE memory.memory_items ADD COLUMN IF NOT EXISTS search_vector_es tsvector, ADD COLUMN IF NOT EXISTS search_vector_en tsvector;
    UPDATE memory.memory_items SET
        search_vector_es = memory.item_fts('spanish', concat_ws(' ', payload->>'title', payload->>'problem', payload->>'correction'), payload->>'content'),
        search_vector_en = memory.item_fts('english', concat_ws(' ', payload->>'title', payload->>'problem', payload->>'correction'), payload->>'content')
        WHERE search_vector_es IS NULL OR search_vector_en IS NULL;
    CREATE OR REPLACE FUNCTION memory.item_fts_sync() RETURNS trigger LANGUAGE plpgsql AS $function$
    BEGIN
        -- Rows written by code that only knows `search_vector` (a previous release, direct SQL) get the language vectors.
        IF NEW.search_vector_es IS NULL OR NEW.search_vector_en IS NULL
           OR (TG_OP = 'UPDATE' AND NEW.search_vector IS DISTINCT FROM OLD.search_vector
               AND NEW.search_vector_es IS NOT DISTINCT FROM OLD.search_vector_es AND NEW.search_vector_en IS NOT DISTINCT FROM OLD.search_vector_en) THEN
            NEW.search_vector_es := memory.item_fts('spanish', concat_ws(' ', NEW.payload->>'title', NEW.payload->>'problem', NEW.payload->>'correction'), NEW.payload->>'content');
            NEW.search_vector_en := memory.item_fts('english', concat_ws(' ', NEW.payload->>'title', NEW.payload->>'problem', NEW.payload->>'correction'), NEW.payload->>'content');
        END IF;
        RETURN NEW;
    END
    $function$;
    CREATE OR REPLACE TRIGGER item_fts_sync BEFORE INSERT OR UPDATE ON memory.memory_items
        FOR EACH ROW EXECUTE FUNCTION memory.item_fts_sync();
    CREATE INDEX IF NOT EXISTS memory_item_search_es ON memory.memory_items USING gin(search_vector_es);
    CREATE INDEX IF NOT EXISTS memory_item_search_en ON memory.memory_items USING gin(search_vector_en);
    CREATE INDEX IF NOT EXISTS memory_document_search_es ON memory.documents USING gin(search_vector_es);
    CREATE INDEX IF NOT EXISTS memory_document_search_en ON memory.documents USING gin(search_vector_en);
    CREATE INDEX IF NOT EXISTS memory_item_title_trgm ON memory.memory_items USING gin(memory.trigram_key(payload->>'title') public.gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS memory_document_title_trgm ON memory.documents USING gin(memory.trigram_key(body->>'title') public.gin_trgm_ops);
    INSERT INTO memory.schema_versions(version) VALUES (9) ON CONFLICT DO NOTHING;
END
$fts$;
