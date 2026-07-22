from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    BudgetScope,
    HardValidationResult,
    Phase1Research,
    ReviewResult,
    TravelEntities,
    TravelPlan,
)


class RevisionAgent(Protocol):
    def revise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        """Return a revised copy without changing the proposed plan version."""

    async def arevise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        """Asynchronous revision."""


class LangChainRevisionAgent:
    """Revise a full itinerary with a Pro-class model under code validation."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            TravelPlan,
            method="json_mode",
        )

    def revise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        result = self._runner.invoke(
            self._messages(
                plan,
                entities,
                hard_validation,
                review_result,
                revision_number,
            )
        )
        revised = result if isinstance(result, TravelPlan) else TravelPlan.model_validate(result)
        return self._normalize(revised, plan, entities, phase1, revision_number)

    async def arevise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        result = await self._runner.ainvoke(
            self._messages(
                plan,
                entities,
                hard_validation,
                review_result,
                revision_number,
            )
        )
        revised = result if isinstance(result, TravelPlan) else TravelPlan.model_validate(result)
        return self._normalize(revised, plan, entities, phase1, revision_number)

    @staticmethod
    def _messages(
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        revision_number: int,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "你是一键游的行程修订 Agent。根据代码硬校验错误和体验评审意见，输出完整的修订后方案。"
                    "优先修复硬错误，再改善节奏与偏好匹配。不得新增原方案中不存在的 location_id、"
                    "ticket_option_id、hotel_area_id 或 transport_option_id；不得改变 plan_id、version、"
                    "destination、currency 和 created_at。不要只输出差异。"
                    "只输出 JSON，不要使用 Markdown。输出必须符合以下 JSON Schema："
                    f"{json.dumps(TravelPlan.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"修订轮次：{revision_number}\n"
                    f"本次需求：{entities.model_dump_json()}\n"
                    f"硬校验：{hard_validation.model_dump_json()}\n"
                    f"体验评审：{review_result.model_dump_json()}\n"
                    f"原方案：{plan.model_dump_json()}"
                )
            ),
        ]

    @staticmethod
    def _normalize(
        revised: TravelPlan,
        original: TravelPlan,
        entities: TravelEntities,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        original_by_location = {
            item.location_id: item
            for day in original.days
            for item in day.items
            if item.location_id
        }
        allowed_locations = set(original_by_location)
        allowed_tickets = {
            item.ticket_option_id
            for day in original.days
            for item in day.items
            if item.ticket_option_id
        }
        hotel_prices = {
            option.area_id: option.nightly_price_hint
            for option in (phase1.hotel_areas if phase1 else [])
        }
        transport_prices = {
            option.option_id: option.price
            for option in (phase1.transport_options if phase1 else [])
        }
        chosen_hotel = (
            revised.hotel_area_id
            if revised.hotel_area_id in hotel_prices
            else original.hotel_area_id
        )
        chosen_transport = (
            revised.transport_option_id
            if revised.transport_option_id in transport_prices
            else original.transport_option_id
        )
        normalized = revised.model_copy(deep=True)
        seen_locations: set[str] = set()
        for day_index, day in enumerate(normalized.days, start=1):
            source_day = original.days[day_index - 1] if day_index <= len(original.days) else None
            day.day_index = day_index
            day.date = source_day.date if source_day else None
            day.hotel_option_id = chosen_hotel
            grounded_items = []
            for item in day.items:
                if (
                    item.location_id not in allowed_locations
                    or item.location_id in seen_locations
                    or (
                        item.ticket_option_id is not None
                        and item.ticket_option_id not in allowed_tickets
                    )
                ):
                    continue
                source = original_by_location[item.location_id]
                item.name = source.name
                item.description = source.description
                item.ticket_option_id = source.ticket_option_id
                item.estimated_cost = source.estimated_cost
                item.visit_minutes = source.visit_minutes
                item.travel_minutes = source.travel_minutes
                grounded_items.append(item)
                seen_locations.add(item.location_id)
            day.items = grounded_items

        LangChainRevisionAgent._repair_schedule_with_opening_hours(normalized)
        people = entities.people or 1
        grounded_total = original.total_cost
        grounded_total -= sum(
            item.estimated_cost * people
            for location_id, item in original_by_location.items()
            if location_id not in seen_locations
        )
        if chosen_hotel != original.hotel_area_id:
            old_price = hotel_prices.get(original.hotel_area_id or "", 0)
            new_price = hotel_prices.get(chosen_hotel or "", old_price)
            grounded_total += (new_price - old_price) * original.hotel_nights
        if chosen_transport != original.transport_option_id:
            old_price = transport_prices.get(original.transport_option_id or "", 0)
            new_price = transport_prices.get(chosen_transport or "", old_price)
            grounded_total += (new_price - old_price) * people
        grounded_total = max(grounded_total, 0)
        assumptions = list(dict.fromkeys([
            *normalized.assumptions,
            f"已完成第 {revision_number} 轮自动修订。",
        ]))
        return normalized.model_copy(
            update={
                "plan_id": original.plan_id,
                "version": original.version,
                "destination": original.destination,
                "hotel_area_id": chosen_hotel,
                "transport_option_id": chosen_transport,
                "hotel_nights": original.hotel_nights,
                "total_cost": grounded_total,
                "currency": original.currency,
                "created_at": original.created_at,
                "assumptions": assumptions,
            }
        )

    @staticmethod
    def _repair_schedule_with_opening_hours(plan: TravelPlan) -> None:
        """Fit activities into opening windows and spill overflow to later days."""
        if not plan.days:
            return

        opening_pattern = re.compile(r"(\d{2}:\d{2})-(\d{2}:\d{2})")
        pending = [
            (day_index, item)
            for day_index, day in enumerate(plan.days)
            for item in day.items
        ]
        scheduled: list[list] = [[] for _ in plan.days]
        cursors = [
            datetime.combine(day.date or datetime.min.date(), time(hour=8))
            for day in plan.days
        ]

        for preferred_day, item in pending:
            placed = False
            for day_index in range(preferred_day, len(plan.days)):
                day = plan.days[day_index]
                base_date = day.date or datetime.min.date()
                match = opening_pattern.search(item.description or "")
                opening_start = time.fromisoformat(match.group(1)) if match else time(hour=8)
                opening_end = time.fromisoformat(match.group(2)) if match else time(hour=20)
                opens_at = datetime.combine(base_date, opening_start)
                closes_at = datetime.combine(base_date, opening_end)
                start = max(
                    cursors[day_index] + timedelta(minutes=item.travel_minutes),
                    opens_at,
                )
                available_minutes = int((closes_at - start).total_seconds() // 60)
                requested_minutes = max(item.visit_minutes, 30)
                if available_minutes < min(requested_minutes, 30):
                    continue

                item.visit_minutes = min(requested_minutes, available_minutes)
                end = start + timedelta(minutes=item.visit_minutes)
                item.start_time = start.time()
                item.end_time = end.time()
                item.start_at = start if day.date else None
                item.end_at = end if day.date else None
                scheduled[day_index].append(item)
                cursors[day_index] = end + timedelta(minutes=30)
                placed = True
                break

            if not placed:
                # Keep impossible items visible so hard validation can reject them.
                day_index = len(plan.days) - 1
                day = plan.days[day_index]
                start = cursors[day_index] + timedelta(minutes=item.travel_minutes)
                end = start + timedelta(minutes=max(item.visit_minutes, 30))
                item.start_time = start.time()
                item.end_time = end.time()
                item.start_at = start if day.date else None
                item.end_at = end if day.date else None
                scheduled[day_index].append(item)
                cursors[day_index] = end + timedelta(minutes=30)

        for day_index, day in enumerate(plan.days):
            day.items = scheduled[day_index]
            for item_index, item in enumerate(day.items, start=1):
                item.item_id = f"D{day.day_index}-I{item_index}"
            names = " + ".join(item.name for item in day.items) or "自由活动"
            day.title = f"第 {day.day_index} 天：{names}"

    @staticmethod
    def _reflow_with_opening_hours(plan: TravelPlan) -> None:
        opening_pattern = re.compile(r"(\d{2}:\d{2})-(\d{2}:\d{2})")
        for day in plan.days:
            base_date = day.date or datetime.min.date()
            cursor = datetime.combine(base_date, time(hour=9))
            for item_index, item in enumerate(day.items, start=1):
                opening_start = None
                opening_end = None
                match = opening_pattern.search(item.description or "")
                if match:
                    opening_start = time.fromisoformat(match.group(1))
                    opening_end = time.fromisoformat(match.group(2))
                start = cursor + timedelta(minutes=item.travel_minutes)
                if opening_start:
                    start = max(start, datetime.combine(base_date, opening_start))
                end = start + timedelta(minutes=item.visit_minutes)
                if opening_end:
                    closes_at = datetime.combine(base_date, opening_end)
                    if end > closes_at:
                        latest_start = closes_at - timedelta(minutes=item.visit_minutes)
                        start = max(datetime.combine(base_date, opening_start or time.min), latest_start)
                        end = start + timedelta(minutes=item.visit_minutes)
                item.item_id = f"D{day.day_index}-I{item_index}"
                item.start_time = start.time()
                item.end_time = end.time()
                item.start_at = start if day.date else None
                item.end_at = end if day.date else None
                cursor = end + timedelta(minutes=30)
            names = " + ".join(item.name for item in day.items) or "自由活动"
            day.title = f"第 {day.day_index} 天：{names}"


class RuleBasedRevisionAgent:
    """Repairs deterministic constraints before a future LLM reviser is added."""

    def revise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        revised = plan.model_copy(deep=True)
        error_codes = {issue.code for issue in hard_validation.errors}
        revised.hotel_nights = max(len(revised.days) - 1, 0)

        if any(issue.startswith("EMPTY_DAY") for issue in review_result.issues):
            self._redistribute_items(revised)
        if "BUDGET_EXCEEDED" in error_codes:
            if phase1 and phase1.hotel_areas:
                old_area_id = revised.hotel_area_id
                prices = {
                    option.area_id: option.nightly_price_hint
                    for option in phase1.hotel_areas
                }
                cheapest = min(
                    phase1.hotel_areas,
                    key=lambda option: option.nightly_price_hint,
                )
                revised.hotel_area_id = cheapest.area_id
                for day in revised.days:
                    day.hotel_option_id = cheapest.area_id
                old_price = prices.get(old_area_id or "", cheapest.nightly_price_hint)
                lodging_saving = max(
                    old_price - cheapest.nightly_price_hint,
                    0,
                ) * revised.hotel_nights
                revised.total_cost = max(revised.total_cost - lodging_saving, 0)
            self._reduce_ticket_cost(revised, entities)
        LangChainRevisionAgent._repair_schedule_with_opening_hours(revised)
        revised.assumptions = [
            *revised.assumptions,
            f"已执行第 {revision_number} 轮自动修订。",
        ]
        return revised

    async def arevise(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        hard_validation: HardValidationResult,
        review_result: ReviewResult,
        phase1: Phase1Research | None,
        revision_number: int,
    ) -> TravelPlan:
        return self.revise(
            plan,
            entities,
            hard_validation,
            review_result,
            phase1,
            revision_number,
        )

    @staticmethod
    def _redistribute_items(plan: TravelPlan) -> None:
        if not plan.days:
            return
        items = [item for day in plan.days for item in day.items]
        for day in plan.days:
            day.items = []
        for index, item in enumerate(items):
            plan.days[index % len(plan.days)].items.append(item)

    @staticmethod
    def _reduce_ticket_cost(plan: TravelPlan, entities: TravelEntities) -> None:
        if entities.budget is None:
            return
        budget_limit = entities.budget
        if entities.budget_scope is BudgetScope.PER_PERSON:
            budget_limit *= entities.people or 1
        people = entities.people or 1
        removable = sorted(
            (
                (item.estimated_cost, day, item)
                for day in plan.days
                for item in day.items
                if item.estimated_cost > 0
            ),
            key=lambda entry: entry[0],
            reverse=True,
        )
        for cost, day, item in removable:
            if plan.total_cost <= budget_limit:
                break
            day.items.remove(item)
            plan.total_cost = max(plan.total_cost - cost * people, 0)

    @staticmethod
    def _reflow_schedule(plan: TravelPlan) -> None:
        for day in plan.days:
            base_date = day.date or datetime.min.date()
            cursor = datetime.combine(base_date, time(hour=9))
            for index, item in enumerate(day.items, start=1):
                start = cursor + timedelta(minutes=item.travel_minutes)
                end = start + timedelta(minutes=item.visit_minutes)
                item.item_id = f"D{day.day_index}-I{index}"
                item.start_time = start.time()
                item.end_time = end.time()
                item.start_at = start if day.date else None
                item.end_at = end if day.date else None
                cursor = end + timedelta(minutes=30)
            names = " + ".join(item.name for item in day.items) or "自由活动"
            day.title = f"第 {day.day_index} 天：{names}"
