from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.candidate_selector import CandidateSelectorAgent
from app.agents.clarification_agent import ClarificationAgent
from app.agents.plan_presenter import PlanPresenterAgent
from app.agents.planner_agent import PlannerAgent
from app.agents.research_agent import Phase1ResearchAgent, Phase2ResearchAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.revision_agent import RevisionAgent
from app.database.contracts import PlanRepository
from app.domain.models import ReviewVerdict
from app.graph.nodes.planning import (
    candidate_validation,
    check_budget_feasibility,
    code_repair,
    make_candidate_selection_node,
    make_hard_validation_node,
    make_phase1_research_node,
    make_phase2_research_node,
    make_planner_node,
    make_review_node,
    make_revision_node,
    make_save_validated_plan_node,
    planning_failure,
    validation_failure,
)
from app.graph.nodes.ask_user import make_ask_user_node
from app.graph.state import TravelState
from app.tools.executor import ToolExecutor
from app.validators.hard_validator import HardValidator


def route_after_phase1(state: TravelState) -> str:
    return "budget" if state.get("phase1_research") else "fail"


def route_after_budget(state: TravelState) -> str:
    if state.get("budget_estimate") is not None and state.get("entities").budget is None:
        return "ask_user"
    feasibility = state.get("budget_feasibility")
    if feasibility is None:
        return "fail"
    return "select" if feasibility.feasible else "ask_user"


def route_after_candidates(state: TravelState) -> str:
    return "research" if not state.get("candidate_validation_errors") else "fail"


def route_after_phase2(state: TravelState) -> str:
    return "plan" if state.get("phase2_research") else "fail"


def route_after_planner(state: TravelState) -> str:
    return "validate" if state.get("plan_draft") else "fail"


def route_after_review(state: TravelState) -> str:
    hard = state.get("hard_validation")
    review = state.get("review_result")
    if state.get("planning_errors") or hard is None or review is None:
        return "fail"
    if hard.hard_pass and review.verdict is ReviewVerdict.PASS:
        return "save"
    repairable_hard_codes = {"BUDGET_EXCEEDED", "HOTEL_NIGHTS_MISMATCH"}
    hard_codes = {issue.code for issue in hard.errors}
    repairable_review = any(issue.startswith("EMPTY_DAY") for issue in review.issues)
    if (
        not state.get("code_repair_attempted", False)
        and (hard_codes.intersection(repairable_hard_codes) or repairable_review)
    ):
        return "code_repair"
    if state.get("revision_count", 0) < 2:
        return "revise"
    return "fail"


def build_planning_subgraph(
    *,
    phase1_research_agent: Phase1ResearchAgent,
    phase2_research_agent: Phase2ResearchAgent,
    candidate_selector: CandidateSelectorAgent,
    clarification_agent: ClarificationAgent,
    planner_agent: PlannerAgent,
    plan_presenter: PlanPresenterAgent,
    reviewer_agent: ReviewerAgent,
    revision_agent: RevisionAgent,
    hard_validator: HardValidator,
    tool_executor: ToolExecutor,
    plan_repository: PlanRepository | None = None,
) -> CompiledStateGraph:
    """Build the two-stage planning workflow inspired by the Dify prototype."""
    graph = StateGraph(TravelState)
    graph.add_node(
        "phase1_research",
        make_phase1_research_node(phase1_research_agent, tool_executor),
    )
    graph.add_node("budget_feasibility", check_budget_feasibility)
    graph.add_node("budget_clarification", make_ask_user_node(clarification_agent))
    graph.add_node("candidate_selection", make_candidate_selection_node(candidate_selector))
    graph.add_node("candidate_validation", candidate_validation)
    graph.add_node(
        "phase2_research",
        make_phase2_research_node(phase2_research_agent, tool_executor),
    )
    graph.add_node("planner", make_planner_node(planner_agent))
    graph.add_node("hard_validation", make_hard_validation_node(hard_validator))
    graph.add_node("review_plan", make_review_node(reviewer_agent))
    graph.add_node("code_repair", code_repair)
    graph.add_node("revise_plan", make_revision_node(revision_agent))
    graph.add_node(
        "save_validated_plan",
        make_save_validated_plan_node(plan_repository, plan_presenter),
    )
    graph.add_node("planning_failure", planning_failure)
    graph.add_node("validation_failure", validation_failure)

    graph.add_edge(START, "phase1_research")
    graph.add_conditional_edges(
        "phase1_research",
        route_after_phase1,
        {"budget": "budget_feasibility", "fail": "planning_failure"},
    )
    graph.add_conditional_edges(
        "budget_feasibility",
        route_after_budget,
        {
            "select": "candidate_selection",
            "ask_user": "budget_clarification",
            "fail": "planning_failure",
        },
    )
    graph.add_edge("budget_clarification", END)
    graph.add_edge("candidate_selection", "candidate_validation")
    graph.add_conditional_edges(
        "candidate_validation",
        route_after_candidates,
        {"research": "phase2_research", "fail": "planning_failure"},
    )
    graph.add_conditional_edges(
        "phase2_research",
        route_after_phase2,
        {"plan": "planner", "fail": "planning_failure"},
    )
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"validate": "hard_validation", "fail": "planning_failure"},
    )
    graph.add_edge("hard_validation", "review_plan")
    graph.add_conditional_edges(
        "review_plan",
        route_after_review,
        {
            "save": "save_validated_plan",
            "code_repair": "code_repair",
            "revise": "revise_plan",
            "fail": "validation_failure",
        },
    )
    graph.add_edge("code_repair", "hard_validation")
    graph.add_edge("revise_plan", "hard_validation")
    graph.add_edge("save_validated_plan", END)
    graph.add_edge("planning_failure", END)
    graph.add_edge("validation_failure", END)
    return graph.compile()
