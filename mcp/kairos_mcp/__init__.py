"""kairos-mcp: the 34 Kairos MCP tools as a front of the `/v1` REST API, with the caller's own credential."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _version():
    for candidate in (HERE.parent / 'VERSION', HERE / 'VERSION'):
        try:
            return candidate.read_text(encoding='utf-8').strip()
        except OSError:
            continue
    return '0.0.0'


__version__ = _version()
