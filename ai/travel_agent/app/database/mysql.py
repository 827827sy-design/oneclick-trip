from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    and_,
    select,
    update,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.domain.models import PersistedPlanState, UserPreferences


metadata = MetaData()

user_travel_preferences = Table(
    "ai_user_travel_preferences",
    metadata,
    # User identity is owned by the Java backend; this table stores only its reference.
    Column("user_id", String(128), primary_key=True),
    Column("preference_json", JSON, nullable=False),
    Column("source_version", Integer, nullable=False, default=0),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    ),
)

travel_plan_versions = Table(
    "ai_travel_plan_versions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False),
    Column("conversation_id", String(128), nullable=False),
    Column("plan_id", String(128), nullable=False),
    Column("plan_version", Integer, nullable=False),
    Column("destination", String(128), nullable=False),
    Column("plan_json", JSON, nullable=False),
    Column("is_current", Boolean, nullable=False, default=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    ),
    UniqueConstraint(
        "user_id",
        "conversation_id",
        "plan_id",
        "plan_version",
        name="uq_ai_plan_version",
    ),
    Index("ix_ai_plan_current", "user_id", "conversation_id", "is_current"),
)


class MySQLRepositories:
    """Async MySQL implementation for preferences and immutable plan versions."""

    def __init__(self, dsn: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(
            dsn,
            echo=echo,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def ping(self) -> bool:
        async with self.engine.connect() as connection:
            await connection.execute(select(1))
        return True

    async def close(self) -> None:
        await self.engine.dispose()

    async def get_by_user_id(self, user_id: str) -> UserPreferences:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(user_travel_preferences.c.preference_json).where(
                        user_travel_preferences.c.user_id == user_id
                    )
                )
            ).scalar_one_or_none()
        return UserPreferences.model_validate(row) if row else UserPreferences()

    async def save(self, user_id: str, preferences: UserPreferences) -> None:
        now = datetime.now(UTC)
        statement = mysql_insert(user_travel_preferences).values(
            user_id=user_id,
            preference_json=preferences.model_dump(mode="json"),
            source_version=preferences.source_version,
            updated_at=now,
        )
        statement = statement.on_duplicate_key_update(
            preference_json=statement.inserted.preference_json,
            source_version=statement.inserted.source_version,
            updated_at=now,
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def get_current(
        self,
        user_id: str,
        conversation_id: str,
    ) -> PersistedPlanState | None:
        statement = (
            select(travel_plan_versions.c.plan_json)
            .where(
                and_(
                    travel_plan_versions.c.user_id == user_id,
                    travel_plan_versions.c.conversation_id == conversation_id,
                    travel_plan_versions.c.is_current.is_(True),
                )
            )
            .order_by(travel_plan_versions.c.plan_version.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        if not row:
            return None
        if "plan" in row:
            return PersistedPlanState.model_validate(row)
        return PersistedPlanState(plan=row)

    async def save_new_version(
        self,
        user_id: str,
        conversation_id: str,
        plan_state: PersistedPlanState,
    ) -> PersistedPlanState:
        plan = plan_state.plan
        values = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "plan_id": plan.plan_id,
            "plan_version": plan.version,
            "destination": plan.destination,
            "plan_json": plan_state.model_dump(mode="json"),
            "is_current": True,
            "created_at": plan.created_at,
        }
        async with self._sessions.begin() as session:
            await session.execute(
                update(travel_plan_versions)
                .where(
                    and_(
                        travel_plan_versions.c.user_id == user_id,
                        travel_plan_versions.c.conversation_id == conversation_id,
                        travel_plan_versions.c.is_current.is_(True),
                    )
                )
                .values(is_current=False)
            )
            statement = mysql_insert(travel_plan_versions).values(**values)
            statement = statement.on_duplicate_key_update(
                plan_json=statement.inserted.plan_json,
                destination=statement.inserted.destination,
                is_current=True,
            )
            await session.execute(statement)
        return plan_state
