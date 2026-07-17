from __future__ import annotations

from typing import Protocol

from app.domain.models import BookingDraft


class BookingBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BookingBackend(Protocol):
    """Boundary owned by the Java business backend in production."""

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
        """Create a backend-owned draft and return only its public reference."""

    def confirm_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        """Confirm through the backend security boundary."""

    def cancel_booking(
        self,
        *,
        draft_id: str,
        conversation_id: str,
        user_id: str,
        plan_id: str,
        plan_version: int,
    ) -> BookingDraft:
        """Cancel a pending draft through the backend boundary."""
