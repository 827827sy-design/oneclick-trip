from __future__ import annotations

import json
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    CandidateSelection,
    CandidateVisit,
    Phase1Research,
    TravelEntities,
    UserPreferences,
)


def _compact_area_and_internal_pois(
    poi_ids: list[str],
    research: Phase1Research,
    entities: TravelEntities,
    maximum: int,
) -> tuple[list[str], dict[str, str]]:
    """Avoid selecting a full-day area together with several internal POIs."""
    if (entities.days or 1) < 2 or not entities.destination:
        return poi_ids, {}

    by_id = {poi.poi_id: poi for poi in research.poi_candidates}
    destination = entities.destination
    for container_id in poi_ids:
        container = by_id.get(container_id)
        if container is None or container.suggested_duration_minutes < 360:
            continue
        internal_ids = [
            poi_id
            for poi_id in poi_ids
            if poi_id != container_id
            and poi_id in by_id
            and destination in by_id[poi_id].area
        ]
        if len(internal_ids) < 2:
            continue

        independent = [
            poi
            for poi in research.poi_candidates
            if poi.poi_id != container_id
            and poi.poi_id not in internal_ids
            and destination not in poi.area
            and poi.suggested_duration_minutes <= 240
        ]
        if not independent:
            continue

        target_count = min(max(entities.days or 2, 2), maximum)
        compacted = [poi.poi_id for poi in independent[: target_count - 1]]
        compacted.append(container_id)
        forced_days = {
            poi_id: f"DAY_{min(index + 1, max((entities.days or 2) - 1, 1))}"
            for index, poi_id in enumerate(compacted[:-1])
        }
        forced_days[container_id] = f"DAY_{min(entities.days or 2, 2)}"
        return compacted, forced_days

    return poi_ids, {}


