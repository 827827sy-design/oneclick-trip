from __future__ import annotations

import httpx

from app.domain.models import PersistedPlanState, UserPreferences


class JavaBusinessRepositories:
    """HTTP repositories backed by the authenticated Java business service."""

    def __init__(
        self,
        base_url: str,
        internal_service_secret: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Internal-Service-Key": internal_service_secret},
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_by_user_id(self, user_id: str) -> UserPreferences:
        response = await self._client.get(
            f"/api/internal/ai/users/{user_id}/preferences"
        )
        response.raise_for_status()
        payload = response.json()
        return UserPreferences.model_validate(payload.get("preferences") or {})

    async def save(self, user_id: str, preferences: UserPreferences) -> None:
        response = await self._client.put(
            f"/api/internal/ai/users/{user_id}/preferences",
            json={
                "preferences": preferences.model_dump(mode="json"),
                "source_version": preferences.source_version,
            },
        )
        response.raise_for_status()

    async def get_current(
        self,
        user_id: str,
        conversation_id: str,
    ) -> PersistedPlanState | None:
        response = await self._client.get(
            "/api/internal/ai/plans/current",
            params={"user_id": user_id, "conversation_id": conversation_id},
        )
        response.raise_for_status()
        if not response.content or response.text == "null":
            return None
        return PersistedPlanState.model_validate(response.json())

    async def save_new_version(
        self,
        user_id: str,
        conversation_id: str,
        plan_state: PersistedPlanState,
    ) -> PersistedPlanState:
        response = await self._client.post(
            "/api/internal/ai/plans/versions",
            json={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "plan_state": plan_state.model_dump(mode="json"),
            },
        )
        response.raise_for_status()
        return PersistedPlanState.model_validate(response.json())
