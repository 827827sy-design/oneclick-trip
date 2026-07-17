from __future__ import annotations

import json
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    HardValidationResult,
    Phase1Research,
    ReviewResult,
    ReviewVerdict,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)


class ReviewerAgent(Protocol):
    def review(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        """Review preference fit, pace and experience quality."""

    async def areview(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        """Asynchronous soft review."""


class RuleBasedReviewerAgent:
    """Deterministic reviewer used until a production LLM is configured."""

    def review(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        del entities
        issues: list[str] = []
        suggestions: list[str] = []
        if not hard_validation.hard_pass:
            issues.append("HARD_VALIDATION_FAILED")

        # Candidate tags only exist in the research-tool flow. Direct LLM plans
        # have no synthetic candidate set, so their preference fit is reviewed
        # by the LLM reviewer instead of inventing missing tags here.
        if phase1 is not None:
            poi_by_id = {poi.poi_id: poi for poi in phase1.poi_candidates}
            selected_pois = [
                poi_by_id[item.location_id]
                for day in plan.days
                for item in day.items
                if item.location_id in poi_by_id
            ]
            selected_tags = {tag for poi in selected_pois for tag in poi.tags}
            disliked_matches = selected_tags.intersection(preferences.disliked_tags)
            if disliked_matches:
                issues.append(f"DISLIKED_TAG_INCLUDED:{','.join(sorted(disliked_matches))}")
                suggestions.append("移除与用户明确不喜欢标签冲突的景点。")
            if preferences.liked_tags and not selected_tags.intersection(preferences.liked_tags):
                issues.append("PREFERENCE_COVERAGE_LOW")
                suggestions.append("至少安排一个与用户核心偏好匹配的体验。")

        for day in plan.days:
            if not day.items:
                issues.append(f"EMPTY_DAY:{day.day_index}")
                suggestions.append(f"为第 {day.day_index} 天补充合理活动或缩短总天数。")
                continue
            active_minutes = sum(
                item.travel_minutes + item.visit_minutes for item in day.items
            )
            if len(day.items) > 3 or active_minutes > 600:
                issues.append(f"PACE_TOO_FAST:{day.day_index}")
                suggestions.append(f"降低第 {day.day_index} 天的景点数量或交通耗时。")
            if preferences.pace in {"懒散", "轻松", "slow", "relaxed"} and len(day.items) > 2:
                issues.append(f"PACE_MISMATCH:{day.day_index}")
                suggestions.append(f"第 {day.day_index} 天最多安排两个主要活动。")

        score = max(0, 100 - len(issues) * 20)
        return ReviewResult(
            verdict=ReviewVerdict.REVISE if issues else ReviewVerdict.PASS,
            score=score,
            issues=issues,
            suggestions=list(dict.fromkeys(suggestions)),
        )

    async def areview(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        return self.review(plan, entities, preferences, phase1, hard_validation)


class LangChainReviewerAgent:
    """Production structured-output adapter for a Flash-class review model."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            ReviewResult,
            method="json_mode",
        )

    def review(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        result = self._runner.invoke(
            self._messages(plan, entities, preferences, phase1, hard_validation)
        )
        return result if isinstance(result, ReviewResult) else ReviewResult.model_validate(result)

    async def areview(
        self,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> ReviewResult:
        result = await self._runner.ainvoke(
            self._messages(plan, entities, preferences, phase1, hard_validation)
        )
        return result if isinstance(result, ReviewResult) else ReviewResult.model_validate(result)

    @staticmethod
    def _messages(
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        phase1: Phase1Research | None,
        hard_validation: HardValidationResult,
    ) -> list[SystemMessage | HumanMessage]:
        grounding_rule = (
            "候选集合与工具数据存在时，只能在这些信息范围内评审。"
            if phase1 is not None
            else (
                "这是大模型基于通用知识直接生成的方案，没有候选工具数据；"
                "只评审方案自身，不得补造实时价格、营业时间或票务余量。"
            )
        )
        return [
            SystemMessage(
                content=(
                    "你是旅游体验评审员，只评价偏好匹配、节奏和体验。"
                    "不要重新计算预算或日期。hard_pass 为 false 时 verdict 必须是 revise。"
                    f"{grounding_rule}"
                    "不得用常识推翻工具返回的开放时间。"
                    "hard_pass 为 true 时，只有空白日、明确偏好冲突或明显节奏失衡才应 revise；"
                    "一般优化建议应保持 verdict=pass 并写入 suggestions。"
                    "只输出 JSON，不要使用 Markdown。输出必须符合以下 JSON Schema："
                    f"{json.dumps(ReviewResult.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"需求：{entities.model_dump_json()}\n"
                    f"偏好：{preferences.model_dump_json()}\n"
                    f"候选：{phase1.model_dump_json() if phase1 else '{}'}\n"
                    f"硬校验：{hard_validation.model_dump_json()}\n"
                    f"方案：{plan.model_dump_json()}"
                )
            ),
        ]
