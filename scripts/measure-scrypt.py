#!/usr/bin/env python3
"""Measure scrypt time and memory inside the containers that derive it (CA-09, T-01).

Builds a LOCAL image from the working tree (tag `kairos-measure:<target>`) and runs ephemeral containers
`kairos-measure-<service>` with the same `mem_limit` that docker-compose.yml declares for `memory-api`,
`memory-bootstrap` and `memory-admin` (`--network=none`, one at a time, `--rm`). It never touches containers,
volumes or networks of the deployed `knowledge-graphs-*` project and needs no secret. Prints one JSON document.

    python scripts/measure-scrypt.py --image-target operator [--reps 7] [--skip-build] [--keep-image]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / 'docker-compose.yml'
SERVICES = ('memory-api', 'memory-bootstrap', 'memory-admin')
# (label, n, r, p): the current value, the candidates of the spec (P-04) and the in-between steps.
CANDIDATES = (('current 2^14', 1 << 14, 8, 1), ('2^15', 1 << 15, 8, 1), ('2^16', 1 << 16, 8, 1),
              ('2^16 p=2', 1 << 16, 8, 2), ('2^17', 1 << 17, 8, 1))
CONCURRENCY = (1, 2, 3, 4, 6, 8)  # capped: the host is shared and real memory is k * 128 * n * r bytes
# The VPS sizes memory-api at 1 GB (docs/configuration.md); the compose default is 2 GB: both are measured.
EXTRA_LIMITS = {'memory-api': ('1g',)}
# Module the real process of each service imports: its idle memory is the baseline scrypt is added to.
MODULES = {'memory-api': 'memory_platform.app', 'memory-bootstrap': 'memory_platform.admin', 'memory-admin': 'memory_platform.admin'}

WORKER = r'''
import hashlib, importlib, json, os, resource, subprocess, sys, threading, time

CASES = json.loads(sys.argv[1]); REPS = int(sys.argv[2]); CONC = json.loads(sys.argv[3]); MODULE = sys.argv[4]
CHILD = r"""
import hashlib, importlib, json, os, resource, sys, threading, time
n, r, p, k, reps, module = (sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6])
n, r, p = int(n), int(r), int(p)
importlib.import_module(module)
def rss():
    for line in open('/proc/self/status'):
        if line.startswith('VmRSS:'): return int(line.split()[1]) / 1024
def derive(): hashlib.scrypt(b'measure-password', salt=os.urandom(16), n=n, r=r, p=p, maxmem=1 << 30, dklen=64)
base = rss(); times = []
for _ in range(reps if k == 1 else 1):
    threads = [threading.Thread(target=derive) for _ in range(k)]; t0 = time.perf_counter()
    for t in threads: t.start()
    for t in threads: t.join()
    times.append(time.perf_counter() - t0)
