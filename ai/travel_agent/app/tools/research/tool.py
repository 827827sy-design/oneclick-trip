from __future__ import annotations

from app.domain.models import ToolDataMode, ToolResult
from app.tools.contracts import ToolContext
from app.tools.research.coordinator import AgentReachResearchCoordinator
from app.tools.research.policy import DestinationResearchPolicy


class TravelResearchTool:
    """Read-only web research tool; never returns bookable supplier inventory."""

    is_realtime_provider = True

    def __init__(
        self,
        coordinator: AgentReachResearchCoordinator,
        *,
        policy: DestinationResearchPolicy | None = None,
        limit: int = 5,
        fetch_top: int = 2,
    ) -> None:
        self._coordinator = coordinator
        self._policy = policy or DestinationResearchPolicy()
        self._limit = limit
        self._fetch_top = fetch_top

    def __call__(self, context: ToolContext) -> ToolResult:
        query = build_research_query(context)
        if not query:
            return ToolResult(
                success=False,
                source="agent-reach/travel-research",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "联网研究缺少用户问题或目的地"},
                error_code="TRAVEL_RESEARCH_QUERY_MISSING",
                retryable=False,
            )
        official_domains = self._policy.official_domains(
            context.entities.destination,
            query,
        )
        result = self._coordinator.research(
            query,
            official_domains=official_domains,
            limit=self._limit,
            fetch_top=self._fetch_top,
        )
        data = dict(result.data)
        data["usage_policy"] = {
            "read_only": True,
            "bookable": False,
            "official_domains": official_domains,
            "numeric_facts_require_corroboration": True,
        }
        return result.model_copy(update={"data": data, "bookable": False})


def build_research_query(context: ToolContext) -> str:
    query = (context.query or "").strip()
    destination = (context.entities.destination or "").strip()
    if not query and destination:
        query = f"{destination}旅游攻略"
    if not query:
        return ""

    planning_request = any(
        (
            context.entities.days,
            context.entities.start_date,
            context.entities.end_date,
            context.entities.budget is not None,
            context.entities.people,
        )
    )
    if planning_request:
        query = f"{query} 景点路线 完整游览时长 开放时间 官方安全规则"
    preference_terms = [
        *context.entities.explicit_preferences,
        *context.preferences.liked_tags,
    ]
    if preference_terms:
        query = f"{query} {' '.join(dict.fromkeys(preference_terms[:5]))}"
    return " ".join(query.split())
