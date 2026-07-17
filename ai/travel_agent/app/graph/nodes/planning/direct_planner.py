from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.direct_planner_agent import DirectPlannerAgent
from app.domain.models import (
    BudgetFeasibility,
    BudgetScope,
    CandidateSelection,
    NextAction,
    TravelEntities,
    UserPreferences,
)
from app.graph.state import TravelState, TravelStatePatch


def make_direct_planner_node(agent: DirectPlannerAgent) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState) -> dict:
        return {
            "query": _latest_query(state),
            "conversation_id": state.get("conversation_id", "unknown"),
            "current_version": state.get("plan_version"),
            "entities": state.get("entities") or TravelEntities(),
            "preferences": state.get("effective_preferences") or UserPreferences(),
        }

    def patch(state: TravelState, proposal) -> TravelStatePatch:
        if proposal.feasible and proposal.plan is not None:
            poi_ids = [
                item.location_id
                for day in proposal.plan.days
                for item in day.items
                if item.location_id
            ]
            return {
                "plan_draft": proposal.plan,
                "candidate_selection": CandidateSelection(
                    selected_poi_ids=poi_ids,
                    reasons=["由大模型直接生成，未使用 Mock 研究工具。"],
                ),
                "planning_errors": [],
            }
        entities = state.get("entities") or TravelEntities()
        people = entities.people or 1
        budget_limit = entities.budget or 0
        if entities.budget_scope is BudgetScope.PER_PERSON:
            budget_limit *= people
        suggested = proposal.suggested_budget or budget_limit
        message = proposal.message or "当前预算可能无法覆盖这趟旅行，请调整预算或缩短行程。"
        return {
            "plan_draft": None,
            "plan_saved": False,
            "budget_feasibility": BudgetFeasibility(
                feasible=False,
                budget_limit=budget_limit,
                estimated_minimum=suggested,
                suggested_budget=suggested,
                currency=entities.currency,
            ),
            "missing_fields": ["budget"],
            "planning_errors": ["AI_BUDGET_INFEASIBLE"],
            "next_action": NextAction.ASK_USER,
            "messages": [AIMessage(content=message)],
        }

    def direct_plan(state: TravelState) -> TravelStatePatch:
        return patch(state, agent.propose(**arguments(state)))

    async def adirect_plan(state: TravelState) -> TravelStatePatch:
        return patch(state, await agent.apropose(**arguments(state)))

    return RunnableLambda(direct_plan, afunc=adirect_plan, name="direct_planner")


def _latest_query(state: TravelState) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )
