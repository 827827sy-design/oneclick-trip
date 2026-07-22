from app.config import Settings
from app.domain.models import ToolName
from app.tools.provider_tools import (
    PoiCoordinateProviderTool,
    RouteProviderTool,
    WeatherProviderTool,
)
from app.tools.providers import (
    NominatimPoiCoordinateProvider,
    OpenMeteoWeatherProvider,
    OsrmRouteProvider,
)
from app.tools.research import (
    AgentReachResearchCoordinator,
    AgentReachWebFetch,
    AgentReachWebSearch,
    ResearchResultCache,
    TravelResearchTool,
    XiaohongshuResearchTool,
)
from app.tools.registry import ToolRegistry
from app.tools.knowledge import HybridKnowledgeSearchTool
from app.vectorstore import ChromaTravelKnowledgeBase


def build_live_tool_registry(
    settings: Settings,
    knowledge_base: ChromaTravelKnowledgeBase | None = None,
) -> ToolRegistry:
    """Build only tools that may run in an end-user Agent request."""
    weather_provider = OpenMeteoWeatherProvider(
        base_url=settings.open_meteo_base_url,
        geocoding_url=settings.open_meteo_geocoding_url,
        nominatim_url=settings.nominatim_base_url,
        nominatim_user_agent=settings.nominatim_user_agent,
        timeout_seconds=settings.tool_http_timeout_seconds,
    )
    route_provider = OsrmRouteProvider(
        base_url=settings.osrm_base_url,
        timeout_seconds=settings.tool_http_timeout_seconds,
    )
    coordinate_provider = NominatimPoiCoordinateProvider(
        base_url=settings.nominatim_base_url,
        user_agent=settings.nominatim_user_agent,
        timeout_seconds=settings.tool_http_timeout_seconds,
    )
    tools = {
        ToolName.WEATHER: WeatherProviderTool(weather_provider),
        ToolName.POI_COORDINATES: PoiCoordinateProviderTool(coordinate_provider),
        ToolName.ROUTE_MATRIX: RouteProviderTool(route_provider),
    }
    if knowledge_base is not None:
        tools[ToolName.KNOWLEDGE_SEARCH] = HybridKnowledgeSearchTool(knowledge_base)
    return ToolRegistry(tools)


def build_knowledge_research_registry(settings: Settings) -> ToolRegistry:
    """Build offline collectors for the B-02 admin knowledge pipeline."""
    if not settings.agent_reach_enabled:
        return ToolRegistry()
    cache = ResearchResultCache(settings.agent_reach_cache_ttl_seconds)
    tools = {
        ToolName.TRAVEL_RESEARCH: TravelResearchTool(
            AgentReachResearchCoordinator(
                AgentReachWebSearch(cache=cache),
                AgentReachWebFetch(cache=cache),
            ),
            limit=settings.agent_reach_result_limit,
            fetch_top=max(
                settings.agent_reach_fetch_top,
                settings.agent_reach_result_limit,
            ),
        )
    }
    if settings.xiaohongshu_enabled:
        tools[ToolName.XIAOHONGSHU_RESEARCH] = XiaohongshuResearchTool(
            cache=cache,
            result_limit=settings.xiaohongshu_result_limit,
            detail_limit=settings.xiaohongshu_detail_limit,
            detail_delay_seconds=settings.xiaohongshu_detail_delay_seconds,
        )
    return ToolRegistry(tools)
