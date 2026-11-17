"""Envelopes shared by every agent: request in, response or error out."""

from uuid import UUID, uuid4

from pydantic import Field

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    TraceId,
    new_trace_id,
)
from autonomous_qa_agent.models.enums import AgentStatus


class AgentRequest[InputT: ContractModel](ContractModel):
    """Typed input for one agent invocation.

    ``request_id`` identifies this invocation; ``trace_id`` correlates it with the wider unit of
    work (a CLI call, an API request, a whole run) and is shared by everything done for it.
    """

    request_id: UUID = Field(default_factory=uuid4)
    trace_id: TraceId = Field(default_factory=new_trace_id)
    input: InputT


class AgentResponse[OutputT: ContractModel](ContractModel):
    """Typed output of one agent invocation plus how it was produced.

    ``request_id`` and ``trace_id`` echo the request. ``llm_enriched`` is true only when the LLM
    contributed to ``output``; otherwise the output is the agent's rule-based result.
    ``warnings`` are safe to show to users (no internals).
    """

    request_id: UUID
    trace_id: TraceId
    agent: NonEmptyStr = Field(max_length=100)
    status: AgentStatus
    output: OutputT
    llm_enriched: bool = False
    warnings: tuple[NonEmptyStr, ...] = ()


class ErrorResponse(ContractModel):
    """What callers see when a request fails. Safe to return: never carries internal detail."""

    code: Identifier  # stable, machine-readable: "invalid_request", "internal_error", ...
    message: NonEmptyStr
    details: tuple[NonEmptyStr, ...] = ()
    trace_id: TraceId | None = None  # quote this when reporting a problem; it finds the logs
