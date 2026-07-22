from __future__ import annotations

from datetime import UTC, date as Date, datetime as DateTime, time as Time
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Intent(StrEnum):
    UNKNOWN = "unknown"
    WEATHER_QUERY = "weather_query"
    HOTEL_QUERY = "hotel_query"
    TRANSPORT_QUERY = "transport_query"
    GENERAL_QA = "general_qa"
    TRIP_PLAN = "trip_plan"
    MODIFY_PLAN = "modify_plan"
    BOOKING = "booking"
    BOOKING_CONFIRM = "booking_confirm"
    MEMORY_MANAGE = "memory_manage"


class NextAction(StrEnum):
    LOAD_USER_MEMORY = "load_user_memory"
    RECOGNIZE_INTENT = "recognize_intent"
    NORMALIZE_STATE = "normalize_state"
    SUPERVISE = "supervise"
    ASK_USER = "ask_user"
    QUERY_FLOW = "query_flow"
    PLANNING_FLOW = "planning_flow"
    MODIFY_FLOW = "modify_flow"
    MEMORY_FLOW = "memory_flow"
    BOOKING_FLOW = "booking_flow"
    COMPLETE = "complete"
    ABORT = "abort"


class BudgetScope(StrEnum):
    TOTAL = "total"
    PER_PERSON = "per_person"


class BudgetMode(StrEnum):
    FIXED = "fixed"
    ESTIMATE = "estimate"
    MINIMIZE = "minimize"


class BookingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ToolName(StrEnum):
    WEATHER = "weather"
    HOTEL_SEARCH = "hotel_search"
    TRAIN_SEARCH = "train_search"
    FLIGHT_SEARCH = "flight_search"
    POI_SEARCH = "poi_search"
    ROUTE_MATRIX = "route_matrix"
    OPENING_HOURS = "opening_hours"
    TICKET = "ticket"


class ToolRecoveryAction(StrEnum):
    RETRY = "retry"
    FALLBACK = "fallback"
    CONTINUE = "continue"
    ABORT = "abort"


class ReviewVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"


class ModifyImpact(StrEnum):
    SIMPLE = "simple"
    RESEARCH_REQUIRED = "research_required"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class TravelEntities(DomainModel):
    destination: str | None = None
    origin: str | None = None
    start_date: Date | None = None
    end_date: Date | None = None
    days: int | None = Field(default=None, ge=1, le=60)
    people: int | None = Field(default=None, ge=1, le=100)
    budget: Decimal | None = Field(default=None, ge=0)
    budget_scope: BudgetScope | None = None
    budget_mode: BudgetMode | None = None
    currency: str = "CNY"
    explicit_preferences: list[str] = Field(default_factory=list)
    explicit_dislikes: list[str] = Field(default_factory=list)
    selected_option_ids: list[str] = Field(default_factory=list)
    booking_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_order(self) -> TravelEntities:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class MemoryItem(DomainModel):
    category: Literal[
        "pace", "budget_style", "food", "transport", "hotel", "activity", "avoidance", "tag"
    ]
    key: str
    value: str
    confidence: float = Field(ge=0, le=1)
    evidence: str


class MemoryOperation(MemoryItem):
    action: Literal["upsert", "delete"]
    source: Literal["explicit", "repeated"]


class MemoryExtraction(DomainModel):
    operations: list[MemoryOperation] = Field(default_factory=list)


class UserPreferences(DomainModel):
    liked_tags: list[str] = Field(default_factory=list)
    disliked_tags: list[str] = Field(default_factory=list)
    preferred_transport: list[str] = Field(default_factory=list)
    pace: str | None = None
    typical_budget_scope: BudgetScope | None = None
    memory_items: list[MemoryItem] = Field(default_factory=list)
    source_version: int = 0
    updated_at: DateTime = Field(default_factory=lambda: DateTime.now(UTC))


class IntentContext(DomainModel):
    """Compact conversation context supplied to the intent model."""

    recent_messages: list[str] = Field(default_factory=list)
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    previous_intent: Intent = Intent.UNKNOWN
    pending_missing_fields: list[str] = Field(default_factory=list)
    current_plan_id: str | None = None
    current_plan_version: int | None = None
    booking_draft_id: str | None = None
    booking_status: BookingStatus | None = None


