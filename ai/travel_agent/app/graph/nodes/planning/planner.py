from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.planner_agent import PlannerAgent
from app.domain.models import TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def make_planner_node(agent: PlannerAgent) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState) -> dict:
        return {
            "conversation_id": state.get("conversation_id", "unknown"),
            "current_version": state.get("plan_version"),
            "entities": state.get("entities") or TravelEntities(),
            "preferences": state.get("effective_preferences") or UserPreferences(),
            "phase1": state["phase1_research"],
            "selection": state["candidate_selection"],
            "phase2": state["phase2_research"],
        }

    def planner(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("phase1_research", "candidate_selection", "phase2_research")
        ):
            return {"planning_errors": ["PLANNER_INPUT_MISSING"]}
        return {"plan_draft": agent.plan(**arguments(state))}

    async def aplanner(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("phase1_research", "candidate_selection", "phase2_research")
        ):
            return {"planning_errors": ["PLANNER_INPUT_MISSING"]}
        return {"plan_draft": await agent.aplan(**arguments(state))}

    return RunnableLambda(planner, afunc=aplanner, name="planner")