print(json.dumps({'baseline_mb': round(base, 1), 'times': times, 'peak_mb': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1), 'rss_after_mb': round(rss(), 1)}))
"""
def run(n, r, p, k, reps):
    c = subprocess.run([sys.executable, '-c', CHILD, str(n), str(r), str(p), str(k), str(reps), MODULE], capture_output=True, text=True)
    if c.returncode != 0:
        return {'ok': False, 'returncode': c.returncode, 'error': (c.stderr or '').strip().splitlines()[-1:] }
    return dict(json.loads(c.stdout.strip().splitlines()[-1]), ok=True)

def median(xs):
    xs = sorted(xs); m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2

rows = []
for label, n, r, p in CASES:
    one = run(n, r, p, 1, REPS)
    row = {'candidate': label, 'n': n, 'r': r, 'p': p, 'scrypt_mb': round(128 * r * n / 1048576, 1)}
    if not one['ok']:
        row.update(fits=False, error=one)
    else:
        row.update(fits=True, seconds=round(median(one['times']), 3), seconds_min=round(min(one['times']), 3), seconds_max=round(max(one['times']), 3),
                   peak_mb=one['peak_mb'], baseline_mb=one['baseline_mb'], rss_after_mb=one['rss_after_mb'], max_concurrent_ok=1, concurrent=[])
        for k in CONC[1:]:
            res = run(n, r, p, k, 1)
            row['concurrent'].append({'k': k, 'ok': res['ok'], 'seconds': round(median(res['times']), 3) if res['ok'] else None,
                                      'peak_mb': res.get('peak_mb'), 'returncode': res.get('returncode')})
            if not res['ok']:
                break
            row['max_concurrent_ok'] = k
    rows.append(row)

# Does hashlib.scrypt release the GIL? A ticker thread must keep ticking while another one derives.
n, r, p = 1 << 16, 8, 1
gaps = []; stop = False
def tick():
    last = time.perf_counter()
    while not stop:
        time.sleep(0.001); now = time.perf_counter(); gaps.append(now - last); last = now
def derive():
    hashlib.scrypt(b'measure-password', salt=os.urandom(16), n=n, r=r, p=p, maxmem=1 << 30, dklen=64)
th = threading.Thread(target=tick); th.start(); time.sleep(0.05); gaps.clear()
try:
    t0 = time.perf_counter(); derive(); span = time.perf_counter() - t0
finally:
    stop = True; th.join()
gil = {'derive_seconds': round(span, 3), 'max_ticker_gap_seconds': round(max(gaps), 4), 'gil_released': max(gaps) < span / 4}
print(json.dumps({'rows': rows, 'gil': gil}))
'''


def compose_limits():
    """mem_limit and cpus defaults of the three services, read from docker-compose.yml."""
    out, current = {}, None
    for line in COMPOSE.read_text(encoding='utf-8').splitlines():
        m = re.match(r'^  ([a-z][\w-]*):\s*$', line)
        if m:
            current = m.group(1)
        if current in SERVICES:
            m = re.match(r'^    (mem_limit|cpus):\s*\$\{\w+:-(\w+)\}', line)
            if m:
                out.setdefault(current, {})[m.group(1)] = m.group(2)
    return out


def docker(*args, **kw):
    return subprocess.run(['docker', *args], capture_output=True, text=True, **kw)


def measure_containers(names):
    """The containers this script started: those whose name BEGINS with `kairos-measure-` (Docker's `name=` filter matches anywhere in the name, so `x-kairos-measure-y` would pass it)."""
    return [name for name in names.split() if name.startswith('kairos-measure-')]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--image-target', default='operator')
    ap.add_argument('--reps', type=int, default=7)
    ap.add_argument('--skip-build', action='store_true')
    ap.add_argument('--keep-image', action='store_true')
    args = ap.parse_args(argv)
    tag = f'kairos-measure:{args.image_target}'
    limits = compose_limits()
    if set(limits) != set(SERVICES):
        sys.exit(f'docker-compose.yml: no mem_limit found for {sorted(set(SERVICES) - set(limits))}')
    if not args.skip_build:
        b = subprocess.run(['docker', 'build', '-f', 'server/memory_platform/Dockerfile', '--target', args.image_target, '-t', tag, '.'],
                           cwd=ROOT, stdout=sys.stderr, stderr=sys.stderr)
        if b.returncode:
            sys.exit('docker build failed')
    report = {'image': tag, 'reps': args.reps, 'compose': limits, 'containers': [], 'gil_released': None}
    try:
        for service in SERVICES:
            for mem in (limits[service]['mem_limit'],) + EXTRA_LIMITS.get(service, ()):
                name = f'kairos-measure-{service}' + ('' if mem == limits[service]['mem_limit'] else f'-{mem}')
                cpus = limits[service]['cpus']
                cmd = ['docker', 'run', '--rm', '-i', '--name', name, f'--memory={mem}', f'--memory-swap={mem}', '--network=none', '--entrypoint', 'python']
                if cpus not in ('0', '0.0'):
                    cmd.append(f'--cpus={cpus}')
                cmd += [tag, '-', json.dumps(CANDIDATES), str(args.reps), json.dumps(CONCURRENCY), MODULES[service]]
                print(f'measuring {name} (mem_limit {mem}, cpus {cpus})', file=sys.stderr)
                c = subprocess.run(cmd, input=WORKER, capture_output=True, text=True)
                if c.returncode != 0:
                    sys.exit(f'{name} failed: {c.stderr[-500:]}')
                data = json.loads(c.stdout.strip().splitlines()[-1])
                report['containers'].append({'container': name, 'service': service, 'mem_limit': mem, 'cpus': cpus, **data})
                if report['gil_released'] is None:
                    report['gil_released'] = data['gil']['gil_released']
    finally:
        for left in measure_containers(docker('ps', '-a', '--format', '{{.Names}}', '--filter', 'name=kairos-measure-').stdout):
            docker('rm', '-f', left)
        if not args.skip_build and not args.keep_image:
            docker('rmi', tag)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
