from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.clarification_agent import ClarificationAgent, RuleBasedClarificationAgent
from app.domain.models import (
    ClarificationAction,
    Intent,
    NextAction,
    TravelEntities,
    UserPreferences,
)
from app.graph.state import TravelState, TravelStatePatch

def ask_user(state: TravelState) -> TravelStatePatch:
    return _compose_patch(state, RuleBasedClarificationAgent().compose(**_agent_input(state)))


def make_ask_user_node(
    agent: ClarificationAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def compose(state: TravelState) -> TravelStatePatch:
        return _compose_patch(state, agent.compose(**_agent_input(state)))

    async def acompose(state: TravelState) -> TravelStatePatch:
        return _compose_patch(state, await agent.acompose(**_agent_input(state)))

    return RunnableLambda(compose, afunc=acompose, name="ask_user")


def _agent_input(state: TravelState) -> dict:
    user_message = next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )
    return {
        "user_message": user_message,
        "intent": state.get("intent", Intent.UNKNOWN),
        "entities": state.get("entities") or TravelEntities(),
        "missing_fields": _active_missing_fields(state),
        "preferences": state.get("effective_preferences")
        or state.get("user_preferences")
        or UserPreferences(),
        "budget_feasibility": state.get("budget_feasibility"),
        "budget_estimate": state.get("budget_estimate"),
        "conversation_context": [
            f"{'user' if isinstance(message, HumanMessage) else 'assistant'}: {message.content}"
            for message in state.get("messages", [])[-20:]
            if isinstance(message, (HumanMessage, AIMessage))
        ],
    }


def _active_missing_fields(state: TravelState) -> list[str]:
    missing_fields = state.get("missing_fields") or ["intent"]
    return missing_fields[:1]


def _compose_patch(state: TravelState, reply) -> TravelStatePatch:
    choice_prompt, actions = _clarification_actions(state)
    reply = reply.model_copy(
        update={
            "choice_prompt": choice_prompt,
            "actions": actions,
        }
    )
    return {
        "messages": [AIMessage(content=reply.message)],
        "clarification_reply": reply,
        "next_action": NextAction.ASK_USER,
    }


def _clarification_actions(
    state: TravelState,
) -> tuple[str | None, list[ClarificationAction]]:
    estimate = state.get("budget_estimate")
    if estimate is not None:
        return (
            "选一种预算方式，或直接输入其他金额",
            [
                _action(
                    "budget-survival",
                    "budget_confirmation",
                    f"极限穷游 ¥{estimate.survival.total}",
                    f"选择极限穷游方案，总预算{estimate.survival.total}元",
                    recommended=True,
                ),
                _action(
                    "budget-comfortable",
                    "budget_confirmation",
                    f"正常舒适 ¥{estimate.comfortable.total}",
                    f"选择正常舒适方案，总预算{estimate.comfortable.total}元",
                ),
            ],
        )

    feasibility = state.get("budget_feasibility")
    if feasibility is not None and not feasibility.feasible:
        return (
            "可以接受建议预算，也可以重新看两档估算",
            [
                _action(
                    "budget-accept-suggestion",
                    "budget",
                    f"调到 ¥{feasibility.suggested_budget}",
                    f"总预算调整到{feasibility.suggested_budget}元，继续规划",
                    recommended=True,
                ),
                _action(
                    "budget-estimate-again",
                    "budget",
                    "重新估算两档",
                    "请重新帮我估算极限穷游和正常舒适两档预算",
                ),
            ],
        )

    builders = {
        "destination": _destination_actions,
        "origin": _origin_actions,
        "duration": _duration_actions,
        "people": _people_actions,
        "budget": _budget_actions,
        "booking_type": _booking_type_actions,
        "intent": _intent_actions,
        "preference_update": _preference_update_actions,
    }
    prompts = {
        "destination": "先选一个目的地，也可以输入其他城市",
        "origin": "你准备从哪个城市出发？",
        "duration": "旅行准备玩几天？具体日期也可以直接输入",
        "people": "这次一共几个人出发？",
        "budget": "选一个总预算，也可以直接输入其他金额",
        "booking_type": "这次准备预订什么？",
        "intent": "这次想让我帮你做什么？",
        "preference_update": "想让我记住或调整什么旅行习惯吗？",
    }
    for field in state.get("missing_fields", []):
        builder = builders.get(field)
        if builder is not None:
            return prompts[field], builder()
    return None, []


