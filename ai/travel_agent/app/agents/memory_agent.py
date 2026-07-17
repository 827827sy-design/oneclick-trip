from __future__ import annotations

import json
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    MemoryExtraction,
    MemoryOperation,
    TravelEntities,
    UserPreferences,
)


class MemoryCandidateAgent(Protocol):
    def extract(
        self,
        query: str,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> MemoryExtraction:
        """Extract only stable, non-sensitive long-term travel memories."""

    async def aextract(self, **kwargs) -> MemoryExtraction:
        """Asynchronous memory extraction."""


class LangChainMemoryCandidateAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(MemoryExtraction, method="json_mode")

    def extract(self, query, entities, preferences) -> MemoryExtraction:
        result = self._runner.invoke(self._messages(query, entities, preferences))
        return result if isinstance(result, MemoryExtraction) else MemoryExtraction.model_validate(result)

    async def aextract(self, query, entities, preferences) -> MemoryExtraction:
        result = await self._runner.ainvoke(self._messages(query, entities, preferences))
        return result if isinstance(result, MemoryExtraction) else MemoryExtraction.model_validate(result)

    @staticmethod
    def _messages(
        query: str,
        entities: TravelEntities,
        preferences: UserPreferences,
    ) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(
                content=(
                    "你是长期旅游记忆提取 Agent，只输出 JSON，不要 Markdown。"
                    "只保存跨多次旅行仍有价值的稳定习惯，例如‘我通常喜欢睡到自然醒’、"
                    "‘我不吃辣’、‘以后优先高铁’。一次性的目的地、日期、人数和本次预算不是长期记忆；"
                    "‘这次想住五星酒店’不能推断为永久偏好。用户说‘忘掉、不再、改成’时生成 delete 或覆盖操作。"
                    "禁止保存身份证、手机号、支付信息、密码、健康等敏感信息。没有可靠候选时 operations 为空数组。"
                    "upsert 的 confidence 只有在用户明确表达稳定习惯或多次重复时才能达到 0.85。"
                    "输出必须符合以下 JSON Schema："
                    f"{json.dumps(MemoryExtraction.model_json_schema(), ensure_ascii=False)}"
                )
            ),
            HumanMessage(
                content=(
                    f"当前请求：{query}\n"
                    f"当前状态：{entities.model_dump_json()}\n"
                    f"已有记忆：{preferences.model_dump_json()}"
                )
            ),
        ]


class RuleBasedMemoryCandidateAgent:
    def extract(self, query, entities, preferences) -> MemoryExtraction:
        del preferences
        stable = any(
            marker in query
            for marker in ("以后", "通常", "一直", "每次", "总是", "习惯", "优先")
        )
        if not stable:
            return MemoryExtraction()
        operations = [
            MemoryOperation(
                action="upsert",
                category="tag",
                key=tag,
                value=tag,
                confidence=0.95,
                evidence=query,
                source="explicit",
            )
            for tag in entities.explicit_preferences
        ]
        operations.extend(
            MemoryOperation(
                action="upsert",
                category="avoidance",
                key=tag,
                value=tag,
                confidence=0.95,
                evidence=query,
                source="explicit",
            )
            for tag in entities.explicit_dislikes
        )
        return MemoryExtraction(operations=operations)

    async def aextract(self, query, entities, preferences) -> MemoryExtraction:
        return self.extract(query, entities, preferences)
