from decimal import Decimal, ROUND_CEILING

from app.domain.models import (
    BudgetFeasibility,
    BudgetScope,
    NextAction,
    TravelEntities,
)
from app.graph.state import TravelState, TravelStatePatch


DAILY_BASIC_COST_PER_PERSON = Decimal("230")


def check_budget_feasibility(state: TravelState) -> TravelStatePatch:
    research = state.get("phase1_research")
    entities = state.get("entities") or TravelEntities()
    if research is None or entities.budget is None:
        return {"planning_errors": ["BUDGET_FEASIBILITY_INPUT_MISSING"]}

    people = entities.people or 1
    days = entities.days or _date_duration(entities) or 1
    nights = max(days - 1, 0)
    lodging_cost = min(
        (area.nightly_price_hint for area in research.hotel_areas),
        default=Decimal("0"),
    ) * nights
    transport_cost = min(
        (option.price for option in research.transport_options),
        default=Decimal("0"),
    ) * people
    daily_basic_cost = DAILY_BASIC_COST_PER_PERSON * people * days
    estimated_minimum = lodging_cost + transport_cost + daily_basic_cost
    budget_limit = entities.budget
    if entities.budget_scope is BudgetScope.PER_PERSON:
        budget_limit *= people
    suggested_budget = _round_up_to_hundred(estimated_minimum)
    result = BudgetFeasibility(
        feasible=estimated_minimum <= budget_limit,
        budget_limit=budget_limit,
        estimated_minimum=estimated_minimum,
        transport_cost=transport_cost,
        lodging_cost=lodging_cost,
        daily_basic_cost=daily_basic_cost,
        suggested_budget=suggested_budget,
        currency=entities.currency,
    )
    if result.feasible:
        return {"budget_feasibility": result}

    return {
        "budget_feasibility": result,
        "missing_fields": ["budget"],
        "planning_errors": ["AI_BUDGET_INFEASIBLE"],
        "plan_saved": False,
        "validation_exhausted": False,
        "next_action": NextAction.ASK_USER,
    }


def _date_duration(entities: TravelEntities) -> int | None:
    if entities.start_date and entities.end_date:
        return (entities.end_date - entities.start_date).days + 1
    return None


def _round_up_to_hundred(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return (value / Decimal("100")).to_integral_value(rounding=ROUND_CEILING) * Decimal("100")
