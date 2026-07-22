from __future__ import annotations

from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    BudgetMode,
    Phase1Research,
    ReviewResult,
    ToolResult,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)


class PlanVoice(BaseModel):
    """Non-factual copy slots; itinerary facts are rendered by code."""

    model_config = ConfigDict(extra="forbid")
    opening: str = Field(min_length=1, max_length=100)
    preference_note: str = Field(default="", max_length=100)


class PlanPresenterAgent(Protocol):
    def present(
        self,
        *,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        review: ReviewResult,
        revision_count: int,
        tool_results: dict[str, ToolResult],
        phase1: Phase1Research | None = None,
    ) -> str:
        """Present a validated and persisted plan to the user."""

    async def apresent(self, **kwargs) -> str:
        """Asynchronous final presentation."""


class LangChainPlanPresenterAgent:
    """Pro-class final presenter grounded in the saved plan."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(PlanVoice, method="json_mode")

    def present(self, **kwargs) -> str:
        result = self._runner.invoke(self._messages(**kwargs))
        voice = result if isinstance(result, PlanVoice) else PlanVoice.model_validate(result)
        return self._render(voice=voice, **kwargs)

    async def apresent(self, **kwargs) -> str:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        voice = result if isinstance(result, PlanVoice) else PlanVoice.model_validate(result)
        return self._render(voice=voice, **kwargs)

    @staticmethod
    def _messages(
        *,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        review: ReviewResult,
        revision_count: int,
        tool_results: dict[str, ToolResult],
        phase1: Phase1Research | None = None,
    ) -> list[SystemMessage | HumanMessage]:
        del review, revision_count, tool_results, phase1
        return [
            SystemMessage(
                content=(
                    "你负责给已完成的旅行方案写两句自然中文，不负责复述行程事实。"
                    "opening 表达方案已经准备好及整体感觉；preference_note 只说明它如何照顾给定偏好。"
                    "不得加入任何景点、人物、动物昵称、菜名、酒店、交通、价格、日期、引用或预订信息。"
                    "不要使用您好、祝旅途愉快等客服套话，不要用 Markdown。只输出 JSON。"
                )
            ),
            HumanMessage(
                content=(
                    f"目的地：{plan.destination}\n"
                    f"天数：{len(plan.days)}\n"
                    f"明确需求：{entities.explicit_preferences}\n"
                    f"明确不喜欢：{entities.explicit_dislikes}\n"
                    f"有效偏好：{preferences.model_dump_json()}"
                )
            ),
        ]

    @staticmethod
    def _render(
        *,
        voice: PlanVoice,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        review: ReviewResult,
        revision_count: int,
        tool_results: dict[str, ToolResult],
        phase1: Phase1Research | None = None,
    ) -> str:
        del preferences
        lines = [voice.opening.strip()]
        if voice.preference_note.strip():
            lines.append(voice.preference_note.strip())
        lines.extend(_research_summary(plan, phase1, entities))
        for day in plan.days:
            lines.extend(_day_summary(day))
        lines.append(
            f"预估总费用约 {plan.total_cost} {plan.currency}，体验评分 {review.score}/100。"
        )
        if revision_count:
            lines.append(f"这份方案已自动优化 {revision_count} 次。")
        if any(
            result.data.get("data_mode") in {"MOCK", "DEMO"}
            for result in tool_results.values()
            if result.success
        ):
            lines.append(
                "天气来自演示接口，其余行程来自 AI 通用知识建议；价格、营业时间和余量请在出行前核实。"
            )
        else:
            lines.append("行程来自 AI 通用知识建议，不是实时搜索；价格、营业时间和余量请在出行前核实。")
        return "\n".join(lines)


class RuleBasedPlanPresenterAgent:
    """Deterministic final presenter used when no model is configured."""

    def present(
        self,
        *,
        plan: TravelPlan,
        entities: TravelEntities,
        preferences: UserPreferences,
        review: ReviewResult,
        revision_count: int,
        tool_results: dict[str, ToolResult],
        phase1: Phase1Research | None = None,
    ) -> str:
        del preferences
        lines = [f"已经为你整理好 {plan.destination} {len(plan.days)} 天行程。"]
        lines.extend(_research_summary(plan, phase1, entities))
        for day in plan.days:
            lines.extend(_day_summary(day))
        lines.append(f"预估总费用约 {plan.total_cost} {plan.currency}，体验评分 {review.score}/100。")
        if revision_count:
            lines.append(f"方案已自动优化 {revision_count} 次。")
        if any(
            result.data.get("data_mode") in {"MOCK", "DEMO"}
            for result in tool_results.values()
            if result.success
        ):
            lines.append(
                "天气来自演示接口，其余行程来自 AI 通用知识建议；价格、营业时间和余量请在出行前核实。"
            )
        else:
            lines.append("行程来自 AI 通用知识建议，不是实时搜索；价格、营业时间和余量请在出行前核实。")
        return "\n".join(lines)

    async def apresent(self, **kwargs) -> str:
        return self.present(**kwargs)


def _research_summary(
    plan: TravelPlan,
    phase1: Phase1Research | None,
    entities: TravelEntities,
) -> list[str]:
    if phase1 is None:
        return []
    lines: list[str] = []
    area = next(
        (item for item in phase1.hotel_areas if item.area_id == plan.hotel_area_id),
        None,
    )
    if area is not None:
        if entities.budget_mode is BudgetMode.MINIMIZE:
            lines.append(
                f"住宿区域：{area.name}。{area.reason} "
                "本方案按青旅床位或同级最低价住宿核算。"
            )
        else:
            lines.append(
                f"住宿区域：{area.name}。{area.reason} "
                f"普通住宿参考约 {area.nightly_price_hint} 元/晚。"
            )
    transport = next(
        (
            item
            for item in phase1.transport_options
            if item.option_id == plan.transport_option_id
        ),
        None,
    )
    if transport is not None:
        lines.append(
            f"城际交通：{transport.name}，预计约 {transport.duration_minutes} 分钟，"
            f"参考约 {transport.price} 元/人。"
        )
    if phase1.weather_summary:
        lines.append(f"天气参考：{phase1.weather_summary}")
    if phase1.research_sources:
        official_count = sum(
            source.source_tier == "official" for source in phase1.research_sources
        )
        evidence_label = (
            "知识库依据" if phase1.data_mode == "RAG_HYBRID" else "联网依据"
        )
        lines.append(
            f"{evidence_label}：参考 {len(phase1.research_sources)} 个来源，"
            f"其中官方来源 {official_count} 个；未交叉验证的数据仍需出发前确认。"
        )
        for source in phase1.research_sources[:3]:
            lines.append(f"资料来源：{source.title}（{source.url}）")
        xiaohongshu_count = sum(
            source.source_tier == "community"
            and "xiaohongshu.com" in source.url
            for source in phase1.research_sources
        )
        if xiaohongshu_count:
            lines.append(
                f"小红书经验：已参考 {xiaohongshu_count} 篇笔记，"
                "仅用于补充真实体验和节奏建议，不替代官方信息。"
            )
    return lines


def _day_summary(day) -> list[str]:
    names = "、".join(item.name for item in day.items) or "自由活动与休息"
    return [f"第 {day.day_index} 天：{names}"]
