from __future__ import annotations

from app.domain.models import Intent, ToolName, TravelEntities


INTENT_TOOL_ALLOWLIST: dict[Intent, frozenset[ToolName]] = {
    Intent.WEATHER_QUERY: frozenset({ToolName.WEATHER}),
    Intent.HOTEL_QUERY: frozenset(),
    Intent.TRANSPORT_QUERY: frozenset(),
    Intent.GENERAL_QA: frozenset(),
}

PHASE1_TOOL_ALLOWLIST: frozenset[ToolName] = frozenset()
PHASE2_TOOL_ALLOWLIST: frozenset[ToolName] = frozenset()
MODIFY_DISCOVERY_ALLOWLIST: frozenset[ToolName] = frozenset()
MODIFY_DEPENDENT_ALLOWLIST: frozenset[ToolName] = frozenset()


class ToolSelector:
    """Code-owned tool selection; model suggestions are advisory only."""

    def for_query(
        self,
        intent: Intent,
        entities: TravelEntities,
        requested_tools: list[str] | None = None,
    ) -> list[ToolName]:
        allowed = INTENT_TOOL_ALLOWLIST.get(intent, frozenset())
        defaults = sorted(allowed, key=str)
        selected = self._filter(requested_tools, allowed) if requested_tools else defaults
        if intent is Intent.TRANSPORT_QUERY and not entities.origin:
            return []
        return selected

    def for_planning_phase1(
        self,
        entities: TravelEntities,
        requested_tools: list[str] | None = None,
    ) -> list[ToolName]:
        del entities, requested_tools
        return []

    def for_planning_phase2(
        self,
        requested_tools: list[str] | None = None,
    ) -> list[ToolName]:
        del requested_tools
        return []

    def for_modify_discovery(
        self,
        requested_tools: list[ToolName | str],
    ) -> list[ToolName]:
        return self._filter(
            [str(name) for name in requested_tools],
            MODIFY_DISCOVERY_ALLOWLIST,
        )

    def for_modify_dependencies(
        self,
        requested_tools: list[ToolName | str],
    ) -> list[ToolName]:
        return self._filter(
            [str(name) for name in requested_tools],
            MODIFY_DEPENDENT_ALLOWLIST,
        )

    @staticmethod
    def _filter(
        requested_tools: list[str],
        allowed: frozenset[ToolName],
    ) -> list[ToolName]:
        selected: list[ToolName] = []
        for raw_name in requested_tools:
            try:
                tool_name = ToolName(raw_name)
            except ValueError:
                continue
            if tool_name in allowed and tool_name not in selected:
                selected.append(tool_name)
        return selected
