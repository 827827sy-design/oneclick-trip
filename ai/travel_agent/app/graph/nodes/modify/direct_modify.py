from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.direct_modify_agent import DirectModifyAgent
from app.domain.models import CandidateSelection, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def make_direct_modify_node(agent: DirectModifyAgent) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState) -> dict:
        return {
            "query": _latest_query(state),
            "conversation_id": state.get("conversation_id", "unknown"),
            "current_plan": state["current_plan"],
            "entities": state.get("entities") or TravelEntities(),
            "preferences": state.get("effective_preferences") or UserPreferences(),
            "conversation_context": [
                f"{'user' if isinstance(message, HumanMessage) else 'assistant'}: {message.content}"
                for message in state.get("messages", [])[-20:]
                if isinstance(message, (HumanMessage, AIMessage))
            ],
        }

    def modified_entities(state: TravelState) -> TravelEntities:
        entities = (state.get("entities") or TravelEntities()).model_copy(deep=True)
        analysis = state.get("modify_analysis")
        if analysis is None:
            return entities
        request = analysis.request
        if request.new_budget is not None:
            entities.budget = request.new_budget
        elif request.budget_delta is not None and entities.budget is not None:
            entities.budget = max(entities.budget + request.budget_delta, 0)
        return entities

    def patch(state: TravelState, plan) -> TravelStatePatch:
        return {
            "plan_draft": plan,
            "entities": modified_entities(state),
            "candidate_selection": CandidateSelection(
                selected_poi_ids=[
                    item.location_id
                    for day in plan.days
                    for item in day.items
                    if item.location_id
                ],
                reasons=["由大模型直接修改，未使用 Mock 研究工具。"],
            ),
            "phase1_research": None,
            "phase2_research": None,
            "modification_errors": [],
        }

    def modify(state: TravelState) -> TravelStatePatch:
        if state.get("current_plan") is None:
            return {"modification_errors": ["CURRENT_PLAN_MISSING"]}
        try:
            return patch(state, agent.modify(**arguments(state)))
        except (ValueError, KeyError) as error:
            return {"modification_errors": [str(error) or "DIRECT_MODIFICATION_FAILED"]}

    async def amodify(state: TravelState) -> TravelStatePatch:
        if state.get("current_plan") is None:
            return {"modification_errors": ["CURRENT_PLAN_MISSING"]}
        try:
            return patch(state, await agent.amodify(**arguments(state)))
        except (ValueError, KeyError) as error:
            return {"modification_errors": [str(error) or "DIRECT_MODIFICATION_FAILED"]}

    return RunnableLambda(modify, afunc=amodify, name="direct_modify")


def _latest_query(state: TravelState) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )
