#!/usr/bin/env python3
"""Rehearsal of the reliable-operations initiative (CA-07, CA-37), in an isolated project `kairos-ops-*` that is removed at the end.

Stage `a` (closing of milestone A) runs the two closing criteria on ONE isolated project, one step after the other, Docker in the foreground:

  1. restore runbook   the whole of scripts/rehearse-restore.py (deploy, keys, `backup-cycle` to a simulated destination, download, verify, decrypt, restore into a NEW ephemeral
                       PostgreSQL) with a realistic volume of `memory.embeddings` seeded before the copy, so that the duration of the fingerprints says something
  2. fingerprints      the duration of the row fingerprints of the backup and of `restore-check` (`table_digest`/`table_fingerprints`), measured in the operator image of the project and
                       compared with `--backup-timeout` (3600 s); the cost per row and what 5 GB of embeddings would take at that rate
  3. database restart  with jobs queued, `memory-postgres` is stopped and started: `memory-worker` must not restart by its own error (same restart counter and same start time), the queue
                       must empty and no job may end `failed`

and ends with `restored_and_content_verified` and `worker_survived_db_restart`. It never touches `knowledge-graphs-*`, the Ollama of the host or any other project: the whole run is the
project given with --project-name (`kairos-ops-<name>`) and the resources the restore rehearsal names by exact name. Later stages of the initiative extend `--stage`; `all` runs every
stage there is.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STAGES = ('a', 'all')
PROJECT_ID = 'rehearsal'  # the project the deployment's own round trip creates (capture on)
SEED_MODEL, SEED_DIMS = 'rehearsal-seed', 768  # a model no index covers; the dimension of the usual embedding models
DEFAULT_SEED_ROWS, DEFAULT_QUEUE_JOBS = 30000, 300
DB_DOWN_SECONDS, DRAIN_SECONDS, READY_SECONDS = 30, 600, 180
BACKUP_TIMEOUT_SECONDS = 3600  # `--backup-timeout` of scripts/deploy-memory.py
REFERENCE_BYTES = 5 * 1024 ** 3  # the volume the review of milestone A worried about
FINGERPRINT_CODE = '''
import json, time
from memory_platform.config import Settings
from memory_platform.store import Store
from memory_platform import backup
store = Store(Settings.from_env().dsn)
with store.transaction() as connection:
    size = connection.execute("SELECT pg_table_size('memory.embeddings') AS n").fetchone()['n']
    started = time.monotonic()
    rows, _ = backup.table_digest(connection, 'embeddings')
    embeddings = time.monotonic() - started
    started = time.monotonic()
    tables = backup.table_fingerprints(connection)
    everything = time.monotonic() - started
print(json.dumps({'rows': rows, 'table_bytes': size, 'embeddings_seconds': round(embeddings, 2), 'all_tables_seconds': round(everything, 2), 'tables': len(tables)}))
'''


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


restore_module = load('kairos_rehearse_restore_ops', 'rehearse-restore.py')
RehearsalError = restore_module.RehearsalError


class OperationsRehearsal(restore_module.Rehearsal):
    def __init__(self, args, root=ROOT, run=None, portal=None):
        super().__init__(args, root, run)
        self.portal_factory = portal
        self.sleep = time.sleep
        self.clock = time.monotonic

    # -- helpers ----------------------------------------------------------------------------------------------------------------

    def compose_run(self, *arguments, timeout=restore_module.STEP_TIMEOUT, check=True):
        return self.run(self.compose() + list(arguments), timeout=timeout, environment=self.compose_environment(), check=check)

    def psql(self, statement):
        return self.compose_run('exec', '-T', 'memory-postgres', 'psql', '-U', 'memory', '-d', 'agent_memory', '-v', 'ON_ERROR_STOP=1', '-At', '-F', '|', '-c', statement)

    def job_states(self):
        counts = {}
        for line in self.psql('SELECT state, count(*) FROM memory.jobs GROUP BY state').splitlines():
            if '|' in line:
                state, count = line.split('|')
                counts[state.strip()] = int(count)
        return counts

    def container_of(self, service):
        """The id of the project's container of `service` (stopped or not)."""
        found = self.compose_run('ps', '-a', '-q', service).strip().splitlines()
        if len(found) != 1:
            raise RehearsalError(f'The project has no single {service} container')
        return found[0]

    def stop(self, service):
        """A plain `docker stop` of the project's container: `compose start` would insist on the one-shot `memory-migrate` that already ran and was removed."""
        self.run(['docker', 'stop', '--time', '60', self.container_of(service)])

    def start(self, service):
        self.run(['docker', 'start', self.container_of(service)])

    def worker(self):
        """(restart count, start time, running) of the project's `memory-worker` container."""
        out = self.run(['docker', 'inspect', '-f', '{{.RestartCount}}|{{.State.StartedAt}}|{{.State.Running}}', self.container_of('memory-worker')]).strip()
        count, started, running = out.split('|')
        return int(count), started, running == 'true'

    def wait_for(self, what, check, seconds, pause=2):
        deadline = self.clock() + seconds
        while True:
            value = check()
            if value:
                return value
            if self.clock() >= deadline:
                raise RehearsalError(f'{what} did not happen within {seconds} s')
            self.sleep(pause)

    def portal(self):
        factory = self.portal_factory
        if factory is None:
            factory = load('kairos_deploy_ops', 'deploy-memory.py').Portal
        return factory(f'http://127.0.0.1:{self.args.web_port}')

    # -- the steps --------------------------------------------------------------------------------------------------------------

    def seed_embeddings(self):
        """Rows of `memory.embeddings` of realistic width in the project of the round trip (the trigger fills the pgvector column like for any other writer)."""
        self.step('seed')
        rows = self.args.seed_rows
        self.psql(f"INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) SELECT '{PROJECT_ID}','seed-'||g,'item',1,md5(g::text),'{SEED_MODEL}',"
                  f'array_fill((g::float8)/1000000, ARRAY[{SEED_DIMS}]) FROM generate_series(1,{int(rows)}) g')
        present = int(self.psql(f"SELECT count(*) FROM memory.embeddings WHERE model='{SEED_MODEL}'").strip())
        if present != rows:
            raise RehearsalError(f'{present} seeded embeddings, expected {rows}')
        self.report['seed'] = {'embeddings': present, 'dims': SEED_DIMS}

    def timed(self, step):
        started = self.clock()
        step()
        return round(self.clock() - started, 1)

    def measure_fingerprints(self):
        self.step('fingerprints')
        out = self.compose_run('run', '--rm', '--no-deps', '-T', '--name', self.container('fingerprints'), '--entrypoint', 'python', 'memory-admin', '-c', FINGERPRINT_CODE,
                               timeout=restore_module.DEPLOY_TIMEOUT)
        measured = self.json(out.strip().splitlines()[-1] if out.strip() else '')
        seconds, size = max(measured['embeddings_seconds'], 0.01), measured['table_bytes']
        measured['seconds_per_row'] = round(seconds / max(measured['rows'], 1), 6)
        measured['megabytes_per_second'] = round(size / seconds / 1e6, 1)
        measured['seconds_for_5_gb'] = round(REFERENCE_BYTES / (size / seconds))
        measured['backup_timeout_seconds'] = BACKUP_TIMEOUT_SECONDS
        measured['within_timeout'] = measured['seconds_for_5_gb'] < BACKUP_TIMEOUT_SECONDS
        self.report['fingerprints'] = measured

    def queue_jobs(self):
        """Stop the worker, write `--queue-jobs` events through the API (each one queues an embed job), start the worker again: the queue is what it has to drain."""
        self.step('queue')
        password = restore_module.Path(self.work / 'secrets' / 'bootstrap_password').read_text(encoding='utf-8').strip()
        portal = self.portal()
        portal.login(password)
        key_id = None
        try:
            created = portal.request('/v1/keys', {'name': 'rehearsal-queue', 'project_ids': [PROJECT_ID], 'scopes': ['read', 'write']})
            key_id, token = created['id'], created['token']
            self.stop('memory-worker')
            for number in range(self.args.queue_jobs):
                event = {'event_id': str(uuid.uuid4()), 'project_id': PROJECT_ID, 'session_id': 'rehearsal-queue', 'agent_id': 'kairos-rehearsal', 'event_type': 'note',
                         'occurred_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'item_id': str(uuid.uuid4()), 'version': 1, 'generate': False,
                         'payload': {'title': f'Queued observation {number}', 'content': f'Observation {number} of the database restart rehearsal {uuid.uuid4().hex}.',
                                     'source': {'uri': 'fixture://rehearsal-queue'}}}
                portal.request('/v1/events', event, bearer=token)
        finally:
            try:
                if key_id:
                    portal.request('/v1/keys/' + key_id, method='DELETE')
            finally:
                portal.logout()
        waiting = self.job_states()
        self.report['queue'] = {'events': self.args.queue_jobs, 'pending_before_worker': waiting.get('pending', 0)}
        if not waiting.get('pending'):
            raise RehearsalError('No job was queued by the events')

    def database_restart(self):
        self.step('database_restart')
        self.start('memory-worker')
        self.wait_for('the worker running', lambda: self.worker()[2], READY_SECONDS)
        before = self.worker()
        def unfinished():
            states = self.job_states()
            return states.get('pending', 0) + states.get('running', 0) + states.get('unknown', 0)
        if not unfinished():
            raise RehearsalError('The queue was empty before the database stopped; raise --queue-jobs')
        pending = unfinished()  # the count that proves anything is this one, the last before `docker stop`: the worker drains while the first look is being read and the container started
        if not pending:
            raise RehearsalError('The queue was empty before the database stopped (the worker drained it first); raise --queue-jobs')
        self.stop('memory-postgres')
        self.sleep(DB_DOWN_SECONDS)
        during = self.worker()
        self.start('memory-postgres')
        self.wait_for('the database accepting connections', lambda: self.compose_run('exec', '-T', 'memory-postgres', 'pg_isready', '-U', 'memory', '-d', 'agent_memory', check=False) is not None
                      and self.last_code == 0, READY_SECONDS)

        def drained():
            states = self.job_states()
            return states if not states.get('pending') and not states.get('running') and not states.get('unknown') else None
        states = self.wait_for('the queue emptying', drained, DRAIN_SECONDS)
        after = self.worker()
        failed = states.get('failed', 0)
        result = {'restarts_before': before[0], 'restarts_after': after[0], 'same_start': before[1] == after[1], 'running': after[2], 'running_while_down': during[2],
                  'pending_at_stop': pending, 'down_seconds': DB_DOWN_SECONDS, 'jobs': states, 'failed': failed}
        self.report['worker_survived_db_restart'] = result
        if after[0] != before[0] or before[1] != after[1] or not after[2]:
            raise RehearsalError('memory-worker restarted (or stopped) when the database went down: ' + json.dumps(result, sort_keys=True))
        if failed:
            raise RehearsalError(f'{failed} job(s) ended failed after the database restart: ' + json.dumps(result, sort_keys=True))

    # -- the rehearsal ----------------------------------------------------------------------------------------------------------

    def sequence(self):
        timings = self.report.setdefault('timings', {})

        def cycle():
            timings['backup_cycle_seconds'] = self.timed(super(OperationsRehearsal, self).cycle)

        def restore():
            timings['restore_step_seconds'] = self.timed(super(OperationsRehearsal, self).restore)
        return [self.deploy, self.seed_embeddings, self.make_keys, cycle, self.download, self.verify, self.decrypt, restore, self.measure_fingerprints, self.queue_jobs, self.database_restart]

    def rehearse(self):
        failure = None
        self.work = Path(tempfile.mkdtemp(prefix='kairos-rehearse-'))
        try:
            self.refuse_existing()
        except BaseException:  # nothing was created: the resources of a project that already exists are not ours to remove
            shutil.rmtree(self.work, ignore_errors=True)
            raise
        try:
            for action in self.sequence():
                action()
        except BaseException as error:
            failure = error
        try:
            cleanup = self.cleanup()
        except BaseException as error:  # the cleanup never hides the failure that came first
            cleanup = f'incomplete: the cleanup stopped ({type(error).__name__})'
        if failure is not None:
            print('rehearsal partial report: ' + json.dumps(self.report, sort_keys=True), file=sys.stderr, flush=True)  # what was measured before the failure is not lost with the project
            if cleanup != 'complete':
                print(f'rehearsal cleanup: {cleanup}', file=sys.stderr, flush=True)
            raise failure
        if cleanup != 'complete':
            raise RehearsalError('The rehearsal succeeded but its cleanup is ' + cleanup)
        return dict(status='restored_and_content_verified', project=self.project, stage=self.args.stage, steps=self.steps, cleanup=cleanup, **self.report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-name', required=True, help='kairos-ops-<name>: the isolated project of the rehearsal (created and removed here)')
    parser.add_argument('--embed-stub', action='store_true', help='Required: the simulated embedding provider; the Ollama of the host is never used')
    parser.add_argument('--stage', choices=STAGES, default='all', help='a: the closing of milestone A (restore runbook, fingerprints, database restart); all: every stage there is')
    parser.add_argument('--seed-rows', type=int, default=DEFAULT_SEED_ROWS, help='Rows of memory.embeddings seeded before the copy (default %(default)s)')
    parser.add_argument('--queue-jobs', type=int, default=DEFAULT_QUEUE_JOBS, help='Events written (one embed job each) before the database is stopped (default %(default)s)')
    parser.add_argument('--api-port', type=int, default=restore_module.DEFAULT_API_PORT)
    parser.add_argument('--web-port', type=int, default=restore_module.DEFAULT_WEB_PORT)
    args = parser.parse_args(argv)
    if args.seed_rows < 1 or args.queue_jobs < 1:
        parser.error('--seed-rows and --queue-jobs must be 1 or more')
    try:
        report = OperationsRehearsal(args).apply()
    except RehearsalError as error:
        print(f'rehearsal_failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
