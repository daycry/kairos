"""Executes a tool call as the contract says: arguments become `/v1` requests (translate), answers become MCP results (budget, envelope)."""
from .budget import OUTPUT
from .errors import ToolError


class Executor:
    def __init__(self, contract, client):
        self.contract, self.client = contract, client
        self.tools = {tool['name']: tool for tool in contract['tools']}

    async def execute(self, name, arguments, authorization):
        if name not in OUTPUT:
            raise ToolError('This tool is not available in this build of kairos-mcp')
        raise ToolError('not implemented')
