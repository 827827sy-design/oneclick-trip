from __future__ import annotations

from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import (
    BudgetFeasibility,
    ClarificationReply,
    Intent,
    TravelEntities,
    UserPreferences,
)


FIELD_LABELS = {
    "destination": "想去哪里",
    "origin": "从哪里出发",
    "duration": "旅行天数或出发与返程日期",
    "people": "同行人数",
    "budget": "大概预算",
    "current_plan": "要修改的已有行程",
    "booking_type": "想预订酒店、交通还是门票",
    "selected_option_ids": "想预订的具体选项",
    "booking_draft": "待确认的订单草稿",
    "preference_update": "希望记住或删除的旅行偏好",
    "intent": "这次想咨询或办理什么",
}


class ClarificationAgent(Protocol):
    def compose(
        self,
        *,
        user_message: str,
        intent: Intent,
        entities: TravelEntities,
        missing_fields: list[str],
        preferences: UserPreferences,
        budget_feasibility: BudgetFeasibility | None = None,
        conversation_context: list[str] | None = None,
    ) -> ClarificationReply:
        """Create user-facing clarification copy without changing routing state."""

    async def acompose(self, **kwargs) -> ClarificationReply:
        """Asynchronous clarification copy generation."""


class RuleBasedClarificationAgent:
    """Availability fallback used only when no chat model can answer."""

    def compose(self, **kwargs) -> ClarificationReply:
        feasibility = kwargs.get("budget_feasibility")
        if feasibility is not None and not feasibility.feasible:
            destination = kwargs["entities"].destination or "这趟旅行"
            return ClarificationReply(
                kicker="预算可以再商量",
                title=f"{destination}行程差一点点",
                message=(
                    f"按目前的行程范围保守估算约需 {feasibility.estimated_minimum} 元，"
                    f"你现在的预算是 {feasibility.budget_limit} 元。"
                    f"想把预算调整到约 {feasibility.suggested_budget} 元，还是减少一些安排？"
                ),
            )
        missing_fields = kwargs["missing_fields"] or ["intent"]
        labels = [FIELD_LABELS.get(field, field) for field in missing_fields]
        destination = kwargs["entities"].destination
        return ClarificationReply(
            kicker="再了解你一点",
            title=f"{destination}已经记下啦" if destination else "先聊聊这次旅行",
            message="再告诉我" + "、".join(labels) + "，我就可以接着帮你规划。",
        )

    async def acompose(self, **kwargs) -> ClarificationReply:
        return self.compose(**kwargs)


class LangChainClarificationAgent:
    """Use a Flash-class model to write concise, contextual follow-up copy."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            ClarificationReply,
            method="function_calling",
            strict=True,
        )

    def compose(self, **kwargs) -> ClarificationReply:
        result = self._runner.invoke(self._messages(**kwargs))
        return (
            result
            if isinstance(result, ClarificationReply)
            else ClarificationReply.model_validate(result)
        )

    async def acompose(self, **kwargs) -> ClarificationReply:
        result = await self._runner.ainvoke(self._messages(**kwargs))
        return (
            result
            if isinstance(result, ClarificationReply)
            else ClarificationReply.model_validate(result)
        )

    @staticmethod
    def _messages(
        *,
        user_message: str,
        intent: Intent,
        entities: TravelEntities,
        missing_fields: list[str],
        preferences: UserPreferences,
        budget_feasibility: BudgetFeasibility | None = None,
        conversation_context: list[str] | None = None,
    ) -> list[SystemMessage | HumanMessage]:
        requested = [FIELD_LABELS.get(field, field) for field in missing_fields]
        return [
            SystemMessage(
                content=(
                    "你是一键游里亲切、自然、有分寸的旅行顾问。"
                    "始终用‘你’而不是‘您’，像熟悉旅行的朋友聊天，不要使用客服腔。"
                    "先轻轻复述用户已经说过的信息，再只询问代码判定缺少的内容，最多追问 3 项。"
                    "可以根据已知表达给出 2 至 4 个初步旅行标签，并明确这些标签随时可以修改。"
                    "不要说‘字段、补充信息、完整起止日期、校验、参数’，不要像表单提示。"
                    "已知目的地时，标题要自然地接住目的地；禁止使用‘先了解几个细节’、"
                    "‘还需要一点信息’、‘请补充’这类泛化标题。"
                    "正文最多两句，可以给简短回答示例。"
                    "不得自行增加缺失项，不要生成完整行程，也不得承诺已经查到尚未查询的数据。"
                    "如果给出了 budget_feasibility 且 feasible=false，不要再次询问当前预算是多少；"
                    "自然说明当前预算与保守估算之间的差额，再让用户选择提高预算或减少安排。"
                    "不得擅自把 suggested_budget 当成用户已经接受的预算。"
                )
            ),
            HumanMessage(
                content=(
                    f"用户刚才说：{user_message}\n"
                    f"识别意图：{intent.value}\n"
                    f"已知信息：{entities.model_dump_json()}\n"
                    f"长期偏好：{preferences.model_dump_json()}\n"
                    f"最近 20 轮对话：{conversation_context or []}\n"
                    f"预算评估：{budget_feasibility.model_dump_json() if budget_feasibility else '{}'}\n"
                    f"这次只需要询问：{requested}"
                )
            ),
        ]
