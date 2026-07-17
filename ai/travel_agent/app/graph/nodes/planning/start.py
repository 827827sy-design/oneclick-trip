from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch
from app.graph.tool_runtime import reset_tool_execution


def start_planning(_: TravelState) -> TravelStatePatch:
    return {
        **reset_tool_execution(),
        "plan_draft": None,
        "phase1_research": None,
        "budget_feasibility": None,
        "candidate_selection": None,
        "candidate_validation_errors": [],
        "phase2_research": None,
        "planning_errors": [],
        "hard_validation": None,
        "review_result": None,
        "plan_saved": False,
        "validation_exhausted": False,
        "revision_count": 0,
        "next_action": NextAction.PLANNING_FLOW,
    }
