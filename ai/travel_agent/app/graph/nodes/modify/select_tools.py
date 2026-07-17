from app.graph.state import TravelState, TravelStatePatch
from app.tools.selector import ToolSelector


def make_modify_discovery_selector_node(selector: ToolSelector):
    def select_discovery(state: TravelState) -> TravelStatePatch:
        analysis = state.get("modify_analysis")
        selected = selector.for_modify_discovery(
            analysis.discovery_tools if analysis else []
        )
        names = [tool.value for tool in selected]
        return {"pending_tools": names, "selected_tools": names}

    return select_discovery


def make_modify_dependency_selector_node(selector: ToolSelector):
    def select_dependencies(state: TravelState) -> TravelStatePatch:
        analysis = state.get("modify_analysis")
        selected = selector.for_modify_dependencies(
            analysis.dependent_tools if analysis else []
        )
        names = [tool.value for tool in selected]
        return {"pending_tools": names, "selected_tools": names}

    return select_dependencies
