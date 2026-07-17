from app.graph.state import TravelState, TravelStatePatch
from app.tools.selector import ToolSelector


def make_phase2_tool_selector_node(selector: ToolSelector):
    def select_phase2_tools(_: TravelState) -> TravelStatePatch:
        names = [tool.value for tool in selector.for_planning_phase2()]
        return {"pending_tools": names, "selected_tools": names}

    return select_phase2_tools
