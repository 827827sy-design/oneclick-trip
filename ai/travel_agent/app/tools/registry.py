from __future__ import annotations

from collections.abc import Mapping

from app.domain.models import ToolName, ToolResult
from app.tools.contracts import ToolContext, TravelTool


class ToolRegistry:
    def __init__(self, tools: Mapping[ToolName, TravelTool] | None = None) -> None:
        self._tools: dict[ToolName, TravelTool] = dict(tools or {})

    def register(self, name: ToolName, tool: TravelTool) -> None:
        self._tools[name] = tool

    def invoke(self, name: ToolName, context: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error_code="TOOL_NOT_REGISTERED",
                retryable=False,
            )
        try:
            return tool(context)
        except Exception as exc:  # Provider exceptions must not escape the graph.
            return ToolResult(
                success=False,
                data={"message": str(exc)},
                error_code="TOOL_UNHANDLED_EXCEPTION",
                retryable=False,
            )

    @property
    def names(self) -> frozenset[ToolName]:
        return frozenset(self._tools)

    @property
    def realtime_names(self) -> frozenset[ToolName]:
        return frozenset(
            name
            for name, tool in self._tools.items()
            if bool(getattr(tool, "is_realtime_provider", False))
        )
