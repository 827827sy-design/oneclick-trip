"""Optional internet-research adapters used by isolated proofs of concept."""

from app.tools.research.agent_reach import (
    AgentReachDiagnostics,
    AgentReachWebFetch,
    AgentReachWebSearch,
    FetchedPage,
    ResearchItem,
)
from app.tools.research.cache import ResearchResultCache
from app.tools.research.coordinator import AgentReachResearchCoordinator
from app.tools.research.policy import DestinationResearchPolicy
from app.tools.research.quality import ResearchQualityPipeline, SourceTier
from app.tools.research.tool import TravelResearchTool
from app.tools.research.xiaohongshu import XiaohongshuResearchTool

__all__ = [
    "AgentReachDiagnostics",
    "AgentReachWebFetch",
    "AgentReachWebSearch",
    "AgentReachResearchCoordinator",
    "DestinationResearchPolicy",
    "FetchedPage",
    "ResearchItem",
    "ResearchQualityPipeline",
    "ResearchResultCache",
    "SourceTier",
    "TravelResearchTool",
    "XiaohongshuResearchTool",
]
