"""How each tool answers: its output shape and the byte budget of its text; a tool absent from `OUTPUT` is not served yet.

The numbers and the marker are those of the internal MCP (`agent_tools.py`): a text over its budget is cut at the UTF-8 byte limit, marker included.
"""
import json

NORMAL_BYTES = 32_768
DETAIL_BYTES = 262_144
TRUNCATION = '\n[Output shortened at the UTF-8 byte budget; narrow the selection to retrieve more.]'

OBJECT, TEXT, PLAIN = 'object', 'text', 'plain'
# tool -> (shape, byte budget). `object`: the answer is a JSON object, sent as structured content and as indented JSON text, as FastMCP sends the
# dict a tool returns; `text`: the tool is declared `-> str` in the internal MCP, so the text is compact JSON and the structured content wraps it as
# `{"result": text}`; `plain`: fixed text, not JSON.
OUTPUT = {
    # T-41: the group of `mcp.py`. The internal MCP gives these dicts no byte budget; kairos-mcp caps them at the larger one.
    **{name: (OBJECT, DETAIL_BYTES) for name in ('projects', 'remember', 'publish_document', 'document_status', 'document_manifest', 'revoke_document',
                                                 'search', 'details', 'context', 'timeline', 'event_status', 'capture_policy')},
}


def render(value, budget=NORMAL_BYTES):
    """Compact JSON text with an explicit marker, the marker counted in the byte cap (`agent_tools.render`)."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return cut(encoded, budget)


def cut(encoded, budget):
    marker = TRUNCATION.encode('utf-8')
    if len(encoded) <= budget:
        return encoded.decode('utf-8')
    return encoded[:budget - len(marker)].decode('utf-8', errors='ignore') + TRUNCATION
