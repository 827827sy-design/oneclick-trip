from app.agents.modify_agent import ModifyAgent
from app.domain.models import POICandidate, ToolName, TravelEntities
from app.graph.state import TravelState, TravelStatePatch


def make_apply_modification_node(agent: ModifyAgent):
    def apply_modification(state: TravelState) -> TravelStatePatch:
        plan = state.get("plan_draft")
        analysis = state.get("modify_analysis")
        if plan is None or analysis is None:
            return {"modification_errors": ["MODIFICATION_INPUT_MISSING"]}

        candidates: list[POICandidate] = []
        poi_result = state.get("tool_results", {}).get(ToolName.POI_SEARCH.value)
        if poi_result and poi_result.success:
            candidates = [
                POICandidate.model_validate(item)
                for item in poi_result.data.get("candidates", [])
            ]
        elif state.get("phase1_research"):
            candidates = list(state["phase1_research"].poi_candidates)

        result = agent.apply(
            plan,
            analysis,
            state.get("entities") or TravelEntities(),
            candidates,
        )
        return {
            "plan_draft": result.plan,
            "entities": result.entities,
            "candidate_selection": result.selection,
            "modification_errors": result.errors,
        }

    return apply_modification
