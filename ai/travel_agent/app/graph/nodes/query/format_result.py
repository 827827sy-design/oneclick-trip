from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.query_presenter import QueryPresenterAgent
from app.domain.models import Intent, NextAction, TravelEntities
from app.graph.state import TravelState, TravelStatePatch


def make_format_query_result_node(
    agent: QueryPresenterAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def guard(state: TravelState) -> TravelStatePatch | None:
        if state.get("tool_abort_requested"):
            return {
                "next_action": NextAction.ABORT,
                "messages": [AIMessage(content="查询服务暂时不可用，请稍后再试。")],
            }
        return None

    def format_result(state: TravelState) -> TravelStatePatch:
        blocked = guard(state)
        if blocked:
            return blocked
        reply = agent.present(
            _latest_query(state),
            state.get("intent", Intent.UNKNOWN),
            state.get("entities") or TravelEntities(),
            state.get("tool_results", {}),
            _conversation_context(state),
        )
        return {"messages": [AIMessage(content=reply)]}

    async def aformat_result(state: TravelState) -> TravelStatePatch:
        blocked = guard(state)
        if blocked:
            return blocked
        reply = await agent.apresent(
            _latest_query(state),
            state.get("intent", Intent.UNKNOWN),
            state.get("entities") or TravelEntities(),
            state.get("tool_results", {}),
            _conversation_context(state),
        )
        return {"messages": [AIMessage(content=reply)]}

    return RunnableLambda(
        format_result,
        afunc=aformat_result,
        name="format_query_result",
    )


def _latest_query(state: TravelState) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def _conversation_context(state: TravelState) -> list[str]:
    return [
        f"{'user' if isinstance(message, HumanMessage) else 'assistant'}: {message.content}"
        for message in state.get("messages", [])[-20:]
        if isinstance(message, (HumanMessage, AIMessage))
    ]
