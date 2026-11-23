"""Operator commands. Passwords are read from files, never command arguments."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import hashlib

from . import observability
from . import probe as round_trip
from .backup import BackupError, check_keep, create_backup, encrypted_name, encryption_plan, manifest_path, prune_backups, table_fingerprints, terminate_as_exit, verify_backup
from .chunking import chunk_text, embedding_text
from .config import (Settings, backup_destination, backup_interval_seconds, backup_keep, backup_recipients_file, backup_remote_keep, backup_require_encryption, retention_windows)
from .errors import MemoryError
from .offsite import CycleError, parse_destination, record_failure, run_cycle, run_loop
from .store import Store
from .store_vectors import CURRENT_RESOURCE

LOOP_CYCLES = None  # `backup-cycle --loop` runs for ever; a test sets a number
# The direct connections of `admin` (and the service file `pg_dump`/`pg_restore` read) of a service that lives for ever (`backup-cycle --loop`): a half-open connection must fail instead of
# hanging the cycle. NO statement_timeout: a dump or a prune is a long query on purpose. Whatever the operator put in the DSN wins. 10 s to connect; a dead peer is noticed after 30 + 3 * 10 s idle.
CONNECTION_GUARDS = {'connect_timeout': '10', 'keepalives': '1', 'keepalives_idle': '30', 'keepalives_interval': '10', 'keepalives_count': '3', 'tcp_user_timeout': '60000'}


def guarded_dsn(dsn):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    return make_conninfo(**dict(CONNECTION_GUARDS, **conninfo_to_dict(dsn)))






def store_fingerprints(store):
    """Include provenance, grants, jobs, versions and tombstones in restore QA."""
    with store.transaction() as connection:
        return table_fingerprints(connection)


@contextmanager
def pg_environment(dsn):
    from psycopg.conninfo import conninfo_to_dict
    values = conninfo_to_dict(dsn)
    with tempfile.TemporaryDirectory(prefix='memory-pg-service-') as temporary:
        service = Path(temporary) / 'pg_service.conf'
        if any('\n' in str(v) or '\r' in str(v) for v in values.values()):
            raise ValueError('Invalid PostgreSQL connection parameter')
        service.write_text('[memory]\n' + '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n', encoding='utf-8')
        service.chmod(0o600)
        yield dict(os.environ, PGSERVICEFILE=str(service), PGSERVICE='memory')


def inspect_store(store):
    with store.transaction() as connection:
        tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
        # Identifiers are from our schema inventory, not request input.
        from psycopg import sql
        return {row['table_name']: connection.execute(sql.SQL('SELECT count(*) AS n FROM memory.{}').format(sql.Identifier(row['table_name']))).fetchone()['n'] for row in tables}


def content_manifest(store):
    """Read canonical identities and hashes without document bodies or credentials."""
    with store.transaction() as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        documents = connection.execute('SELECT project_id,id,version,canonical_hash,deleted,body FROM memory.documents ORDER BY project_id,id').fetchall()
        items = connection.execute('SELECT project_id,id,version,canonical_hash,deleted,superseded_by FROM memory.memory_items ORDER BY project_id,id').fetchall()
        projects = connection.execute('SELECT id,title,policy FROM memory.projects ORDER BY id').fetchall()
        result = []
        for document in documents:
            body = document.pop('body')
            source_hash = hashlib.sha256(body.get('content', '').encode('utf-8')).hexdigest()
            expected = body.get('source', {}).get('sha256')
            if source_hash != expected:
                raise RuntimeError('A document source hash does not match its exact UTF-8 content')
            tags = body.get('tags', [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise RuntimeError('Document tags must remain a list of strings')
            result.append(dict(document, source_sha256=source_hash, title=body.get('title'), tags=tags, source=body.get('source', {})))
        manifest = {'projects': projects, 'documents': result, 'items': items}
        encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        return dict(manifest, sha256=hashlib.sha256(encoded.encode('utf-8')).hexdigest())


# Current resources (the same notion of "current" as the semantic search) with no fragment for the model and no job in flight, that were
# meant to be embedded: an `embed` job exists at this version (any state) or an item-level embedding does. Technical items (captures,
# agent activity) never get one and stay out. Each source is read in key order starting after the last key already handled
# (`{after}`), so a run walks every table once instead of re-scanning what it already queued.
BACKFILL_SOURCES = {
    'document': """SELECT 'document'::text AS resource_type, d.project_id, d.id AS item_id, d.version, d.canonical_hash
        FROM memory.documents d WHERE NOT d.deleted AND (%(project)s::text IS NULL OR d.project_id=%(project)s){after}""",
    'item': """SELECT 'item'::text AS resource_type, i.project_id, i.id AS item_id, i.version, i.canonical_hash
        FROM memory.memory_items i LEFT JOIN memory.memory_items p ON p.project_id=i.project_id AND p.id=i.parent_item_id
        WHERE NOT i.deleted AND i.superseded_by IS NULL AND (%(project)s::text IS NULL OR i.project_id=%(project)s)
        AND (i.parent_item_id IS NULL OR (p.version=i.parent_version AND p.canonical_hash=i.parent_hash AND NOT p.deleted AND p.superseded_by IS NULL)){after}""",
}
BACKFILL_AFTER = {'document': ' AND (%(after_project)s::text IS NULL OR (d.project_id,d.id)>(%(after_project)s,%(after_item)s))',
                  'item': ' AND (%(after_project)s::text IS NULL OR (i.project_id,i.id)>(%(after_project)s,%(after_item)s))'}
BACKFILL_PENDING = """
WHERE NOT EXISTS (SELECT 1 FROM memory.embedding_chunks k WHERE k.project_id=r.project_id AND k.item_id=r.item_id
        AND k.resource_type=r.resource_type AND k.version=r.version AND k.model=%(model)s)
  AND NOT EXISTS (SELECT 1 FROM memory.jobs j WHERE j.project_id=r.project_id AND j.item_id=r.item_id AND j.resource_type=r.resource_type
        AND j.version=r.version AND j.destination='embed' AND j.operation='upsert' AND j.state IN ('pending','running','unknown'))
  AND (%(retry_failed)s OR NOT EXISTS (SELECT 1 FROM memory.jobs j WHERE j.project_id=r.project_id AND j.item_id=r.item_id AND j.resource_type=r.resource_type
        AND j.version=r.version AND j.destination='embed' AND j.operation='upsert' AND j.state='failed'))
  AND (EXISTS (SELECT 1 FROM memory.jobs j WHERE j.project_id=r.project_id AND j.item_id=r.item_id AND j.resource_type=r.resource_type
        AND j.version=r.version AND j.destination='embed' AND j.operation='upsert')
       OR EXISTS (SELECT 1 FROM memory.embeddings e WHERE e.project_id=r.project_id AND e.item_id=r.item_id AND e.resource_type=r.resource_type
        AND e.version=r.version AND e.canonical_hash=r.canonical_hash))
