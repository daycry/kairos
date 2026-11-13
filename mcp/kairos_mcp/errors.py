"""What a tool call says when `/v1` refuses or cannot answer: the same texts the internal MCP gives (`mcp.py` `safe`)."""

UNAVAILABLE = 'Memory service temporarily unavailable'
UNAUTHORIZED = {'code': 'unauthorized', 'message': 'Authentication required'}


class ToolError(ValueError):
    """A failed tool call: `str(error)` is the message the client sees."""


def unavailable():
    return ToolError(UNAVAILABLE)


def unauthorized_body():
    """The 401 body of the internal MCP (`AuthenticatedMCP`): a domain error plus an empty request id."""
    return {'error': dict(UNAUTHORIZED), 'request_id': ''}
