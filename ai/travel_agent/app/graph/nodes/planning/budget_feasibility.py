from decimal import Decimal, ROUND_CEILING
from math import ceil

from app.domain.models import (
    BudgetEstimate,
    BudgetFeasibility,
    BudgetMode,
    BudgetScope,
    BudgetTierEstimate,
    NextAction,
    TravelEntities,
)
from app.graph.state import TravelState, TravelStatePatch


DAILY_BASIC_COST_PER_PERSON = Decimal("230")
SURVIVAL_FOOD_PER_DAY = Decimal("35")
SURVIVAL_LOCAL_TRANSPORT_PER_DAY = Decimal("15")
COMFORTABLE_FOOD_PER_DAY = Decimal("140")
COMFORTABLE_LOCAL_TRANSPORT_PER_DAY = Decimal("45")
COMFORTABLE_TICKETS_PER_DAY = Decimal("70")


def check_budget_feasibility(state: TravelState) -> TravelStatePatch:
    research = state.get("phase1_research")
    entities = state.get("entities") or TravelEntities()
    if research is None:
        return {"planning_errors": ["BUDGET_FEASIBILITY_INPUT_MISSING"]}

    if entities.budget is None and entities.budget_mode in {
        BudgetMode.ESTIMATE,
        BudgetMode.MINIMIZE,
    }:
        return {
            "budget_estimate": _estimate_budget_tiers(entities, research),
            "budget_feasibility": None,
            "missing_fields": ["budget_confirmation"],
            "planning_errors": [],
            "plan_saved": False,
            "validation_exhausted": False,
            "next_action": NextAction.ASK_USER,
        }

    if entities.budget is None:
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
    if entities.budget_mode is BudgetMode.MINIMIZE:
        survival = _estimate_budget_tiers(entities, research).survival
        estimated_minimum = survival.total
        transport_cost = survival.intercity_transport
        lodging_cost = survival.lodging
        daily_basic_cost = survival.food + survival.local_transport + survival.tickets
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


def _estimate_budget_tiers(entities: TravelEntities, research) -> BudgetEstimate:
    people = entities.people or 1
    days = entities.days or _date_duration(entities) or 1
    nights = max(days - 1, 0)
    positive_transport = sorted(
        option.price for option in research.transport_options if option.price > 0
    )
    intercity_floor = (positive_transport[0] if positive_transport else Decimal("0")) * people

    hotel_hints = sorted(
        area.nightly_price_hint for area in research.hotel_areas if area.nightly_price_hint > 0
    )
    cheapest_room = hotel_hints[0] if hotel_hints else Decimal("180")
    hostel_bed = max(Decimal("45"), min(Decimal("90"), cheapest_room * Decimal("0.35")))
    survival_lodging = hostel_bed * people * nights
    survival_food = SURVIVAL_FOOD_PER_DAY * people * days
    survival_local = SURVIVAL_LOCAL_TRANSPORT_PER_DAY * people * days
    survival_total = _round_up_to_fifty(
        intercity_floor + survival_lodging + survival_food + survival_local
    )

    rooms = max(1, ceil(people / 2)) if nights else 0
    comfortable_nightly = max(Decimal("180"), cheapest_room)
    comfortable_lodging = comfortable_nightly * rooms * nights
    comfortable_food = COMFORTABLE_FOOD_PER_DAY * people * days
    comfortable_local = COMFORTABLE_LOCAL_TRANSPORT_PER_DAY * people * days
    comfortable_tickets = COMFORTABLE_TICKETS_PER_DAY * people * days
    comfortable_transport = _comfortable_transport(positive_transport, people)
    comfortable_total = _round_up_to_hundred(
        comfortable_transport
        + comfortable_lodging
        + comfortable_food
        + comfortable_local
        + comfortable_tickets
    )

    return BudgetEstimate(
        survival=BudgetTierEstimate(
            name="极限穷游",
            total=survival_total,
            intercity_transport=intercity_floor,
            lodging=survival_lodging,
            food=survival_food,
            local_transport=survival_local,
            tickets=Decimal("0"),
            assumptions=[
                "青旅床位或同级最低价住宿",
                "绿皮火车或候选中最低价的可行城际交通",
                "市内以步行、公交、共享单车或助力车为主",
                "泡面、便利店和基础饱腹餐",
                "免费景点为主，只保留必要开销",
            ],
        ),
        comfortable=BudgetTierEstimate(
            name="正常舒适",
            total=comfortable_total,
            intercity_transport=comfortable_transport,
            lodging=comfortable_lodging,
            food=comfortable_food,
            local_transport=comfortable_local,
            tickets=comfortable_tickets,
            assumptions=[
                "经济型或舒适型住宿",
                "选择时间和价格较均衡的城际交通",
                "正常体验当地餐饮，不以泡面为主",
                "公交地铁结合必要网约车",
                "可安排主要付费景点",
            ],
        ),
        currency=entities.currency,
    )


def _comfortable_transport(prices: list[Decimal], people: int) -> Decimal:
    if not prices:
        return Decimal("0")
    option = prices[1] if len(prices) > 1 else prices[0] * Decimal("1.15")
    return option * people


def _round_up_to_fifty(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return (value / Decimal("50")).to_integral_value(rounding=ROUND_CEILING) * Decimal("50")