class IntentDecision(DomainModel):
    intent: Intent
    entities: TravelEntities = Field(default_factory=TravelEntities)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    advisory_missing_fields: list[str] = Field(default_factory=list)


class ClarificationAction(DomainModel):
    id: str = Field(min_length=1, max_length=48)
    field: str = Field(min_length=1, max_length=48)
    label: str = Field(min_length=1, max_length=24)
    message: str = Field(min_length=1, max_length=120)
    recommended: bool = False


class ClarificationReply(DomainModel):
    kicker: str = Field(min_length=1, max_length=24)
    title: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=180)
    choice_prompt: str | None = Field(default=None, max_length=60)
    actions: list[ClarificationAction] = Field(default_factory=list, max_length=6)


class SelectedOptions(DomainModel):
    poi_ids: list[str] = Field(default_factory=list)
    hotel_option_ids: list[str] = Field(default_factory=list)
    transport_option_ids: list[str] = Field(default_factory=list)
    ticket_option_ids: list[str] = Field(default_factory=list)


class POICandidate(DomainModel):
    poi_id: str
    name: str
    area: str
    tags: list[str] = Field(default_factory=list)
    suggested_duration_minutes: int = Field(ge=30)
    ticket_price: Decimal = Decimal("0")


class HotelAreaCandidate(DomainModel):
    area_id: str
    name: str
    reason: str
    nightly_price_hint: Decimal = Decimal("0")


class TransportCandidate(DomainModel):
    option_id: str
    mode: str
    name: str
    duration_minutes: int = Field(ge=0)
    price: Decimal = Decimal("0")


class Phase1Research(DomainModel):
    data_mode: str = "AI_KNOWLEDGE"
    destination: str
    weather_summary: str
    poi_candidates: list[POICandidate] = Field(default_factory=list)
    hotel_areas: list[HotelAreaCandidate] = Field(default_factory=list)
    transport_options: list[TransportCandidate] = Field(default_factory=list)


class BudgetFeasibility(DomainModel):
    feasible: bool
    budget_limit: Decimal = Field(ge=0)
    estimated_minimum: Decimal = Field(ge=0)
    transport_cost: Decimal = Field(default=Decimal("0"), ge=0)
    lodging_cost: Decimal = Field(default=Decimal("0"), ge=0)
    daily_basic_cost: Decimal = Field(default=Decimal("0"), ge=0)
    suggested_budget: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = "CNY"


class BudgetTierEstimate(DomainModel):
    name: str
    total: Decimal = Field(ge=0)
    intercity_transport: Decimal = Field(default=Decimal("0"), ge=0)
    lodging: Decimal = Field(default=Decimal("0"), ge=0)
    food: Decimal = Field(default=Decimal("0"), ge=0)
    local_transport: Decimal = Field(default=Decimal("0"), ge=0)
    tickets: Decimal = Field(default=Decimal("0"), ge=0)
    assumptions: list[str] = Field(default_factory=list)


class BudgetEstimate(DomainModel):
    survival: BudgetTierEstimate
    comfortable: BudgetTierEstimate
    currency: str = "CNY"
    data_mode: str = "AI_ESTIMATE"
    disclaimer: str = "基于 AI 通用知识的保守估算，不代表实时票价或房价。"


class CandidateVisit(DomainModel):
    poi_id: str
    visit_date: str
    estimated_duration_minutes: int = Field(ge=30)


class CandidateSelection(DomainModel):
    selected_poi_ids: list[str] = Field(default_factory=list)
    selected_pois: list[CandidateVisit] = Field(default_factory=list)
    hotel_area_id: str | None = None
    transport_option_id: str | None = None
    destinations: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RouteLeg(DomainModel):
    from_id: str
    to_id: str
    distance_km: float = Field(ge=0)
    duration_minutes: int = Field(ge=0)


class POIVisitDetail(DomainModel):
    poi_id: str
    opening_hours: str
    ticket_option_id: str | None = None
    ticket_price: Decimal = Decimal("0")
    available: bool | None = None


