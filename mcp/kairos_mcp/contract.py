"""The contract of the 34 tools: `contract/kairos-mcp.json`, a copy of `docs/contracts/kairos-mcp.json` (a test on the server side keeps them equal).

The contract is the only source of what kairos-mcp serves: the names, descriptions, input schemas and annotations of `tools/list`, and
where each tool goes in `/v1` (`x-kairos-endpoint`, translated by `translate.py`). Nothing is copied from the server code (CA-08).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATH = HERE.parent / 'contract' / 'kairos-mcp.json'


def load(path=None):
    contract = json.loads(Path(path or PATH).read_text(encoding='utf-8'))
    tools = contract['tools']
    names = [tool['name'] for tool in tools]
    if len(set(names)) != len(names):
        raise ValueError('the contract lists a tool twice')
    for tool in tools:
        if 'x-kairos-endpoint' not in tool:
            raise ValueError('the contract has no x-kairos-endpoint for ' + tool['name'])
    return contract


def read_only(tool):
    """Whether the tool only reads: its annotation says so, which is what the untrusted-data envelope (S-05) is keyed on."""
    return bool((tool.get('annotations') or {}).get('readOnlyHint'))
