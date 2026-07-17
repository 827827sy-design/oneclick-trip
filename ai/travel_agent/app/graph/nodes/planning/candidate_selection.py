from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.candidate_selector import CandidateSelectorAgent
from app.domain.models import TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def make_candidate_selection_node(
    agent: CandidateSelectorAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def candidate_selection(state: TravelState) -> TravelStatePatch:
        research = state.get("phase1_research")
        if research is None:
            return {"planning_errors": ["PHASE1_RESEARCH_MISSING"]}
        selection = agent.select(
            research,
            state.get("entities") or TravelEntities(),
            state.get("effective_preferences") or UserPreferences(),
        )
        return {"candidate_selection": selection}

    async def acandidate_selection(state: TravelState) -> TravelStatePatch:
        research = state.get("phase1_research")
        if research is None:
            return {"planning_errors": ["PHASE1_RESEARCH_MISSING"]}
        selection = await agent.aselect(
            research,
            state.get("entities") or TravelEntities(),
            state.get("effective_preferences") or UserPreferences(),
        )
        return {"candidate_selection": selection}

    return RunnableLambda(
        candidate_selection,
        afunc=acandidate_selection,
        name="candidate_selection",
    )
