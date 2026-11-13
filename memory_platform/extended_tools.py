"""Authenticated MCP adapters for observation writes and shared team work."""
import asyncio
from typing import Annotated

from pydantic import Field

from .agent_tools import DETAIL_BYTES, Name, Project, Version, render, untrusted
from .extended_store import ExtendedStore
from .models import Event


def register_extended_tools(server, actor, safe, store):
    from mcp.types import ToolAnnotations

    service = ExtendedStore(store)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

    async def call(method, *args, reading=False, **kwargs):
        result = await safe(asyncio.to_thread(getattr(service, method), actor(), *args, **kwargs))
        return render(untrusted(result) if reading else result, DETAIL_BYTES)

    @server.tool(name='observation_add', annotations=write)
    async def observation_add(event: Event) -> str:
        """Create a version-1 observation with stable event/item UUIDs and consent.

        Reuse the exact event after uncertain delivery. Poll event_status for
        extraction completion; acceptance does not imply model completion.
        """
        return await call('observation_add', event)

    @server.tool(name='observation_record_event', annotations=destructive)
    async def observation_record_event(event: Event) -> str:
        """Append an observation revision, correction, session event or withdrawal.

        Supply the next item version and stable event UUID. Corrections use
        payload.supersedes. Validated content needs validation permission/evidence.
        """
        return await call('observation_record_event', event)

    @server.tool(name='get_tool_uses', annotations=read)
    async def get_tool_uses(project: Project, session_id: Name | None = None, tool: Name | None = None,
                            limit: Annotated[int, Field(ge=1, le=100)] = 20, cursor: str | None = None) -> str:
        """Recover current technical tool summaries in an authorized project.

        Returns no raw arguments, output or withdrawn/historical items. Follow
        next_cursor with identical filters when has_more; scans are bounded.
        """
        return await call('get_tool_uses', project, session_id, tool, limit, cursor, reading=True)

    @server.tool(name='team_work_write', annotations=write)
    async def team_work_write(project: Project, list: Name, fields: dict, request_id: Name,
                              expected_version: Version | None = None) -> str:
        """Update a project-shared work list with attribution and exact retry identity.

        All project readers see team lists; private work_state lists stay private.
        Supply expected_version to prevent lost concurrent changes. Fields are
        scalar; task selects a task, null clears a field; status is todo/doing/done/dropped.
        """
        return await call('team_write', project, list, fields, request_id, expected_version)

    @server.tool(name='team_work_read', annotations=read)
    async def team_work_read(project: Project, list: Name | None = None, include_closed: bool = False) -> str:
        """Read shared project work, excluding completed/dropped tasks by default."""
        return await call('team_read', project, list, include_closed, reading=True)

    @server.tool(name='team_search', annotations=read)
    async def team_search(project: Project, query: str = '', limit: Annotated[int, Field(ge=1, le=100)] = 20) -> str:
        """Search current shared lists and open task fields as plain text."""
        return await call('team_search', project, query, limit, reading=True)

    @server.tool(name='team_brief', annotations=read)
    async def team_brief(project: Project, limit: Annotated[int, Field(ge=1, le=100)] = 20) -> str:
        """Read a bounded shared work brief with versions and author attribution."""
        return await call('team_brief', project, limit, reading=True)

    return service
