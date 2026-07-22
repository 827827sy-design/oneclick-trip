import re
from datetime import date, timedelta
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.intent_agent import (
    IntentAgent,
    RuleBasedIntentAgent,
    enforce_code_owned_intent,
    infer_query_tasks,
)
from app.domain.models import (
    BudgetMode,
    BudgetScope,
    Intent,
    IntentContext,
    IntentTask,
    NextAction,
    TravelEntities,
    UserPreferences,
)
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
        decision = _repair_intent_decision(query, decision)
        previous = state.get("entities") or TravelEntities()
        explicit_update = _sanitize_explicit_update(
            state,
            query,
            decision.entities.model_dump(exclude_unset=True),
        )
        intent = _resolve_intent_for_slot_follow_up(
            state,
            decision.intent,
            explicit_update,
            query,
        )
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
        intent_tasks = _normalize_intent_tasks(
            state,
            query,
            decision.tasks,
            intent,
            merged_entities,
        )
        return {
            **reset_tool_execution(),
            "intent": intent,
            "intent_confidence": decision.confidence,
            "intent_tasks": intent_tasks,
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


def _repair_intent_decision(query: str, decision):
    """Reject structurally valid but unusable LLM routing decisions."""
    return enforce_code_owned_intent(query, decision)


def _normalize_intent_tasks(
    state: TravelState,
    query: str,
    model_tasks: list[IntentTask],
    primary_intent: Intent,
    primary_entities: TravelEntities,
) -> list[IntentTask]:
    if primary_intent not in QUERY_INTENTS:
        return [
            IntentTask(
                task_id="task-1",
                query=query,
                intent=primary_intent,
                entities=primary_entities,
            )
        ]

    code_tasks = infer_query_tasks(query)
    valid_model_tasks = [item for item in model_tasks if item.intent in QUERY_INTENTS]
    candidates = (
        code_tasks
        if len(code_tasks) > 1
        else valid_model_tasks
        if len(valid_model_tasks) > 1
        else code_tasks or valid_model_tasks
    )
    normalized: list[IntentTask] = []
    for index, task in enumerate(candidates or []):
        task_query = task.query.strip() or query
        explicit = _sanitize_explicit_update(
            state,
            task_query,
            task.entities.model_dump(exclude_unset=True),
        )
        entities = _query_task_entities(primary_entities, explicit, task.intent)
        normalized.append(
            IntentTask(
                task_id=f"task-{index + 1}",
                query=task_query,
                intent=task.intent,
                entities=entities,
            )
        )
    return normalized or [
        IntentTask(
            task_id="task-1",
            query=query,
            intent=primary_intent,
            entities=primary_entities,
        )
    ]


def _query_task_entities(
    shared: TravelEntities,
    explicit: dict,
    intent: Intent,
) -> TravelEntities:
    values = dict(explicit)
    shared_fields = ["destination", "start_date", "end_date", "days", "currency"]
    if intent is Intent.TRANSPORT_QUERY:
        shared_fields.append("origin")
    for field in shared_fields:
        value = getattr(shared, field)
        if values.get(field) in (None, "") and value is not None:
            values[field] = value
    return TravelEntities(**values)


def _resolve_intent_for_slot_follow_up(
    state: TravelState,
    detected_intent,
    explicit_update: dict,
    query: str,
):
    previous_intent = state.get("intent")
    missing_fields = set(state.get("missing_fields", []))
    if not missing_fields:
        return detected_intent

    if (
        previous_intent is Intent.TRIP_PLAN
        and detected_intent in {Intent.GENERAL_QA, Intent.MODIFY_PLAN}
        and _looks_like_trip_preference_update(query, explicit_update)
    ):
        return previous_intent

    if detected_intent.value != "general_qa":
        return detected_intent

    slot_keys = {
        "destination": {"destination"},
        "destination_detail": {"destination"},
        "origin": {"origin"},
        "duration": {"days", "start_date", "end_date"},
        "people": {"people"},
        "budget": {"budget", "budget_scope", "budget_mode"},
        "budget_confirmation": {"budget", "budget_scope", "budget_mode"},
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
    sanitized = _apply_explicit_budget_update(state, query, dict(explicit_update))
    if not _query_sets_budget(state, query):
        sanitized.pop("budget", None)
    sanitized = _apply_explicit_date_update(state, query, sanitized)
    if not re.search(
        r"(?:\d{1,3}|[一二两三四五六七八九十])\s*(?:个)?人|独自|单人|情侣|夫妻|一家|亲子",
        query,
    ):
        sanitized.pop("people", None)
    return sanitized


def _query_sets_budget(state: TravelState, query: str) -> bool:
    if _is_relative_budget_change(query):
        return False
    return (
        _extract_budget_amount(state, query) is not None
        or _selected_estimate_tier(state, query) is not None
    )


def _apply_explicit_budget_update(
    state: TravelState,
    query: str,
    sanitized: dict,
) -> dict:
    if _is_relative_budget_change(query):
        sanitized.pop("budget", None)
        sanitized.pop("budget_scope", None)
        sanitized.pop("budget_mode", None)
        return sanitized
    estimate = state.get("budget_estimate")
    selected_tier = _selected_estimate_tier(state, query)
    amount = _extract_budget_amount(state, query)
    if selected_tier == "survival" and estimate is not None:
        amount = estimate.survival.total
    elif selected_tier == "comfortable" and estimate is not None:
        amount = estimate.comfortable.total

    if amount is not None:
        sanitized["budget"] = amount
        sanitized["budget_mode"] = (
            BudgetMode.MINIMIZE if selected_tier == "survival" else BudgetMode.FIXED
        )
        if _budget_scope_from_query(query) is not None:
            sanitized["budget_scope"] = _budget_scope_from_query(query)
        elif estimate is not None or set(state.get("missing_fields", [])).intersection(
            {"budget", "budget_confirmation"}
        ):
            sanitized["budget_scope"] = BudgetScope.TOTAL
    else:
        sanitized.pop("budget", None)
        scope = _budget_scope_from_query(query)
        if scope is not None:
            sanitized["budget_scope"] = scope
        else:
            sanitized.pop("budget_scope", None)
        if _requests_budget_estimate(query):
            sanitized["budget_mode"] = (
                BudgetMode.MINIMIZE if _requests_minimum_budget(query) else BudgetMode.ESTIMATE
            )
            sanitized.pop("budget_scope", None)
        elif "budget_mode" in sanitized:
            sanitized.pop("budget_mode", None)
    return sanitized


def _extract_budget_amount(state: TravelState, query: str) -> Decimal | None:
    if _is_relative_budget_change(query):
        return None
    number = r"(\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)"
    separator = r"[^，。；\d零〇一二两三四五六七八九十百千万]"
    patterns = [
        rf"(?:总预算|预算|人均|每人|总共){separator}{{0,8}}{number}",
        rf"{number}\s*(?:元|块)(?:左右|以内|上下)?",
    ]
    if set(state.get("missing_fields", [])).intersection({"budget", "budget_confirmation"}):
        patterns.extend(
            [
                rf"(?:那就|就按|就|按|控制在|定在|选)\s*{number}",
                rf"^\s*{number}\s*(?:元|块)?\s*(?:左右|以内|上下)?\s*(?:吧|就行|可以)?\s*$",
            ]
        )
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return _parse_budget_number(match.group(1))
    return None


def _is_relative_budget_change(query: str) -> bool:
    return bool(re.search(r"预算.{0,4}(?:降低|减少|下调|提高|增加|上调)\s*\d", query))


def _budget_scope_from_query(query: str) -> BudgetScope | None:
    if re.search(r"人均|每人", query):
        return BudgetScope.PER_PERSON
    if re.search(r"总预算|总共|全部预算|整体预算|预算", query):
        return BudgetScope.TOTAL
    return None


def _requests_budget_estimate(query: str) -> bool:
    return bool(
        re.search(
            r"(?:估计|估算|估一下|算算|帮我算).{0,12}(?:预算|费用|多少钱)|"
            r"(?:预算|费用).{0,12}(?:估|算|多少|怎么定)|"
            r"(?:不知道|不清楚|没概念).{0,8}(?:预算|多少钱)|"
            r"需要多少(?:预算|钱)",
            query,
        )
    )


def _requests_minimum_budget(query: str) -> bool:
    return bool(
        re.search(r"尽可能少|越少越好|越省越好|最低预算|最省|穷游|能省则省", query)
    )


def _selected_estimate_tier(state: TravelState, query: str) -> str | None:
    if state.get("budget_estimate") is None:
        return None
    if re.search(
        r"极限穷游|穷游版|最低预算|最省(?:方案|那档|版)?|预算再省(?:一)?点|再省(?:一)?点|便宜的",
        query,
    ):
        return "survival"
    if re.search(r"正常舒适|舒适版|舒服(?:一点|那档|版)?|正常玩", query):
        return "comfortable"
    return None


def _looks_like_trip_preference_update(query: str, explicit_update: dict) -> bool:
    if {"explicit_preferences", "explicit_dislikes"}.intersection(explicit_update):
        return True
    return bool(
        re.search(
            r"喜欢|不喜欢|不要|避开|多安排|少安排|想吃|爱吃|清淡|辣|海鲜|美食|徒步|拍照|早起|购物",
            query,
        )
    )


def _parse_budget_number(raw: str) -> Decimal:
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return Decimal(raw)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    small_units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    section = 0
    number = 0
    for character in raw:
        if character in digits:
            number = digits[character]
        elif character in small_units:
            section += (number or 1) * small_units[character]
            number = 0
        elif character == "万":
            total += (section + number or 1) * 10000
            section = 0
            number = 0
    return Decimal(total + section + number)


def _apply_explicit_date_update(
    state: TravelState,
    query: str,
    sanitized: dict,
) -> dict:
    del state
    relative_days = {"今天": 0, "明天": 1, "后天": 2}
    relative = next((offset for marker, offset in relative_days.items() if marker in query), None)
    has_numeric_date = bool(
        re.search(r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|\d{4}[-/]\d{1,2}[-/]\d{1,2}", query)
    )
    if relative is None and not has_numeric_date:
        sanitized.pop("start_date", None)
        sanitized.pop("end_date", None)
        return sanitized

    if relative is not None:
        start = date.today() + timedelta(days=relative)
        sanitized["start_date"] = start
        days = sanitized.get("days")
        if days:
            sanitized["end_date"] = start + timedelta(days=int(days) - 1)
        else:
            sanitized.pop("end_date", None)
    return sanitized
