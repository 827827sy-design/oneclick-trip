import asyncio

from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.research_agent import Phase1ResearchAgent, Phase2ResearchAgent
from app.domain.models import (
    RouteLeg,
    ToolDataMode,
    ToolName,
    TravelEntities,
    UserPreferences,
)
from app.graph.state import TravelState, TravelStatePatch
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor
from app.tools.provider_tools import apply_verified_coordinates
from app.graph.tool_runtime import context_from_state


def make_phase1_research_node(
    agent: Phase1ResearchAgent,
    executor: ToolExecutor,
) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(
        state: TravelState,
        weather_summary: str,
        research_context: dict | None,
    ) -> dict:
        return {
            "entities": state.get("entities") or TravelEntities(),
            "preferences": state.get("effective_preferences") or UserPreferences(),
            "weather_summary": weather_summary,
            "research_context": research_context,
        }

    def execute_tools(state: TravelState):
        context = context_from_state(state)
        outcome = executor.execute(ToolName.WEATHER, context)
        summary = (
            str(outcome.result.data.get("summary", "天气信息待核实"))
            if outcome.result.success
            else "天气接口暂不可用，出行前请重新查询"
        )
        knowledge_outcome = (
            executor.execute(ToolName.KNOWLEDGE_SEARCH, context)
            if ToolName.KNOWLEDGE_SEARCH in executor.available_tools
            else None
        )
        return outcome, summary, knowledge_outcome

    def enrich_coordinates(state: TravelState, research):
        if ToolName.POI_COORDINATES not in executor.realtime_tools:
            return research, None
        coordinate_outcome = executor.execute(
            ToolName.POI_COORDINATES,
            ToolContext(
                entities=state.get("entities") or TravelEntities(),
                preferences=state.get("effective_preferences") or UserPreferences(),
                phase1_research=research,
            ),
        )
        return (
            apply_verified_coordinates(research, coordinate_outcome.result),
            coordinate_outcome,
        )

    def patch(research, outcome, coordinate_outcome, knowledge_outcome) -> TravelStatePatch:
        selected_tools = [ToolName.WEATHER.value]
        results = {ToolName.WEATHER.value: outcome.result}
        errors = list(outcome.errors)
        attempts = {ToolName.WEATHER.value: outcome.attempts}
        if knowledge_outcome is not None:
            selected_tools.append(ToolName.KNOWLEDGE_SEARCH.value)
            results[ToolName.KNOWLEDGE_SEARCH.value] = knowledge_outcome.result
            errors.extend(knowledge_outcome.errors)
            attempts[ToolName.KNOWLEDGE_SEARCH.value] = knowledge_outcome.attempts
        if coordinate_outcome is not None:
            selected_tools.append(ToolName.POI_COORDINATES.value)
            results[ToolName.POI_COORDINATES.value] = coordinate_outcome.result
            errors.extend(coordinate_outcome.errors)
            attempts[ToolName.POI_COORDINATES.value] = coordinate_outcome.attempts
        return {
            "phase1_research": research,
            "selected_tools": selected_tools,
            "tool_results": results,
            "tool_errors": errors,
            "tool_attempts": attempts,
            "tool_abort_requested": False,
            "planning_errors": [],
        }

    def research(state: TravelState) -> TravelStatePatch:
        outcome, summary, knowledge_outcome = execute_tools(state)
        research_context = (
            knowledge_outcome.result.data
            if knowledge_outcome is not None and knowledge_outcome.result.success
            else None
        )
        phase1 = agent.research(**arguments(state, summary, research_context))
        phase1, coordinate_outcome = enrich_coordinates(state, phase1)
        return patch(phase1, outcome, coordinate_outcome, knowledge_outcome)

    async def aresearch(state: TravelState) -> TravelStatePatch:
        context = context_from_state(state)
        weather_task = executor.aexecute(ToolName.WEATHER, context)
        knowledge_task = (
            executor.aexecute(ToolName.KNOWLEDGE_SEARCH, context)
            if ToolName.KNOWLEDGE_SEARCH in executor.available_tools
            else None
        )
        if knowledge_task is None:
            outcome = await weather_task
            knowledge_outcome = None
        else:
            outcome, knowledge_outcome = await asyncio.gather(
                weather_task,
                knowledge_task,
            )
        summary = (
            str(outcome.result.data.get("summary", "天气信息待核实"))
            if outcome.result.success
            else "天气接口暂不可用，出行前请重新查询"
        )
        research_context = (
            knowledge_outcome.result.data
            if knowledge_outcome is not None and knowledge_outcome.result.success
            else None
        )
        phase1 = await agent.aresearch(**arguments(state, summary, research_context))
        if ToolName.POI_COORDINATES in executor.realtime_tools:
            coordinate_outcome = await executor.aexecute(
                ToolName.POI_COORDINATES,
                ToolContext(
                    entities=state.get("entities") or TravelEntities(),
                    preferences=state.get("effective_preferences") or UserPreferences(),
                    phase1_research=phase1,
                ),
            )
            phase1 = apply_verified_coordinates(phase1, coordinate_outcome.result)
        else:
            coordinate_outcome = None
        return patch(phase1, outcome, coordinate_outcome, knowledge_outcome)

    return RunnableLambda(research, afunc=aresearch, name="phase1_research")


