from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.memory_agent import MemoryCandidateAgent
from app.database.contracts import UserPreferenceRepository
from app.domain.models import MemoryExtraction, MemoryItem, TravelEntities, UserPreferences
from app.graph.nodes.state_normalizer import merge_preferences
from app.graph.state import TravelState, TravelStatePatch


ALLOWED_CATEGORIES = {
    "pace", "budget_style", "food", "transport", "hotel", "activity", "avoidance", "tag"
}
SENSITIVE_MARKERS = {"身份证", "银行卡", "密码", "手机号", "支付", "病史", "疾病"}
ONE_OFF_MARKERS = ("这次", "本次", "这趟", "本趟", "只去", "只玩", "只逛", "总预算")
STABLE_MARKERS = ("以后", "通常", "一直", "每次", "总是", "习惯", "长期", "从不", "都喜欢")
GENERIC_AVOIDANCES = {"其他景点", "其它景点", "别的景点"}


def make_memory_candidate_node(
    agent: MemoryCandidateAgent,
    repository: UserPreferenceRepository | None,
) -> Runnable[TravelState, TravelStatePatch]:
    def extract(state: TravelState) -> TravelStatePatch:
        if repository is not None:
            raise RuntimeError("repository-backed memory extraction requires async invocation")
        return _build_patch(state, agent.extract(**_arguments(state)))

    async def aextract(state: TravelState) -> TravelStatePatch:
        extraction = await agent.aextract(**_arguments(state))
        patch = _build_patch(state, extraction)
        if repository is not None and patch.get("memory_updated"):
            try:
                await repository.save(state["user_id"], patch["user_preferences"])
            except Exception:
                return {"memory_errors": ["USER_PREFERENCE_PERSISTENCE_FAILED"]}
        return patch

    return RunnableLambda(extract, afunc=aextract, name="extract_long_term_memory")


def _arguments(state: TravelState) -> dict:
    query = next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )
    return {
        "query": query,
        "entities": state.get("entities") or TravelEntities(),
        "preferences": state.get("user_preferences") or UserPreferences(),
    }


def _build_patch(state: TravelState, extraction: MemoryExtraction) -> TravelStatePatch:
    query = _latest_query(state)
    accepted = [
        operation
        for operation in extraction.operations
        if operation.category in ALLOWED_CATEGORIES
        and operation.evidence.strip()
        and not any(marker in operation.evidence for marker in SENSITIVE_MARKERS)
        and (operation.action == "delete" or operation.confidence >= 0.85)
        and _is_durable_memory(operation, query)
    ]
    current = state.get("user_preferences") or UserPreferences()
    updated = _apply_operations(current, accepted)
    changed = updated != current
    if changed:
        updated.source_version = current.source_version + 1
    return {
        "memory_candidates": extraction,
        "memory_operations": accepted,
        "memory_updated": changed,
        "user_preferences": updated,
        "effective_preferences": merge_preferences(
            updated,
            state.get("entities") or TravelEntities(),
        ),
        "memory_errors": [],
    }


def _latest_query(state: TravelState) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def _is_durable_memory(operation, query: str) -> bool:
    if operation.action == "delete":
        return True
    combined = f"{query}\n{operation.evidence}"
    stable = any(marker in combined for marker in STABLE_MARKERS)
    if any(marker in combined for marker in ONE_OFF_MARKERS) and not stable:
        return False
    if operation.category == "avoidance" and operation.value in GENERIC_AVOIDANCES:
        return False
    if operation.category == "budget_style" and not stable:
        return False
    return True


def _apply_operations(preferences: UserPreferences, operations) -> UserPreferences:
    updated = preferences.model_copy(deep=True)
    items = list(updated.memory_items)
    for operation in operations:
        items = [
            item
            for item in items
            if not (item.category == operation.category and item.key == operation.key)
        ]
        if operation.action == "delete":
            if operation.category == "pace" and updated.pace == operation.value:
                updated.pace = None
            elif operation.category == "transport":
                updated.preferred_transport = [
                    item for item in updated.preferred_transport if item != operation.value
                ]
            elif operation.category == "avoidance":
                updated.disliked_tags = [
                    item for item in updated.disliked_tags if item != operation.value
                ]
            elif operation.category in {"food", "hotel", "activity", "tag"}:
                updated.liked_tags = [
                    item for item in updated.liked_tags if item != operation.value
                ]
            continue
        item = MemoryItem(**operation.model_dump(exclude={"action", "source"}))
        items.append(item)
        if operation.category == "pace":
            updated.pace = operation.value
        elif operation.category == "transport" and operation.value not in updated.preferred_transport:
            updated.preferred_transport.append(operation.value)
        elif operation.category == "avoidance" and operation.value not in updated.disliked_tags:
            updated.disliked_tags.append(operation.value)
        elif operation.category in {"food", "hotel", "activity", "tag"}:
            tag = operation.value
            if tag not in updated.liked_tags:
                updated.liked_tags.append(tag)
    updated.memory_items = items
    return updated
