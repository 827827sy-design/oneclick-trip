from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.clarification_agent import ClarificationAgent, RuleBasedClarificationAgent
from app.domain.models import Intent, NextAction, TravelEntities, UserPreferences
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
        "missing_fields": state.get("missing_fields") or ["intent"],
        "preferences": state.get("effective_preferences")
        or state.get("user_preferences")
        or UserPreferences(),
        "budget_feasibility": state.get("budget_feasibility"),
        "conversation_context": [
            f"{'user' if isinstance(message, HumanMessage) else 'assistant'}: {message.content}"
            for message in state.get("messages", [])[-20:]
            if isinstance(message, (HumanMessage, AIMessage))
        ],
    }


def _compose_patch(state: TravelState, reply) -> TravelStatePatch:
    del state
    return {
        "messages": [AIMessage(content=reply.message)],
        "clarification_reply": reply,
        "next_action": NextAction.ASK_USER,
    }
