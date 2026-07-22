from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.domain.models import (
    BudgetScope,
    HardValidationResult,
    ItineraryItem,
    Phase2Research,
    TravelEntities,
    TravelPlan,
    ValidationIssue,
)


class HardValidator:
    """Deterministic checks for constraints that must not be delegated to an LLM."""

    def validate(
        self,
        plan: TravelPlan | None,
        entities: TravelEntities,
        phase2: Phase2Research | None,
    ) -> HardValidationResult:
        if plan is None:
            return HardValidationResult(
                hard_pass=False,
                errors=[ValidationIssue(code="PLAN_MISSING", message="缺少待校验方案")],
            )

        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        self._validate_duration(plan, entities, errors)
        self._validate_hotel_nights(plan, errors)
        self._validate_dates(plan, entities, errors)
        self._validate_budget(plan, entities, errors, warnings)
        self._validate_schedule(plan, phase2, errors, warnings)
        self._validate_routes(phase2, errors)
        self._validate_cost_sum(plan, errors, warnings)
        return HardValidationResult(
            hard_pass=not errors,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _validate_duration(
        plan: TravelPlan,
        entities: TravelEntities,
        errors: list[ValidationIssue],
    ) -> None:
        expected_days = entities.days
        if expected_days is None and entities.start_date and entities.end_date:
            expected_days = (entities.end_date - entities.start_date).days + 1
        if expected_days is not None and len(plan.days) != expected_days:
            errors.append(
                ValidationIssue(
                    code="DAY_COUNT_MISMATCH",
                    message=f"方案为 {len(plan.days)} 天，需求为 {expected_days} 天",
                )
            )
        actual_indices = [day.day_index for day in plan.days]
        expected_indices = list(range(1, len(plan.days) + 1))
        if actual_indices != expected_indices:
            errors.append(
                ValidationIssue(
                    code="DAY_INDEX_INVALID",
                    message="行程天序必须从 1 连续递增",
                )
            )

    @staticmethod
    def _validate_hotel_nights(
        plan: TravelPlan,
        errors: list[ValidationIssue],
    ) -> None:
        expected_nights = max(len(plan.days) - 1, 0)
        if plan.hotel_nights != expected_nights:
            errors.append(
                ValidationIssue(
                    code="HOTEL_NIGHTS_MISMATCH",
                    message=f"住宿 {plan.hotel_nights} 晚，应为 {expected_nights} 晚",
                )
            )

    @staticmethod
    def _validate_budget(
        plan: TravelPlan,
        entities: TravelEntities,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        if entities.budget is None:
            return
        budget_limit = entities.budget
        if entities.budget_scope is BudgetScope.PER_PERSON:
            budget_limit *= entities.people or 1
        if plan.total_cost > budget_limit:
            overage = plan.total_cost - budget_limit
            estimate_tolerance = budget_limit * Decimal("0.05")
            if budget_limit > 0 and overage <= estimate_tolerance:
                warnings.append(
                    ValidationIssue(
                        code="BUDGET_ESTIMATE_MARGIN",
                        message=(
                            f"预估 {plan.total_cost} {plan.currency}，比预算高 {overage}，"
                            "处于 AI 估算的 5% 浮动范围内"
                        ),
                    )
                )
                return
            errors.append(
                ValidationIssue(
                    code="BUDGET_EXCEEDED",
                    message=f"预估 {plan.total_cost} {plan.currency}，超过预算 {budget_limit}",
                )
            )

    def _validate_schedule(
        self,
        plan: TravelPlan,
        phase2: Phase2Research | None,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        details = {item.poi_id: item for item in (phase2.poi_details if phase2 else [])}
        seen_item_ids: set[str] = set()
        seen_locations: set[str] = set()
        for day in plan.days:
            previous_end: datetime | None = None
            for item in day.items:
                if item.item_id in seen_item_ids:
                    errors.append(
                        ValidationIssue(
                            code="DUPLICATE_ITEM_ID",
                            message=f"重复行程项 ID：{item.item_id}",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                seen_item_ids.add(item.item_id)
                if item.location_id and item.location_id in seen_locations:
                    errors.append(
                        ValidationIssue(
                            code="DUPLICATE_POI",
                            message=f"景点重复安排：{item.name}",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                if item.location_id:
                    seen_locations.add(item.location_id)
                start, end = self._item_bounds(item, day.date)
                if start is None or end is None:
                    errors.append(
                        ValidationIssue(
                            code="ITEM_TIME_MISSING",
                            message=f"{item.name} 缺少完整起止时间",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                    continue
                if start >= end:
                    errors.append(
                        ValidationIssue(
                            code="ITEM_TIME_INVALID",
                            message=f"{item.name} 的结束时间必须晚于开始时间",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                if previous_end and start < previous_end:
                    errors.append(
                        ValidationIssue(
                            code="TIME_CONFLICT",
                            message=f"{item.name} 与前一行程时间冲突",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                previous_end = max(previous_end, end) if previous_end else end
                if item.travel_minutes > 180:
                    errors.append(
                        ValidationIssue(
                            code="TRAVEL_TIME_EXCESSIVE",
                            message=f"前往 {item.name} 的交通时间超过 180 分钟",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )

                detail = details.get(item.location_id or "")
                if detail is None:
                    warnings.append(
                        ValidationIssue(
                            code="POI_DETAIL_MISSING",
                            message=f"{item.name} 缺少开放时间或门票详情",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                    continue
                opening = self._parse_opening_hours(detail.opening_hours)
                if opening is None:
                    warnings.append(
                        ValidationIssue(
                            code="OPENING_HOURS_UNCONFIRMED",
                            message=f"{item.name} 的开放时间需要人工确认",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                elif start.time() < opening[0] or end.time() > opening[1]:
                    errors.append(
                        ValidationIssue(
                            code="OUTSIDE_OPENING_HOURS",
                            message=f"{item.name} 安排在开放时间之外",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )
                if not detail.available:
                    warnings.append(
                        ValidationIssue(
                            code="TICKET_UNCONFIRMED",
                            message=f"{item.name} 的门票余量尚未确认",
                            day_index=day.day_index,
                            item_id=item.item_id,
                        )
                    )

    @staticmethod
    def _validate_routes(
        phase2: Phase2Research | None,
        errors: list[ValidationIssue],
    ) -> None:
        if phase2 is None:
            return
        for leg in phase2.route_legs:
            if leg.duration_minutes > 180 or leg.distance_km > 100:
                errors.append(
                    ValidationIssue(
                        code="ROUTE_UNREASONABLE",
                        message=f"{leg.from_id} 到 {leg.to_id} 的路线距离或耗时过大",
                    )
                )

    @staticmethod
    def _validate_dates(
        plan: TravelPlan,
        entities: TravelEntities,
        errors: list[ValidationIssue],
    ) -> None:
        if not entities.start_date:
            return
        start = entities.start_date
        end = entities.end_date
        if end is None and entities.days:
            from datetime import timedelta
            end = start + timedelta(days=entities.days - 1)
        if end is None:
            return
        for day in plan.days:
            if day.date is None:
                continue
            if day.date < start or day.date > end:
                errors.append(
                    ValidationIssue(
                        code="DATE_OUT_OF_RANGE",
                        message=f"第{day.day_index}天日期 {day.date} 不在旅行范围内 ({start} 至 {end})",
                        day_index=day.day_index,
                    )
                )

    @staticmethod
    def _validate_cost_sum(
        plan: TravelPlan,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        item_total = Decimal("0")
        for day in plan.days:
            for item in day.items:
                item_total += item.estimated_cost or Decimal("0")
        if item_total == Decimal("0"):
            return
        diff = abs(plan.total_cost - item_total)
        if plan.total_cost > Decimal("0") and diff > plan.total_cost * Decimal("0.15"):
            warnings.append(
                ValidationIssue(
                    code="COST_SUM_MISMATCH",
                    message=(
                        f"行程项费用合计 {item_total} 与总费用 {plan.total_cost} "
                        f"相差 {diff}（超过 15%），建议核实"
                    ),
                )
            )

    @staticmethod
    def _item_bounds(
        item: ItineraryItem,
        day_date: date | None,
    ) -> tuple[datetime | None, datetime | None]:
        if item.start_at and item.end_at:
            return item.start_at, item.end_at
        if item.start_time and item.end_time:
            base_date = day_date or date.min
            return (
                datetime.combine(base_date, item.start_time),
                datetime.combine(base_date, item.end_time),
            )
        return None, None

    @staticmethod
    def _parse_opening_hours(raw: str) -> tuple[time, time] | None:
        match = re.fullmatch(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", raw.strip())
        if not match:
            return None
        try:
            return (
                time(int(match.group(1)), int(match.group(2))),
                time(int(match.group(3)), int(match.group(4))),
            )
        except ValueError:
            return None
