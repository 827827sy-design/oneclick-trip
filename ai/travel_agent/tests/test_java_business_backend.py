import asyncio

import httpx

from app.booking.java_backend import JavaBookingBackend
from app.database.java_backend import JavaBusinessRepositories
from app.domain.models import (
    BookingStatus,
    ItineraryDay,
    PersistedPlanState,
    TravelPlan,
    UserPreferences,
)


def test_java_preference_repository_uses_internal_service_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "user_id": "42",
                    "preferences": {
                        "liked_tags": ["自然"],
                        "source_version": 2,
                    },
                    "source_version": 2,
                },
            )
        return httpx.Response(200, json={})

    async def execute() -> UserPreferences:
        repository = JavaBusinessRepositories("http://java", "shared-secret")
        await repository._client.aclose()
        repository._client = httpx.AsyncClient(
            base_url="http://java",
            headers={"X-Internal-Service-Key": "shared-secret"},
            transport=httpx.MockTransport(handler),
        )
        preferences = await repository.get_by_user_id("42")
        await repository.save("42", preferences)
        await repository.close()
        return preferences

    preferences = asyncio.run(execute())

    assert preferences.liked_tags == ["自然"]
    assert requests[0].headers["X-Internal-Service-Key"] == "shared-secret"
    assert requests[1].method == "PUT"


def test_java_plan_repository_preserves_structured_plan_state() -> None:
    plan_state = PersistedPlanState(
        plan=TravelPlan(
            plan_id="plan-1",
            version=1,
            destination="成都",
            days=[ItineraryDay(day_index=1)],
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=plan_state.model_dump(mode="json"))
        return httpx.Response(200, json=plan_state.model_dump(mode="json"))

    async def execute() -> tuple[PersistedPlanState | None, PersistedPlanState]:
        repository = JavaBusinessRepositories("http://java", "shared-secret")
        await repository._client.aclose()
        repository._client = httpx.AsyncClient(
            base_url="http://java",
            transport=httpx.MockTransport(handler),
        )
        current = await repository.get_current("42", "conversation-1")
        saved = await repository.save_new_version("42", "conversation-1", plan_state)
        await repository.close()
        return current, saved

    current, saved = asyncio.run(execute())

    assert current is not None
    assert current.plan.plan_id == "plan-1"
    assert saved.plan.destination == "成都"


def test_java_booking_backend_keeps_confirmation_token_out_of_state() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = "confirmed" if request.url.path.endswith("/confirm") else "pending_confirmation"
        payload = {
            "draft_id": "DRAFT-1",
            "status": status,
            "conversation_id": "conversation-1",
            "user_id": "42",
            "plan_id": "plan-1",
            "plan_version": 1,
            "booking_types": ["hotel"],
            "selected_option_ids": ["hotel-1"],
            "created_at": "2026-07-22T10:00:00",
            "expires_at": "2026-07-22T10:15:00",
        }
        if status == "pending_confirmation":
            payload["confirmation_token"] = "server-generated-token"
        return httpx.Response(200, json=payload)

    backend = JavaBookingBackend("http://java", "shared-secret")
    backend._client.close()
    backend._client = httpx.Client(
        base_url="http://java",
        transport=httpx.MockTransport(handler),
    )

    draft = backend.create_booking_draft(
        conversation_id="conversation-1",
        user_id="42",
        plan_id="plan-1",
        plan_version=1,
        booking_types=["hotel"],
        selected_option_ids=["hotel-1"],
    )
    confirmed = backend.confirm_booking(
        draft_id=draft.draft_id,
        conversation_id="conversation-1",
        user_id="42",
        plan_id="plan-1",
        plan_version=1,
    )
    backend.close()

    assert draft.status is BookingStatus.PENDING_CONFIRMATION
    assert "confirmation_token" not in draft.model_dump()
    assert confirmed.status is BookingStatus.CONFIRMED
    confirm_body = requests[1].read().decode("utf-8")
    assert "server-generated-token" in confirm_body
    assert "idempotency_key" in confirm_body
