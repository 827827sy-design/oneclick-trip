from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.modify_agent import ModifyAnalyzerAgent
from app.domain.models import TravelEntities
from app.graph.state import TravelState, TravelStatePatch


def make_modify_analysis_node(
    agent: ModifyAnalyzerAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def query_from(state: TravelState) -> str:
        return next(
            (
                str(message.content)
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage)
            ),
            "",
        )

    def analyze(state: TravelState) -> TravelStatePatch:
        current = state.get("current_plan")
        if current is None:
            return {"modification_errors": ["CURRENT_PLAN_MISSING"]}
        return {
            "modify_analysis": agent.analyze(
                query_from(state),
                current,
                state.get("entities") or TravelEntities(),
            )
        }

    async def aanalyze(state: TravelState) -> TravelStatePatch:
        current = state.get("current_plan")
        if current is None:
            return {"modification_errors": ["CURRENT_PLAN_MISSING"]}
        return {
            "modify_analysis": await agent.aanalyze(
                query_from(state),
                current,
                state.get("entities") or TravelEntities(),
            )
        }

    return RunnableLambda(analyze, afunc=aanalyze, name="analyze_modification")
