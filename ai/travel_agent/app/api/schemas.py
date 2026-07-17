from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import (
    HardValidationResult,
    BookingDraft,
    BudgetEstimate,
    BudgetFeasibility,
    CandidateSelection,
    ClarificationReply,
    Intent,
    ModifyAnalysis,
    NextAction,
    Phase1Research,
    Phase2Research,
    ReviewResult,
    ToolError,
    ToolResult,
    TravelPlan,
    TravelEntities,
    UserPreferences,
)


class AgentRunRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=10_000)


class AgentResumeRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    confirmed: bool


class AgentRunResponse(BaseModel):
    conversation_id: str
    intent: Intent
    next_action: NextAction
    entities: TravelEntities = Field(default_factory=TravelEntities)
    checkpoint_version: int
    message_count: int
    missing_fields: list[str] = Field(default_factory=list)
    clarification_reply: ClarificationReply | None = None
    budget_feasibility: BudgetFeasibility | None = None
    budget_estimate: BudgetEstimate | None = None
    phase1_research: Phase1Research | None = None
    candidate_selection: CandidateSelection | None = None
    candidate_validation_errors: list[str] = Field(default_factory=list)
    phase2_research: Phase2Research | None = None
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    memory_errors: list[str] = Field(default_factory=list)
    plan_draft: TravelPlan | None = None
    current_plan: TravelPlan | None = None
    plan_version: int | None = None
    hard_validation: HardValidationResult | None = None
    review_result: ReviewResult | None = None
    revision_count: int = 0
    plan_saved: bool = False
    validation_exhausted: bool = False
    modify_analysis: ModifyAnalysis | None = None
    modification_errors: list[str] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    tool_results: dict[str, ToolResult] = Field(default_factory=dict)
    tool_errors: list[ToolError] = Field(default_factory=list)
    tool_attempts: dict[str, int] = Field(default_factory=dict)
    planning_errors: list[str] = Field(default_factory=list)
    booking_draft: BookingDraft | None = None
    booking_errors: list[str] = Field(default_factory=list)
    booking_completed: bool = False
    interrupted: bool = False
    interrupt_id: str | None = None
    interrupt_payload: dict[str, Any] | None = None
    reply: str | None = None


class HealthResponse(BaseModel):
    status: str
    phase: str


class InfrastructureHealthResponse(BaseModel):
    status: str
    components: dict[str, str] = Field(default_factory=dict)
