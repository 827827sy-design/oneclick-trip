from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    CandidateSelection,
    ModificationRequest,
    ModificationResult,
    ModifyAnalysis,
    ModifyImpact,
    Phase2Research,
    POICandidate,
    ToolName,
    TravelEntities,
    TravelPlan,
)


class ModifyAnalyzerAgent(Protocol):
    def analyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        """Classify modification impact and required tool stages."""

    async def aanalyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        """Asynchronous modification analysis."""


class ModifyAgent(Protocol):
    def apply(
        self,
        plan: TravelPlan,
        analysis: ModifyAnalysis,
        entities: TravelEntities,
        poi_candidates: list[POICandidate],
    ) -> ModificationResult:
        """Apply the structured request to a copied plan."""

    def enrich(
        self,
        plan: TravelPlan,
        phase2: Phase2Research,
        people: int,
    ) -> TravelPlan:
        """Merge refreshed route, opening-hours and ticket data."""


class RuleBasedModifyAnalyzerAgent:
    CHINESE_NUMBERS = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def analyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        del current_plan, entities
        request = ModificationRequest(
            target_day=self._target_day(query),
            target_period=next(
                (period for period in ("上午", "下午", "晚上") if period in query),
                None,
            ),
            replacement_name=self._replacement(query),
            budget_delta=self._budget_delta(query),
            new_budget=self._new_budget(query),
            remove_tags=self._remove_tags(query),
            swap_days=self._swap_days(query),
        )
        discovery: list[ToolName] = []
        dependent: list[ToolName] = []
        impact = (
            ModifyImpact.RESEARCH_REQUIRED
            if request.replacement_name or request.remove_tags
            else ModifyImpact.SIMPLE
        )
        if impact is ModifyImpact.RESEARCH_REQUIRED:
            reasons = ["地点变更由修改 Agent 基于当前方案生成新版本。"]
        else:
            reasons = ["简单调整不需要调用外部工具。"]
        return ModifyAnalysis(
            impact=impact,
            request=request,
            discovery_tools=discovery,
            dependent_tools=dependent,
            reasons=reasons,
        )

    async def aanalyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        return self.analyze(query, current_plan, entities)

    def _target_day(self, query: str) -> int | None:
        match = re.search(r"第(\d{1,2}|[一二两三四五六七八九十])天", query)
        if not match:
            return None
        raw = match.group(1)
        return int(raw) if raw.isdigit() else self.CHINESE_NUMBERS[raw]

    @staticmethod
    def _replacement(query: str) -> str | None:
        match = re.search(r"换成([^，。；]+)", query)
        return match.group(1).strip() if match else None

    @staticmethod
    def _budget_delta(query: str) -> Decimal | None:
        match = re.search(r"预算(?:降低|减少)(\d+(?:\.\d+)?)", query)
        if match:
            return -Decimal(match.group(1))
        match = re.search(r"预算(?:提高|增加)(\d+(?:\.\d+)?)", query)
        return Decimal(match.group(1)) if match else None

    @staticmethod
    def _new_budget(query: str) -> Decimal | None:
        match = re.search(r"预算(?:改成|调整为|设为)(\d+(?:\.\d+)?)", query)
        return Decimal(match.group(1)) if match else None

    @staticmethod
    def _remove_tags(query: str) -> list[str]:
        match = re.search(r"(?:不要|删除|删掉)([^，。；]+?)(?:景点|$)", query)
        return [match.group(1).strip()] if match else []

    def _swap_days(self, query: str) -> tuple[int, int] | None:
        match = re.search(
            r"(?:交换|把)第(\d{1,2}|[一二两三四五六七八九十])天(?:和|与)第"
            r"(\d{1,2}|[一二两三四五六七八九十])天(?:交换)?",
            query,
        )
        if not match:
            return None
        return self._number(match.group(1)), self._number(match.group(2))

    def _number(self, raw: str) -> int:
        return int(raw) if raw.isdigit() else self.CHINESE_NUMBERS[raw]


