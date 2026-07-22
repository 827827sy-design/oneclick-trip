from app.agents.revision_agent import RuleBasedRevisionAgent
from app.domain.models import TravelEntities
from app.graph.state import TravelState, TravelStatePatch


def code_repair(state: TravelState) -> TravelStatePatch:
    """Apply cheap deterministic repairs once before invoking the LLM reviser."""
    plan = state.get("plan_draft")
    hard = state.get("hard_validation")
    review = state.get("review_result")
    if plan is None or hard is None or review is None:
        return {
            "planning_errors": ["CODE_REPAIR_INPUT_MISSING"],
            "code_repair_attempted": True,
        }
    repaired = RuleBasedRevisionAgent().revise(
        plan,
        state.get("entities") or TravelEntities(),
        hard,
        review,
        state.get("phase1_research"),
        0,
    )
    return {
        "plan_draft": repaired,
        "code_repair_attempted": True,
    }
