from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.types import Overwrite, Send

from app.domain.models import Intent, IntentTask, QueryToolCall, ToolName, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor


def reset_tool_execution() -> TravelStatePatch:
    return {
        "selected_tools": Overwrite([]),
        "pending_tools": [],
        "active_tool": None,
        "tool_results": Overwrite({}),
        "query_task_results": Overwrite({}),
        "query_tool_calls": [],
        "active_query_task": None,
        "tool_errors": Overwrite([]),
        "tool_attempts": Overwrite({}),
        "tool_abort_requested": Overwrite(False),
    }


def make_tool_executor_node(
    executor: ToolExecutor,
    *,
    name: str,
) -> Runnable[TravelState, TravelStatePatch]:
    def execute_tool(state: TravelState) -> TravelStatePatch:
        raw_name = state.get("active_tool")
        if not raw_name:
            return {"tool_abort_requested": True}
        try:
            tool_name = ToolName(raw_name)
        except ValueError:
            return {"tool_abort_requested": True}
        outcome = executor.execute(tool_name, context_from_state(state))
        return {
            "tool_results": {tool_name.value: outcome.result},
            "tool_errors": outcome.errors,
            "tool_attempts": {tool_name.value: outcome.attempts},
            "tool_abort_requested": outcome.abort_requested,
        }

    async def aexecute_tool(state: TravelState) -> TravelStatePatch:
        raw_name = state.get("active_tool")
        if not raw_name:
            return {"tool_abort_requested": True}
        try:
            tool_name = ToolName(raw_name)
        except ValueError:
            return {"tool_abort_requested": True}
        outcome = await executor.aexecute(tool_name, context_from_state(state))
        return {
            "tool_results": {tool_name.value: outcome.result},
            "tool_errors": outcome.errors,
            "tool_attempts": {tool_name.value: outcome.attempts},
            "tool_abort_requested": outcome.abort_requested,
        }

    return RunnableLambda(execute_tool, afunc=aexecute_tool, name=name)


def make_query_tool_executor_node(
    executor: ToolExecutor,
) -> Runnable[TravelState, TravelStatePatch]:
    def execute_query_tool(state: TravelState) -> TravelStatePatch:
        return _query_tool_patch(executor.execute, state)

    async def aexecute_query_tool(state: TravelState) -> TravelStatePatch:
        return await _aquery_tool_patch(executor, state)

    return RunnableLambda(
        execute_query_tool,
        afunc=aexecute_query_tool,
        name="execute_query_tool",
    )


def make_tool_dispatcher(target_node: str) -> Callable[[TravelState], list[Send]]:
    def dispatch(state: TravelState) -> list[Send]:
        return [
            Send(target_node, send_payload(state, tool_name))
            for tool_name in state.get("pending_tools", [])
        ]

    return dispatch


def context_from_state(state: TravelState) -> ToolContext:
    return ToolContext(
        query=_latest_query(state),
        entities=state.get("entities") or TravelEntities(),
        preferences=state.get("effective_preferences") or UserPreferences(),
        phase1_research=state.get("phase1_research"),
        candidate_selection=state.get("candidate_selection"),
    )


def send_payload(state: TravelState, tool_name: str) -> TravelState:
    return {
        "conversation_id": state.get("conversation_id", ""),
        "user_id": state.get("user_id", ""),
        "messages": state.get("messages", []),
        "intent_tasks": state.get("intent_tasks", []),
        "entities": state.get("entities") or TravelEntities(),
        "effective_preferences": state.get("effective_preferences") or UserPreferences(),
        "phase1_research": state.get("phase1_research"),
        "candidate_selection": state.get("candidate_selection"),
        "active_tool": tool_name,
    }


def query_send_payload(state: TravelState, call: QueryToolCall) -> TravelState:
    task = next(
        (
            item
            for item in state.get("intent_tasks", [])
            if item.task_id == call.task_id
        ),
        None,
    )
    if task is None:
        task = IntentTask(
            task_id=call.task_id,
            query=_latest_query(state) or "当前查询",
            intent=state.get("intent", Intent.UNKNOWN),
            entities=state.get("entities") or TravelEntities(),
        )
    return {
        "conversation_id": state.get("conversation_id", ""),
        "user_id": state.get("user_id", ""),
        "messages": state.get("messages", []),
        "intent_tasks": state.get("intent_tasks", []),
        "entities": task.entities,
        "effective_preferences": state.get("effective_preferences") or UserPreferences(),
        "active_tool": call.tool_name.value,
        "active_query_task": task,
    }


def _query_tool_patch(execute, state: TravelState) -> TravelStatePatch:
    raw_name = state.get("active_tool")
    task = state.get("active_query_task")
    if not raw_name or task is None:
        return {"tool_abort_requested": True}
    try:
        tool_name = ToolName(raw_name)
    except ValueError:
        return {"tool_abort_requested": True}
    outcome = execute(
        tool_name,
        ToolContext(
            query=task.query,
            entities=task.entities,
            preferences=state.get("effective_preferences") or UserPreferences(),
        ),
    )
    return _query_outcome_patch(
        task,
        tool_name,
        outcome,
        allow_partial=len(state.get("intent_tasks", [])) > 1,
    )


async def _aquery_tool_patch(
    executor: ToolExecutor,
    state: TravelState,
) -> TravelStatePatch:
    raw_name = state.get("active_tool")
    task = state.get("active_query_task")
    if not raw_name or task is None:
        return {"tool_abort_requested": True}
    try:
        tool_name = ToolName(raw_name)
    except ValueError:
        return {"tool_abort_requested": True}
    outcome = await executor.aexecute(
        tool_name,
        ToolContext(
            query=task.query,
            entities=task.entities,
            preferences=state.get("effective_preferences") or UserPreferences(),
        ),
    )
    return _query_outcome_patch(
        task,
        tool_name,
        outcome,
        allow_partial=len(state.get("intent_tasks", [])) > 1,
    )


def _query_outcome_patch(
    task,
    tool_name,
    outcome,
    *,
    allow_partial: bool,
) -> TravelStatePatch:
    return {
        "tool_results": {tool_name.value: outcome.result},
        "query_task_results": {
            task.task_id: {tool_name.value: outcome.result},
        },
        "tool_errors": outcome.errors,
        "tool_attempts": {tool_name.value: outcome.attempts},
        "tool_abort_requested": outcome.abort_requested and not allow_partial,
    }


def _latest_query(state: TravelState) -> str | None:
    return next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        None,
    )
