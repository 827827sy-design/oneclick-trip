from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.booking import BookingBackend, MockJavaBookingBackend
from app.database.contracts import PlanRepository, UserPreferenceRepository
from app.agents.clarification_agent import ClarificationAgent, RuleBasedClarificationAgent
from app.agents.candidate_selector import CandidateSelectorAgent, RuleBasedCandidateSelectorAgent
from app.agents.direct_modify_agent import DirectModifyAgent, RuleBasedDirectModifyAgent
from app.agents.intent_agent import IntentAgent, RuleBasedIntentAgent
from app.agents.memory_agent import MemoryCandidateAgent, RuleBasedMemoryCandidateAgent
from app.agents.modify_agent import (
    ModifyAgent,
    ModifyAnalyzerAgent,
    RuleBasedModifyAgent,
    RuleBasedModifyAnalyzerAgent,
)
from app.agents.planner_agent import PlannerAgent, RuleBasedPlannerAgent
from app.agents.plan_presenter import PlanPresenterAgent, RuleBasedPlanPresenterAgent
from app.agents.query_presenter import QueryPresenterAgent, RuleBasedQueryPresenterAgent
from app.agents.reviewer_agent import ReviewerAgent, RuleBasedReviewerAgent
from app.agents.revision_agent import RevisionAgent, RuleBasedRevisionAgent
from app.agents.research_agent import (
    Phase1ResearchAgent,
    Phase2ResearchAgent,
    RuleBasedPhase1ResearchAgent,
    RuleBasedPhase2ResearchAgent,
)
from app.graph.nodes import (
    abort,
    complete,
    load_conversation_state,
    load_user_memory,
    make_intent_recognition_node,
    make_ask_user_node,
    normalize_state,
)
from app.graph.nodes.load_conversation_state import make_load_conversation_state_node
from app.graph.nodes.load_user_memory import make_load_user_memory_node
from app.graph.nodes.memory_candidate import make_memory_candidate_node
from app.graph.nodes.user_memory import (
    make_persist_observed_preferences_node,
    manage_user_preferences,
)
from app.graph.nodes.booking.start import start_booking
from app.graph.nodes.modify.start import start_modify
from app.graph.nodes.planning.start import start_planning
from app.graph.nodes.query.start import start_query
from app.graph.router import SUPERVISOR_ROUTE_TARGETS, route_after_supervisor
from app.graph.state import TravelState
from app.graph.subgraphs.modify import build_modify_subgraph
from app.graph.subgraphs.booking import build_booking_subgraph
from app.graph.subgraphs.planning import build_planning_subgraph
from app.graph.subgraphs.query import build_query_subgraph
from app.graph.supervisor import supervisor
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import build_allowed_demo_registry
from app.tools.registry import ToolRegistry
from app.tools.selector import ToolSelector
from app.validators.hard_validator import HardValidator


