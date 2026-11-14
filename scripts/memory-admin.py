"""Prepare deployment secret files or run explicit local operator commands."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(argv):
    parser = argparse.ArgumentParser(description='Prepare private memory-platform secrets without starting Docker')
    parser.add_argument('--secret-dir', default='C:/docker-secrets/knowledge-memory' if os.name == 'nt' else str(Path.home() / '.local/share/knowledge-memory/secrets'), help='Private directory outside OneDrive and Git')
    parser.add_argument('--env-output', default=str(ROOT / '.private' / 'memory-platform.env'))
    args = parser.parse_args(argv)
    destination = Path(args.secret_dir).absolute()
    for candidate in [destination, *destination.parents]:
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            parser.error('Secret directory must not traverse a symlink or junction')
    destination.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        destination.chmod(0o700)

    def write_once(name, value):
        path = destination / name
        if path.is_symlink():
            parser.error('Secret file must not be a symlink')
        try:
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(value + '\n')
        except FileExistsError:
            if not path.is_file() or not path.read_text(encoding='utf-8').strip():
                parser.error('An existing secret file is invalid; it was not replaced')
        # Docker's application UID 10001 and postgres UID 999 must both read
        # their bind-mounted files; the parent directory remains owner-only.
        if os.name != 'nt':
            path.chmod(0o444)
        return path.read_text(encoding='utf-8').strip()

    password = write_once('postgres_password', secrets.token_urlsafe(36))
    from urllib.parse import quote
    write_once('dsn', f'postgresql://memory:{quote(password, safe="")}@memory-postgres:5432/agent_memory')
    write_once('bootstrap_password', secrets.token_urlsafe(24))
    output = Path(args.env_output).absolute()
    for candidate in [output, *output.parents]:
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            parser.error('Environment output must not traverse a symlink or junction')
    output.parent.mkdir(parents=True, exist_ok=True)
    if '\n' in str(destination) or '\r' in str(destination):
        parser.error('Invalid directory name')
    rendered = 'MEMORY_SECRETS_DIR=' + destination.as_posix() + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != rendered:
        parser.error('Existing environment configuration points elsewhere; it was not replaced')
    if not output.exists():
        output.write_text(rendered, encoding='utf-8')
    if os.name != 'nt':
        output.chmod(0o600)
    print(f'Private files prepared at {destination}. No existing secret was replaced.')
    print(f'Compose path configuration: {output}')
    print('Read bootstrap_password privately for the first portal login; do not paste it into chat.')
    if os.name == 'nt':
        print('Windows: use an owner-restricted NTFS directory outside OneDrive; chmod does not set NTFS ACLs. Docker Desktop must be allowed to read its bind mounts.')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'prepare':
        return prepare(sys.argv[2:])
    sys.path.insert(0, str(ROOT / 'server'))
    from memory_platform.admin import main as operator
    return operator(sys.argv[1:])


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'Administration failed ({type(exc).__name__}); no credentials are printed.') from None