def _destination_actions() -> list[ClarificationAction]:
    return [
        _action("destination-chengdu", "destination", "成都", "我想去成都"),
        _action("destination-xiamen", "destination", "厦门", "我想去厦门"),
        _action("destination-xian", "destination", "西安", "我想去西安"),
        _action("destination-dali", "destination", "大理", "我想去大理"),
    ]


def _duration_actions() -> list[ClarificationAction]:
    return [
        _action(f"duration-{days}", "duration", f"{days} 天", f"旅行玩{days}天")
        for days in (2, 3, 4, 5, 7)
    ]


def _people_actions() -> list[ClarificationAction]:
    return [
        _action(f"people-{people}", "people", f"{people} 人", f"一共{people}个人")
        for people in (1, 2, 3, 4)
    ]


def _budget_actions() -> list[ClarificationAction]:
    return [
        _action(
            "budget-auto-estimate",
            "budget",
            "帮我估算",
            "我还没想好预算，请帮我估算两档预算",
            recommended=True,
        ),
        *[
            _action(
                f"budget-{amount}",
                "budget",
                f"¥{amount:,}",
                f"总预算{amount}元",
            )
            for amount in (1500, 3000, 5000)
        ],
    ]


def _booking_type_actions() -> list[ClarificationAction]:
    return [
        _action("booking-hotel", "booking_type", "酒店", "帮我预订酒店"),
        _action("booking-train", "booking_type", "火车票", "帮我购买火车票"),
        _action("booking-flight", "booking_type", "机票", "帮我购买机票"),
        _action("booking-ticket", "booking_type", "景点门票", "帮我购买景点门票"),
    ]


def _origin_actions() -> list[ClarificationAction]:
    return [
        _action("origin-beijing", "origin", "北京", "我从北京出发"),
        _action("origin-shanghai", "origin", "上海", "我从上海出发"),
        _action("origin-guangzhou", "origin", "广州", "我从广州出发"),
        _action("origin-nanjing", "origin", "南京", "我从南京出发"),
        _action("origin-hangzhou", "origin", "杭州", "我从杭州出发"),
        _action("origin-shenzhen", "origin", "深圳", "我从深圳出发"),
    ]


def _preference_update_actions() -> list[ClarificationAction]:
    return [
        _action("pref-like-food", "preference_update", "喜欢美食", "记住：我喜欢美食，优先推荐本地特色"),
        _action("pref-like-nature", "preference_update", "喜欢自然风光", "记住：我喜欢自然风光，优先推荐户外景点"),
        _action("pref-like-slow", "preference_update", "喜欢慢节奏", "记住：我喜欢慢节奏，行程不要太赶"),
        _action("pref-dislike-crowded", "preference_update", "避开拥挤", "记住：我讨厌人多的地方，尽量避开"),
    ]


def _intent_actions() -> list[ClarificationAction]:
    return [
        _action("intent-plan", "intent", "规划完整行程", "帮我规划一次完整旅行"),
        _action("intent-weather", "intent", "查天气", "我想查询目的地天气"),
        _action("intent-hotel", "intent", "找酒店", "我想找合适的酒店"),
        _action("intent-transport", "intent", "比较交通", "我想比较火车和飞机"),
    ]


def _action(
    action_id: str,
    field: str,
    label: str,
    message: str,
    *,
    recommended: bool = False,
) -> ClarificationAction:
    return ClarificationAction(
        id=action_id,
        field=field,
        label=label,
        message=message,
        recommended=recommended,
    )
