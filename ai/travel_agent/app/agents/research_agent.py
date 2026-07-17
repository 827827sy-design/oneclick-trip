from __future__ import annotations

import json
from decimal import Decimal
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    CandidateSelection,
    HotelAreaCandidate,
    Phase1Research,
    Phase2Research,
    POICandidate,
    POIVisitDetail,
    RouteLeg,
    TransportCandidate,
    TravelEntities,
    UserPreferences,
)


class Phase1ResearchAgent(Protocol):
    def research(
        self,
        entities: TravelEntities,
        preferences: UserPreferences,
        weather_summary: str,
    ) -> Phase1Research:
        """Build destination, accommodation, transport and POI candidates."""

    async def aresearch(self, **kwargs) -> Phase1Research:
        """Asynchronous Phase 1 research."""


class Phase2ResearchAgent(Protocol):
    def research(
        self,
        entities: TravelEntities,
        phase1: Phase1Research,
        selection: CandidateSelection,
    ) -> Phase2Research:
        """Deepen only the validated candidate selection."""

    async def aresearch(self, **kwargs) -> Phase2Research:
        """Asynchronous Phase 2 research."""


class LangChainPhase1ResearchAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(Phase1Research, method="json_mode")

    def research(self, **kwargs) -> Phase1Research:
        result = self._runner.invoke(self._messages(**kwargs))
        research = result if isinstance(result, Phase1Research) else Phase1Research.model_validate(result)
        return self._normalize(research, **kwargs)

    async def aresearch(self, **kwargs) -> Phase1Research:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        research = result if isinstance(result, Phase1Research) else Phase1Research.model_validate(result)
        return self._normalize(research, **kwargs)

    @staticmethod
    def _messages(
        *,
        entities: TravelEntities,
        preferences: UserPreferences,
        weather_summary: str,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "你是一键游规划阶段 1 的旅游研究 Agent，只输出 JSON，不要 Markdown。"
                    "根据本次明确需求和长期旅游画像，生成景点候选、住宿区域候选和城际交通方式候选；"
                    "本次明确要求优先于历史记忆。景点应是真实存在且你有把握的地点，覆盖用户偏好并避免明确反感项。"
                    "住宿只推荐区域，不虚构酒店；交通只给方式级建议，不虚构班次、航班号或实时余票。"
                    "票价、住宿价和交通价只能填写保守的 AI 估算，用于预算规划，不得声称为实时报价。"
                    "没有出发地时 transport_options 为空。data_mode 必须为 AI_KNOWLEDGE。"
                    "所有候选必须有唯一 ID；禁止生成 quote_id、供应商 option_id 或可直接预订的库存。"
                    "输出必须符合以下 JSON Schema："
                    f"{json.dumps(Phase1Research.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"本次需求：{entities.model_dump_json()}\n"
                    f"长期画像：{preferences.model_dump_json()}\n"
                    f"天气接口摘要：{weather_summary}"
                )
            ),
        ]

    @staticmethod
    def _normalize(
        research: Phase1Research,
        *,
        entities: TravelEntities,
        preferences: UserPreferences,
        weather_summary: str,
    ) -> Phase1Research:
        del preferences
        pois = [
            poi.model_copy(update={"poi_id": f"AI-POI-{index}"})
            for index, poi in enumerate(research.poi_candidates, start=1)
            if poi.name.strip()
        ]
        areas = [
            area.model_copy(update={"area_id": f"AI-AREA-{index}"})
            for index, area in enumerate(research.hotel_areas, start=1)
            if area.name.strip()
        ]
        transport = [
            option.model_copy(update={"option_id": f"AI-TRANSPORT-{index}"})
            for index, option in enumerate(research.transport_options, start=1)
            if option.name.strip()
        ] if entities.origin else []
        return research.model_copy(
            update={
                "data_mode": "AI_KNOWLEDGE",
                "destination": entities.destination or research.destination,
                "weather_summary": weather_summary,
                "poi_candidates": pois,
                "hotel_areas": areas,
                "transport_options": transport,
            }
        )


