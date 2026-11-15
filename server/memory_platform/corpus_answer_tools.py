"""Generated answers are explicit, opt-in MCP operations, separate from retrieval."""
import asyncio
from typing import Annotated

from pydantic import Field

from .agent_tools import DETAIL_BYTES, Name, Project, render, untrusted
from .corpus_answers import CorpusAnswers


def register_corpus_answer_tools(server, actor, safe, store, settings):
    from mcp.types import ToolAnnotations
    service = CorpusAnswers(store, settings)

    @server.tool(name='corpus_answer', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    async def corpus_answer(project: Project, name: Name, question: Annotated[str, Field(min_length=1, max_length=4000)],
                            request_id: Name, expected_session_id: Name,
                            expected_generation: Annotated[int, Field(ge=1, le=2_147_483_646)]) -> str:
        """Generate an unverified, source-cited answer using the configured model.

        Prime first, then pass its exact session_id and version as generation.
        Explicitly reusing request_id reads the same operation, never resends it.
        Generation, authorization, source withdrawal and token admission budgets
        are checked. Unknown/pending delivery keeps its reservation; use status.
        query_corpus remains lexical and never invokes a model.
        """
        return render(await safe(service.answer(actor(), project, name, question, request_id,
                                                expected_session_id, expected_generation)), DETAIL_BYTES)

    @server.tool(name='corpus_answer_status', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    async def corpus_answer_status(project: Project, name: Name, request_id: Name) -> str:
        """Read an existing generated answer; recheck source and access freshness.

        An expired pending request becomes unknown without another provider call.
        Reprime/withdrawal invalidates access to answers from the old generation.
        """
        return render(untrusted(await safe(asyncio.to_thread(service.status, actor(), project, name, request_id))), DETAIL_BYTES)

    return service
