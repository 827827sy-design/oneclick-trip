import asyncio

from langchain_core.messages import HumanMessage

from app.domain.models import PersistedPlanState, UserPreferences
from app.graph.builder import build_travel_graph
from app.graph.nodes.load_user_memory import make_load_user_memory_node
from app.memory.checkpoints import InMemoryCheckpointBackend


class FakeRepositories:
    def __init__(self) -> None:
        self.preferences: dict[str, UserPreferences] = {}
        self.plans: dict[tuple[str, str], PersistedPlanState] = {}
        self.preference_reads = 0

    async def get_by_user_id(self, user_id: str) -> UserPreferences:
        self.preference_reads += 1
        return self.preferences.get(user_id, UserPreferences())

    async def save(self, user_id: str, preferences: UserPreferences) -> None:
        self.preferences[user_id] = preferences.model_copy(deep=True)

    async def get_current(
        self,
        user_id: str,
        conversation_id: str,
    ) -> PersistedPlanState | None:
        return self.plans.get((user_id, conversation_id))

    async def save_new_version(
        self,
        user_id: str,
        conversation_id: str,
        plan_state: PersistedPlanState,
    ) -> PersistedPlanState:
        self.plans[(user_id, conversation_id)] = plan_state.model_copy(deep=True)
        return plan_state


def test_plan_and_preferences_restore_after_checkpoint_loss() -> None:
    repositories = FakeRepositories()
    conversation_id = "persistence-restore"
    user_id = "persistent-user"

    async def execute() -> tuple[dict, dict]:
        first_graph = build_travel_graph(
            InMemoryCheckpointBackend().create(),
            plan_repository=repositories,
            preference_repository=repositories,
        )
        first = await first_graph.ainvoke(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "messages": [
                    HumanMessage(
                        content="帮我规划成都三日游，两个人，总预算5000；我以后旅行都喜欢美食"
                    )
                ],
            },
            config={"configurable": {"thread_id": conversation_id}},
        )

        fresh_graph = build_travel_graph(
            InMemoryCheckpointBackend().create(),
            plan_repository=repositories,
            preference_repository=repositories,
        )
        modified = await fresh_graph.ainvoke(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "messages": [HumanMessage(content="预算降低1000")],
            },
            config={"configurable": {"thread_id": conversation_id}},
        )
        return first, modified

    first, modified = asyncio.run(execute())

    assert first["plan_saved"] is True
    assert repositories.preferences[user_id].liked_tags == ["美食"]
    assert modified["plan_saved"] is True, (
        modified.get("planning_errors"),
        modified.get("modification_errors"),
        modified.get("hard_validation"),
        modified.get("review_result"),
    )
    assert modified["current_plan"].plan_id == first["current_plan"].plan_id
    assert modified["plan_version"] == 2
    assert repositories.plans[(user_id, conversation_id)].plan.version == 2


def test_load_user_memory_can_ignore_persisted_preferences_for_one_turn() -> None:
    repositories = FakeRepositories()
    repositories.preferences["private-user"] = UserPreferences(liked_tags=["美食"])
    node = make_load_user_memory_node(repositories)

    result = asyncio.run(
        node(
            {
                "user_id": "private-user",
                "ignore_user_preferences": True,
            }
        )
    )

    assert result["user_preferences"].liked_tags == []
    assert result["user_preferences"].disliked_tags == []
    assert result["user_preferences"].pace is None
    assert repositories.preference_reads == 0
