from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from hashlib import sha1
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    BudgetMode,
    CandidateSelection,
    ItineraryDay,
    ItineraryItem,
    Phase1Research,
    Phase2Research,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)


class PlannerAgent(Protocol):
    def plan(
        self,
        *,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research,
        selection: CandidateSelection,
        phase2: Phase2Research,
    ) -> TravelPlan:
        """Generate a structured plan draft from validated research state."""

    async def aplan(self, **kwargs) -> TravelPlan:
        """Asynchronous structured planning."""


class LangChainPlannerAgent:
    """Generate the itinerary structure with a Pro-class chat model."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            TravelPlan,
            method="json_mode",
        )

    def plan(self, **kwargs) -> TravelPlan:
        result = self._runner.invoke(self._messages(**kwargs))
        plan = result if isinstance(result, TravelPlan) else TravelPlan.model_validate(result)
        return self._normalize(plan, **kwargs)

    async def aplan(self, **kwargs) -> TravelPlan:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        plan = result if isinstance(result, TravelPlan) else TravelPlan.model_validate(result)
        return self._normalize(plan, **kwargs)

    @staticmethod
    def _messages(
        *,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research,
        selection: CandidateSelection,
        phase2: Phase2Research,
    ) -> list[SystemMessage | HumanMessage]:
        del conversation_id, current_version
        return [
            SystemMessage(
                content=(
                    "你是 Dify V3 一键游中的完整行程规划 Agent，只输出完整 JSON 行程。"
                    "只能使用给定候选、路线、开放时间和门票数据，"
                    "不得编造景点 ID、酒店区域 ID、交通选项 ID 或票务选项 ID。"
                    "本次明确需求优先于长期偏好；安排应避免时间冲突和无效折返。"
                    "当 entities.budget_mode=minimize 时，必须采用极限穷游成本结构：青旅床位、"
                    "候选中最低价城际交通、市内步行公交或共享助力车、泡面与基础饱腹餐、免费景点优先；"
                    "必须遵守 candidate_selection.selected_pois 中的 visit_date 和 estimated_duration_minutes，"
                    "生成逐日时间安排、交通衔接、住宿区域、费用汇总和必要说明。"
                    "days 中每个项目都要有稳定 item_id、visit_start/end、travel_minutes、visit_minutes；"
                    "每天提供清楚的 title、summary，每个活动 description 说明体验重点与衔接建议。"
                    "开放时间、路线和价格来自第二阶段时必须标明为 AI 估算，不得声称实时、可购买或有库存。"
                    "输出完整 TravelPlan，不要只输出摘要或局部天数。"
                    "只输出 JSON，不要使用 Markdown。输出必须符合以下 JSON Schema："
                    f"{json.dumps(TravelPlan.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"本次需求：{entities.model_dump_json()}\n"
                    f"有效偏好：{preferences.model_dump_json()}\n"
                    f"第一阶段研究：{phase1.model_dump_json()}\n"
                    f"已验证选择：{selection.model_dump_json()}\n"
                    f"第二阶段研究：{phase2.model_dump_json()}"
                )
            ),
        ]

    @staticmethod
    def _normalize(
        plan: TravelPlan,
        *,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research,
        selection: CandidateSelection,
        phase2: Phase2Research,
    ) -> TravelPlan:
        del preferences
        day_count = entities.days or RuleBasedPlannerAgent._date_duration(entities) or len(plan.days)
        hotel_nights = max(day_count - 1, 0)
        plan_key = sha1(conversation_id.encode("utf-8")).hexdigest()[:12].upper()
        normalized = plan.model_copy(deep=True)
        allowed_ids = set(selection.selected_poi_ids)
        poi_by_id = {
            poi.poi_id: poi
            for poi in phase1.poi_candidates
            if poi.poi_id in allowed_ids
        }
        poi_id_by_name = {poi.name: poi.poi_id for poi in poi_by_id.values()}
        detail_by_id = {detail.poi_id: detail for detail in phase2.poi_details}
        route_minutes = {leg.to_id: leg.duration_minutes for leg in phase2.route_legs}
        seen_locations: set[str] = set()

        for day_index, day in enumerate(normalized.days, start=1):
            travel_date = (
                entities.start_date + timedelta(days=day_index - 1)
                if entities.start_date
                else None
            )
            day.day_index = day_index
            day.date = travel_date
            day.hotel_option_id = selection.hotel_area_id
            base_date = travel_date or datetime.min.date()
            cursor = datetime.combine(base_date, time(hour=8))
            grounded_items: list[ItineraryItem] = []
            for item in day.items:
                location_id = item.location_id if item.location_id in allowed_ids else None
                location_id = location_id or poi_id_by_name.get(item.name)
                poi = poi_by_id.get(location_id or "")
                if poi is None or poi.poi_id in seen_locations:
                    continue
                seen_locations.add(poi.poi_id)
                detail = detail_by_id.get(poi.poi_id)
                travel_minutes = route_minutes.get(
                    poi.poi_id,
                    30 if grounded_items else 20,
                )
                visit_minutes = max(poi.suggested_duration_minutes, 30)
                start_at = cursor + timedelta(minutes=travel_minutes)
                if detail:
                    try:
                        opening_start = time.fromisoformat(
                            detail.opening_hours.split("-", 1)[0]
                        )
                    except ValueError:
                        opening_start = None
                    if opening_start:
                        start_at = max(start_at, datetime.combine(base_date, opening_start))
                end_at = start_at + timedelta(minutes=visit_minutes)
                item.item_id = f"D{day_index}-I{len(grounded_items) + 1}"
                item.name = poi.name
                item.item_type = RuleBasedPlannerAgent._item_type(poi.tags)
                item.location_id = poi.poi_id
                item.travel_minutes = travel_minutes
                item.visit_minutes = visit_minutes
                item.start_time = start_at.time()
                item.end_time = end_at.time()
                item.start_at = start_at if travel_date else None
                item.end_at = end_at if travel_date else None
                item.ticket_option_id = detail.ticket_option_id if detail else None
                item.estimated_cost = detail.ticket_price if detail else poi.ticket_price
                opening_note = (
                    f"开放时间参考：{detail.opening_hours}。"
                    if detail
                    else "开放时间待确认。"
                )
                item.description = " ".join(
                    part for part in (item.description, opening_note) if part
                )
                grounded_items.append(item)
                cursor = end_at + timedelta(minutes=30)
            day.items = grounded_items

        total_cost = RuleBasedPlannerAgent._estimate_cost(
            entities=entities,
            phase1=phase1,
            selection=selection,
            phase2=phase2,
            hotel_nights=hotel_nights,
        )
        disclosure = "景点、住宿区域、路线与费用来自 AI 通用知识估算，不是实时搜索结果。"
        assumptions = list(dict.fromkeys([*normalized.assumptions, disclosure]))
        return normalized.model_copy(
            update={
                "plan_id": f"PLAN-{plan_key}",
                "version": (current_version or 0) + 1,
                "destination": phase1.destination,
                "hotel_area_id": selection.hotel_area_id,
                "transport_option_id": selection.transport_option_id,
                "hotel_nights": hotel_nights,
                "total_cost": total_cost,
                "currency": entities.currency,
                "assumptions": assumptions,
            }
        )


class RuleBasedPlannerAgent:
    """Deterministic planner used to exercise the graph before LLM wiring."""

    def plan(
        self,
        *,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research,
        selection: CandidateSelection,
        phase2: Phase2Research,
    ) -> TravelPlan:
        del preferences
        day_count = entities.days or self._date_duration(entities) or 1
        poi_by_id = {poi.poi_id: poi for poi in phase1.poi_candidates}
        detail_by_id = {detail.poi_id: detail for detail in phase2.poi_details}
        route_minutes = {
            leg.to_id: leg.duration_minutes
            for leg in phase2.route_legs
        }
        days: list[ItineraryDay] = []

        selected_pois = [
            poi_by_id[poi_id]
            for poi_id in selection.selected_poi_ids
            if poi_id in poi_by_id
        ]
        for day_index in range(1, day_count + 1):
            day_pois = selected_pois[day_index - 1 :: day_count]
            travel_date = (
                entities.start_date + timedelta(days=day_index - 1)
                if entities.start_date
                else None
            )
            cursor = datetime.combine(
                travel_date or datetime.min.date(),
                time(hour=9),
            )
            items: list[ItineraryItem] = []
            for item_index, poi in enumerate(day_pois, start=1):
                travel_minutes = route_minutes.get(poi.poi_id, 30 if items else 20)
                start_at = cursor + timedelta(minutes=travel_minutes)
                end_at = start_at + timedelta(minutes=poi.suggested_duration_minutes)
                detail = detail_by_id.get(poi.poi_id)
                items.append(
                    ItineraryItem(
                        item_id=f"D{day_index}-I{item_index}",
                        name=poi.name,
                        item_type=self._item_type(poi.tags),
                        start_at=start_at if travel_date else None,
                        end_at=end_at if travel_date else None,
                        start_time=start_at.time(),
                        end_time=end_at.time(),
                        location_id=poi.poi_id,
                        description=f"开放时间：{detail.opening_hours if detail else '待查询'}。",
                        travel_minutes=travel_minutes,
                        visit_minutes=poi.suggested_duration_minutes,
                        ticket_option_id=detail.ticket_option_id if detail else None,
                        estimated_cost=detail.ticket_price if detail else poi.ticket_price,
                    )
                )
                cursor = end_at + timedelta(minutes=60)
            days.append(
                ItineraryDay(
                    day_index=day_index,
                    date=travel_date,
                    title=f"第 {day_index} 天：{self._day_title(day_pois)}",
                    summary="按区域组合景点，减少无效折返。" if day_pois else "预留休息与自由活动时间。",
                    items=items,
                    hotel_option_id=selection.hotel_area_id,
                )
            )

        hotel_nights = max(day_count - 1, 0)
        total_cost = self._estimate_cost(
            entities=entities,
            phase1=phase1,
            selection=selection,
            phase2=phase2,
            hotel_nights=hotel_nights,
        )
        plan_key = sha1(conversation_id.encode("utf-8")).hexdigest()[:12].upper()
        assumptions = [
            "景点、住宿区域、路线与费用来自 AI 通用知识估算，不是实时搜索结果。"
        ]
        if entities.budget_mode is BudgetMode.MINIMIZE:
            assumptions.append(
                "本方案按极限穷游核算：青旅床位、最低价城际交通、步行公交或共享助力车、"
                "泡面与基础饱腹餐、免费景点优先。"
            )
        if not entities.origin:
            assumptions.append("未提供出发地，城际交通暂不计入有效方案选择。")
        if not entities.start_date:
            assumptions.append("未提供具体出发日期，行程仅展示相对日次和时刻。")
        return TravelPlan(
            plan_id=f"PLAN-{plan_key}",
            version=(current_version or 0) + 1,
            destination=phase1.destination,
            days=days,
            hotel_area_id=selection.hotel_area_id,
            transport_option_id=selection.transport_option_id,
            hotel_nights=hotel_nights,
            assumptions=assumptions,
            total_cost=total_cost,
            currency=entities.currency,
        )

    async def aplan(self, **kwargs) -> TravelPlan:
        return self.plan(**kwargs)

    @staticmethod
    def _date_duration(entities: TravelEntities) -> int | None:
        if entities.start_date and entities.end_date:
            return (entities.end_date - entities.start_date).days + 1
        return None

    @staticmethod
    def _day_title(pois) -> str:
        return " + ".join(poi.name for poi in pois) if pois else "自由探索"

    @staticmethod
    def _item_type(tags: list[str]) -> str:
        if any(tag in {"美食", "餐饮", "小吃", "夜市", "咖啡"} for tag in tags):
            return "FOOD"
        if any(tag in {"交通", "高铁", "飞机"} for tag in tags):
            return "TRANSPORT"
        return "SPOT"

    @staticmethod
    def _estimate_cost(
        *,
        entities: TravelEntities,
        phase1: Phase1Research,
        selection: CandidateSelection,
        phase2: Phase2Research,
        hotel_nights: int,
    ) -> Decimal:
        people = entities.people or 1
        hotel_area = next(
            (area for area in phase1.hotel_areas if area.area_id == selection.hotel_area_id),
            None,
        )
        transport = next(
            (item for item in phase1.transport_options if item.option_id == selection.transport_option_id),
            None,
        )
        nightly_price = hotel_area.nightly_price_hint if hotel_area else Decimal("0")
        if entities.budget_mode is BudgetMode.MINIMIZE and hotel_nights:
            nightly_price = max(
                Decimal("45"),
                min(Decimal("90"), (nightly_price or Decimal("180")) * Decimal("0.35")),
            ) * people
        hotel_cost = nightly_price * hotel_nights
        transport_cost = (transport.price if transport else Decimal("0")) * people
        ticket_cost = sum((detail.ticket_price for detail in phase2.poi_details), Decimal("0")) * people
        food_and_local_rate = (
            Decimal("50")
            if entities.budget_mode is BudgetMode.MINIMIZE
            else Decimal("230")
        )
        food_and_local = food_and_local_rate * people * max(entities.days or 1, 1)
        return hotel_cost + transport_cost + ticket_cost + food_and_local