class LangChainModifyAnalyzerAgent:
    """Structured-output adapter; code still filters the returned tool names."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            ModifyAnalysis,
            method="function_calling",
            strict=True,
        )

    def analyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        result = self._runner.invoke(self._messages(query, current_plan, entities))
        return result if isinstance(result, ModifyAnalysis) else ModifyAnalysis.model_validate(result)

    async def aanalyze(
        self,
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> ModifyAnalysis:
        result = await self._runner.ainvoke(self._messages(query, current_plan, entities))
        return result if isinstance(result, ModifyAnalysis) else ModifyAnalysis.model_validate(result)

    @staticmethod
    def _messages(
        query: str,
        current_plan: TravelPlan,
        entities: TravelEntities,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "分析用户对已有行程的修改，只输出结构化 ModifyAnalysis。"
                    "地点替换、日期变化或移除某类景点时 impact 使用 research_required，"
                    "discovery_tools 和 dependent_tools 必须为空；"
                    "简单排序或预算调整不调用工具。"
                    "dependent_tools 必须为空。工具建议最终仍会由代码白名单过滤。"
                )
            ),
            HumanMessage(
                content=(
                    f"请求：{query}\n实体：{entities.model_dump_json()}\n"
                    f"当前方案：{current_plan.model_dump_json()}"
                )
            ),
        ]


class RuleBasedModifyAgent:
    def apply(
        self,
        plan: TravelPlan,
        analysis: ModifyAnalysis,
        entities: TravelEntities,
        poi_candidates: list[POICandidate],
    ) -> ModificationResult:
        revised = plan.model_copy(deep=True)
        revised_entities = entities.model_copy(deep=True)
        errors: list[str] = []
        request = analysis.request
        poi_by_id = {poi.poi_id: poi for poi in poi_candidates}

        operation_found = any(
            (
                request.replacement_name,
                request.budget_delta is not None,
                request.new_budget is not None,
                request.remove_tags,
                request.swap_days,
            )
        )
        if not operation_found:
            errors.append("UNSUPPORTED_MODIFICATION")

        if request.replacement_name:
            self._replace_poi(revised, request, poi_candidates, revised_entities, errors)
        if request.remove_tags:
            self._remove_tagged_pois(revised, request.remove_tags, poi_by_id, revised_entities)
        if request.swap_days:
            self._swap_days(revised, request.swap_days, errors)
        self._update_budget(revised_entities, request, errors)
        self._reflow(revised)
        revised.assumptions = [*revised.assumptions, "已根据用户修改请求生成新版本候选方案。"]

        selection = CandidateSelection(
            selected_poi_ids=[
                item.location_id
                for day in revised.days
                for item in day.items
                if item.location_id
            ],
            hotel_area_id=revised.hotel_area_id,
            transport_option_id=revised.transport_option_id,
            reasons=list(analysis.reasons),
        )
        return ModificationResult(
            plan=revised,
            entities=revised_entities,
            selection=selection,
            errors=errors,
        )

    def enrich(
        self,
        plan: TravelPlan,
        phase2: Phase2Research,
        people: int,
    ) -> TravelPlan:
        revised = plan.model_copy(deep=True)
        details = {detail.poi_id: detail for detail in phase2.poi_details}
        route_minutes = {leg.to_id: leg.duration_minutes for leg in phase2.route_legs}
        old_ticket_total = sum(
            item.estimated_cost for day in revised.days for item in day.items
        ) * people
        for day in revised.days:
            for item in day.items:
                detail = details.get(item.location_id or "")
                if detail:
                    item.description = f"开放时间：{detail.opening_hours}。"
                    item.ticket_option_id = detail.ticket_option_id
                    item.estimated_cost = detail.ticket_price
                item.travel_minutes = route_minutes.get(
                    item.location_id or "",
                    item.travel_minutes,
                )
        new_ticket_total = sum(
            item.estimated_cost for day in revised.days for item in day.items
        ) * people
        revised.total_cost = max(revised.total_cost - old_ticket_total + new_ticket_total, 0)
        self._reflow(revised)
        return revised

    def _replace_poi(
        self,
        plan: TravelPlan,
        request: ModificationRequest,
        candidates: list[POICandidate],
        entities: TravelEntities,
        errors: list[str],
    ) -> None:
        target_day = next(
            (day for day in plan.days if day.day_index == request.target_day),
            None,
        )
        if target_day is None:
            errors.append("TARGET_DAY_NOT_FOUND")
            return
        target_item = self._target_item(target_day.items, request.target_period)
        if target_item is None:
            errors.append("TARGET_PERIOD_NOT_FOUND")
            return
        replacement = self._find_poi(request.replacement_name or "", candidates)
        if replacement is None:
            errors.append("REPLACEMENT_POI_NOT_FOUND")
            return

        old_item = target_item.model_copy(deep=True)
        existing = next(
            (
                item
                for day in plan.days
                for item in day.items
                if item is not target_item and item.location_id == replacement.poi_id
            ),
            None,
        )
        if existing:
            self._copy_poi_fields(existing, old_item)
        else:
            plan.total_cost += (replacement.ticket_price - target_item.estimated_cost) * (
                entities.people or 1
            )
        target_item.name = replacement.name
        target_item.location_id = replacement.poi_id
        target_item.visit_minutes = replacement.suggested_duration_minutes
        target_item.ticket_option_id = None
        target_item.estimated_cost = replacement.ticket_price

    @staticmethod
    def _copy_poi_fields(target, source) -> None:
        target.name = source.name
        target.location_id = source.location_id
        target.visit_minutes = source.visit_minutes
        target.ticket_option_id = source.ticket_option_id
        target.estimated_cost = source.estimated_cost
        target.description = source.description

    @staticmethod
    def _target_item(items, period: str | None):
        if not items:
            return None
        if period == "上午":
            return next((item for item in items if item.start_time and item.start_time.hour < 12), None)
        if period == "下午":
            return next(
                (item for item in items if item.start_time and 12 <= item.start_time.hour < 18),
                None,
            )
        if period == "晚上":
            return next((item for item in items if item.start_time and item.start_time.hour >= 18), None)
        return items[0]

    @staticmethod
    def _find_poi(name: str, candidates: list[POICandidate]) -> POICandidate | None:
        direct = next((poi for poi in candidates if name in poi.name or poi.name in name), None)
        if direct:
            return direct
        keywords = ("熊猫", "杜甫", "草堂", "武侯", "宽窄", "锦里", "春熙")
        return next(
            (poi for keyword in keywords if keyword in name for poi in candidates if keyword in poi.name),
            None,
        )

    @staticmethod
    def _remove_tagged_pois(
        plan: TravelPlan,
        tags: list[str],
        poi_by_id: dict[str, POICandidate],
        entities: TravelEntities,
    ) -> None:
        people = entities.people or 1
        for day in plan.days:
            retained = []
            for item in day.items:
                poi = poi_by_id.get(item.location_id or "")
                if poi and set(tags).intersection(poi.tags):
                    plan.total_cost = max(plan.total_cost - item.estimated_cost * people, 0)
                else:
                    retained.append(item)
            day.items = retained

    @staticmethod
    def _swap_days(
        plan: TravelPlan,
        swap_days: tuple[int, int],
        errors: list[str],
    ) -> None:
        first = next((day for day in plan.days if day.day_index == swap_days[0]), None)
        second = next((day for day in plan.days if day.day_index == swap_days[1]), None)
        if first is None or second is None:
            errors.append("SWAP_DAY_NOT_FOUND")
            return
        first.items, second.items = second.items, first.items

    @staticmethod
    def _update_budget(
        entities: TravelEntities,
        request: ModificationRequest,
        errors: list[str],
    ) -> None:
        if request.new_budget is not None:
            entities.budget = request.new_budget
        elif request.budget_delta is not None:
            if entities.budget is None:
                errors.append("CURRENT_BUDGET_MISSING")
            else:
                updated = entities.budget + request.budget_delta
                if updated < 0:
                    errors.append("BUDGET_BELOW_ZERO")
                else:
                    entities.budget = updated

    @staticmethod
    def _reflow(plan: TravelPlan) -> None:
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
                cursor = end + timedelta(minutes=60)
            names = " + ".join(item.name for item in day.items) or "自由活动"
            day.title = f"第 {day.day_index} 天：{names}"
        plan.created_at = datetime.now(UTC)
