from __future__ import annotations

from collections.abc import Callable

from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.types import Overwrite, Send

from app.domain.models import ToolName, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor


def reset_tool_execution() -> TravelStatePatch:
    return {
        "selected_tools": Overwrite([]),
        "pending_tools": [],
        "active_tool": None,
        "tool_results": Overwrite({}),
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
        return execute_tool(state)

    return RunnableLambda(execute_tool, afunc=aexecute_tool, name=name)


def make_tool_dispatcher(target_node: str) -> Callable[[TravelState], list[Send]]:
    def dispatch(state: TravelState) -> list[Send]:
        return [
            Send(target_node, send_payload(state, tool_name))
            for tool_name in state.get("pending_tools", [])
        ]

    return dispatch


def context_from_state(state: TravelState) -> ToolContext:
    return ToolContext(
        entities=state.get("entities") or TravelEntities(),
        preferences=state.get("effective_preferences") or UserPreferences(),
        phase1_research=state.get("phase1_research"),
        candidate_selection=state.get("candidate_selection"),
    )


def send_payload(state: TravelState, tool_name: str) -> TravelState:
    return {
        "conversation_id": state.get("conversation_id", ""),
        "user_id": state.get("user_id", ""),
        "entities": state.get("entities") or TravelEntities(),
        "effective_preferences": state.get("effective_preferences") or UserPreferences(),
        "phase1_research": state.get("phase1_research"),
        "candidate_selection": state.get("candidate_selection"),
        "active_tool": tool_name,
    }
