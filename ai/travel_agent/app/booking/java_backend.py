from __future__ import annotations

import hashlib

import httpx
import redis

from app.booking.contracts import BookingBackendError
from app.domain.models import BookingDraft


class JavaBookingBackend:
    """Calls Java-owned draft APIs without placing confirmation tokens in TravelState."""

    def __init__(
        self,
        base_url: str,
        internal_service_secret: str,
        *,
        timeout_seconds: float = 10.0,
        redis_url: str | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Internal-Service-Key": internal_service_secret},
            timeout=timeout_seconds,
        )
        self._confirmation_tokens: dict[str, str] = {}
        self._redis: redis.Redis | None = None
        if redis_url:
            candidate = redis.Redis.from_url(redis_url, decode_responses=True)
            try:
                candidate.ping()
                self._redis = candidate
            except redis.RedisError:
                candidate.close()

    def close(self) -> None:
        self._client.close()
        if self._redis is not None:
            self._redis.close()

    def create_booking_draft(
        self,
        *,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
        booking_types: list[str],
        selected_option_ids: list[str],
    ) -> BookingDraft:
        payload = self._post(
            "/api/internal/ai/booking-drafts",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "booking_types": booking_types,
                "selected_option_ids": selected_option_ids,
            },
        )
        token = str(payload.pop("confirmation_token", ""))
        draft = BookingDraft.model_validate(payload)
        if not token:
            raise BookingBackendError(
                "CONFIRMATION_TOKEN_MISSING",
                "Java backend did not return a confirmation token",
            )
        self._store_confirmation_token(draft.draft_id, token)
        return draft

    def confirm_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        return self._change_status(
            "confirm",
            draft_id=draft_id,
            conversation_id=conversation_id,
            user_id=user_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )

    def cancel_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        return self._change_status(
            "cancel",
            draft_id=draft_id,
            conversation_id=conversation_id,
            user_id=user_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )

    def _change_status(
        self,
        action: str,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        token = self._load_confirmation_token(draft_id)
        if not token:
            raise BookingBackendError(
                "CONFIRMATION_CONTEXT_LOST",
                "Confirmation context is no longer available; create a new draft",
            )
        idempotency_key = hashlib.sha256(
            f"{draft_id}:{action}:{user_id}".encode("utf-8")
        ).hexdigest()
        payload = self._post(
            f"/api/internal/ai/booking-drafts/{draft_id}/{action}",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "confirmation_token": token,
                "idempotency_key": idempotency_key,
            },
        )
        payload.pop("confirmation_token", None)
        return BookingDraft.model_validate(payload)

    def _store_confirmation_token(self, draft_id: str, token: str) -> None:
        self._confirmation_tokens[draft_id] = token
        if self._redis is not None:
            self._redis.setex(f"oneclick-trip:booking-token:{draft_id}", 15 * 60, token)

    def _load_confirmation_token(self, draft_id: str) -> str | None:
        token = self._confirmation_tokens.get(draft_id)
        if token or self._redis is None:
            return token
        cached = self._redis.get(f"oneclick-trip:booking-token:{draft_id}")
        if cached:
            self._confirmation_tokens[draft_id] = cached
        return cached

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
            return dict(response.json())
        except httpx.HTTPStatusError as exc:
            message = _error_message(exc.response)
            raise BookingBackendError("JAVA_BOOKING_REJECTED", message) from exc
        except httpx.HTTPError as exc:
            raise BookingBackendError("JAVA_BACKEND_UNAVAILABLE", str(exc)) from exc


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("message") or payload.get("detail") or response.text)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
