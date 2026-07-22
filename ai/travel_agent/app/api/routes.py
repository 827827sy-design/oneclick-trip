import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, StateSnapshot

from app.api.schemas import (
    AgentResumeRequest,
    AgentRunAccepted,
    AgentRunJobResponse,
    AgentRunRequest,
    AgentRunResponse,
    HealthResponse,
    InfrastructureHealthResponse,
)
from app.domain.models import Intent, NextAction
from app.graph.state import TravelState
from app.knowledge_pipeline import (
    KnowledgeBatch,
    KnowledgeBatchDecisionRequest,
    KnowledgeBatchList,
    KnowledgeCollectRequest,
    KnowledgePipelineService,
    KnowledgePublishRequest,
    KnowledgePreviewRequest,
    KnowledgeRebuildResult,
    KnowledgeStats,
    KnowledgeRecordDeleteRequest,
    KnowledgeRecordReviewRequest,
)


router = APIRouter()


JOB_STAGE_BY_NODE = {
    "load_conversation_state": (5, "加载会话", "正在恢复本次对话状态"),
    "load_user_memory": (10, "读取偏好", "正在读取长期旅行偏好"),
    "recognize_intent": (16, "识别意图", "正在理解目的地、时间、人数与预算"),
    "normalize_state": (20, "整理需求", "正在合并本轮需求与历史上下文"),
    "extract_long_term_memory": (24, "更新画像", "正在判断是否存在稳定旅行偏好"),
    "supervisor": (28, "任务分流", "总控 Agent 正在选择处理链路"),
    "phase1_research": (40, "候选研究", "正在并行查询天气、知识库和目的地候选"),
    "budget_feasibility": (48, "预算检查", "正在核算预算范围与旅行档次"),
    "candidate_selection": (55, "筛选候选", "正在选择景点、住宿区域与交通方案"),
    "candidate_validation": (60, "候选校验", "正在检查候选来源与有效性"),
    "phase2_research": (70, "路线精查", "正在并行核对路线、开放时间与门票信息"),
    "planner": (78, "生成行程", "规划 Agent 正在生成逐日安排"),
    "hard_validation": (84, "硬性校验", "正在检查预算、时间冲突与路线合理性"),
    "review_plan": (89, "体验评审", "正在检查节奏与偏好匹配"),
    "code_repair": (91, "规则修复", "正在用代码修复预算或空白日问题"),
    "revise_plan": (93, "自动修订", "修订 Agent 正在调整未通过的方案"),
    "save_validated_plan": (97, "保存方案", "正在保存通过校验的行程版本"),
    "ask_user": (95, "准备追问", "正在整理需要你选择的信息"),
    "query_subgraph": (70, "查询资料", "正在调用对应查询工具"),
    "modify_subgraph": (70, "修改方案", "正在分析影响并生成新版本"),
    "booking_subgraph": (70, "创建草稿", "正在准备预订草稿与确认步骤"),
}


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", phase="phase_8")


@router.get("/health/infrastructure", response_model=InfrastructureHealthResponse)
async def infrastructure_health(request: Request) -> InfrastructureHealthResponse:
    components = dict(getattr(request.app.state, "infrastructure_status", {}))
    healthy_values = {"ok", "deepseek", "java-owned"}
    overall = (
        "ok"
        if components and all(value in healthy_values for value in components.values())
        else "degraded"
    )
    return InfrastructureHealthResponse(status=overall, components=components)


@router.get("/v1/internal/knowledge/stats", response_model=KnowledgeStats)
def knowledge_stats(request: Request) -> KnowledgeStats:
    return _knowledge_pipeline(request).stats()


@router.post("/v1/internal/knowledge/rebuild", response_model=KnowledgeRebuildResult)
def rebuild_knowledge_index(request: Request) -> KnowledgeRebuildResult:
    return _knowledge_pipeline(request).rebuild_index()


@router.get("/v1/internal/knowledge/batches", response_model=KnowledgeBatchList)
def list_knowledge_batches(request: Request) -> KnowledgeBatchList:
    return KnowledgeBatchList(batches=_knowledge_pipeline(request).list())