class LangChainPhase2ResearchAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(Phase2Research, method="json_mode")

    def research(self, **kwargs) -> Phase2Research:
        result = self._runner.invoke(self._messages(**kwargs))
        research = result if isinstance(result, Phase2Research) else Phase2Research.model_validate(result)
        return self._normalize(research, **kwargs)

    async def aresearch(self, **kwargs) -> Phase2Research:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        research = result if isinstance(result, Phase2Research) else Phase2Research.model_validate(result)
        return self._normalize(research, **kwargs)

    @staticmethod
    def _messages(
        *,
        entities: TravelEntities,
        phase1: Phase1Research,
        selection: CandidateSelection,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "你是一键游规划阶段 2 的精查与路线研究 Agent，只输出 JSON，不要 Markdown。"
                    "只能处理已验证的 selected_poi_ids，所有 poi_id 必须逐字来自候选选择，不得新增景点。"
                    "先为候选地点估算合理的路线距离与通行时间，再整理通常开放时间和门票参考。"
                    "不得在没有 poi_id 时生成门票信息，不得在没有候选目的地时生成路线矩阵。"
                    "所有距离、耗时、开放时间和票价均为 AI 通用知识估算，不是实时查询；"
                    "无法确认时 opening_hours 写‘待核实’，ticket_price 写 0。"
                    "ticket_option_id 必须为空，available 必须为空，禁止伪造库存、quote_id 或可购买状态。"
                    "data_mode 必须为 AI_KNOWLEDGE。输出必须符合以下 JSON Schema："
                    f"{json.dumps(Phase2Research.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"本次需求：{entities.model_dump_json()}\n"
                    f"第一阶段候选：{phase1.model_dump_json()}\n"
                    f"已验证选择：{selection.model_dump_json()}"
                )
            ),
        ]

    @staticmethod
    def _normalize(
        research: Phase2Research,
        *,
        entities: TravelEntities,
        phase1: Phase1Research,
        selection: CandidateSelection,
    ) -> Phase2Research:
        del entities, phase1
        allowed = set(selection.selected_poi_ids)
        details_by_id = {
            detail.poi_id: detail
            for detail in research.poi_details
            if detail.poi_id in allowed
        }
        details = [
            details_by_id.get(
                poi_id,
                POIVisitDetail(poi_id=poi_id, opening_hours="待核实"),
            ).model_copy(update={"ticket_option_id": None, "available": None})
            for poi_id in selection.selected_poi_ids
        ]
        allowed_route_ids = allowed | {"START", selection.hotel_area_id or ""}
        routes = [
            leg for leg in research.route_legs
            if leg.from_id in allowed_route_ids and leg.to_id in allowed_route_ids
        ]
        return Phase2Research(
            data_mode="AI_KNOWLEDGE",
            route_legs=routes,
            poi_details=details,
        )


class RuleBasedPhase1ResearchAgent:
    """Offline development fallback; values are generic estimates, never live claims."""

    def research(
        self,
        entities: TravelEntities,
        preferences: UserPreferences,
        weather_summary: str,
    ) -> Phase1Research:
        destination = entities.destination or "目的地"
        tags = preferences.liked_tags[:2] or ["城市体验"]
        count = max((entities.days or 1) * 2, 2)
        return Phase1Research(
            data_mode="OFFLINE_FALLBACK",
            destination=destination,
            weather_summary=weather_summary,
            poi_candidates=[
                POICandidate(
                    poi_id=f"AI-POI-{index}",
                    name=f"{destination}第 {index} 项当地体验",
                    area="待核实区域",
                    tags=tags,
                    suggested_duration_minutes=120,
                    ticket_price=Decimal("0"),
                )
                for index in range(1, count + 1)
            ],
            hotel_areas=[
                HotelAreaCandidate(
                    area_id="AI-AREA-1",
                    name=f"{destination}公共交通便利区域",
                    reason="优先选择公共交通和餐饮较集中的区域，具体住宿需另行核实。",
                    nightly_price_hint=Decimal("300"),
                )
            ],
            transport_options=(
                [
                    TransportCandidate(
                        option_id="AI-TRANSPORT-1",
                        mode="public_transport",
                        name=f"{entities.origin}至{destination}公共交通方案",
                        duration_minutes=240,
                        price=Decimal("200"),
                    )
                ]
                if entities.origin else []
            ),
        )

    async def aresearch(self, **kwargs) -> Phase1Research:
        return self.research(**kwargs)


class RuleBasedPhase2ResearchAgent:
    def research(
        self,
        entities: TravelEntities,
        phase1: Phase1Research,
        selection: CandidateSelection,
    ) -> Phase2Research:
        del entities, phase1
        route_legs = []
        previous = "START"
        for poi_id in selection.selected_poi_ids:
            route_legs.append(
                RouteLeg(
                    from_id=previous,
                    to_id=poi_id,
                    distance_km=5,
                    duration_minutes=30,
                )
            )
            previous = poi_id
        return Phase2Research(
            data_mode="OFFLINE_FALLBACK",
            route_legs=route_legs,
            poi_details=[
                POIVisitDetail(
                    poi_id=poi_id,
                    opening_hours="待核实",
                    ticket_price=Decimal("0"),
                    available=None,
                )
                for poi_id in selection.selected_poi_ids
            ],
        )

    async def aresearch(self, **kwargs) -> Phase2Research:
        return self.research(**kwargs)
