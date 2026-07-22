from app.domain.models import (
    Intent,
    IntentTask,
    QueryToolCall,
    ToolDataMode,
    ToolError,
    ToolResult,
    TravelEntities,
)
from app.graph.state import TravelState, TravelStatePatch
from app.tools.selector import ToolSelector


def make_query_tool_selector_node(selector: ToolSelector):
    def select_query_tools(state: TravelState) -> TravelStatePatch:
        tasks = state.get("intent_tasks") or [
            IntentTask(
                task_id="task-1",
                query="当前查询",
                intent=state.get("intent", Intent.UNKNOWN),
                entities=state.get("entities") or TravelEntities(),
            )
        ]
        calls: list[QueryToolCall] = []
        names: list[str] = []
        unavailable_results: dict[str, dict[str, ToolResult]] = {}
        unavailable_errors: list[ToolError] = []
        for task in tasks:
            eligible = selector.eligible_for_query(task.intent, task.entities)
            selected = selector.for_query(task.intent, task.entities)
            for tool in selected:
                calls.append(
                    QueryToolCall(
                        task_id=task.task_id,
                        tool_name=tool,
                    )
                )
                if tool.value not in names:
                    names.append(tool.value)
            for tool in (item for item in eligible if item not in selected):
                message = f"{tool.value} 接口尚未接入当前运行环境"
                unavailable_results.setdefault(task.task_id, {})[tool.value] = ToolResult(
                    success=False,
                    data={"message": message},
                    source="tool-registry",
                    data_mode=ToolDataMode.UNKNOWN,
                    error_code="TOOL_NOT_CONFIGURED",
                    retryable=False,
                )
                unavailable_errors.append(
                    ToolError(
                        tool_name=tool.value,
                        error_code="TOOL_NOT_CONFIGURED",
                        message=message,
                        retryable=False,
                    )
                )
        return {
            "pending_tools": names,
            "selected_tools": names,
            "query_tool_calls": calls,
            "query_task_results": unavailable_results,
            "tool_errors": unavailable_errors,
        }

    return select_query_tools