"""


def backfill_query(kind, *, after=True):
    """Candidates of one source, in key order: parameters project, model, after_project, after_item, limit."""
    source = BACKFILL_SOURCES[kind].format(after=BACKFILL_AFTER[kind] if after else '')
    return 'SELECT r.resource_type,r.project_id,r.item_id,r.version,r.canonical_hash FROM (' + source + ') r' + BACKFILL_PENDING +         ' ORDER BY r.project_id,r.item_id' + (' LIMIT %(limit)s' if after else '')


# Current resources without fragments whose embed job of this version FAILED (the worker already used its attempts): a run does not queue them
# again (`--retry-failed` does) and reports how many wait for a decision.
BACKFILL_FAILED = """
WHERE NOT EXISTS (SELECT 1 FROM memory.embedding_chunks k WHERE k.project_id=r.project_id AND k.item_id=r.item_id
        AND k.resource_type=r.resource_type AND k.version=r.version AND k.model=%(model)s)
  AND EXISTS (SELECT 1 FROM memory.jobs j WHERE j.project_id=r.project_id AND j.item_id=r.item_id AND j.resource_type=r.resource_type
        AND j.version=r.version AND j.destination='embed' AND j.operation='upsert' AND j.state='failed')
"""


def backfill_failed(connection, params):
    union = ' UNION ALL '.join(BACKFILL_SOURCES[kind].format(after='') for kind in BACKFILL_SOURCES)
    return connection.execute('SELECT count(*) AS n FROM (' + union + ') r' + BACKFILL_FAILED, params).fetchone()['n']


def backfill_remaining(connection, params):
    union = ' UNION ALL '.join(BACKFILL_SOURCES[kind].format(after='') for kind in BACKFILL_SOURCES)
    return connection.execute('SELECT count(*) AS n FROM (' + union + ') r' + BACKFILL_PENDING, params).fetchone()['n']


# Queue the job, or put a finished one (succeeded/failed) back in the queue with a fresh attempt budget; a job in flight is never touched.
BACKFILL_ENQUEUE = """
INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,priority)
VALUES(%s,%s,%s,%s,%s,%s,'embed','upsert',1)
ON CONFLICT(project_id,item_id,version,resource_type,destination,operation) DO UPDATE
SET state='pending',attempts=0,available_at=clock_timestamp(),lease_until=NULL,worker_id=NULL,error_code=NULL,canonical_hash=EXCLUDED.canonical_hash,priority=1
WHERE memory.jobs.state IN ('succeeded','failed') RETURNING id
"""  # priority 1: the worker serves every live write (priority 0) first

# A resource whose whole text is ONE fragment and that already has a current item vector of the model (the previous worker embedded exactly that
# text) needs no provider call: its fragment is that vector.
BACKFILL_DERIVE = """
INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding)
SELECT e.project_id,e.item_id,e.resource_type,e.version,e.canonical_hash,e.model,0,0,%(length)s,e.embedding
FROM memory.embeddings e WHERE e.project_id=%(project_id)s AND e.item_id=%(item_id)s AND e.resource_type=%(resource_type)s AND e.version=%(version)s
  AND e.canonical_hash=%(canonical_hash)s AND e.model=%(model)s AND e.embedding IS NOT NULL AND vector_norm(e.embedding)>0
