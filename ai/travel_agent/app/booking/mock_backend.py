from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from app.booking.contracts import BookingBackendError
from app.domain.models import BookingDraft, BookingStatus


class MockJavaBookingBackend:
    """In-memory stand-in for Java APIs; it intentionally has no token logic."""

    def __init__(
        self,
        *,
        ttl_minutes: int = 15,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._drafts: dict[str, BookingDraft] = {}
        self._lock = RLock()

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
        now = self._clock()
        draft = BookingDraft(
            draft_id=f"MOCK-DRAFT-{uuid4().hex.upper()}",
            status=BookingStatus.PENDING_CONFIRMATION,
            conversation_id=conversation_id,
            user_id=user_id,
            plan_id=plan_id,
            plan_version=plan_version,
            booking_types=list(booking_types),
            selected_option_ids=list(selected_option_ids),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._drafts[draft.draft_id] = draft
        return draft.model_copy(deep=True)

    def confirm_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        with self._lock:
            draft = self._load_bound_draft(
                draft_id=draft_id,
                conversation_id=conversation_id,
                user_id=user_id,
                plan_id=plan_id,
                plan_version=plan_version,
            )
            if draft.status is BookingStatus.CONFIRMED:
                return draft.model_copy(deep=True)
            if draft.status is not BookingStatus.PENDING_CONFIRMATION:
                raise BookingBackendError("DRAFT_NOT_CONFIRMABLE", "Draft is not pending confirmation")
            if draft.expires_at <= self._clock():
                draft.status = BookingStatus.EXPIRED
                raise BookingBackendError("DRAFT_EXPIRED", "Booking draft has expired")
            draft.status = BookingStatus.CONFIRMED
            return draft.model_copy(deep=True)

    def cancel_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        with self._lock:
            draft = self._load_bound_draft(
                draft_id=draft_id,
                conversation_id=conversation_id,
                user_id=user_id,
                plan_id=plan_id,
                plan_version=plan_version,
            )
            if draft.status is BookingStatus.CANCELLED:
                return draft.model_copy(deep=True)
            if draft.status is not BookingStatus.PENDING_CONFIRMATION:
                raise BookingBackendError("DRAFT_NOT_CANCELLABLE", "Draft is not pending confirmation")
            draft.status = BookingStatus.CANCELLED
            return draft.model_copy(deep=True)

    def _load_bound_draft(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise BookingBackendError("DRAFT_NOT_FOUND", "Booking draft does not exist")
        if draft.conversation_id != conversation_id or draft.user_id != user_id:
            raise BookingBackendError("DRAFT_IDENTITY_MISMATCH", "Draft identity binding failed")
        if draft.plan_id != plan_id or draft.plan_version != plan_version:
            raise BookingBackendError("DRAFT_PLAN_STALE", "Draft no longer matches the current plan")
        return draft
