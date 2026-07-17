from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, StateSnapshot

from app.api.schemas import (
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResponse,
    HealthResponse,
    InfrastructureHealthResponse,
)
from app.domain.models import Intent, NextAction
from app.graph.state import TravelState


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", phase="phase_8")


@router.get("/health/infrastructure", response_model=InfrastructureHealthResponse)
async def infrastructure_health(request: Request) -> InfrastructureHealthResponse:
    components = dict(getattr(request.app.state, "infrastructure_status", {}))
    healthy_values = {"ok", "deepseek"}
    overall = (
        "ok"
        if components and all(value in healthy_values for value in components.values())
        else "degraded"
    )
    return InfrastructureHealthResponse(status=overall, components=components)


@router.post("/v1/agent/runs", response_model=AgentRunResponse)
async def run_agent(payload: AgentRunRequest, request: Request) -> AgentRunResponse:
    graph = request.app.state.travel_graph
    graph_input: TravelState = {
        "conversation_id": payload.conversation_id,
        "user_id": payload.user_id,
        "messages": [HumanMessage(content=payload.message)],
    }
    config = {"configurable": {"thread_id": payload.conversation_id}}
    existing_snapshot = await graph.aget_state(config)
    if existing_snapshot.values and existing_snapshot.values.get("user_id") != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation user binding does not match",
        )
    if existing_snapshot.interrupts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A human confirmation is pending; use the resume endpoint",
        )
    await graph.ainvoke(graph_input, config=config)
    snapshot = await graph.aget_state(config)
    return _build_response(snapshot)


@router.post("/v1/agent/runs/resume", response_model=AgentRunResponse)
async def resume_agent(payload: AgentResumeRequest, request: Request) -> AgentRunResponse:
    graph = request.app.state.travel_graph
    config = {"configurable": {"thread_id": payload.conversation_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot.interrupts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pending human confirmation exists for this conversation",
        )
    state: TravelState = snapshot.values
    if state.get("user_id") != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation user binding does not match",
        )
    await graph.ainvoke(
        Command(resume={"confirmed": payload.confirmed, "user_id": payload.user_id}),
        config=config,
    )
    resumed_snapshot = await graph.aget_state(config)
    return _build_response(resumed_snapshot)


def _build_response(snapshot: StateSnapshot) -> AgentRunResponse:
    result: TravelState = snapshot.values
    pending_interrupt = snapshot.interrupts[0] if snapshot.interrupts else None
    interrupt_payload: dict[str, Any] | None = None
    if pending_interrupt is not None and isinstance(pending_interrupt.value, dict):
        interrupt_payload = pending_interrupt.value
    reply = next(
        (
            str(message.content)
            for message in reversed(result.get("messages", []))
            if isinstance(message, AIMessage)
        ),
        None,
    )
    return AgentRunResponse(
        conversation_id=result["conversation_id"],
        intent=result.get("intent", Intent.UNKNOWN),
        next_action=result.get("next_action", NextAction.ABORT),
        entities=result.get("entities"),
        checkpoint_version=result.get("checkpoint_version", 0),
        message_count=len(result.get("messages", [])),
        missing_fields=result.get("missing_fields", []),
        clarification_reply=result.get("clarification_reply"),
        budget_feasibility=result.get("budget_feasibility"),
        phase1_research=result.get("phase1_research"),
        candidate_selection=result.get("candidate_selection"),
        candidate_validation_errors=result.get("candidate_validation_errors", []),
        phase2_research=result.get("phase2_research"),
        user_preferences=result.get("user_preferences"),
        memory_errors=result.get("memory_errors", []),
        plan_draft=result.get("plan_draft"),
        current_plan=result.get("current_plan"),
        plan_version=result.get("plan_version"),
        hard_validation=result.get("hard_validation"),
        review_result=result.get("review_result"),
        revision_count=result.get("revision_count", 0),
        plan_saved=result.get("plan_saved", False),
        validation_exhausted=result.get("validation_exhausted", False),
        modify_analysis=result.get("modify_analysis"),
        modification_errors=result.get("modification_errors", []),
        selected_tools=result.get("selected_tools", []),
        tool_results=result.get("tool_results", {}),
        tool_errors=result.get("tool_errors", []),
        tool_attempts=result.get("tool_attempts", {}),
        planning_errors=result.get("planning_errors", []),
        booking_draft=result.get("booking_draft"),
        booking_errors=result.get("booking_errors", []),
        booking_completed=result.get("booking_completed", False),
        interrupted=pending_interrupt is not None,
        interrupt_id=pending_interrupt.id if pending_interrupt else None,
        interrupt_payload=interrupt_payload,
        reply=reply,
    )
