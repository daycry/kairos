"""Calibration of the abstention threshold of the real embeddings model (T-89, P-05): `python -m memory_platform.tests.retrieval_eval.measure_abstention` (from `server/`).

It starts a DISPOSABLE Ollama (container, volume and network of its own, all named `kairos-calib-*`, on a port of your choice that is never the deployed one), pulls
`nomic-embed-text` into it, runs the retrieval-eval harness (`run_postgres` with `MEMORY_RETRIEVAL_EVAL=1`) in a second container on that network against it, and picks
the threshold with `pick_threshold` over the best cosine of every question of `dataset-v1` and of `dataset-v1-negatives`. It always removes what it created (``finally``),
including when the pull or the evaluation fails, and then checks that nothing named `kairos-calib-*` is left. If the model cannot be pulled in time, or no threshold reaches the
goals, the result is `uncalibrated` with the reason and `MEMORY_ABSTAIN_THRESHOLDS` must not name the model (the search answers `abstention: "uncalibrated"`).

It never talks to the Ollama of the host or to the deployed installation: every name must start with `kairos-calib-`, may not contain `knowledge-graphs`, and the port may not be the
deployed one (DEPLOYED_PORT). The suite does not run it (it needs a Docker daemon); `test_metrics.MeasureAbstentionTests` covers it with a fake Docker.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from memory_platform.tests.retrieval_eval.run import HERE, pick_threshold

PREFIX = 'kairos-calib-'
DEPLOYED_PORT = 11434  # the conventional Ollama port, where the deployed installation and the host's Ollama listen: refused, never used
MODEL = 'nomic-embed-text'
OLLAMA_IMAGE = 'ollama/ollama:0.31.1@sha256:f1a705f2bd113fb8d15f85f7c217f0dc5f6bebda6b0cc42b82c3ad165ffcb9dc'  # pinned by digest (checked with `docker image inspect`); a local image: nothing but the model is downloaded
SERVER_DIR = Path(__file__).resolve().parents[3]
MEMORY_LIMIT = '3g'
RESULT_PREFIX = 'RETRIEVAL_EVAL_RESULT '


def check_names(container, volume, network, port):
    """SystemExit unless every resource is one of the disposable `kairos-calib-*` ones and the port is not the deployed Ollama's (nor a privileged one)."""
    for kind, name in (('container', container), ('volume', volume), ('network', network)):
        if not isinstance(name, str) or not name.startswith(PREFIX) or 'knowledge-graphs' in name.lower():
            raise SystemExit('measure_abstention refuses the %s name %r: it must start with %s and never name the deployed installation.' % (kind, name, PREFIX))
    if isinstance(port, bool) or not isinstance(port, int) or port == DEPLOYED_PORT or not 1024 <= port <= 65535:
        raise SystemExit('measure_abstention refuses port %r: it must be an unprivileged port other than the deployed Ollama one (%d).' % (port, DEPLOYED_PORT))


def run_docker(args, timeout=None):
    # UTF-8 with replacement: the output of a container (pytest-style logs, Spanish text) is not in the console code page, and a decode error in subprocess's reader thread loses the whole report
    return subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)


def curve(rows, step=0.05):
    """(threshold, correct abstention, false abstention) every ``step``, to see how far a model is from the goals when no threshold reaches them."""
    negatives, positives = [r for r in rows if r['negative']], [r for r in rows if not r['negative']]

    def rate(group, t):
        return round(sum(1 for r in group if not r['protected'] and r.get('best') is not None and r['best'] < t) / len(group), 4) if group else 0.0
    return [[round(t / 100, 2), rate(negatives, t / 100), rate(positives, t / 100)] for t in range(int(step * 100), 100, int(step * 100))]


def goals_from_thresholds():
    config = json.loads((HERE / 'thresholds.json').read_text(encoding='utf-8')).get('abstention', {})
    return config.get('min_correct_rate', 0.70), config.get('max_false_rate', 0.05)


def parse_report(output):
    lines = [line for line in output.splitlines() if line.startswith(RESULT_PREFIX)]
    if not lines:
        raise SystemExit('measure_abstention: the evaluation printed no report; tail of its output:\n' + '\n'.join(output.splitlines()[-15:]))
    return json.loads(lines[-1][len(RESULT_PREFIX):])


