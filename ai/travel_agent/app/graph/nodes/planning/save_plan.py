from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from app.agents.plan_presenter import PlanPresenterAgent, RuleBasedPlanPresenterAgent
from app.database.contracts import PlanRepository
from app.domain.models import (
    NextAction,
    PersistedPlanState,
    ReviewVerdict,
    SelectedOptions,
    TravelEntities,
    UserPreferences,
)
from app.graph.state import TravelState, TravelStatePatch


def save_validated_plan(state: TravelState) -> TravelStatePatch:
    patch = _build_validated_plan_patch(state)
    return _with_presentation(
        state,
        patch,
        RuleBasedPlanPresenterAgent().present,
    )


def make_save_validated_plan_node(
    repository: PlanRepository | None,
    presenter: PlanPresenterAgent,
) -> Runnable[TravelState, TravelStatePatch]:
    def save_without_repository(state: TravelState) -> TravelStatePatch:
        if repository is not None:
            raise RuntimeError("repository-backed plan saving requires async graph invocation")
        patch = _build_validated_plan_patch(state)
        return _with_presentation(state, patch, presenter.present)

    async def save_persisted_validated_plan(state: TravelState) -> TravelStatePatch:
        patch = _build_validated_plan_patch(state)
        if not patch.get("plan_saved"):
            return patch
        plan = patch.get("current_plan")
        if plan is None:
            return {"plan_saved": False, "planning_errors": ["PLAN_PERSISTENCE_STATE_INVALID"]}
        if repository is not None:
            try:
                selected_options = patch.get("selected_options") or SelectedOptions()
                persisted = await repository.save_new_version(
                    state["user_id"],
                    state["conversation_id"],
                    PersistedPlanState(
                        plan=plan,
                        entities=state.get("entities") or TravelEntities(),
                        selected_options=selected_options,
                        candidate_selection=state.get("candidate_selection"),
                        phase1_research=state.get("phase1_research"),
                        phase2_research=state.get("phase2_research"),
                    ),
                )
            except Exception:
                return {
                    "plan_saved": False,
                    "planning_errors": ["PLAN_PERSISTENCE_FAILED"],
                    "next_action": NextAction.ABORT,
                }
            patch = {
                **patch,
                "current_plan": persisted.plan,
                "plan_version": persisted.plan.version,
                "selected_options": persisted.selected_options,
            }
        return await _with_async_presentation(state, patch, presenter)

    return RunnableLambda(
        save_without_repository,
        afunc=save_persisted_validated_plan,
        name="save_validated_plan",
    )


def _build_validated_plan_patch(state: TravelState) -> TravelStatePatch:
    plan = state.get("plan_draft")
    hard = state.get("hard_validation")
    review = state.get("review_result")
    selection = state.get("candidate_selection")
    phase2 = state.get("phase2_research")
    if (
        not plan
        or not hard
        or not review
        or not hard.hard_pass
        or review.verdict is not ReviewVerdict.PASS
    ):
        return {
            "plan_saved": False,
            "planning_errors": ["SAVE_GUARD_REJECTED"],
        }

    return {
        "current_plan": plan,
        "plan_version": plan.version,
        "plan_saved": True,
        "validation_exhausted": False,
        "booking_draft": None,
        "checkpoint_version": state.get("checkpoint_version", 0) + 1,
        "next_action": NextAction.COMPLETE,
        "selected_options": SelectedOptions(
            poi_ids=list(selection.selected_poi_ids) if selection else [],
            hotel_option_ids=[plan.hotel_area_id]
            if plan.hotel_area_id and plan.hotel_area_id.startswith("HOTEL-")
            else [],
            transport_option_ids=[selection.transport_option_id]
            if selection
            and selection.transport_option_id
            and selection.transport_option_id.startswith(("TRAIN-", "FLIGHT-"))
            else [],
            ticket_option_ids=[
                detail.ticket_option_id
                for detail in (phase2.poi_details if phase2 else [])
                if detail.ticket_option_id
            ],
        ),
    }


def _presentation_kwargs(state: TravelState, patch: TravelStatePatch) -> dict:
    return {
        "plan": patch["current_plan"],
        "entities": state.get("entities") or TravelEntities(),
        "preferences": state.get("effective_preferences") or UserPreferences(),
        "review": state["review_result"],
        "revision_count": state.get("revision_count", 0),
        "tool_results": state.get("tool_results", {}),
        "phase1": state.get("phase1_research"),
    }


def _with_presentation(state: TravelState, patch: TravelStatePatch, present) -> TravelStatePatch:
    if not patch.get("plan_saved"):
        return patch
    reply = present(**_presentation_kwargs(state, patch))
    return {**patch, "messages": [AIMessage(content=reply)]}


async def _with_async_presentation(
    state: TravelState,
    patch: TravelStatePatch,
    presenter: PlanPresenterAgent,
) -> TravelStatePatch:
    if not patch.get("plan_saved"):
        return patch
    reply = await presenter.apresent(**_presentation_kwargs(state, patch))
    return {**patch, "messages": [AIMessage(content=reply)]}
