from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha1
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    DirectPlanProposal,
    ItineraryDay,
    ItineraryItem,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)


class DirectPlannerAgent(Protocol):
    def propose(
        self,
        *,
        query: str,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> DirectPlanProposal:
        """Create a plan from model knowledge without synthetic tool data."""

    async def apropose(self, **kwargs) -> DirectPlanProposal:
        """Asynchronous direct planning."""


class LangChainDirectPlannerAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            DirectPlanProposal,
            method="json_mode",
        )

    def propose(self, **kwargs) -> DirectPlanProposal:
        result = self._runner.invoke(self._messages(**kwargs))
        proposal = (
            result
            if isinstance(result, DirectPlanProposal)
            else DirectPlanProposal.model_validate(result)
        )
        return self._normalize(proposal, **kwargs)

    async def apropose(self, **kwargs) -> DirectPlanProposal:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        proposal = (
            result
            if isinstance(result, DirectPlanProposal)
            else DirectPlanProposal.model_validate(result)
        )
        return self._normalize(proposal, **kwargs)

    @staticmethod
    def _messages(
        *,
        query: str,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> list[SystemMessage | HumanMessage]:
        del conversation_id, current_version
        return [
            SystemMessage(
                content=(
                    "你是一键游的高级旅行规划 Agent。直接使用你的通用知识生成方案，不使用任何 Mock 候选、"
                    "虚构接口返回或伪造的实时数据。可以推荐真实存在且你有把握的景点、区域、美食与交通方式，"
                    "但必须明确它们是 AI 知识建议；不得声称价格、营业时间、票务余量或班次为实时信息。"
                    "本次明确需求优先于长期偏好。预算明显无法覆盖基本交通住宿时 feasible=false，plan=null，"
                    "message 用自然中文解释并给 suggested_budget；否则 feasible=true 并生成完整 TravelPlan。"
                    "方案必须严格满足天数，每天安排合理时间，不重复景点，total_cost 为保守的 AI 估算。"
                    "hotel_area_id、transport_option_id、ticket_option_id 全部留空，因为没有真实供应商报价。"
                    "只输出 JSON，不要使用 Markdown。输出必须符合以下 JSON Schema："
                    f"{json.dumps(DirectPlanProposal.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"用户原话：{query}\n"
                    f"结构化需求：{entities.model_dump_json()}\n"
                    f"有效长期偏好：{preferences.model_dump_json()}"
                )
            ),
        ]

    @classmethod
    def _normalize(
        cls,
        proposal: DirectPlanProposal,
        *,
        query: str,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> DirectPlanProposal:
        del query, preferences
        if not proposal.feasible or proposal.plan is None:
            return proposal.model_copy(update={"plan": None})
        day_count = entities.days or cls._date_duration(entities) or len(proposal.plan.days) or 1
        plan_key = sha1(conversation_id.encode("utf-8")).hexdigest()[:12].upper()
        plan = proposal.plan.model_copy(deep=True)
        days = list(plan.days[:day_count])
        while len(days) < day_count:
            days.append(ItineraryDay(day_index=len(days) + 1, title="自由探索"))
        seen_names: set[str] = set()
        for day_index, day in enumerate(days, start=1):
            day.day_index = day_index
            day.date = entities.start_date + timedelta(days=day_index - 1) if entities.start_date else None
            day.hotel_option_id = None
            base_date = day.date or datetime.min.date()
            cursor = datetime.combine(base_date, time(hour=9))
            normalized_items: list[ItineraryItem] = []
            for item in day.items:
                name = item.name.strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                travel_minutes = min(max(item.travel_minutes or 30, 0), 180)
                visit_minutes = min(max(item.visit_minutes or 120, 30), 360)
                start = cursor + timedelta(minutes=travel_minutes)
                end = start + timedelta(minutes=visit_minutes)
                index = len(normalized_items) + 1
                item.item_id = f"D{day_index}-I{index}"
                item.location_id = f"AI-POI-{day_index}-{index}"
                item.ticket_option_id = None
                item.travel_minutes = travel_minutes
                item.visit_minutes = visit_minutes
                item.start_time = start.time()
                item.end_time = end.time()
                item.start_at = start if day.date else None
                item.end_at = end if day.date else None
                item.description = cls._knowledge_description(item.description)
                normalized_items.append(item)
                cursor = end + timedelta(minutes=60)
            day.items = normalized_items
            day.title = day.title or f"第 {day_index} 天"
        assumptions = list(dict.fromkeys([
            *plan.assumptions,
            "方案由大模型基于通用知识生成，不包含实时价格、班次、营业时间或票务余量。",
            "出行前请通过真实平台核验天气、交通、住宿和门票信息。",
        ]))
        normalized = plan.model_copy(
            update={
                "plan_id": f"PLAN-{plan_key}",
                "version": (current_version or 0) + 1,
                "destination": entities.destination or plan.destination,
                "days": days,
                "hotel_area_id": None,
                "transport_option_id": None,
                "hotel_nights": max(day_count - 1, 0),
                "currency": entities.currency,
                "assumptions": assumptions,
                "created_at": datetime.now(UTC),
            }
        )
        return proposal.model_copy(update={"plan": normalized})

    @staticmethod
    def _date_duration(entities: TravelEntities) -> int | None:
        if entities.start_date and entities.end_date:
            return (entities.end_date - entities.start_date).days + 1
        return None

    @staticmethod
    def _knowledge_description(description: str | None) -> str:
        base = (description or "").strip()
        suffix = "AI 知识建议，开放时间与预约要求请在出行前核实。"
        return f"{base} {suffix}".strip()


class RuleBasedDirectPlannerAgent:
    """Offline fallback that avoids pretending to know destination facts."""

    def propose(
        self,
        *,
        query: str,
        conversation_id: str,
        current_version: int | None,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> DirectPlanProposal:
        del query, preferences
        days_count = entities.days or LangChainDirectPlannerAgent._date_duration(entities) or 1
        people = entities.people or 1
        estimate = Decimal("300") * people * days_count
        budget_limit = entities.budget
        if budget_limit is not None and entities.budget_scope and entities.budget_scope.value == "per_person":
            budget_limit *= people
        if budget_limit is not None and estimate > budget_limit:
            return DirectPlanProposal(
                feasible=False,
                message=(
                    f"按每人每天约 300 元的保守基础估算，这趟旅行至少需要约 {estimate} 元。"
                    "当前预算偏紧，可以提高预算或缩短行程后再生成。"
                ),
                suggested_budget=estimate,
            )
        days = []
        preference_hint = "、".join(entities.explicit_preferences[:2]) or "当地文化"
        for index in range(1, days_count + 1):
            start = time(hour=9)
            end = time(hour=11)
            days.append(
                ItineraryDay(
                    day_index=index,
                    title=f"第 {index} 天：当地体验",
                    summary="等待大模型或真实数据源补充具体地点。",
                    items=[
                        ItineraryItem(
                            item_id=f"D{index}-I1",
                            name=f"第 {index} 天{preference_hint}体验",
                            start_time=start,
                            end_time=end,
                            location_id=f"AI-POI-{index}-1",
                            description="离线兜底建议，具体地点需核实。",
                            travel_minutes=30,
                            visit_minutes=120,
                        )
                    ],
                )
            )
        key = sha1(conversation_id.encode("utf-8")).hexdigest()[:12].upper()
        plan = TravelPlan(
            plan_id=f"PLAN-{key}",
            version=(current_version or 0) + 1,
            destination=entities.destination or "目的地",
            days=days,
            hotel_nights=max(days_count - 1, 0),
            total_cost=estimate,
            currency=entities.currency,
            assumptions=["离线兜底方案未使用 Mock 景点或价格，具体信息需核实。"],
        )
        return DirectPlanProposal(feasible=True, plan=plan)

    async def apropose(self, **kwargs) -> DirectPlanProposal:
        return self.propose(**kwargs)