class CandidateSelectorAgent(Protocol):
    def select(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        """Select only IDs supplied by Phase 1 research."""

    async def aselect(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        """Asynchronous candidate selection."""


class LangChainCandidateSelectorAgent:
    """Use a Pro-class model to select from Phase 1 candidates only."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            CandidateSelection,
            method="json_mode",
        )

    def select(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        result = self._runner.invoke(self._messages(research, entities, preferences))
        selection = (
            result
            if isinstance(result, CandidateSelection)
            else CandidateSelection.model_validate(result)
        )
        return self._normalize(selection, research, entities)

    async def aselect(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        result = await self._runner.ainvoke(
            self._messages(research, entities, preferences)
        )
        selection = (
            result
            if isinstance(result, CandidateSelection)
            else CandidateSelection.model_validate(result)
        )
        return self._normalize(selection, research, entities)

    @staticmethod
    def _messages(
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "你是 Dify V3 一键游中的候选景点与住宿区域选择 Agent，只输出 JSON。"
                    "根据 TravelState 和第一阶段结果选择 selected_pois、hotel_area_id、"
                    "transport_option_id 与 destinations。selected_pois 每项必须包含 poi_id、"
                    "visit_date、estimated_duration_minutes；没有真实日期时 visit_date 使用 DAY_1、DAY_2。"
                    "所有 ID 必须逐字来自第一阶段候选集合，不得编造。每个旅行日一般选择 1 至 2 个主要景点，"
                    "避免用户明确不喜欢的标签；没有出发地时 transport_option_id 可以为空。"
                    "不得在没有 poi_id 时请求门票，不得在没有 destinations 时请求路线矩阵。"
                    "selected_poi_ids 必须与 selected_pois 中的 poi_id 一致，reasons 用简短中文解释取舍。"
                    "只输出 JSON，不要使用 Markdown。输出必须符合以下 JSON Schema："
                    f"{json.dumps(CandidateSelection.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"本次需求：{entities.model_dump_json()}\n"
                    f"有效偏好：{preferences.model_dump_json()}\n"
                    f"第一阶段研究：{research.model_dump_json()}"
                )
            ),
        ]

    @staticmethod
    def _normalize(
        selection: CandidateSelection,
        research: Phase1Research,
        entities: TravelEntities,
    ) -> CandidateSelection:
        allowed_pois = {item.poi_id for item in research.poi_candidates}
        poi_by_id = {item.poi_id: item for item in research.poi_candidates}
        allowed_areas = {item.area_id for item in research.hotel_areas}
        allowed_transport = {item.option_id for item in research.transport_options}
        maximum = max(1, (entities.days or 1) * 2)
        requested_ids = [visit.poi_id for visit in selection.selected_pois]
        requested_ids.extend(selection.selected_poi_ids)
        poi_ids = list(
            dict.fromkeys(
                item for item in requested_ids if item in allowed_pois
            )
        )[:maximum]
        poi_ids, forced_days = _compact_area_and_internal_pois(
            poi_ids,
            research,
            entities,
            maximum,
        )
        visits_by_id = {
            visit.poi_id: visit
            for visit in selection.selected_pois
            if visit.poi_id in poi_ids
        }
        day_count = max(entities.days or 1, 1)
        selected_pois = []
        for index, poi_id in enumerate(poi_ids):
            visit = visits_by_id.get(
                poi_id,
                CandidateVisit(
                    poi_id=poi_id,
                    visit_date=f"DAY_{index % day_count + 1}",
                    estimated_duration_minutes=poi_by_id[poi_id].suggested_duration_minutes,
                ),
            )
            if poi_id in forced_days:
                visit = visit.model_copy(update={"visit_date": forced_days[poi_id]})
            selected_pois.append(visit)
        return selection.model_copy(
            update={
                "selected_poi_ids": poi_ids,
                "selected_pois": selected_pois,
                "hotel_area_id": (
                    selection.hotel_area_id
                    if selection.hotel_area_id in allowed_areas
                    else None
                ),
                "transport_option_id": (
                    selection.transport_option_id
                    if selection.transport_option_id in allowed_transport
                    else None
                ),
                "destinations": poi_ids,
            }
        )


class RuleBasedCandidateSelectorAgent:
    """Deterministic development selector with preference-aware scoring."""

    def select(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        disliked = set(preferences.disliked_tags)
        liked = set(preferences.liked_tags)
        allowed = [poi for poi in research.poi_candidates if not disliked.intersection(poi.tags)]
        ranked = sorted(
            allowed,
            key=lambda poi: (
                -len(liked.intersection(poi.tags)),
                poi.ticket_price,
                poi.poi_id,
            ),
        )
        maximum = max(1, (entities.days or 1) * 2)
        selected_ids, forced_days = _compact_area_and_internal_pois(
            [poi.poi_id for poi in ranked[:maximum]],
            research,
            entities,
            maximum,
        )
        poi_by_id = {poi.poi_id: poi for poi in research.poi_candidates}
        selected = [poi_by_id[poi_id] for poi_id in selected_ids]

        hotel_area = min(
            research.hotel_areas,
            key=lambda area: area.nightly_price_hint,
            default=None,
        )
        transport = self._select_transport(research, preferences)
        reasons = [
            f"优先匹配偏好：{', '.join(preferences.liked_tags) or '未指定'}。",
            f"已排除不喜欢标签：{', '.join(preferences.disliked_tags) or '无'}。",
        ]
        return CandidateSelection(
            selected_poi_ids=[poi.poi_id for poi in selected],
            selected_pois=[
                CandidateVisit(
                    poi_id=poi.poi_id,
                    visit_date=forced_days.get(
                        poi.poi_id,
                        f"DAY_{index % max(entities.days or 1, 1) + 1}",
                    ),
                    estimated_duration_minutes=poi.suggested_duration_minutes,
                )
                for index, poi in enumerate(selected)
            ],
            hotel_area_id=hotel_area.area_id if hotel_area else None,
            transport_option_id=transport.option_id if transport else None,
            destinations=[poi.poi_id for poi in selected],
            reasons=reasons,
        )

    async def aselect(
        self,
        research: Phase1Research,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> CandidateSelection:
        return self.select(research, entities, preferences)

    @staticmethod
    def _select_transport(research: Phase1Research, preferences: UserPreferences):
        preferred_modes = {
            "高铁": "train",
            "火车": "train",
            "飞机": "flight",
        }
        requested_modes = [
            preferred_modes[tag]
            for tag in preferences.preferred_transport + preferences.liked_tags
            if tag in preferred_modes
        ]
        for mode in requested_modes:
            match = next((item for item in research.transport_options if item.mode == mode), None)
            if match:
                return match
        return research.transport_options[0] if research.transport_options else None