def make_phase2_research_node(
    agent: Phase2ResearchAgent,
    executor: ToolExecutor,
) -> Runnable[TravelState, TravelStatePatch]:
    def arguments(state: TravelState) -> dict:
        return {
            "entities": state.get("entities") or TravelEntities(),
            "phase1": state["phase1_research"],
            "selection": state["candidate_selection"],
        }

    def enrich_with_route(state: TravelState, research) -> TravelStatePatch:
        if ToolName.ROUTE_MATRIX not in executor.realtime_tools:
            return {"phase2_research": research}
        outcome = executor.execute(
            ToolName.ROUTE_MATRIX,
            ToolContext(
                entities=state.get("entities") or TravelEntities(),
                preferences=state.get("effective_preferences") or UserPreferences(),
                phase1_research=state.get("phase1_research"),
                candidate_selection=state.get("candidate_selection"),
            ),
        )
        if (
            outcome.result.success
            and outcome.result.data_mode is ToolDataMode.REALTIME
            and outcome.result.data.get("route_legs")
        ):
            research = research.model_copy(
                update={
                    "data_mode": "MIXED_REALTIME_AI",
                    "route_legs": [
                        RouteLeg.model_validate(leg)
                        for leg in outcome.result.data["route_legs"]
                    ],
                }
            )
        return {
            "phase2_research": research,
            "selected_tools": [ToolName.ROUTE_MATRIX.value],
            "tool_results": {ToolName.ROUTE_MATRIX.value: outcome.result},
            "tool_errors": outcome.errors,
            "tool_attempts": {ToolName.ROUTE_MATRIX.value: outcome.attempts},
        }

    def research(state: TravelState) -> TravelStatePatch:
        if not state.get("phase1_research") or not state.get("candidate_selection"):
            return {"planning_errors": ["PHASE2_INPUT_MISSING"]}
        return enrich_with_route(state, agent.research(**arguments(state)))

    async def aresearch(state: TravelState) -> TravelStatePatch:
        if not state.get("phase1_research") or not state.get("candidate_selection"):
            return {"planning_errors": ["PHASE2_INPUT_MISSING"]}
        phase2_task = agent.aresearch(**arguments(state))
        if ToolName.ROUTE_MATRIX not in executor.realtime_tools:
            return {"phase2_research": await phase2_task}
        route_task = executor.aexecute(
            ToolName.ROUTE_MATRIX,
            ToolContext(
                entities=state.get("entities") or TravelEntities(),
                preferences=state.get("effective_preferences") or UserPreferences(),
                phase1_research=state.get("phase1_research"),
                candidate_selection=state.get("candidate_selection"),
            ),
        )
        research, outcome = await asyncio.gather(phase2_task, route_task)
        if (
            outcome.result.success
            and outcome.result.data_mode is ToolDataMode.REALTIME
            and outcome.result.data.get("route_legs")
        ):
            research = research.model_copy(
                update={
                    "data_mode": "MIXED_REALTIME_AI",
                    "route_legs": [
                        RouteLeg.model_validate(leg)
                        for leg in outcome.result.data["route_legs"]
                    ],
                }
            )
        return {
            "phase2_research": research,
            "selected_tools": [ToolName.ROUTE_MATRIX.value],
            "tool_results": {ToolName.ROUTE_MATRIX.value: outcome.result},
            "tool_errors": outcome.errors,
            "tool_attempts": {ToolName.ROUTE_MATRIX.value: outcome.attempts},
        }

    return RunnableLambda(research, afunc=aresearch, name="phase2_research")
