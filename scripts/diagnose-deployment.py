"""Read-only deployment state and bounded startup logs, with credential redaction."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kairos_deploy', ROOT/'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def redactor():
    config = deploy.read_env(ROOT/'.env')
    config.update(deploy.read_env(ROOT/'.private/memory-platform.env'))
    values = []
    if config.get('MEMORY_SECRETS_DIR'):
        directory = deploy.safe_path(Path(config['MEMORY_SECRETS_DIR']))
        for name in ('postgres_password', 'dsn', 'bootstrap_password'):
            source = deploy.safe_path(directory/name)
            if source.is_file():
                value = source.read_text(encoding='utf-8').strip()
                if value:
                    values.append(value)
    def redact(value):
        return deploy.redact_output(value, values)
    return redact


def main():
    redact = redactor()
    compose = ['docker', 'compose', '-p', 'knowledge-graphs', '--project-directory', str(ROOT)]
    for source in (ROOT/'.env', ROOT/'.private/memory-platform.env'):
        if source.is_file():
            compose += ['--env-file', str(source)]
    compose += ['-f', str(ROOT/'docker-compose.yml'), '--profile', 'memory', '--profile', 'memory-admin']
    def run(command):
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=30)
            return {'exit_code': result.returncode, 'stdout': redact(result.stdout)[-20000:], 'stderr': redact(result.stderr)[-8000:]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'error': type(exc).__name__}
    services = ['memory-postgres', 'memory-api', 'memory-worker', 'memory-web', 'ollama']
    report = {'read_only': True, 'state': run(compose+['ps', '-a', '--format', 'json', *services]),
              'logs': run(compose+['logs', '--no-color', '--tail=40', *services[1:]])}
    states = {}
    template = '{"id":{{json .Id}},"image":{{json .Image}},"state":{{json .State}},"entrypoint":{{json .Config.Entrypoint}},"cmd":{{json .Config.Cmd}}}'
    for service in services:
        found = run(compose+['ps', '-a', '-q', service])
        ids = found.get('stdout', '').splitlines()
        states[service] = [run(['docker', 'inspect', '--format', template, ident]) for ident in ids if re.fullmatch(r'[a-f0-9]{12,64}', ident)]
    report['containers'] = states
    report['networks'] = []
    network_format = '{"name":{{json .Name}},"driver":{{json .Driver}},"internal":{{json .Internal}},"labels":{{json .Labels}},"containers":{{json .Containers}}}'
    for name in ('knowledge-graphs_memory-data', 'knowledge-graphs_webui', 'knowledge-graphs_inference', 'knowledge-graphs_egress'):
        report['networks'].append(run(['docker', 'network', 'inspect', '--format', network_format, name]))
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
