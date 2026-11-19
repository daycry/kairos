#!/usr/bin/env python3
"""Rehearsal of the reliable-operations initiative (CA-07, CA-37), in an isolated project `kairos-ops-*` that is removed at the end.

Stage `a` (closing of milestone A) runs the two closing criteria on ONE isolated project, one step after the other, Docker in the foreground:

  1. restore runbook   the whole of scripts/rehearse-restore.py (deploy, keys, `backup-cycle` to a simulated destination, download, verify, decrypt, restore into a NEW ephemeral
                       PostgreSQL) with a realistic volume of `memory.embeddings` seeded before the copy, so that the duration of the fingerprints says something
  2. fingerprints      the duration of the row fingerprints of the backup and of `restore-check` (`table_digest`/`table_fingerprints`), measured in the operator image of the project and
                       compared with `--backup-timeout` (3600 s); the cost per row and what 5 GB of embeddings would take at that rate
  3. database restart  with jobs queued, `memory-postgres` is stopped and started: `memory-worker` must not restart by its own error (same restart counter and same start time), the queue
                       must empty and no job may end `failed`

and ends with `restored_and_content_verified` and `worker_survived_db_restart`.

Stage `rollback` (closing of C-04: CA-24 and the rehearsal case of CA-21) runs on ONE isolated project, one step after the other, Docker in the foreground:

  1. deploy            the first deployment (`--fresh --embed-stub --roundtrip`) and a second one (`--no-verify-backup`): the second tags the images of the first as
                       `rehearsal-<project>-<name>:<version>-<mark>` before it builds and records them in `deployment-status.json`
  2. tags              the recorded tags exist and have the shape `<repository>:<version>-<mark>`, one per image
  3. bad_release       a "faulty release" is put in place: `memory-api` and `memory-worker` are recreated on an image committed from the first one with another label, so that the
                       containers really run something other than what the tags hold
  4. rollback          `deploy-memory.py --apply --rollback`: the services go back to the recorded tags (container image = the tag's image, not the faulty one), no `migrate` ran
                       (the phases are engine, configuration, rollback, verify, roundtrip), the `content-manifest` equals the one read just before, and the round trip finds
                       an observation by search
  5. worker_unhealthy  the loop of `memory-worker` is stopped (SIGSTOP of its process: the container keeps running and its healthcheck keeps running), and the container must turn
                       `unhealthy` within the AMENDED bound of CA-21: the deadline the heartbeat file holds (the last beat) + `interval x retries` of the container's own healthcheck
                       + the durations of the probes (Docker waits `interval` AFTER a probe ends, so each probe adds its own duration: the last good one and the failing ones), all
                       read from `State.Health.Log` together with the instant of the transition (the end of the probe that made it `unhealthy`), not from the clock of the poll;
                       it is then resumed and must be healthy again

and ends with `rollback_ok`, with the measurements under `rollback` and `worker_unhealthy`. It never touches `knowledge-graphs-*`, the Ollama of the host or any other project: the whole run is the
project given with --project-name (`kairos-ops-<name>`) and the resources the restore rehearsal names by exact name (the tagged images and the faulty ones included, removed by exact
reference or id at the end). 
Stage `probe` (C-06, closing criterion 3) runs on ONE isolated project: the deployment, `probe-provision`, then `admin probe` with the definition of the `memory-probe` service:

  1. probe_healthy         ends 0 with `probe_ok`, `kairos_probe_success 1` in the metrics file and a queue read that is not stuck
  2. probe_worker_stopped  with `memory-worker` stopped (and started again at the end, whatever happens) it fails at stage `index` with `timeout` within MEMORY_PROBE_TIMEOUT, exits non-zero,
                           writes `kairos_probe_success 0` and, with MEMORY_QUEUE_STUCK_SECONDS lowered, reports `queue_stuck`
  3. probe_recovered       with the worker back and the queue drained the probe ends `probe_ok` again

and ends with `probe_rehearsal_ok`. `all` runs stage `a`, then the `rollback` steps and then the `probe` ones on the same project.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STAGES = ('a', 'rollback', 'probe', 'all')
PROJECT_ID = 'rehearsal'  # the project the deployment's own round trip creates (capture on)
SEED_MODEL, SEED_DIMS = 'rehearsal-seed', 768  # a model no index covers; the dimension of the usual embedding models
DEFAULT_SEED_ROWS, DEFAULT_QUEUE_JOBS = 30000, 300
DB_DOWN_SECONDS, DRAIN_SECONDS, READY_SECONDS = 30, 600, 180
BACKUP_TIMEOUT_SECONDS = 3600  # `--backup-timeout` of scripts/deploy-memory.py
REFERENCE_BYTES = 5 * 1024 ** 3  # the volume the review of milestone A worried about
ROLLBACK_IMAGES = ('api', 'worker', 'mcp', 'web', 'operator')  # the images a deployment tags (scripts/deploy-memory.py IMAGE_NAMES)
FAULTY_SERVICES = ('api', 'worker')  # recreated on the "faulty release" image before the rollback
FAULTY_LABEL = 'com.kairos.rehearsal=faulty-release'
HEALTH_SLACK_SECONDS = 10  # only the margin of the WAIT, so that a late `unhealthy` can still be measured and reported; the verdict (`within_bound`) is strict and never uses it
POLL_PAUSE_SECONDS = 3  # the pause between two polls of the health: it lengthens the wait only; the instant that counts is the one `State.Health.Log` holds, reported apart
UNHEALTHY_EXTRA_SECONDS, RECOVER_SECONDS, HEALTHY_SECONDS = 240, 240, 300
PROBE_TIMEOUT_SECONDS = 30  # MEMORY_PROBE_TIMEOUT of the probe runs: short, so that the stopped-worker case does not wait the 120 s of the default
PROBE_STUCK_SECONDS = 10  # MEMORY_QUEUE_STUCK_SECONDS of the stopped-worker run: below the 30 s that the embed job waits, so `queue_stuck` is the verdict
PROBE_METRICS_FILE = '/backups/probe/kairos-probe.prom'  # the default of `admin probe`, in the volume of the isolated project
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


def health_time(text):
    """An instant of `State.Health.Log` (RFC 3339 with nanoseconds, written by the daemon) as seconds since the epoch; ValueError if it cannot be read."""
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})', text) if isinstance(text, str) else None
    if not match:
        raise ValueError(f'not an RFC 3339 instant: {text!r}')
    base, fraction, zone = match.groups()
    return datetime.fromisoformat(f"{base}.{(fraction or '')[:6].ljust(6, '0')}{'+00:00' if zone == 'Z' else zone}").timestamp()


def unhealthy_verdict(log, deadline, interval, retries):
    """CA-21 (amended), from the probes of the daemon (`State.Health.Log`, chronological): when the container turned `unhealthy` and the bound that follows from how Docker schedules probes.

    A container turns `unhealthy` at the END of the `retries`-th consecutive failing probe (an exit code other than 0, a timeout included). The last good probe P0 started no later than the deadline D
    (it still passed), the next one starts `interval` after P0 ENDS (Docker resets its timer when a probe finishes), and so on: the transition is at most
    D + duration(P0) + interval x retries + the sum of the durations of the `retries` failing probes. Every duration is read from the log, so a slow probe lengthens the bound by exactly its
    own length; nothing here is a margin. A probe still running (no end) is ignored; without a good probe in the log its duration is unknown and reported as None (taken as 0)."""
    probes = []
    for entry in log if isinstance(log, list) else []:
        try:
            start, end, code = health_time(entry['Start']), health_time(entry['End']), int(entry['ExitCode'])
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue  # a probe that is still running has no end; a time that cannot be read is not evidence
        if end >= start:
            probes.append((start, end, code))
    first = len(probes)
    while first and probes[first - 1][2] != 0:
        first -= 1
    failing = probes[first:]
    if len(failing) < retries:
        raise RehearsalError(f'the health log of the worker holds {len(failing)} failing probe(s) in a row and the healthcheck allows {retries}: it does not show the transition to unhealthy')
    counted = failing[:retries]
    good = probes[first - 1] if first else None
    durations = [round(end - start, 3) for start, end, _ in counted]
    good_seconds = round(good[1] - good[0], 3) if good else None
    unhealthy_at = counted[-1][1]
    bound = deadline + interval * retries + (good_seconds or 0.0) + sum(durations)
    return {'unhealthy_at': unhealthy_at, 'bound': bound, 'late_by': unhealthy_at - bound, 'within_bound': unhealthy_at <= bound, 'failed_probe_seconds': durations,
            'last_ok_probe_seconds': good_seconds, 'transition_source': 'State.Health.Log'}


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

    # -- stage rollback ---------------------------------------------------------------------------------------------------------

    def read_status(self):
        try:
            return json.loads((self.private / 'deployment-status.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise RehearsalError('The deployment left no readable deployment-status.json') from None

    def deploy_command(self, *extra):
        return [sys.executable, str(self.root / 'scripts/deploy-memory.py'), '--apply', *extra, '--project-name', self.project, '--secret-dir', str(self.work / 'secrets'),
                '--api-port', str(self.args.api_port), '--web-port', str(self.args.web_port), '--embed-stub', '--roundtrip']

    def second_deploy(self):
        """The second deployment of the project: it tags the images of the first (the previous release) before it builds."""
        self.step('deploy_again')
        self.run(self.deploy_command('--no-verify-backup'), timeout=restore_module.DEPLOY_TIMEOUT)

    def image_id(self, reference):
        out = self.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', reference], check=False)
        return out.strip() if self.last_code == 0 and out.strip() else None

    def container_image(self, service):
        return self.run(['docker', 'inspect', '-f', '{{.Image}}', self.container_of(service)]).strip()

    def content_hash(self):
        out = self.compose_run('run', '--rm', '--no-deps', '-T', '--name', self.container('manifest'), 'memory-admin', 'content-manifest', timeout=restore_module.DEPLOY_TIMEOUT)
        return self.json(out.strip())['sha256']

    def tagged_images(self):
        self.step('tags')
        recorded = self.read_status().get('images') or {}
        previous = recorded.get('previous') or {}
        missing = [name for name in ROLLBACK_IMAGES if name not in previous]
        if missing:
            raise RehearsalError('The second deployment recorded no previous tag for: ' + ', '.join(missing))
        ids = {}
        for name, tag in previous.items():
            if not re.fullmatch(re.escape(f'rehearsal-{self.project}-{name}') + r':[A-Za-z0-9_.]+-\d{8}T\d{6}Z', tag):
                raise RehearsalError(f'The recorded tag {tag} is not rehearsal-{self.project}-{name}:<version>-<mark>')
            ids[name] = self.image_id(tag)
            if not ids[name]:
                raise RehearsalError(f'The recorded tag {tag} does not exist in Docker')
        self.previous_ids = ids
        self.report['tags'] = {'previous': previous, 'ids': ids, 'kept': recorded.get('kept')}

    def faulty_release(self):
        """Put something else than the tagged images in `:latest` and under `memory-api` and `memory-worker`: an image committed from the previous one with another label (an exact copy
        otherwise, so the stack still works). Without it two deployments of the same source would hold the same image and a rollback could not be told from doing nothing."""
        self.step('bad_release')
        self.faulty_ids = []
        for name in FAULTY_SERVICES:
            temporary = self.container(f'faulty-{name}')
            self.run(['docker', 'create', '--name', temporary, self.previous_ids[name]])
            self.run(['docker', 'commit', '-c', f'LABEL {FAULTY_LABEL}', temporary, self.image(name)])
            self.run(['docker', 'rm', '--force', temporary])
            self.faulty_ids.append(self.image_id(self.image(name)))
        services = [f'memory-{name}' for name in FAULTY_SERVICES]
        self.compose_run('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', *services, timeout=restore_module.DEPLOY_TIMEOUT)
        for name, faulty in zip(FAULTY_SERVICES, self.faulty_ids):
            if self.container_image(f'memory-{name}') != faulty or faulty == self.previous_ids[name]:
                raise RehearsalError(f'memory-{name} does not run the faulty image that was put in place')
        self.report['faulty_release'] = {name: faulty for name, faulty in zip(FAULTY_SERVICES, self.faulty_ids)}

    def rollback_deployment(self):
        self.step('rollback')
        before = self.content_hash()
        self.run(self.deploy_command('--rollback'), timeout=restore_module.DEPLOY_TIMEOUT)
        status = self.read_status()
        rollback, images = status.get('rollback') or {}, status.get('images') or {}
        phases = status.get('phases') or []
        if status.get('status') != 'rolled_back' or rollback.get('migrated') is not False:
            raise RehearsalError('The deployment did not report a rollback without migrating: ' + json.dumps({k: status.get(k) for k in ('status', 'failed_phase', 'message')}))
        if phases[:4] != ['engine', 'configuration', 'rollback', 'verify'] or any('migrate' in phase or phase in ('backup', 'bootstrap', 'backfill', 'build') for phase in phases):
            raise RehearsalError('The rollback ran phases it must not: ' + ', '.join(phases))
        if status.get('content_sha256') != before:
            raise RehearsalError('The content-manifest after the rollback differs from the one read before it')
        for name in ROLLBACK_IMAGES:
            if (images.get('current') or {}).get(name) != self.previous_ids[name]:
                raise RehearsalError(f'The recorded current image of {name} is not the one of its tag')
        for name in FAULTY_SERVICES:
            running = self.container_image(f'memory-{name}')
            if running != self.previous_ids[name] or running in self.faulty_ids:
                raise RehearsalError(f'memory-{name} does not run the image of its recorded tag after the rollback')
        found = (status.get('roundtrip') or {}).get('found_ref')
        if not found:
            raise RehearsalError('The search after the rollback found nothing')
        self.report['rollback'] = {'status': status['status'], 'migrated': False, 'phases': phases, 'content_sha256': before, 'content_equal': True, 'search_found_ref': found,
                                   'restored_to': {name: self.previous_ids[name] for name in FAULTY_SERVICES}, 'replaced_faulty': dict(zip(FAULTY_SERVICES, self.faulty_ids))}

    def health(self, service):
        return self.run(['docker', 'inspect', '-f', '{{.State.Health.Status}}', self.container_of(service)]).strip()

    def health_log(self, container):
        return self.json(self.run(['docker', 'inspect', '-f', '{{json .State.Health.Log}}', container]).strip())

    def container_now(self, container):
        return float(self.run(['docker', 'exec', container, 'python', '-c', 'import time;print(time.time())']).strip())

    def worker_unhealthy(self):
        """CA-21 (amended): with the loop stopped the container turns `unhealthy` within the deadline the heartbeat file holds + `interval x retries` + the durations of the probes (`unhealthy_verdict`).
        The deadline and the stop are read on the container's clock, the one the healthcheck compares the deadline with; the transition and the probes come from `State.Health.Log`, written by the daemon
        on the same machine (the same kernel clock), so the poll that notices it, which is later by up to its pause plus the time of the command, does not enter the verdict."""
        self.step('worker_unhealthy')
        container = self.container_of('memory-worker')
        check = self.json(self.run(['docker', 'inspect', '-f', '{{json .Config.Healthcheck}}', container]).strip())
        interval, retries, timeout = check['Interval'] / 1e9, int(check['Retries']), check.get('Timeout', 0) / 1e9
        self.wait_for('the worker healthy before its loop is stopped', lambda: self.health('memory-worker') == 'healthy', HEALTHY_SECONDS, pause=5)
        stopped = False
        try:
            self.run(['docker', 'kill', '--signal', 'SIGSTOP', container])
            stopped = True
            stopped_at = self.container_now(container)
            deadline = float(self.run(['docker', 'exec', container, 'python', '-c', "print(open('/tmp/kairos-worker-heartbeat').read().strip())"]).strip())  # frozen: the last beat
            ceiling = deadline + interval * retries + (retries + 1) * timeout  # the longest the bound can be (probes that all time out): only for how long to WAIT
            self.wait_for('memory-worker turning unhealthy with its loop stopped', lambda: self.health('memory-worker') == 'unhealthy',
                          max(ceiling - stopped_at, 0) + HEALTH_SLACK_SECONDS + UNHEALTHY_EXTRA_SECONDS, pause=POLL_PAUSE_SECONDS)
            verdict = unhealthy_verdict(self.health_log(container), deadline, interval, retries)
            unhealthy_at, bound = verdict['unhealthy_at'], verdict['bound']
            result = {'loop_stopped': 'SIGSTOP of the process of memory-worker (the container and its healthcheck keep running)', 'interval_seconds': interval, 'retries': retries,
                      'deadline_after_stop_seconds': round(deadline - stopped_at, 1), 'bound_after_stop_seconds': round(bound - stopped_at, 1),
                      'unhealthy_after_stop_seconds': round(unhealthy_at - stopped_at, 1), 'unhealthy_after_deadline_seconds': round(unhealthy_at - deadline, 1),
                      'late_by_seconds': round(verdict['late_by'], 1), 'failed_probe_seconds': verdict['failed_probe_seconds'], 'last_ok_probe_seconds': verdict['last_ok_probe_seconds'],
                      'transition_source': verdict['transition_source'], 'measurement_pause_seconds': POLL_PAUSE_SECONDS, 'within_bound': verdict['within_bound']}
            self.report['worker_unhealthy'] = result
            if not result['within_bound']:
                raise RehearsalError('memory-worker turned unhealthy later than the deadline of its last beat + interval x retries + the durations of the probes: ' + json.dumps(result, sort_keys=True))
        finally:
            if stopped:
                self.run(['docker', 'kill', '--signal', 'SIGCONT', container], check=False)
        self.wait_for('memory-worker healthy again once its loop runs', lambda: self.health('memory-worker') == 'healthy', RECOVER_SECONDS, pause=5)
        self.report['worker_unhealthy']['recovered'] = True

    def remove_tagged_images(self):
        """What the deployments of this rehearsal left in the image store, by exact repository and id: the tags `<version>-<mark>`, `:latest` and the faulty images. Returns the problems."""
        problems = []
        for name in ROLLBACK_IMAGES:
            repository = f'rehearsal-{self.project}-{name}'
            for reference in self.run(['docker', 'image', 'ls', repository, '--format', '{{.Repository}}:{{.Tag}}'], check=False).split():
                if reference.startswith(repository + ':'):
                    self.run(['docker', 'image', 'rm', reference], check=False)
        for image_id in getattr(self, 'faulty_ids', []):
            if image_id:
                self.run(['docker', 'image', 'rm', image_id], check=False)
        for name in ROLLBACK_IMAGES:
            repository = f'rehearsal-{self.project}-{name}'
            left = [r for r in self.run(['docker', 'image', 'ls', repository, '--format', '{{.Repository}}:{{.Tag}}'], check=False).split() if r.startswith(repository + ':')]
            problems += [f'image left in docker: {r}' for r in left]
        for image_id in getattr(self, 'faulty_ids', []):
            if image_id and self.image_id(image_id):
                problems.append(f'faulty image left in docker: {image_id}')
        return problems

    def cleanup(self):
        result = super().cleanup()
        try:
            extra = self.remove_tagged_images()
        except BaseException as error:  # the rest of the cleanup is done; this one never hides the failure that came first
            extra = [f'tagged images ({type(error).__name__})']
        if not extra:
            return result
        return ('incomplete: ' if result == 'complete' else result + ', ') + ', '.join(extra)

    # -- stage `probe` (T-77, criterion of closing 3): the round trip healthy and with memory-worker stopped ------------------------------------------

    def probe_run(self, label, timeout, stuck=None):
        """One `admin probe` with the definition of the `memory-probe` service (profile `probe`: its image, secret, volume and network) and the command of a single run. Returns (exit code, the report
        it printed, the metrics file it left). The probe key and the metrics file live in the volume of the isolated project, never in the host."""
        settings = ['-e', f'MEMORY_PROBE_TIMEOUT={timeout}'] + (['-e', f'MEMORY_QUEUE_STUCK_SECONDS={stuck}'] if stuck else [])
        out = self.run(self.compose() + ['--profile', 'probe', 'run', '--rm', '--no-deps', '-T', '--name', self.container(label)] + settings + ['memory-probe', 'probe'],
                       timeout=restore_module.DEPLOY_TIMEOUT, environment=self.compose_environment(), check=False)
        code = self.last_code
        lines = [line for line in out.splitlines() if line.startswith('{')]
        report = self.json(lines[-1] if lines else '')
        metrics = self.compose_run('run', '--rm', '--no-deps', '-T', '--name', self.container(label + '-metrics'), '--entrypoint', 'cat', 'memory-admin', PROBE_METRICS_FILE)
        return code, report, metrics

    def probe_provision(self):
        self.step('probe_provision')
        out = self.compose_run('run', '--rm', '--no-deps', '-T', '--name', self.container('probe-provision'), 'memory-admin', 'probe-provision')
        lines = [line for line in out.splitlines() if line.startswith('{')]
        self.report['probe_provision'] = {'status': self.json(lines[-1] if lines else '').get('status')}

    def probe_healthy(self):
        """A healthy installation: the probe ends with 0, `probe_ok` and `kairos_probe_success 1`; the queue it read (through the database of the project) is not stuck."""
        self.step('probe_healthy')
        code, report, metrics = self.probe_run('probe-ok', PROBE_TIMEOUT_SECONDS)
        if code != 0 or report.get('status') != 'probe_ok' or not re.search(r'^kairos_probe_success 1\.0$', metrics, re.M):
            raise RehearsalError('The probe of a healthy installation did not end probe_ok with kairos_probe_success 1: ' + json.dumps({'exit': code, 'status': report.get('status'), 'stage': report.get('stage'), 'code': report.get('code')}))
        if not report.get('queue') or report['queue'].get('stuck'):
            raise RehearsalError('The probe of a healthy installation did not read a queue that is not stuck: ' + json.dumps(report.get('queue')))
        self.report['probe_healthy'] = {'exit': code, 'status': report['status'], 'stages': report.get('stages'), 'total_seconds': report.get('total_seconds'), 'queue': report['queue'], 'kairos_probe_success': 1}

    def probe_worker_stopped(self):
        """`memory-worker` stopped (a plain `docker stop`, as in the other stages): the probe must fail at stage `index` with `timeout` within MEMORY_PROBE_TIMEOUT, exit non-zero, write
        `kairos_probe_success 0` and, with the threshold lowered, report `queue_stuck` (the embed job it wrote waits for a worker that is not there). The worker is started again at the end, always."""
        self.step('probe_worker_stopped')
        self.stop('memory-worker')
        try:
            code, report, metrics = self.probe_run('probe-stopped', PROBE_TIMEOUT_SECONDS, stuck=PROBE_STUCK_SECONDS)
        finally:
            self.start('memory-worker')
        spent = round((report.get('stages') or {}).get('write', 0) + (report.get('stages') or {}).get('index', 0), 3)
        if code == 0 or (report.get('status'), report.get('stage'), report.get('code')) != ('probe_failed', 'index', 'timeout') or not re.search(r'^kairos_probe_success 0\.0$', metrics, re.M):
            raise RehearsalError('The probe with memory-worker stopped did not fail at stage index with timeout and kairos_probe_success 0: ' + json.dumps({'exit': code, 'status': report.get('status'), 'stage': report.get('stage'), 'code': report.get('code')}))
        if spent > PROBE_TIMEOUT_SECONDS + 1:
            raise RehearsalError(f'The probe failed after {spent} s of write and index, above MEMORY_PROBE_TIMEOUT ({PROBE_TIMEOUT_SECONDS} s)')
        if not (report.get('queue') or {}).get('stuck'):
            raise RehearsalError('The probe did not report queue_stuck with the embed job waiting and the threshold at ' + str(PROBE_STUCK_SECONDS) + ' s: ' + json.dumps(report.get('queue')))
        self.report['probe_worker_stopped'] = {'exit': code, 'status': report['status'], 'stage': report['stage'], 'code': report['code'], 'seconds_to_failure': spent, 'timeout_seconds': PROBE_TIMEOUT_SECONDS,
                                               'retired': report.get('retired'), 'queue': report['queue'], 'kairos_probe_success': 0}

    def probe_recovered(self):
        """The worker is back: it drains what the failed probe left and the next probe ends `probe_ok` again."""
        self.step('probe_recovered')
        self.wait_for('the worker running', lambda: self.worker()[2], READY_SECONDS)
        def drained():
            states = self.job_states()
            return not (states.get('pending', 0) + states.get('running', 0) + states.get('unknown', 0))
        self.wait_for('the queue drained', drained, DRAIN_SECONDS, pause=5)
        code, report, metrics = self.probe_run('probe-recovered', PROBE_TIMEOUT_SECONDS)
        if code != 0 or report.get('status') != 'probe_ok' or not re.search(r'^kairos_probe_success 1\.0$', metrics, re.M):
            raise RehearsalError('The probe did not end probe_ok once memory-worker was running again: ' + json.dumps({'exit': code, 'status': report.get('status'), 'stage': report.get('stage'), 'code': report.get('code')}))
        self.report['probe_recovered'] = {'exit': code, 'status': report['status']}

    def probe_steps(self):
        return [self.probe_provision, self.probe_healthy, self.probe_worker_stopped, self.probe_recovered]

    # -- the rehearsal ----------------------------------------------------------------------------------------------------------

    def rollback_steps(self):
        return [self.second_deploy, self.tagged_images, self.faulty_release, self.rollback_deployment, self.worker_unhealthy]

    def sequence(self):
        if self.args.stage == 'rollback':
            return [self.deploy] + self.rollback_steps()
        if self.args.stage == 'probe':
            return [self.deploy] + self.probe_steps()
        timings = self.report.setdefault('timings', {})

        def cycle():
            timings['backup_cycle_seconds'] = self.timed(super(OperationsRehearsal, self).cycle)

        def restore():
            timings['restore_step_seconds'] = self.timed(super(OperationsRehearsal, self).restore)
        stage_a = [self.deploy, self.seed_embeddings, self.make_keys, cycle, self.download, self.verify, self.decrypt, restore, self.measure_fingerprints, self.queue_jobs, self.database_restart]
        return stage_a + (self.rollback_steps() + self.probe_steps() if self.args.stage == 'all' else [])

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
        status = {'a': 'restored_and_content_verified', 'rollback': 'rollback_ok', 'probe': 'probe_rehearsal_ok', 'all': 'rehearsal_ok'}[self.args.stage]
        return dict(status=status, project=self.project, stage=self.args.stage, steps=self.steps, cleanup=cleanup, **self.report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-name', required=True, help='kairos-ops-<name>: the isolated project of the rehearsal (created and removed here)')
    parser.add_argument('--embed-stub', action='store_true', help='Required: the simulated embedding provider; the Ollama of the host is never used')
    parser.add_argument('--stage', choices=STAGES, default='all', help='a: the closing of milestone A (restore runbook, fingerprints, database restart); probe: the round trip healthy and with memory-worker stopped (C-06); rollback: two tagged deployments, --rollback without migrating and the worker turning unhealthy with its loop stopped (C-04); all: every stage there is')
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
