from __future__ import annotations

from typing import Protocol

from pydantic import Field

from app.domain.models import (
    CandidateSelection,
    DomainModel,
    Phase1Research,
    ToolError,
    ToolName,
    ToolResult,
    TravelEntities,
    UserPreferences,
)


class ToolContext(DomainModel):
    query: str | None = None
    entities: TravelEntities = Field(default_factory=TravelEntities)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    phase1_research: Phase1Research | None = None
    candidate_selection: CandidateSelection | None = None


class ToolExecutionOutcome(DomainModel):
    tool_name: ToolName
    result: ToolResult
    errors: list[ToolError] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1, le=2)
    abort_requested: bool = False


class TravelTool(Protocol):
    def __call__(self, context: ToolContext) -> ToolResult:
        """Execute one tool call and return the unified result envelope."""
