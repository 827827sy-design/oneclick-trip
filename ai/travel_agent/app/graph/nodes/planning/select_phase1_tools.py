from app.domain.models import TravelEntities
from app.graph.state import TravelState, TravelStatePatch
from app.tools.selector import ToolSelector


def make_phase1_tool_selector_node(selector: ToolSelector):
    def select_phase1_tools(state: TravelState) -> TravelStatePatch:
        selected = selector.for_planning_phase1(
            state.get("entities") or TravelEntities()
        )
        names = [tool.value for tool in selected]
        return {"pending_tools": names, "selected_tools": names}

    return select_phase1_tools