ON CONFLICT DO NOTHING RETURNING 1
"""


# Item vectors of resources that are no longer current (older versions, superseded, deleted: written before fragments existed, so still
# flagged unchunked) are derived data nobody can search. Flagging them keeps the partial index `memory_embeddings_unchunked` limited to live work.
# Never a DELETE. Parameters: project x2, after (project, item, type, version, model) x1 + x5 (or NULL), the eight of CURRENT_RESOURCE, limit.
STALE_UNCHUNKED = '''WITH stale AS (SELECT e.project_id,e.item_id,e.resource_type,e.version,e.model FROM memory.embeddings e
    WHERE NOT e.chunked AND (%s::text IS NULL OR e.project_id=%s)
    AND (%s::text IS NULL OR (e.project_id,e.item_id,e.resource_type,e.version,e.model)>(%s,%s,%s,%s,%s))
    AND NOT ''' + CURRENT_RESOURCE + ''' ORDER BY e.project_id,e.item_id,e.resource_type,e.version,e.model LIMIT %s),
marked AS (UPDATE memory.embeddings e SET chunked=true FROM stale s WHERE e.project_id=s.project_id AND e.item_id=s.item_id AND e.resource_type=s.resource_type
    AND e.version=s.version AND e.model=s.model RETURNING 1)
SELECT project_id,item_id,resource_type,version,model FROM stale ORDER BY project_id,item_id,resource_type,version,model'''


def mark_stale_unchunked(store, project, batch):
    """Flag every non-current item vector as chunked, in batches of `batch` rows (one short transaction each); idempotent. Returns how many."""
    total, after = 0, (None,) * 5
    while True:
        with store.transaction() as connection:
            rows = connection.execute(STALE_UNCHUNKED, [project, project, after[0], *after, *(None,) * 8, batch]).fetchall()
        total += len(rows)
        if len(rows) < batch:
            return total
        after = tuple(rows[-1][key] for key in ('project_id', 'item_id', 'resource_type', 'version', 'model'))  # the database's own order, not Python's


def derive_single_fragment(connection, row, model):
    """True when the resource fitted one fragment and its fragment was derived from the item vector (no job needed)."""
    table, column = ('memory.documents', 'body') if row['resource_type'] == 'document' else ('memory.memory_items', 'payload')
    source = connection.execute('SELECT ' + column + ' AS source FROM ' + table + ' WHERE project_id=%s AND id=%s', (row['project_id'], row['item_id'])).fetchone()['source']
    text = embedding_text(source.get('title', ''), source.get('content', ''))
    chunks = chunk_text(text)
    if len(chunks) != 1 or chunks.truncated or (chunks[0].char_start, chunks[0].char_end) != (0, len(text)):
        return False
    if not connection.execute(BACKFILL_DERIVE, dict(row, model=model, length=len(text))).fetchone():
        return False
    connection.execute('UPDATE memory.embeddings SET chunked=true WHERE project_id=%s AND item_id=%s AND resource_type=%s AND version=%s AND model=%s',
                       (row['project_id'], row['item_id'], row['resource_type'], row['version'], model))
    return True


def backfill_chunks(store, model, *, batch=200, max_jobs=None, project=None, retry_failed=False):
    """Queue `embed` jobs for current resources without fragments, in short transactions of `batch` jobs.

    Idempotent (a resource with a job in flight, or with fragments, is not queued again), resumable (a run that stops at
    `max_jobs` or by a failure is continued by running it again) and bounded (every batch is its own transaction: no table is
    locked for the length of the run, only the rows of the jobs being queued; each source is walked once in key order). It also fills `embeddings.embedding` where the
    pgvector column is still empty. Jobs are queued at priority 1, behind every live write. A resource whose text is one fragment and
    already has its item vector is completed without a job (`derived`). Jobs that already FAILED are not queued again unless
    `retry_failed`; they are counted in `failed`. Returns counts only: {enqueued, derived, failed, pending, remaining, batches, embedding_filled, stale_marked}.
    """
    import uuid
    if not isinstance(batch, int) or not 1 <= batch <= 5000 or (max_jobs is not None and (not isinstance(max_jobs, int) or max_jobs < 1)):
        raise ValueError('batch must be 1..5000 and max_jobs a positive integer')
    params = {'project': project, 'model': model, 'retry_failed': bool(retry_failed)}
    enqueued = batches = filled = derived = 0
    for kind in BACKFILL_SOURCES:
        last = (None, None)
        while max_jobs is None or enqueued < max_jobs:
            with store.transaction() as connection:
                rows = connection.execute(backfill_query(kind), dict(params, after_project=last[0], after_item=last[1],
                                                                       limit=batch if max_jobs is None else min(batch, max_jobs - enqueued))).fetchall()
                queued = 0
                for row in rows:
                    if derive_single_fragment(connection, row, model):
                        derived += 1
                    elif connection.execute(BACKFILL_ENQUEUE, (str(uuid.uuid4()), row['project_id'], row['item_id'], row['version'],
                                                               row['canonical_hash'], row['resource_type'])).fetchone():
                        queued += 1
            if not rows:
                break  # this source is exhausted
            enqueued += queued
            batches += 1
            last = (rows[-1]['project_id'], rows[-1]['item_id'])
    while True:
        with store.transaction() as connection:
            done = len(connection.execute('UPDATE memory.embeddings SET embedding=vector::vector WHERE ctid=ANY(ARRAY(SELECT ctid FROM memory.embeddings WHERE embedding IS NULL LIMIT %s)) RETURNING 1', (batch,)).fetchall())
        filled += done
        if not done:
            break
    stale = mark_stale_unchunked(store, project, batch)
    with store.transaction() as connection:
        remaining = backfill_remaining(connection, params)
        failed = backfill_failed(connection, params)
        pending = connection.execute("SELECT count(*) AS n FROM memory.jobs WHERE destination='embed' AND priority=1 AND state IN ('pending','running','unknown') AND (%(project)s::text IS NULL OR project_id=%(project)s)", params).fetchone()['n']
    return {'enqueued': enqueued, 'derived': derived, 'failed': failed, 'pending': pending, 'remaining': remaining, 'batches': batches, 'embedding_filled': filled, 'stale_marked': stale}


# Retention (decision P-03): what `prune-tables` may delete, per table. `%(cutoff)s` is the instant that the window ends at (rows OLDER than it go; a row exactly at it stays).
# Nothing here is a migration, and every statement takes its values as parameters. Rows are walked in ascending key order with a cursor (`id > after`, `after` starting at the
# second element), so a batch never looks again at what an earlier one already deleted.
#   login_attempts  attempts older than the window.
#   web_sessions    sessions that EXPIRED or were REVOKED longer ago than the window; a live session (not expired, not revoked) is never touched.
#   audit_events    audit rows older than the window.
#   jobs            only `failed` jobs, last scheduled (created_at and available_at) before the window, that NO client can still reach (the MCP/REST contract stays as it is):
#                   no receipt in `projection_receipts` (the receipt references it and says the work was done), not cited by the receipt of any kept `events` row
#                   (`event_status` and the idempotent `ingest_event` read it), and not a job of the CURRENT version of its document or item (`document_status` lists those and
#                   `backfill-chunks` reads them). What goes is the orphan: a job of a past version, of a resource that no longer exists, cited by no kept event.
#   events          the capture journal: only when its window is set explicitly.
JOBS_PREDICATE = ("t.state = 'failed' AND t.created_at < %(cutoff)s AND t.available_at < %(cutoff)s "
                  "AND NOT EXISTS (SELECT 1 FROM memory.projection_receipts r WHERE r.job_id = t.id) "
                  "AND NOT EXISTS (SELECT 1 FROM memory.events e, jsonb_array_elements_text(CASE WHEN jsonb_typeof(e.receipt->'jobs') = 'array' THEN e.receipt->'jobs' ELSE '[]'::jsonb END) AS cited(job_id) WHERE cited.job_id = t.id) "
                  "AND NOT EXISTS (SELECT 1 FROM memory.documents d WHERE t.resource_type = 'document' AND d.project_id = t.project_id AND d.id = t.item_id AND d.version = t.version) "
                  "AND NOT EXISTS (SELECT 1 FROM memory.memory_items i WHERE t.resource_type <> 'document' AND i.project_id = t.project_id AND i.id = t.item_id AND i.version = t.version)")
RETENTION_TABLES = {
    'login_attempts': ('t.happened_at < %(cutoff)s', 0),
    'web_sessions': ('(t.expires_at < %(cutoff)s OR (t.revoked_at IS NOT NULL AND t.revoked_at < %(cutoff)s))', ''),
    'audit_events': ('t.happened_at < %(cutoff)s', 0),
    'events': ('t.created_at < %(cutoff)s', ''),  # before `jobs`: a job cited only by an event this run removes can go in the same run
    'jobs': (JOBS_PREDICATE, ''),
}
PRUNE_BATCH_MAX = 5000
PRUNE_AUDIT_ACTION = 'retention_prune'


def prune_tables(store, windows, *, batch=1000, dry_run=False, tables=None, now=None):
    """Delete the rows the retention `windows` ({table: days or None}) select, `batch` rows per transaction; with `dry_run` only count them, in a READ ONLY transaction.

    One `now` for the whole run (the database clock unless given) fixes every cutoff, so a run ends: rows inserted meanwhile are newer than any cutoff. Each batch is its own
    transaction (a failure rolls back that batch alone and leaves every earlier one committed), rows are claimed in ascending key order after a cursor with FOR UPDATE SKIP LOCKED
    (two runs at the same time share the work and never delete a row twice; a table is done when a batch removes fewer rows than `batch`) and a second run finds nothing to do.
    A table without a window (`events` by default) is reported and left alone. A real run ends by writing ONE `audit_events` row (action `retention_prune`, resource_id = JSON of
    the days and rows deleted per table), after `audit_events` was pruned so the run cannot erase its own trace; it is written even when the run failed half way (`complete: false`).
    Returns {status, dry_run, batch, now, tables: {table: {window_days, cutoff, would_delete, deleted, batches}}}."""
    from datetime import timedelta
    if isinstance(batch, bool) or not isinstance(batch, int) or not 1 <= batch <= PRUNE_BATCH_MAX:
        raise ValueError(f'batch must be an integer between 1 and {PRUNE_BATCH_MAX}')
    selected = list(RETENTION_TABLES) if tables is None else list(tables)
    if any(table not in RETENTION_TABLES for table in selected) or any(table not in windows for table in RETENTION_TABLES):
        raise ValueError('prune-tables knows the tables ' + ', '.join(RETENTION_TABLES) + ' and needs a window (or None) for each')
    if now is None:
        with store.transaction() as connection:
            now = connection.execute('SELECT clock_timestamp() AS now').fetchone()['now']
    report = {}
    complete = False
    try:
        for table in selected:
            days = windows[table]
            entry = {'window_days': days, 'would_delete': 0, 'deleted': 0, 'batches': 0}
            report[table] = entry
            if days is None:
                entry['skipped'] = 'no_window'
                continue
            cutoff = now - timedelta(days=days)
            entry['cutoff'] = cutoff.isoformat()
            predicate, after = RETENTION_TABLES[table]
            if dry_run:
                with store.transaction() as connection:
                    connection.execute('SET TRANSACTION READ ONLY')
                    entry['would_delete'] = connection.execute(f'SELECT count(*) AS n FROM memory.{table} t WHERE {predicate}', {'cutoff': cutoff}).fetchone()['n']
                continue
            statement = (f'WITH gone AS (DELETE FROM memory.{table} WHERE id IN (SELECT t.id FROM memory.{table} t WHERE {predicate} AND t.id > %(after)s '
                         f'ORDER BY t.id LIMIT %(batch)s FOR UPDATE SKIP LOCKED) RETURNING id) SELECT count(*) AS n, max(id) AS last FROM gone')
            while True:
                with store.transaction() as connection:
                    result = connection.execute(statement, {'cutoff': cutoff, 'batch': batch, 'after': after}).fetchone()
                removed = result['n']
                if removed:
                    entry['deleted'] += removed
                    entry['batches'] += 1
                    after = result['last']
                if removed < batch:
                    break
        complete = True
    finally:
        if not dry_run:
            summary = {table: {'days': info['window_days'], 'deleted': info['deleted']} for table, info in report.items() if info['window_days'] is not None}
            if not complete:
                summary['complete'] = False
            with store.transaction() as connection:
                connection.execute('INSERT INTO memory.audit_events(action,resource_id) VALUES(%s,%s)', (PRUNE_AUDIT_ACTION, json.dumps(summary, sort_keys=True, separators=(',', ':'))))
    return {'status': 'dry_run' if dry_run else 'pruned', 'dry_run': dry_run, 'batch': batch, 'now': now.isoformat(), 'tables': report}


def password_from_file(path):
    """The password in a file: exactly the text of the file minus ONE final line break (a LF or a CR LF, what an editor or `echo` adds). Nothing else is removed: a password may start or end with spaces,
    and a second line break is part of it. Read as bytes so that the platform does not translate the line endings."""
    text = path.read_bytes().decode('utf-8')
    for ending in ('\r\n', '\n'):
        if text.endswith(ending):
            return text[:-len(ending)]
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description='Manage only the isolated memory platform database')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    bootstrap = commands.add_parser('bootstrap')
    bootstrap.add_argument('--username', default='admin')
    bootstrap.add_argument('--password-file', default=os.environ.get('MEMORY_BOOTSTRAP_PASSWORD_FILE'))
    bootstrap.add_argument('--with-projects', action='store_true', help='Create allowlisted project shells; capture stays off')
    set_password = commands.add_parser('set-password', help='Recover an account: set the password of --username from --password-file (one final newline is removed, nothing else) and close every session of the user; the API keys stay unless --revoke-keys; nothing secret is printed')
    set_password.add_argument('--username', required=True)
    set_password.add_argument('--password-file', required=True)
    set_password.add_argument('--revoke-keys', action='store_true', help='also revoke every API key of the user, in the same transaction (the account may have been used by someone else, who may have made keys)')
    backfill = commands.add_parser('backfill-chunks', help='Queue embed jobs for current resources without fragments (idempotent, resumable)')
    backfill.add_argument('--batch', type=int, default=200, help='Jobs queued per transaction (1..5000)')
    backfill.add_argument('--max-jobs', type=int, default=None, help='Stop after queueing this many jobs; run again to continue')
    backfill.add_argument('--project', default=None, help='Only this project id')
    backfill.add_argument('--retry-failed', action='store_true', help='Also queue again the jobs that already failed (otherwise they are only counted)')
    prune = commands.add_parser('prune-tables', help='Delete old rows of the tables that only grow, in batches, by the MEMORY_RETENTION_*_DAYS windows (P-03)')
    prune.add_argument('--dry-run', action='store_true', help='Only report what each table would lose; nothing is written')
    prune.add_argument('--batch', type=int, default=1000, help=f'Rows deleted per transaction (1..{PRUNE_BATCH_MAX})')
    prune.add_argument('--table', action='append', choices=sorted(RETENTION_TABLES), help='Only this table (repeatable); default: every table that has a window')
    provision = commands.add_parser('probe-provision', help='Make the project kairos-probe and a key that reaches only it (read and write), idempotent; the token goes to --key-file, never to the output')
    provision.add_argument('--key-file', default=os.environ.get('MEMORY_PROBE_KEY_FILE', round_trip.DEFAULT_KEY_FILE), help='Where the token of the probe key is kept (0600)')
    provision.add_argument('--as', dest='operator', default=None, help='Username of the administrator that makes the project kairos-probe (default: the first enabled administrator); the key is owned by the service account kairos-probe, never by this user')
    probe = commands.add_parser('probe', help='Round trip through /v1 with the probe key: write a synthetic note, wait for its embed receipt, search for it, retire it; exit 1 with probe_failed and the stage when any fails')
    probe.add_argument('--url', default=None, help='Where /v1 answers (default MEMORY_PROBE_URL or http://memory-api:8790)')
    probe.add_argument('--key-file', default=os.environ.get('MEMORY_PROBE_KEY_FILE', round_trip.DEFAULT_KEY_FILE), help='The probe key written by probe-provision')
    probe.add_argument('--metrics-file', default=os.environ.get('MEMORY_PROBE_METRICS_FILE', round_trip.DEFAULT_METRICS_FILE), help='Where kairos_probe_* are written for a textfile collector (empty: nowhere)')
    probe.add_argument('--loop', action='store_true', help='Repeat the probe: one run, then MEMORY_PROBE_INTERVAL seconds (default 300) of wait, so the period is the duration of a run plus the interval: what the memory-probe service runs. A failed run is reported (probe_failed, queue_stuck) and the next one runs; only a stop of the service ends it (probe_interrupted)')
    probe.add_argument('--heartbeat-file', default=None, help='With --loop: the file the loop touches at the start and the end of every cycle, which the healthcheck of memory-probe reads (default MEMORY_PROBE_HEARTBEAT_FILE, else next to the metrics file with the suffix .heartbeat)')
    commands.add_parser('inspect')
    commands.add_parser('content-manifest')
    backup = commands.add_parser('backup', help='pg_dump to a new file with its manifest <file>.json (sha256, bytes, schema version, time, counts)')
    backup.add_argument('--output', required=True)
    backup.add_argument('--prune', action='store_true', help='After the copy, delete the older verified copies of this tool beyond the --keep newest (never anything else)')
    backup.add_argument('--keep', default=None, help='With --prune: copies to keep, 1 or more (default MEMORY_BACKUP_KEEP, 7)')
    cycle = commands.add_parser('backup-cycle', help='A copy, encrypted, verified, sent to MEMORY_BACKUP_DESTINATION (dir: or rclone:) and verified there, with the retention of both places (--loop: every MEMORY_BACKUP_INTERVAL)')
    cycle.add_argument('--output-dir', default='/backups', help='Where the local copies are written and kept (default /backups, the volume of the service)')
    cycle.add_argument('--loop', action='store_true', help='Repeat the cycle every MEMORY_BACKUP_INTERVAL (default 24h); a failed cycle is reported and the next one retries')
    cycle.add_argument('--prune-tables', action='store_true', help='At the end of each cycle also run prune-tables with the MEMORY_RETENTION_*_DAYS windows')
    verify = commands.add_parser('verify-backup', help='Recompute the sha256 of a copy and compare it with its manifest (never decrypts)')
    verify.add_argument('--backup', required=True)
    verify.add_argument('--manifest', default=None, help='The manifest of the ENCRYPTED copy (<copy>.age.json) when --backup is its decrypted dump: its sha256 is compared with content_sha256')
    restore = commands.add_parser('restore-check')
    restore.add_argument('--backup', required=True)
    restore.add_argument('--target-dsn-file', required=True)
    restore.add_argument('--from-manifest', nargs='?', const='auto', default=None, metavar='MANIFEST',
                         help='Verify the copy against <backup>.json (or against MANIFEST, the manifest of the ciphertext, when --backup is its decrypted dump) and compare the restored tables with the counts recorded there (one snapshot with the dump) instead of with the live database, which is then never read')
    args = parser.parse_args(argv)
    if args.command == 'prune-tables':
        if not 1 <= args.batch <= PRUNE_BATCH_MAX:
            parser.error(f'--batch must be an integer between 1 and {PRUNE_BATCH_MAX}')
        try:
            windows = retention_windows()
        except ValueError as error:
            parser.error(str(error))  # a clear message and nothing touched
    if args.command == 'backup-cycle':  # every setting is validated before a copy exists
        try:
            def setting(read, code):
                try:
                    return read()
                except ValueError as error:
                    raise BackupError(code, str(error)) from None
            destination = parse_destination(backup_destination())
            remote_keep, keep = setting(backup_remote_keep, 'backup_keep_invalid'), setting(backup_keep, 'backup_keep_invalid')
            interval = setting(backup_interval_seconds, 'backup_config_invalid')
            require_encryption = setting(backup_require_encryption, 'backup_config_invalid')
            recipients_file = backup_recipients_file()
            if encryption_plan(recipients_file, require_encryption) is None:  # whatever MEMORY_BACKUP_REQUIRE_ENCRYPTION says: an external copy is never sent in the clear
                raise BackupError('backup_encryption_required', 'backup-cycle sends the copies to an external destination and only sends encrypted ones: set MEMORY_BACKUP_RECIPIENTS_FILE (public recipients); nothing was written or sent')
        except BackupError as error:
            record_failure(Path(args.output_dir).resolve())  # a restarting service must not leave the metric of its last good cycle at 1
            raise SystemExit(f'{error.code}: {error}') from None
        if args.prune_tables:
            try:
                windows = retention_windows()
            except ValueError as error:
                record_failure(Path(args.output_dir).resolve())  # the same refusal at start as the settings above: the metric of the last good cycle is not left at 1
                parser.error(str(error))
    if args.command == 'verify-backup':  # needs no database: it reads the copy and its manifest
        try:
            manifest = verify_backup(Path(args.backup), backup_recipients_file(), args.manifest)
        except BackupError as error:
            raise SystemExit(f'{error.code}: {error}') from None
        content = manifest['verified'] == 'content'  # a decrypted dump: what was checked is the content, not the ciphertext
        print(json.dumps({'status': 'verified', 'verified': manifest['verified'], 'path': str(Path(args.backup).resolve()),
                          'bytes': manifest['content_bytes' if content else 'bytes'], 'sha256': manifest['content_sha256' if content else 'sha256'],
                          'encrypted': manifest['encrypted'], 'schema_version': manifest['schema_version'], 'created_at': manifest['created_at']}, sort_keys=True))
        return
    if args.command == 'probe':  # needs no database: it only speaks /v1 with its own key
        observability.configure_logging()  # `probe_failed` goes to stderr as one JSON line
        def open_store():  # the retired notes of kairos-probe are purged through the database this command already has settings for; no database is no failure of the probe
            settings = Settings.from_env()
            return Store(guarded_dsn(settings.dsn), project_maps=settings.project_maps, embedding_enabled=True)
        def run_once():
            """One probe: its report is printed and the verdict is the message an exit would carry (None: all fine)."""
            report = round_trip.probe_command(args.url, args.key_file, args.metrics_file, store_factory=open_store)
            print(json.dumps(report, sort_keys=True), flush=True)
            if report['status'] != 'probe_ok':
                return report, 'probe_failed: stage=%s code=%s' % (report['stage'], report['code'])
            if report.get('metrics_written') is False:  # the probe worked but the file a monitor reads did not change: that is a failure of the check
                return report, 'probe_metrics_failed: the metrics file could not be written'
            if (report.get('queue') or {}).get('stuck'):  # the round trip worked but the jobs queue holds a job that has waited longer than MEMORY_QUEUE_STUCK_SECONDS
                return report, 'queue_stuck: oldest_pending_seconds=%s threshold_seconds=%s' % (report['queue']['oldest_pending_seconds'], report['queue']['threshold_seconds'])
            return report, None
        if not args.loop:
            report, verdict = run_once()
            if verdict:
                raise SystemExit(verdict)
            return
        try:
            interval = round_trip.probe_interval()
        except round_trip.ProbeError as error:
            raise SystemExit('%s: %s' % (error.code, error)) from None
        beat = round_trip.heartbeat_path(args.metrics_file, args.heartbeat_file)
        done, stopped = 0, False
        try:
            with round_trip.terminate_as_interrupt():  # SIGTERM is Ctrl-C for the whole life of the loop, the wait between runs included (it is where the loop spends nearly all its time)
                while LOOP_CYCLES is None or done < LOOP_CYCLES:
                    done += 1
                    round_trip.write_heartbeat(beat)  # the healthcheck reads this file, which only the loop writes (a manual `admin probe` also writes the .prom)
                    report, verdict = run_once()
                    round_trip.write_heartbeat(beat)
                    if verdict:
                        print(verdict, file=sys.stderr, flush=True)  # the service stays up: the metric, the event and this line are the alert; the next run retries
                    if report.get('code') == 'interrupted' or report.get('interrupted'):  # a stop reached the run or what follows it: the note is retired and the result is in the file
                        stopped = True
                        break
                    if LOOP_CYCLES is None or done < LOOP_CYCLES:
                        time.sleep(interval)
        except KeyboardInterrupt:  # a stop of the service in the wait, or between two lines of the loop
            stopped = True
        if stopped:
            raise SystemExit('probe_interrupted: the service was stopped')
        return
    try:
        settings = Settings.from_env()
        dsn = guarded_dsn(settings.dsn)
        store = Store(dsn, project_maps=settings.project_maps, embedding_enabled=True)
    except Exception:
        if args.command == 'backup-cycle':  # a setting of the environment that is invalid (MEMORY_MAX_ATTEMPTS=0): nothing ran, and the metric of the last good cycle must not stay at 1
            record_failure(Path(args.output_dir).resolve())
        raise
    if args.command == 'migrate':
        store.migrate()
        print(json.dumps({'status': 'migrated'}))
    elif args.command == 'backfill-chunks':
        if not getattr(settings, 'embed_enabled', True):
            print(json.dumps({'status': 'skipped', 'reason': 'embeddings_disabled', 'enqueued': 0}))
        else:
            print(json.dumps(dict(backfill_chunks(store, settings.embedding_model, batch=args.batch, max_jobs=args.max_jobs, project=args.project, retry_failed=args.retry_failed), status='backfilled'), sort_keys=True))
    elif args.command == 'probe-provision':
        try:
            print(json.dumps(round_trip.provision(store, args.key_file, operator=args.operator), sort_keys=True))
        except round_trip.ProbeError as error:
            raise SystemExit(f'{error.code}: {error}') from None
    elif args.command == 'prune-tables':
        print(json.dumps(prune_tables(store, windows, batch=args.batch, dry_run=args.dry_run, tables=args.table), sort_keys=True))
    elif args.command == 'bootstrap':
        if not args.password_file:
            parser.error('--password-file or MEMORY_BOOTSTRAP_PASSWORD_FILE is required')
        password = Path(args.password_file).read_text(encoding='utf-8').strip()
        actor = store.bootstrap_user(args.username, password)
        projects = []
        if args.with_projects:
            for project_id in settings.project_maps:
                store.create_project(actor, {'id': project_id, 'title': project_id})
                projects.append(project_id)
        print(json.dumps({'status': 'bootstrapped', 'username': args.username, 'projects': projects, 'capture': 'off'}))
    elif args.command == 'set-password':
        password = password_from_file(Path(args.password_file))
        try:
            result = store.set_password(args.username, password, revoke_keys=args.revoke_keys)
        except MemoryError as error:
            raise SystemExit(f'set_password_failed: {error.code}') from None  # the code only: neither the password nor a hash is in it
        print(json.dumps({'status': 'password_set', **result}, sort_keys=True))
    elif args.command == 'inspect':
        print(json.dumps({'tables': inspect_store(store)}, sort_keys=True))
    elif args.command == 'content-manifest':
        print(json.dumps(content_manifest(store), sort_keys=True, default=str))
    elif args.command == 'backup':
        output = Path(args.output).resolve()
        try:
            keep = None
            if args.keep is not None and not args.prune:
                raise BackupError('backup_keep_invalid', '--keep only applies with --prune')
            if args.prune:  # validated before anything is written or deleted
                if args.keep is None:
                    try:
                        keep = backup_keep()
                    except ValueError as error:
                        raise BackupError('backup_keep_invalid', str(error)) from None
                else:
                    if not args.keep.strip().isascii() or not args.keep.strip().isdigit():
                        raise BackupError('backup_keep_invalid', '--keep must be a whole number of 1 or more')
                    keep = check_keep(int(args.keep))
            # Before any file exists: a copy that must be encrypted and cannot be fails here, in the clear it is never written.
            recipients_file = backup_recipients_file()
            try:
                require_encryption = backup_require_encryption()
            except ValueError as error:  # a typo in the requirement fails closed, with a code a script can test
                raise BackupError('backup_config_invalid', str(error)) from None
            recipients = encryption_plan(recipients_file, require_encryption)
            output = encrypted_name(output, recipients)
            plain = output.with_name(output.name[:-4]) if output.name.endswith('.age') else output  # the name is taken in either form
            if any(os.path.lexists(name) or os.path.lexists(manifest_path(name)) for name in (plain, plain.with_name(plain.name + '.age'))):
                parser.error('Backup destination already exists; choose a new filename')
            with pg_environment(dsn) as environment:
                report = create_backup(store, output, environment=environment, recipients=recipients)
                if keep is not None:
                    try:
                        report['prune'] = prune_backups(output.parent, keep, protect=output)
                    except (BackupError, OSError) as error:  # the copy exists and is valid: its report is printed whatever stopped the prune
                        code = error.code if isinstance(error, BackupError) else 'backup_prune_failed'
                        print(json.dumps(dict(report, prune={'status': 'failed', 'code': code}), sort_keys=True))
                        raise BackupError(code, str(error) if isinstance(error, BackupError) else f'the prune failed ({type(error).__name__})') from None
                print(json.dumps(report, sort_keys=True))
        except BackupError as error:
            raise SystemExit(f'{error.code}: {error}') from None
    elif args.command == 'backup-cycle':
        observability.configure_logging()  # `backup_offsite_failed` goes to stderr as one JSON line
        output_dir = Path(args.output_dir).resolve()

        def one_cycle():
            try:
                return cycle_body()
            except Exception as error:  # a failure before `run_cycle` took over (the recipients, the service file): the metric of the cycle says so too
                if not getattr(error, 'offsite_recorded', False):
                    record_failure(output_dir)
                raise

        def cycle_body():
            recipients = encryption_plan(recipients_file, require_encryption)  # each cycle: a rotated recipients file is picked up
            if recipients is None:
                raise BackupError('backup_encryption_required', 'backup-cycle only sends encrypted copies and MEMORY_BACKUP_RECIPIENTS_FILE lists no recipients')
            tables = {}

            def end_with_tables():
                if args.prune_tables:
                    try:
                        tables['prune_tables'] = {'status': prune_tables(store, windows)['status']}
                    except Exception as error:  # the copy is made: what stopped the retention of the tables is a field of its report
                        tables['prune_tables'] = {'status': 'failed', 'error': type(error).__name__}
            with pg_environment(dsn) as environment:
                try:
                    report = run_cycle(lambda output: create_backup(store, encrypted_name(output, recipients), environment=environment, recipients=recipients),
                                       output_dir, destination, keep=keep, remote_keep=remote_keep, recipients_file=recipients_file)
                except CycleError as error:
                    end_with_tables()
                    error.report.update(tables)
                    raise
            end_with_tables()
            return dict(report, **tables)
        try:
            if args.loop:
                with terminate_as_exit():
                    run_loop(one_cycle, interval, cycles=LOOP_CYCLES)
            else:
                print(json.dumps(one_cycle(), sort_keys=True))
        except CycleError as error:
            print(json.dumps(error.report, sort_keys=True))
            raise SystemExit(f'{error.code}: {error}') from None
        except BackupError as error:
            raise SystemExit(f'{error.code}: {error}') from None
    elif args.command == 'restore-check':
        target = Path(args.target_dsn_file).read_text(encoding='utf-8').strip()
        if target == settings.dsn:
            parser.error('Restore target must be a separate, freshly created memory_restore* database')
        from psycopg.conninfo import conninfo_to_dict
        source_info, target_info = conninfo_to_dict(settings.dsn), conninfo_to_dict(target)
        if target == settings.dsn or not target_info.get('dbname', '').startswith('memory_restore') or (target_info.get('dbname') == source_info.get('dbname') and target_info.get('host') == source_info.get('host')):
            parser.error('Restore target must be a separate, freshly created memory_restore* database')
        restored = Store(guarded_dsn(target))
        with restored.transaction() as connection:
            if connection.execute("SELECT 1 FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') LIMIT 1").fetchone():
                parser.error('Restore target must be empty; no cleanup or overwrite is performed')
        if args.from_manifest:
            try:
                manifest = verify_backup(Path(args.backup), manifest_file=None if args.from_manifest == 'auto' else args.from_manifest)
                if manifest['encrypted'] and manifest['verified'] != 'content':
                    raise BackupError('backup_encrypted', 'This copy is encrypted: decrypt it with the private key (which is not on this host) and restore the plain dump')
            except BackupError as error:
                raise SystemExit(f'{error.code}: {error}') from None
            before = manifest['fingerprints']
        else:
            before = store_fingerprints(store)
        with pg_environment(guarded_dsn(target)) as environment:
            subprocess.run(['pg_restore', '--dbname=service=memory', '--no-owner', '--no-acl', '--exit-on-error', str(Path(args.backup).resolve())], env=environment, check=True, capture_output=True)
        after = store_fingerprints(restored)
        if before != after:
            if args.from_manifest:
                differing = sorted(table for table in set(before) | set(after) if before.get(table) != after.get(table))
                raise SystemExit('backup_restore_mismatch: the restored tables differ from the manifest of the copy: ' + ', '.join(differing))
            raise RuntimeError('Restore data fingerprints differ; inspect the isolated restored database')
        print(json.dumps({'status': 'restored_and_content_verified', 'tables': after}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Connection/provider errors may contain passwords or DSNs. Do not print them.
        raise SystemExit(f'Administration failed ({type(exc).__name__}); no credentials are printed.') from None