@router.get("/v1/internal/knowledge/batches/{batch_id}", response_model=KnowledgeBatch)
def get_knowledge_batch(batch_id: str, request: Request) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).get(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次不存在") from exc


@router.post("/v1/internal/knowledge/batches/preview", response_model=KnowledgeBatch)
def preview_knowledge_batch(
    payload: KnowledgePreviewRequest,
    request: Request,
) -> KnowledgeBatch:
    return _knowledge_pipeline(request).preview(payload.records)


@router.post("/v1/internal/knowledge/collect", response_model=KnowledgeBatch)
def collect_knowledge_batch(
    payload: KnowledgeCollectRequest,
    request: Request,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).collect(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/v1/internal/knowledge/batches/{batch_id}/publish", response_model=KnowledgeBatch)
def publish_knowledge_batch(
    batch_id: str,
    request: Request,
    payload: KnowledgePublishRequest | None = None,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).publish(
            batch_id,
            reviewer=payload.reviewer if payload else "internal-admin",
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/v1/internal/knowledge/batches/{batch_id}/records/{record_id}/review",
    response_model=KnowledgeBatch,
)
def review_knowledge_record(
    batch_id: str,
    record_id: str,
    payload: KnowledgeRecordReviewRequest,
    request: Request,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).review_record(batch_id, record_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次或资料不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete(
    "/v1/internal/knowledge/batches/{batch_id}/records/{record_id}",
    response_model=KnowledgeBatch,
)
def delete_approved_knowledge_record(
    batch_id: str,
    record_id: str,
    payload: KnowledgeRecordDeleteRequest,
    request: Request,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).delete_approved_record(
            batch_id,
            record_id,
            payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次或资料不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/v1/internal/knowledge/batches/{batch_id}/reject",
    response_model=KnowledgeBatch,
)
def reject_knowledge_batch(
    batch_id: str,
    payload: KnowledgeBatchDecisionRequest,
    request: Request,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).reject_batch(batch_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/v1/internal/knowledge/batches/{batch_id}/reopen",
    response_model=KnowledgeBatch,
)
def reopen_knowledge_batch(
    batch_id: str,
    payload: KnowledgePublishRequest,
    request: Request,
) -> KnowledgeBatch:
    try:
        return _knowledge_pipeline(request).reopen_batch(batch_id, payload.reviewer)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识批次不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/v1/agent/runs", response_model=AgentRunResponse)
async def run_agent(payload: AgentRunRequest, request: Request) -> AgentRunResponse:
    graph = request.app.state.travel_graph
    graph_input: TravelState = {
        "conversation_id": payload.conversation_id,
        "user_id": payload.user_id,
        "ignore_user_preferences": payload.ignore_user_preferences,
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


@router.post(
    "/v1/agent/runs/async",
    response_model=AgentRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_agent_run(payload: AgentRunRequest, request: Request) -> AgentRunAccepted:
    graph = request.app.state.travel_graph
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

    jobs: dict[str, dict[str, Any]] = request.app.state.agent_jobs
    if any(
        job["conversation_id"] == payload.conversation_id
        and job["status"] in {"QUEUED", "RUNNING"}
        for job in jobs.values()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation already has an active Agent run",
        )

    run_id = str(uuid4())
    jobs[run_id] = {
        "run_id": run_id,
        "conversation_id": payload.conversation_id,
        "user_id": payload.user_id,
        "status": "QUEUED",
        "stage": "等待执行",
        "progress": 0,
        "detail": "任务已进入 Agent 执行队列",
        "model_mode": request.app.state.llm_mode,
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "node_timings": {},
        "result": None,
        "error": None,
    }
    task = asyncio.create_task(
        _execute_agent_job(request.app, run_id, payload),
        name=f"agent-run-{run_id}",
    )
    request.app.state.agent_job_tasks[run_id] = task
    task.add_done_callback(
        lambda _: request.app.state.agent_job_tasks.pop(run_id, None)
    )
    return AgentRunAccepted(
        run_id=run_id,
        conversation_id=payload.conversation_id,
        status="QUEUED",
    )


@router.get("/v1/agent/runs/jobs/{run_id}", response_model=AgentRunJobResponse)
async def get_agent_run_job(
    run_id: str,
    user_id: str,
    request: Request,
) -> AgentRunJobResponse:
    job = request.app.state.agent_jobs.get(run_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    if job["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent run user mismatch")
    return AgentRunJobResponse.model_validate(job)


async def _execute_agent_job(application, run_id: str, payload: AgentRunRequest) -> None:
    job = application.state.agent_jobs[run_id]
    graph = application.state.travel_graph
    config = {"configurable": {"thread_id": payload.conversation_id}}
    graph_input: TravelState = {
        "conversation_id": payload.conversation_id,
        "user_id": payload.user_id,
        "ignore_user_preferences": payload.ignore_user_preferences,
        "messages": [HumanMessage(content=payload.message)],
    }
    started_at = perf_counter()
    node_started_at: dict[str, tuple[str, float]] = {}
    job.update(
        status="RUNNING",
        stage="启动 Agent",
        progress=2,
        detail="正在加载会话和旅行画像",
        started_at=datetime.now(UTC).isoformat(),
    )
    try:
        async for event in graph.astream_events(
            graph_input,
            config=config,
            version="v2",
        ):
            event_type = str(event.get("event", ""))
            node_name = str(event.get("name", ""))
            milestone = JOB_STAGE_BY_NODE.get(node_name)
            if milestone is None:
                continue
            event_run_id = str(event.get("run_id", ""))
            if event_type == "on_chain_start":
                node_started_at[event_run_id] = (node_name, perf_counter())
                progress, stage_name, detail = milestone
                if progress >= job["progress"]:
                    job.update(progress=progress, stage=stage_name, detail=detail)
            elif event_type in {"on_chain_end", "on_chain_error"}:
                started = node_started_at.pop(event_run_id, None)
                if started is not None:
                    elapsed_ms = max(0, round((perf_counter() - started[1]) * 1000))
                    timings = job["node_timings"]
                    timings[node_name] = timings.get(node_name, 0) + elapsed_ms
        snapshot = await graph.aget_state(config)
        job.update(
            status="COMPLETED",
            stage="处理完成",
            progress=100,
            detail="Agent 已完成本次处理",
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            result=_build_response(snapshot),
        )
    except Exception as exc:
        job.update(
            status="FAILED",
            stage="执行失败",
            progress=max(job["progress"], 1),
            detail="Agent 执行过程中发生错误",
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            error=str(exc) or type(exc).__name__,
        )


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
        intent_tasks=result.get("intent_tasks", []),
        next_action=result.get("next_action", NextAction.ABORT),
        entities=result.get("entities"),
        checkpoint_version=result.get("checkpoint_version", 0),
        message_count=len(result.get("messages", [])),
        missing_fields=result.get("missing_fields", []),
        clarification_reply=result.get("clarification_reply"),
        budget_feasibility=result.get("budget_feasibility"),
        budget_estimate=result.get("budget_estimate"),
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
        query_task_results=result.get("query_task_results", {}),
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


def _knowledge_pipeline(request: Request) -> KnowledgePipelineService:
    service = getattr(request.app.state, "knowledge_pipeline", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识库管道未启用",
        )
    return service
