from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.graph.nodes.query import (
    make_format_query_result_node,
    make_query_tool_selector_node,
)
from app.agents.query_presenter import QueryPresenterAgent
from app.graph.state import TravelState
from app.graph.tool_runtime import make_tool_executor_node, send_payload
from app.tools.executor import ToolExecutor
from app.tools.selector import ToolSelector


def route_query_execution(state: TravelState):
    pending = state.get("pending_tools", [])
    if not pending:
        return "format_query_result"
    return [
        Send("execute_query_tool", send_payload(state, tool_name))
        for tool_name in pending
    ]


def build_query_subgraph(
    *,
    selector: ToolSelector,
    executor: ToolExecutor,
    presenter: QueryPresenterAgent,
) -> CompiledStateGraph:
    graph = StateGraph(TravelState)
    graph.add_node("select_query_tools", make_query_tool_selector_node(selector))
    graph.add_node(
        "execute_query_tool",
        make_tool_executor_node(executor, name="execute_query_tool"),
    )
    graph.add_node("format_query_result", make_format_query_result_node(presenter))

    graph.add_edge(START, "select_query_tools")
    graph.add_conditional_edges(
        "select_query_tools",
        route_query_execution,
    )
    graph.add_edge("execute_query_tool", "format_query_result")
    graph.add_edge("format_query_result", END)
    return graph.compile()