class Phase2Research(DomainModel):
    data_mode: str = "AI_KNOWLEDGE"
    route_legs: list[RouteLeg] = Field(default_factory=list)
    poi_details: list[POIVisitDetail] = Field(default_factory=list)


class ItineraryItem(DomainModel):
    item_id: str
    name: str
    item_type: str = "SPOT"
    start_at: DateTime | None = None
    end_at: DateTime | None = None
    start_time: Time | None = None
    end_time: Time | None = None
    location_id: str | None = None
    description: str | None = None
    travel_minutes: int = Field(default=0, ge=0)
    visit_minutes: int = Field(default=0, ge=0)
    ticket_option_id: str | None = None
    estimated_cost: Decimal = Decimal("0")


class ItineraryDay(DomainModel):
    day_index: int = Field(ge=1)
    date: Date | None = None
    title: str | None = None
    summary: str | None = None
    items: list[ItineraryItem] = Field(default_factory=list)
    hotel_option_id: str | None = None


class TravelPlan(DomainModel):
    plan_id: str
    version: int = Field(ge=1)
    destination: str
    days: list[ItineraryDay] = Field(default_factory=list)
    hotel_area_id: str | None = None
    transport_option_id: str | None = None
    hotel_nights: int = Field(default=0, ge=0)
    assumptions: list[str] = Field(default_factory=list)
    total_cost: Decimal = Decimal("0")
    currency: str = "CNY"
    created_at: DateTime = Field(default_factory=lambda: DateTime.now(UTC))


class DirectPlanProposal(DomainModel):
    feasible: bool
    plan: TravelPlan | None = None
    message: str = ""
    suggested_budget: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_plan_when_feasible(self) -> DirectPlanProposal:
        if self.feasible and self.plan is None:
            raise ValueError("plan is required when feasible is true")
        return self


class PersistedPlanState(DomainModel):
    """Validated business state required to modify or book a saved plan."""

    plan: TravelPlan
    entities: TravelEntities = Field(default_factory=TravelEntities)
    selected_options: SelectedOptions = Field(default_factory=SelectedOptions)
    candidate_selection: CandidateSelection | None = None
    phase1_research: Phase1Research | None = None
    phase2_research: Phase2Research | None = None


class ValidationIssue(DomainModel):
    code: str
    message: str
    day_index: int | None = None
    item_id: str | None = None


class HardValidationResult(DomainModel):
    hard_pass: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class ReviewResult(DomainModel):
    verdict: ReviewVerdict
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ModificationRequest(DomainModel):
    target_day: int | None = Field(default=None, ge=1)
    target_period: str | None = None
    replacement_name: str | None = None
    budget_delta: Decimal | None = None
    new_budget: Decimal | None = Field(default=None, ge=0)
    remove_tags: list[str] = Field(default_factory=list)
    swap_days: tuple[int, int] | None = None


class ModifyAnalysis(DomainModel):
    impact: ModifyImpact
    request: ModificationRequest = Field(default_factory=ModificationRequest)
    discovery_tools: list[ToolName] = Field(default_factory=list)
    dependent_tools: list[ToolName] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ModificationResult(DomainModel):
    plan: TravelPlan
    entities: TravelEntities
    selection: CandidateSelection
    errors: list[str] = Field(default_factory=list)


class ToolResult(DomainModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
    timestamp: DateTime = Field(default_factory=lambda: DateTime.now(UTC))


class ToolError(DomainModel):
    tool_name: str
    error_code: str
    message: str
    retryable: bool = False
    attempt: int = Field(default=1, ge=1, le=2)
    timestamp: DateTime = Field(default_factory=lambda: DateTime.now(UTC))


class BookingDraft(DomainModel):
    """Reference returned by the Java backend; never stores security tokens."""

    draft_id: str
    status: BookingStatus
    conversation_id: str
    user_id: str
    plan_id: str
    plan_version: int = Field(ge=1)
    booking_types: list[str] = Field(default_factory=list)
    selected_option_ids: list[str] = Field(default_factory=list)
    created_at: DateTime = Field(default_factory=lambda: DateTime.now(UTC))
    expires_at: DateTime
