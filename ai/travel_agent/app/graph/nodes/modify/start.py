from datetime import UTC, datetime

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch
from app.graph.tool_runtime import reset_tool_execution


def start_modify(state: TravelState) -> TravelStatePatch:
    current = state.get("current_plan")
    if current is None:
        return {
            **reset_tool_execution(),
            "plan_draft": None,
            "modification_errors": ["CURRENT_PLAN_MISSING"],
            "plan_saved": False,
            "next_action": NextAction.MODIFY_FLOW,
        }
    draft = current.model_copy(deep=True)
    draft.version = current.version + 1
    draft.created_at = datetime.now(UTC)
    return {
        **reset_tool_execution(),
        "plan_draft": draft,
        "modify_analysis": None,
        "modification_errors": [],
        "planning_errors": [],
        "phase2_research": None,
        "phase1_research": None,
        "candidate_selection": None,
        "hard_validation": None,
        "review_result": None,
        "revision_count": 0,
        "plan_saved": False,
        "validation_exhausted": False,
        "next_action": NextAction.MODIFY_FLOW,
    }