def build_travel_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    intent_agent: IntentAgent | None = None,
    clarification_agent: ClarificationAgent | None = None,
    memory_candidate_agent: MemoryCandidateAgent | None = None,
    candidate_selector: CandidateSelectorAgent | None = None,
    phase1_research_agent: Phase1ResearchAgent | None = None,
    phase2_research_agent: Phase2ResearchAgent | None = None,
    direct_modify_agent: DirectModifyAgent | None = None,
    query_presenter: QueryPresenterAgent | None = None,
    planner_agent: PlannerAgent | None = None,
    plan_presenter: PlanPresenterAgent | None = None,
    reviewer_agent: ReviewerAgent | None = None,
    revision_agent: RevisionAgent | None = None,
    hard_validator: HardValidator | None = None,
    modify_analyzer_agent: ModifyAnalyzerAgent | None = None,
    modify_agent: ModifyAgent | None = None,
    tool_registry: ToolRegistry | None = None,
    tool_selector: ToolSelector | None = None,
    tool_executor: ToolExecutor | None = None,
    booking_backend: BookingBackend | None = None,
    plan_repository: PlanRepository | None = None,
    preference_repository: UserPreferenceRepository | None = None,
) -> CompiledStateGraph:
    """Build the root graph with Phase 4 query and planning tool subgraphs.

    The parent graph owns checkpointing. The compiled child graph inherits the
    parent's state and persistence context.
    """
    configured_intent_agent = intent_agent or RuleBasedIntentAgent()
    configured_clarification_agent = clarification_agent or RuleBasedClarificationAgent()
    configured_memory_candidate_agent = (
        memory_candidate_agent or RuleBasedMemoryCandidateAgent()
    )
    configured_registry = tool_registry or build_allowed_demo_registry()
    configured_selector = tool_selector or ToolSelector(configured_registry.names)
    configured_executor = tool_executor or ToolExecutor(configured_registry)
    configured_reviewer = reviewer_agent or RuleBasedReviewerAgent()
    configured_revision = revision_agent or RuleBasedRevisionAgent()
    configured_plan_presenter = plan_presenter or RuleBasedPlanPresenterAgent()
    configured_validator = hard_validator or HardValidator()
    configured_booking_backend = booking_backend or MockJavaBookingBackend()
    query_subgraph = build_query_subgraph(
        selector=configured_selector,
        executor=configured_executor,
        presenter=query_presenter or RuleBasedQueryPresenterAgent(),
    )
    planning_subgraph = build_planning_subgraph(
        phase1_research_agent=phase1_research_agent or RuleBasedPhase1ResearchAgent(),
        phase2_research_agent=phase2_research_agent or RuleBasedPhase2ResearchAgent(),
        candidate_selector=candidate_selector or RuleBasedCandidateSelectorAgent(),
        clarification_agent=configured_clarification_agent,
        planner_agent=planner_agent or RuleBasedPlannerAgent(),
        plan_presenter=configured_plan_presenter,
        reviewer_agent=configured_reviewer,
        revision_agent=configured_revision,
        hard_validator=configured_validator,
        tool_executor=configured_executor,
        plan_repository=plan_repository,
    )
    modify_subgraph = build_modify_subgraph(
        analyzer_agent=modify_analyzer_agent or RuleBasedModifyAnalyzerAgent(),
        direct_modify_agent=direct_modify_agent or RuleBasedDirectModifyAgent(),
        plan_presenter=configured_plan_presenter,
        reviewer_agent=configured_reviewer,
        revision_agent=configured_revision,
        hard_validator=configured_validator,
        tool_selector=configured_selector,
        tool_executor=configured_executor,
        plan_repository=plan_repository,
    )
    booking_subgraph = build_booking_subgraph(backend=configured_booking_backend)
    graph = StateGraph(TravelState)
    graph.add_node(
        "load_conversation_state",
        make_load_conversation_state_node(plan_repository)
        if plan_repository
        else load_conversation_state,
    )
    graph.add_node(
        "load_user_memory",
        make_load_user_memory_node(preference_repository)
        if preference_repository
        else load_user_memory,
    )
    graph.add_node("recognize_intent", make_intent_recognition_node(configured_intent_agent))
    graph.add_node("normalize_state", normalize_state)
    graph.add_node(
        "extract_memory_candidate",
        make_memory_candidate_node(
            configured_memory_candidate_agent,
            preference_repository,
        ),
    )
    graph.add_node("supervisor", supervisor)
    graph.add_node("ask_user", make_ask_user_node(configured_clarification_agent))
    graph.add_node("query_entry", start_query)
    graph.add_node("planning_entry", start_planning)
    graph.add_node("modify_entry", start_modify)
    graph.add_node(
        "memory_entry",
        make_persist_observed_preferences_node(
            preference_repository,
            include_message=True,
        )
        if preference_repository
        else manage_user_preferences,
    )
    graph.add_node("booking_entry", start_booking)
    graph.add_node("query_subgraph", query_subgraph)
    graph.add_node("planning_subgraph", planning_subgraph)
    graph.add_node("modify_subgraph", modify_subgraph)
    graph.add_node("booking_subgraph", booking_subgraph)
    graph.add_node("complete", complete)
    graph.add_node("abort", abort)

    graph.add_edge(START, "load_conversation_state")
    graph.add_edge("load_conversation_state", "load_user_memory")
    graph.add_edge("load_user_memory", "recognize_intent")
    graph.add_edge("recognize_intent", "normalize_state")
    graph.add_edge("normalize_state", "extract_memory_candidate")
    graph.add_edge("extract_memory_candidate", "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {target: target for target in SUPERVISOR_ROUTE_TARGETS.values()},
    )
    graph.add_edge("query_entry", "query_subgraph")
    graph.add_edge("planning_entry", "planning_subgraph")
    graph.add_edge("modify_entry", "modify_subgraph")
    graph.add_edge("booking_entry", "booking_subgraph")
    graph.add_edge("query_subgraph", END)
    graph.add_edge("planning_subgraph", END)
    graph.add_edge("modify_subgraph", END)
    graph.add_edge("booking_subgraph", END)
    terminal_targets = set(SUPERVISOR_ROUTE_TARGETS.values()) - {
        "query_entry",
        "planning_entry",
        "modify_entry",
        "booking_entry",
    }
    for target in terminal_targets:
        graph.add_edge(target, END)
    return graph.compile(checkpointer=checkpointer)