def measure(container=PREFIX + 'ollama', port=21434, network=PREFIX + 'net', image=OLLAMA_IMAGE, eval_image=None, server_dir=None, pull_timeout=1200,
            eval_timeout=3600, docker=run_docker):
    """Run the calibration; returns the result dict (always with ``leftovers``) and raises SystemExit if the evaluation itself broke (after cleaning up)."""
    volume, evaluation = container + '-data', PREFIX + 'eval'
    check_names(container, volume, network, port)
    check_names(evaluation, volume, network, port)
    server_dir = str(server_dir or SERVER_DIR)
    eval_image = eval_image or 'kairos-test:latest'
    result = {'model': MODEL, 'port': port, 'container': container}
    failed = True  # cleared only when the calibration reached its result
    try:
        for args in (['network', 'create', network], ['volume', 'create', volume]):
            done = docker(args)
            if done.returncode:
                raise SystemExit('measure_abstention: `docker %s` failed: %s' % (' '.join(args[:2]), done.stderr.strip()))
        started = docker(['run', '-d', '--name', container, '--network', network, '--memory', MEMORY_LIMIT, '-v', volume + ':/root/.ollama', '-e', 'OLLAMA_HOST=0.0.0.0:%d' % port,
                          '-p', '127.0.0.1:%d:%d' % (port, port), image])
        if started.returncode:
            raise SystemExit('measure_abstention: the disposable Ollama did not start: ' + started.stderr.strip())
        for _ in range(60):
            if docker(['exec', container, 'ollama', 'list']).returncode == 0:
                break
            subprocess.run([sys.executable, '-c', 'import time; time.sleep(2)'])
        try:
            pulled = docker(['exec', container, 'ollama', 'pull', MODEL], timeout=pull_timeout)
        except subprocess.TimeoutExpired:
            result.update(status='uncalibrated', reason='the pull of %s took more than %d seconds' % (MODEL, pull_timeout))
            return result
        if pulled.returncode:
            result.update(status='uncalibrated', reason='the pull of %s failed: %s' % (MODEL, (pulled.stderr or pulled.stdout).strip()[-300:]))
            return result
        ran = docker(['run', '--rm', '--name', evaluation, '--network', network, '--memory', MEMORY_LIMIT, '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'MEMORY_RETRIEVAL_EVAL=1',
                      '-e', 'MEMORY_RETRIEVAL_EVAL_PROVIDER=ollama', '-e', 'MEMORY_RETRIEVAL_EVAL_OLLAMA_URL=http://%s:%d' % (container, port),
                      '-v', server_dir + ':/app/server:ro', eval_image, 'python', '-m', 'memory_platform.tests.run_postgres'], timeout=eval_timeout)
        report = parse_report((ran.stdout or '') + chr(10) + (ran.stderr or ''))  # the gate may be red (no threshold yet): the report is what matters
        rows = report['abstention']['scores']
        minimum, maximum = goals_from_thresholds()
        errors = report['abstention'].get('measurement_errors') or 0
        picked = None if errors else pick_threshold(rows, minimum, maximum)
        result.update(fused=report['layers']['fused']['overall'], goals={'min_correct_rate': minimum, 'max_false_rate': maximum}, curve=curve(rows), measurement_errors=errors)
        if errors:
            # Not "no threshold reaches the goals": the cosines of some questions were never measured, so no curve or window can be trusted (review phase 14, B3)
            result.update(status='uncalibrated', reason='abstention_measurement_errors: the best cosine of %d questions could not be measured; the calibration is not trustworthy' % errors)
        elif picked is None:
            result.update(status='uncalibrated', reason='no threshold reaches the goals (correct abstention >= %s and false abstention <= %s) with this model on this set' % (minimum, maximum))
        else:
            result.update(status='calibrated', threshold=picked['threshold'], window=[picked['low'], picked['high']],
                          correct_abstention=picked['correct_abstention'], false_abstention=picked['false_abstention'])
        failed = False
        return result
    finally:
        docker(['rm', '-f', evaluation])
        docker(['rm', '-f', container])
        docker(['volume', 'rm', '-f', volume])
        docker(['network', 'rm', network])
        leftovers, unverifiable = [], []
        for args in (['ps', '-a', '--filter', 'name=' + PREFIX, '--format', '{{.Names}}'], ['volume', 'ls', '--filter', 'name=' + PREFIX, '-q'],
                     ['network', 'ls', '--filter', 'name=' + PREFIX, '--format', '{{.Name}}']):
            listing = docker(args)
            if listing.returncode:  # a listing that failed says nothing: it is not "no leftovers"
                unverifiable.append(' '.join(args[:2]))
                continue
            leftovers += [line for line in (listing.stdout or '').split() if line]
        result['leftovers'], result['leftovers_unverifiable'] = leftovers, unverifiable
        if failed and (leftovers or unverifiable):  # the error path reports it too (the original error keeps propagating, with its non-zero exit)
            print(leave_message(leftovers, unverifiable), file=sys.stderr, flush=True)


def leave_message(leftovers, unverifiable):
    parts = []
    if leftovers:
        parts.append('measure_abstention left resources behind: ' + ', '.join(leftovers))
    if unverifiable:
        parts.append('measure_abstention could not check for leftovers (docker %s failed): not verifiable' % ', '.join(unverifiable))
    return '; '.join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ollama-container', default=PREFIX + 'ollama')
    parser.add_argument('--port', type=int, default=21434)
    parser.add_argument('--eval-image', default='kairos-test:latest', help='image of the test target (the server/ directory is mounted over it)')
    parser.add_argument('--pull-timeout', type=int, default=1200)
    args = parser.parse_args(argv)
    result = measure(container=args.ollama_container, port=args.port, eval_image=args.eval_image, pull_timeout=args.pull_timeout)
    print('ABSTENTION_CALIBRATION_RESULT ' + json.dumps(result, sort_keys=True, ensure_ascii=False), flush=True)
    if result.get('leftovers') or result.get('leftovers_unverifiable'):
        raise SystemExit(leave_message(result.get('leftovers', []), result.get('leftovers_unverifiable', [])))


if __name__ == '__main__':
    main(sys.argv[1:])
