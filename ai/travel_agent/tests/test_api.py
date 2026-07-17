import asyncio

from httpx import ASGITransport, AsyncClient, Response

from app.main import create_app
from app.memory.checkpoints import InMemoryCheckpointBackend


def request(method: str, path: str, *, json: dict | None = None) -> Response:
    application = create_app(InMemoryCheckpointBackend())

    async def send() -> Response:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def test_health_endpoint() -> None:
    response = request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": "phase_8"}


def test_isolated_app_reports_in_memory_infrastructure() -> None:
    response = request("GET", "/health/infrastructure")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "components": {
            "mysql": "memory",
            "redis": "memory",
            "chroma": "disabled",
            "llm": "rules",
        },
    }


def test_run_endpoint_executes_graph_skeleton() -> None:
    response = request(
        "POST",
        "/v1/agent/runs",
        json={
            "conversation_id": "conversation-api-1",
            "user_id": "user-api-1",
            "message": "帮我规划成都三日游",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "trip_plan"
    assert body["next_action"] == "ask_user"
    assert body["missing_fields"] == ["people", "budget"]
    assert body["message_count"] == 2
    assert "同行人数" in body["reply"]
    assert body["clarification_reply"]["choice_prompt"] == "这次一共几个人出发？"
    assert [action["label"] for action in body["clarification_reply"]["actions"]] == [
        "1 人",
        "2 人",
        "3 人",
        "4 人",
    ]


def test_run_endpoint_returns_phase_three_plan_draft() -> None:
    response = request(
        "POST",
        "/v1/agent/runs",
        json={
            "conversation_id": "conversation-api-plan",
            "user_id": "user-api-plan",
            "message": "帮我规划成都三日游，两个人，总预算5000，喜欢美食",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "trip_plan"
    assert body["next_action"] == "complete"
    assert body["plan_draft"]["destination"] == "成都"
    assert len(body["plan_draft"]["days"]) == 3
    assert body["current_plan"]["destination"] == "成都"
    assert body["plan_version"] == 1
    assert body["hard_validation"]["hard_pass"] is True
    assert body["review_result"]["verdict"] == "pass"
    assert body["plan_saved"] is True
    assert body["selected_tools"] == ["weather"]
    assert set(body["tool_results"]) == {"weather"}
    assert body["tool_attempts"] == {"weather": 1}
    assert body["phase1_research"]["data_mode"] == "OFFLINE_FALLBACK"
    assert body["phase2_research"]["data_mode"] == "OFFLINE_FALLBACK"
    assert "AI 通用知识建议" in body["reply"]


def test_booking_api_does_not_invent_an_option_from_an_ai_plan() -> None:
    application = create_app(InMemoryCheckpointBackend())

    async def execute_flow() -> tuple[Response, Response]:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            plan = await client.post(
                "/v1/agent/runs",
                json={
                    "conversation_id": "conversation-api-booking",
                    "user_id": "user-api-booking",
                    "message": "帮我规划成都三日游，两个人，总预算5000，喜欢美食",
                },
            )
            interrupted = await client.post(
                "/v1/agent/runs",
                json={
                    "conversation_id": "conversation-api-booking",
                    "user_id": "user-api-booking",
                    "message": "帮我预订酒店",
                },
            )
            return plan, interrupted

    plan, interrupted = asyncio.run(execute_flow())

    assert plan.status_code == 200
    assert interrupted.status_code == 200
    assert interrupted.json()["interrupted"] is False
    assert interrupted.json()["next_action"] == "ask_user"
    assert "selected_option_ids" in interrupted.json()["missing_fields"]


def test_resume_without_pending_booking_is_rejected_but_query_still_works() -> None:
    application = create_app(InMemoryCheckpointBackend())

    async def execute_flow() -> tuple[Response, Response]:
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            wrong_user = await client.post(
                "/v1/agent/runs/resume",
                json={
                    "conversation_id": "conversation-api-guard",
                    "user_id": "owner-user",
                    "confirmed": True,
                },
            )
            bypass = await client.post(
                "/v1/agent/runs",
                json={
                    "conversation_id": "conversation-api-guard",
                    "user_id": "owner-user",
                    "message": "成都明天天气怎么样？",
                },
            )
            return wrong_user, bypass

    wrong_user, bypass = asyncio.run(execute_flow())

    assert wrong_user.status_code == 409
    assert bypass.status_code == 200
    assert bypass.json()["selected_tools"] == ["weather"]
