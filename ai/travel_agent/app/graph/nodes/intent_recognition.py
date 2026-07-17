import re

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.intent_agent import IntentAgent
from app.domain.models import Intent, IntentContext, NextAction, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch
from app.graph.tool_runtime import reset_tool_execution


FRESH_TRIP_MARKERS = (
    "新的旅行",
    "新旅行",
    "重新规划",
    "重新安排",
    "想出去旅游",
    "想出去玩",
    "想去旅游",
    "推荐一个地方",
    "换个目的地",
)

DESTINATION_REFERENCE_MARKERS = (
    "那",
    "那里",
    "当地",
    "这里",
    "这儿",
    "这座城市",
    "这个地方",
)

PENDING_PLAN_ADJUSTMENT_MARKERS = (
    "预算改",
    "总预算",
    "人均",
    "缩短",
    "延长",
    "改成",
    "换成",
    "人数改",
    "保持预算",
)

QUERY_INTENTS = {
    Intent.WEATHER_QUERY,
    Intent.HOTEL_QUERY,
    Intent.TRANSPORT_QUERY,
    Intent.GENERAL_QA,
}


def make_intent_recognition_node(
    agent: IntentAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def query_from(state: TravelState) -> str:
        return next(
            (
                str(message.content)
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage)
            ),
            "",
        )

    def context_from(state: TravelState) -> IntentContext:
        recent_messages = []
        for message in state.get("messages", [])[-20:]:
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                continue
            recent_messages.append(f"{role}: {message.content}")
        plan = state.get("current_plan")
        draft = state.get("booking_draft")
        return IntentContext(
            recent_messages=recent_messages,
            user_preferences=state.get("user_preferences") or UserPreferences(),
            previous_intent=state.get("intent") or Intent.UNKNOWN,
            pending_missing_fields=list(state.get("missing_fields", [])),
            current_plan_id=plan.plan_id if plan else None,
            current_plan_version=plan.version if plan else None,
            booking_draft_id=draft.draft_id if draft else None,
            booking_status=draft.status if draft else None,
        )

    def patch_from(state: TravelState, decision, query: str) -> TravelStatePatch:
        previous = state.get("entities") or TravelEntities()
        explicit_update = _sanitize_explicit_update(
            state,
            query,
            decision.entities.model_dump(exclude_unset=True),
        )
        intent = _resolve_intent_for_slot_follow_up(state, decision.intent, explicit_update)
        inherited = _entity_base_for_turn(
            state,
            previous,
            intent,
            query,
            explicit_update,
        )
        base = inherited.model_copy(
            update={
                "explicit_preferences": [],
                "explicit_dislikes": [],
                "selected_option_ids": [],
                "booking_types": [],
            }
        )
        merged_entities = base.model_copy(update=explicit_update)
        return {
            **reset_tool_execution(),
            "intent": intent,
            "intent_confidence": decision.confidence,
            "entities": merged_entities,
            "missing_fields": decision.advisory_missing_fields,
            "clarification_reply": None,
            "budget_feasibility": None,
            "plan_draft": None,
            "hard_validation": None,
            "review_result": None,
            "planning_errors": [],
            "modification_errors": [],
            "booking_errors": [],
            "plan_saved": False,
            "validation_exhausted": False,
            "revision_count": 0,
            "next_action": NextAction.NORMALIZE_STATE,
        }

    def recognize_intent(state: TravelState) -> TravelStatePatch:
        query = query_from(state)
        return patch_from(
            state,
            agent.classify(query, context=context_from(state)),
            query,
        )

    async def arecognize_intent(state: TravelState) -> TravelStatePatch:
        query = query_from(state)
        return patch_from(
            state,
            await agent.aclassify(query, context=context_from(state)),
            query,
        )

    return RunnableLambda(recognize_intent, afunc=arecognize_intent, name="recognize_intent")


def _resolve_intent_for_slot_follow_up(state: TravelState, detected_intent, explicit_update: dict):
    previous_intent = state.get("intent")
    missing_fields = set(state.get("missing_fields", []))
    if detected_intent.value != "general_qa" or not missing_fields:
        return detected_intent

    slot_keys = {
        "destination": {"destination"},
        "origin": {"origin"},
        "duration": {"days", "start_date", "end_date"},
        "people": {"people"},
        "budget": {"budget", "budget_scope"},
        "booking_type": {"booking_types"},
        "selected_option_ids": {"selected_option_ids"},
    }
    expected_keys = set().union(*(slot_keys.get(field, set()) for field in missing_fields))
    if expected_keys.intersection(explicit_update):
        return previous_intent
    return detected_intent


def _should_inherit_entities(
    state: TravelState,
    intent: Intent,
    query: str,
    explicit_update: dict,
) -> bool:
    """Carry slots only while completing the same pending task.

    Completed queries and plans must not leak their dates, people or budget into
    a new request. Modify and booking flows intentionally operate on the current
    structured plan, so they retain the saved entities.
    """
    if intent in {Intent.MODIFY_PLAN, Intent.BOOKING, Intent.BOOKING_CONFIRM}:
        return True
    if intent is Intent.TRIP_PLAN and any(marker in query for marker in FRESH_TRIP_MARKERS):
        return False
    feasibility = state.get("budget_feasibility")
    if (
        intent is Intent.TRIP_PLAN
        and feasibility is not None
        and not feasibility.feasible
        and "budget" not in explicit_update
        and set(explicit_update).intersection(
            {"destination", "days", "start_date", "end_date", "people"}
        )
        and not any(marker in query for marker in PENDING_PLAN_ADJUSTMENT_MARKERS)
    ):
        return False
    return bool(
        state.get("missing_fields")
        and state.get("intent") == intent
    )


def _entity_base_for_turn(
    state: TravelState,
    previous: TravelEntities,
    intent: Intent,
    query: str,
    explicit_update: dict,
) -> TravelEntities:
    if _should_inherit_entities(state, intent, query, explicit_update):
        return previous
    if (
        intent in QUERY_INTENTS
        and previous.destination
        and any(marker in query for marker in DESTINATION_REFERENCE_MARKERS)
    ):
        return TravelEntities(
            destination=previous.destination,
            origin=previous.origin,
            currency=previous.currency,
        )
    return TravelEntities(currency=previous.currency)


def _sanitize_explicit_update(
    state: TravelState,
    query: str,
    explicit_update: dict,
) -> dict:
    """Reject volatile slots copied by an LLM from conversation context.

    Context helps resolve intent and references, but a budget or party size is
    considered explicit only when the current user message actually says it.
    """
    sanitized = dict(explicit_update)
    if not _query_sets_budget(state, query):
        sanitized.pop("budget", None)
        sanitized.pop("budget_scope", None)
    if not re.search(
        r"(?:\d{1,3}|[一二两三四五六七八九十])\s*(?:个)?人|独自|单人|情侣|夫妻|一家|亲子",
        query,
    ):
        sanitized.pop("people", None)
    return sanitized


def _query_sets_budget(state: TravelState, query: str) -> bool:
    amount = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
    if re.search(rf"(?:预算|人均|每人)[^，。；]{{0,8}}{amount}", query):
        return True
    if re.search(rf"{amount}\s*(?:元|块)(?:左右|以内|上下)?", query):
        return True
    if "budget" not in set(state.get("missing_fields", [])):
        return False
    return bool(re.fullmatch(rf"\s*{amount}\s*(?:元|块)?\s*(?:左右|以内|上下)?\s*", query))
