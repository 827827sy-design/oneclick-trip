from app.domain.models import Intent, TravelEntities
from app.graph.state import TravelState, TravelStatePatch
from app.tools.selector import ToolSelector


def make_query_tool_selector_node(selector: ToolSelector):
    def select_query_tools(state: TravelState) -> TravelStatePatch:
        selected = selector.for_query(
            state.get("intent", Intent.UNKNOWN),
            state.get("entities") or TravelEntities(),
        )
        names = [tool.value for tool in selected]
        return {"pending_tools": names, "selected_tools": names}

    return select_query_tools
