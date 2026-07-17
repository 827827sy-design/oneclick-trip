from app.domain.models import TravelEntities
from app.graph.state import TravelState, TravelStatePatch
from app.validators.hard_validator import HardValidator


def make_hard_validation_node(validator: HardValidator):
    def hard_validation(state: TravelState) -> TravelStatePatch:
        result = validator.validate(
            state.get("plan_draft"),
            state.get("entities") or TravelEntities(),
            state.get("phase2_research"),
        )
        return {"hard_validation": result}

    return hard_validation
