from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.revision_agent import RevisionAgent
from app.domain.models import TravelEntities
from app.graph.state import TravelState, TravelStatePatch


def make_revision_node(agent: RevisionAgent) -> Runnable[TravelState, TravelStatePatch]:
    def inputs(state: TravelState) -> tuple:
        revision_number = state.get("revision_count", 0) + 1
        return (
            state["plan_draft"],
            state.get("entities") or TravelEntities(),
            state["hard_validation"],
            state["review_result"],
            state.get("phase1_research"),
            revision_number,
        )

    def revise(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("plan_draft", "hard_validation", "review_result")
        ):
            return {"planning_errors": ["REVISION_INPUT_MISSING"]}
        args = inputs(state)
        return {
            "plan_draft": agent.revise(*args),
            "revision_count": args[-1],
        }

    async def arevise(state: TravelState) -> TravelStatePatch:
        if not all(
            state.get(field)
            for field in ("plan_draft", "hard_validation", "review_result")
        ):
            return {"planning_errors": ["REVISION_INPUT_MISSING"]}
        args = inputs(state)
        return {
            "plan_draft": await agent.arevise(*args),
            "revision_count": args[-1],
        }

    return RunnableLambda(revise, afunc=arevise, name="revise_plan")
