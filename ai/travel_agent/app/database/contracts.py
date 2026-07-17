from __future__ import annotations

from typing import Protocol

from app.domain.models import PersistedPlanState, UserPreferences


class UserPreferenceRepository(Protocol):
    async def get_by_user_id(self, user_id: str) -> UserPreferences:
        """Load long-term travel preferences from MySQL."""

    async def save(self, user_id: str, preferences: UserPreferences) -> None:
        """Persist a reviewed long-term preference update."""


class PlanRepository(Protocol):
    async def get_current(
        self,
        user_id: str,
        conversation_id: str,
    ) -> PersistedPlanState | None:
        """Load the latest valid plan for the conversation."""

    async def save_new_version(
        self,
        user_id: str,
        conversation_id: str,
        plan_state: PersistedPlanState,
    ) -> PersistedPlanState:
        """Atomically persist a validated immutable plan version."""
