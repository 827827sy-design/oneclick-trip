from __future__ import annotations

import json
import re
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import Intent, ToolName, ToolResult, TravelEntities


class QueryPresenterAgent(Protocol):
    def present(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        """Turn grounded tool data into a direct user-facing answer."""

    async def apresent(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        """Asynchronous result presentation."""


class LangChainQueryPresenterAgent:
    """Flash-class presenter for narrow information queries."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def present(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        reply = self._content(
            self._model.invoke(
                self._messages(query, intent, entities, results, conversation_context)
            )
        )
        self._validate_grounding(reply, results)
        return reply

    async def apresent(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        response = await self._model.ainvoke(
            self._messages(query, intent, entities, results, conversation_context)
        )
        reply = self._content(response)
        self._validate_grounding(reply, results)
        return reply

    @staticmethod
    def _messages(
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> list[SystemMessage | HumanMessage]:
        successful = {
            name: result.model_dump(mode="json")
            for name, result in results.items()
            if result.success
        }
        source_rule = (
            "当前有接口结果时只能依据结果回答，不得补造任何事实。"
            if successful
            else (
                "当前没有调用数据接口，请直接使用你的通用知识回答。必须明确说明这是 AI 知识建议，"
                "不是实时搜索；不得编造实时价格、余量、班次、营业状态或预订结果。"
            )
        )
        return [
            SystemMessage(
                content=(
                    "你是一键游的旅行咨询 Agent。只回答用户当前的单项问题，不要强行生成完整行程，"
                    "也不要追问与本次查询无关的预算、人数或旅行天数。"
                    f"{source_rule}"
                    "数据模式为 MOCK/DEMO 时，只针对该接口结果说明这是演示数据。"
                    "保留用户原话中的相对日期；工具结果没有具体日期时，绝不能自行换算或补充年月日。"
                    "回答使用自然、简洁的中文，先给结论，再列两三条有用信息；不要提内部节点、JSON 或工具名。"
                )
            ),
            HumanMessage(
                content=(
                    f"意图：{intent.value}\n"
                    f"用户原始问题：{query}\n"
                    f"查询条件：{entities.model_dump_json()}\n"
                    f"最近 20 轮对话：{conversation_context or []}\n"
                    f"可用结果：{successful}"
                )
            ),
        ]

    @staticmethod
    def _content(response) -> str:
        content = response.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise ValueError("query presenter returned empty content")

    @staticmethod
    def _validate_grounding(reply: str, results: dict[str, ToolResult]) -> None:
        """Reject concrete dates that are absent from every tool result."""
        if not any(result.success for result in results.values()):
            return
        dates = re.findall(r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日", reply)
        if not dates:
            return
        source = json.dumps(
            {
                name: result.data
                for name, result in results.items()
                if result.success
            },
            ensure_ascii=False,
        )
        if any(date not in source for date in dates):
            raise ValueError("query presenter introduced an ungrounded date")


class RuleBasedQueryPresenterAgent:
    """Grounded deterministic fallback for query presentation."""

    def present(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        del conversation_context
        if not results:
            return (
                "当前没有可用的大模型回答，且我没有使用 Mock 景点、交通或酒店数据。"
                "请确认 DeepSeek 服务后再试。"
            )
        del query, entities
        if intent is Intent.WEATHER_QUERY:
            return self._weather(results)
        if intent is Intent.HOTEL_QUERY:
            return self._hotel(results)
        if intent is Intent.TRANSPORT_QUERY:
            return self._transport(results)
        return self._poi(results)

    async def apresent(
        self,
        query: str,
        intent: Intent,
        entities: TravelEntities,
        results: dict[str, ToolResult],
        conversation_context: list[str] | None = None,
    ) -> str:
        return self.present(query, intent, entities, results, conversation_context)

    @staticmethod
    def _weather(results: dict[str, ToolResult]) -> str:
        result = results.get(ToolName.WEATHER.value)
        if not result or not result.success:
            return "暂时没有可用的天气信息，请稍后再试。"
        mode = result.data.get("data_mode", "DEMO")
        return f"以下是{mode}演示数据：{result.data.get('summary', '暂无天气摘要')}"

    @staticmethod
    def _hotel(results: dict[str, ToolResult]) -> str:
        result = results.get(ToolName.HOTEL_SEARCH.value)
        if not result or not result.success:
            return "暂时没有可用的住宿区域信息，请稍后再试。"
        lines = ["以下是 MOCK 演示数据，住宿区域可以优先看看："]
        lines.extend(
            f"- {area['name']}：{area['reason']}，参考每晚 {area['nightly_price_hint']} 元"
            for area in result.data.get("areas", [])
        )
        return "\n".join(lines)

    @staticmethod
    def _transport(results: dict[str, ToolResult]) -> str:
        options = []
        for tool in (ToolName.TRAIN_SEARCH, ToolName.FLIGHT_SEARCH):
            result = results.get(tool.value)
            if result and result.success:
                options.extend(result.data.get("options", []))
        if not options:
            return "暂时没有可用的城际交通方案，请稍后再试。"
        lines = ["以下是 MOCK 演示数据，交通方案可以这样比较："]
        lines.extend(
            f"- {option['name']}：约 {option['duration_minutes']} 分钟，参考价 {option['price']} 元"
            for option in options
        )
        return "\n".join(lines)

    @staticmethod
    def _poi(results: dict[str, ToolResult]) -> str:
        result = results.get(ToolName.POI_SEARCH.value)
        if not result or not result.success:
            return "暂时没有可用的景点信息，请稍后再试。"
        lines = ["以下是 MOCK 演示数据，可以先关注这些地方："]
        lines.extend(
            f"- {poi['name']}：{', '.join(poi.get('tags', []))}"
            for poi in result.data.get("candidates", [])[:5]
        )
        return "\n".join(lines)
