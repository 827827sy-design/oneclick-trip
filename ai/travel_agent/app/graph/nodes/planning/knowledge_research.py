from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.research_agent import Phase1ResearchAgent, Phase2ResearchAgent
from app.domain.models import ToolName, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor


def make_phase1_research_node(
    agent: Phase1ResearchAgent,
    executor: ToolExecutor,
) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState, weather_summary: str) -> dict:
        return {
            "entities": state.get("entities") or TravelEntities(),
            "preferences": state.get("effective_preferences") or UserPreferences(),
            "weather_summary": weather_summary,
        }

    def weather(state: TravelState):
        entities = state.get("entities") or TravelEntities()
        outcome = executor.execute(
            ToolName.WEATHER,
            ToolContext(
                entities=entities,
                preferences=state.get("effective_preferences") or UserPreferences(),
            ),
        )
        summary = (
            str(outcome.result.data.get("summary", "天气信息待核实"))
            if outcome.result.success
            else "天气接口暂不可用，出行前请重新查询"
        )
        return outcome, summary

    def patch(research, outcome) -> TravelStatePatch:
        return {
            "phase1_research": research,
            "selected_tools": [ToolName.WEATHER.value],
            "tool_results": {ToolName.WEATHER.value: outcome.result},
            "tool_errors": outcome.errors,
            "tool_attempts": {ToolName.WEATHER.value: outcome.attempts},
            "tool_abort_requested": False,
            "planning_errors": [],
        }

    def research(state: TravelState) -> TravelStatePatch:
        outcome, summary = weather(state)
        return patch(agent.research(**arguments(state, summary)), outcome)

    async def aresearch(state: TravelState) -> TravelStatePatch:
        outcome, summary = weather(state)
        return patch(await agent.aresearch(**arguments(state, summary)), outcome)

    return RunnableLambda(research, afunc=aresearch, name="phase1_research")


def make_phase2_research_node(
    agent: Phase2ResearchAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState) -> dict:
        return {
            "entities": state.get("entities") or TravelEntities(),
            "phase1": state["phase1_research"],
            "selection": state["candidate_selection"],
        }

    def research(state: TravelState) -> TravelStatePatch:
        if not state.get("phase1_research") or not state.get("candidate_selection"):
            return {"planning_errors": ["PHASE2_INPUT_MISSING"]}
        return {"phase2_research": agent.research(**arguments(state))}

    async def aresearch(state: TravelState) -> TravelStatePatch:
        if not state.get("phase1_research") or not state.get("candidate_selection"):
            return {"planning_errors": ["PHASE2_INPUT_MISSING"]}
        return {"phase2_research": await agent.aresearch(**arguments(state))}

    return RunnableLambda(research, afunc=aresearch, name="phase2_research")
