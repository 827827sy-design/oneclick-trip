from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.reviewer_agent import ReviewerAgent
from app.domain.models import TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def make_review_node(agent: ReviewerAgent) -> Runnable[TravelState, TravelStatePatch]:
    def inputs(state: TravelState):
        return (
            state["plan_draft"],
            state.get("entities") or TravelEntities(),
            state.get("effective_preferences") or UserPreferences(),
            state.get("phase1_research"),
            state["hard_validation"],
        )

    def review(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("plan_draft", "hard_validation")
        ):
            return {"planning_errors": ["REVIEW_INPUT_MISSING"]}
        return {"review_result": agent.review(*inputs(state))}

    async def areview(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("plan_draft", "hard_validation")
        ):
            return {"planning_errors": ["REVIEW_INPUT_MISSING"]}
        return {"review_result": await agent.areview(*inputs(state))}

    return RunnableLambda(review, afunc=areview, name="review_plan")
