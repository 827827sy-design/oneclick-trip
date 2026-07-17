from app.agents.modify_agent import ModifyAgent
from app.graph.state import TravelState, TravelStatePatch


def make_enrich_modified_plan_node(agent: ModifyAgent):
    def enrich_modified_plan(state: TravelState) -> TravelStatePatch:
        plan = state.get("plan_draft")
        phase2 = state.get("phase2_research")
        if plan is None or phase2 is None:
            return {"modification_errors": ["MODIFY_ENRICH_INPUT_MISSING"]}
        people = state.get("entities").people if state.get("entities") else 1
        return {"plan_draft": agent.enrich(plan, phase2, people or 1)}

    return enrich_modified_plan
