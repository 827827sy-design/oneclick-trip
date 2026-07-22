from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.agents.direct_modify_agent import DirectModifyAgent
from app.agents.modify_agent import ModifyAnalyzerAgent
from app.agents.plan_presenter import PlanPresenterAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.revision_agent import RevisionAgent
from app.database.contracts import PlanRepository
from app.domain.models import ReviewVerdict
from app.graph.nodes.modify import (
    make_direct_modify_node,
    make_modify_analysis_node,
    make_modify_discovery_selector_node,
    modification_failure,
)
from app.graph.nodes.planning import (
    make_hard_validation_node,
    make_review_node,
    make_revision_node,
    make_save_validated_plan_node,
    validation_failure,
)
from app.graph.state import TravelState
from app.graph.tool_runtime import make_tool_executor_node, send_payload
from app.tools.executor import ToolExecutor
from app.tools.selector import ToolSelector
from app.validators.hard_validator import HardValidator


def route_after_direct_modify(state: TravelState) -> str:
    return "fail" if state.get("modification_errors") or not state.get("plan_draft") else "validate"


def route_modify_research(state: TravelState):
    pending = state.get("pending_tools", [])
    if not pending:
        return "direct_modify"
    return [
        Send("execute_modify_research", send_payload(state, tool_name))
        for tool_name in pending
    ]


def route_after_review(state: TravelState) -> str:
    hard = state.get("hard_validation")
    review = state.get("review_result")
    if hard is None or review is None:
        return "fail"
    if hard.hard_pass and review.verdict is ReviewVerdict.PASS:
        return "save"
    if state.get("revision_count", 0) < 2:
        return "revise"
    return "fail"


def build_modify_subgraph(
    *,
    analyzer_agent: ModifyAnalyzerAgent,
    direct_modify_agent: DirectModifyAgent,
    plan_presenter: PlanPresenterAgent,
    reviewer_agent: ReviewerAgent,
    revision_agent: RevisionAgent,
    hard_validator: HardValidator,
    tool_selector: ToolSelector,
    tool_executor: ToolExecutor,
    plan_repository: PlanRepository | None = None,
) -> CompiledStateGraph:
    graph = StateGraph(TravelState)
    graph.add_node("analyze_modification", make_modify_analysis_node(analyzer_agent))
    graph.add_node(
        "select_modify_research",
        make_modify_discovery_selector_node(tool_selector),
    )
    graph.add_node(
        "execute_modify_research",
        make_tool_executor_node(tool_executor, name="execute_modify_research"),
    )
    graph.add_node("direct_modify", make_direct_modify_node(direct_modify_agent))
    graph.add_node("hard_validation", make_hard_validation_node(hard_validator))
    graph.add_node("review_plan", make_review_node(reviewer_agent))
    graph.add_node("revise_plan", make_revision_node(revision_agent))
    graph.add_node("save_modified_plan", make_save_validated_plan_node(plan_repository, plan_presenter))
    graph.add_node("modification_failure", modification_failure)
    graph.add_node("validation_failure", validation_failure)

    graph.add_edge(START, "analyze_modification")
    graph.add_edge("analyze_modification", "select_modify_research")
    graph.add_conditional_edges("select_modify_research", route_modify_research)
    graph.add_edge("execute_modify_research", "direct_modify")
    graph.add_conditional_edges(
        "direct_modify",
        route_after_direct_modify,
        {"validate": "hard_validation", "fail": "modification_failure"},
    )
    graph.add_edge("hard_validation", "review_plan")
    graph.add_conditional_edges(
        "review_plan",
        route_after_review,
        {"save": "save_modified_plan", "revise": "revise_plan", "fail": "validation_failure"},
    )
    graph.add_edge("revise_plan", "hard_validation")
    graph.add_edge("save_modified_plan", END)
    graph.add_edge("modification_failure", END)
    graph.add_edge("validation_failure", END)
    return graph.compile()
