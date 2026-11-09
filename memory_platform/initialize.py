"""Initialize the backup volume mount point without traversing its contents."""
from pathlib import Path
import os


def main():
    path = Path('/backups')
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or path.resolve() != path:
        raise RuntimeError('The backup volume path is linked or resolves outside its mount point')
    path.mkdir(exist_ok=True)
    os.chown(path, 10001, 10001)
    path.chmod(0o700)


if __name__ == '__main__':
    main()
