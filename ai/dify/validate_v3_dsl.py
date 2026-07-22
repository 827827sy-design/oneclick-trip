from __future__ import annotations

import inspect
import json
import time
from collections import Counter, deque
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
DSL_PATH = ROOT / "oneclick-trip-multi-agent-v3.yml"


def load_node_main(nodes_by_id: dict[str, dict], node_id: str):
    namespace: dict = {}
    code = nodes_by_id[node_id]["data"]["code"]
    exec(compile(code, f"<{node_id}>", "exec"), namespace)
    return namespace["main"]


def check_graph(dsl: dict) -> tuple[dict[str, dict], list[str]]:
    graph = dsl["workflow"]["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    node_ids = [node["id"] for node in nodes]
    edge_ids = [edge["id"] for edge in edges]
    errors: list[str] = []

    duplicate_nodes = [key for key, count in Counter(node_ids).items() if count > 1]
    duplicate_edges = [key for key, count in Counter(edge_ids).items() if count > 1]
    if duplicate_nodes:
        errors.append(f"duplicate node ids: {duplicate_nodes}")
    if duplicate_edges:
        errors.append(f"duplicate edge ids: {duplicate_edges}")

    nodes_by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        if edge["source"] not in nodes_by_id or edge["target"] not in nodes_by_id:
            errors.append(f"broken edge: {edge['id']}")

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge["source"] in adjacency:
            adjacency[edge["source"]].append(edge["target"])
    reachable: set[str] = set()
    queue = deque(["start"])
    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(adjacency.get(node_id, []))
    unreachable = sorted(set(node_ids) - reachable)
    if unreachable:
        errors.append(f"unreachable nodes: {unreachable}")

    builtins = {"sys", "conversation", "env"}
    for node in nodes:
        for variable in node.get("data", {}).get("variables", []):
            selector = variable.get("value_selector") or []
            if selector and selector[0] not in nodes_by_id and selector[0] not in builtins:
                errors.append(f"unknown selector source: {node['id']} -> {selector}")

    for node in nodes:
        code = node.get("data", {}).get("code")
        if code:
            try:
                compile(code, f"<{node['id']}>", "exec")
            except SyntaxError as exc:
                errors.append(f"code syntax error in {node['id']}: {exc}")

    return nodes_by_id, errors


def check_state_behaviour(nodes_by_id: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    now = int(time.time())

    hydrate = load_node_main(nodes_by_id, "checkpoint_hydrator")
    hydrated = hydrate(
        "conv-001",
        json.dumps({"active_plan_id": "PLAN-1"}),
        json.dumps({"plan_id": "PLAN-1", "plan_version": 3}),
        json.dumps({"draft_id": "DRAFT-1", "status": "PENDING_CONFIRMATION"}),
        7,
    )
    context = json.loads(hydrated["checkpoint_context_json"])
    if context.get("active_plan_id") != "PLAN-1" or context.get("checkpoint_version") != 7:
        errors.append("checkpoint hydration did not restore plan/version")

    guard = load_node_main(nodes_by_id, "booking_confirmation_guard")
    pending = {
        "draft_id": "DRAFT-1",
        "thread_id": "conv-001",
        "status": "PENDING_CONFIRMATION",
        "expires_at": now + 600,
        "booking_types": ["hotel"],
    }
    guard_cases = [
        ("valid draft", guard("确认预订", "conv-001", json.dumps(pending)), "true", ""),
        ("missing draft", guard("确认预订", "conv-001", "{}"), "false", "NO_PENDING_DRAFT"),
        ("wrong thread", guard("确认预订", "conv-002", json.dumps(pending)), "false", "DRAFT_THREAD_MISMATCH"),
        (
            "submitted draft",
            guard("确认预订", "conv-001", json.dumps({**pending, "status": "SUBMITTED"})),
            "false",
            "DRAFT_NOT_CONFIRMABLE",
        ),
        (
            "expired draft",
            guard("确认预订", "conv-001", json.dumps({**pending, "expires_at": now - 1})),
            "false",
            "DRAFT_EXPIRED",
        ),
        ("no explicit confirmation", guard("看看价格", "conv-001", json.dumps(pending)), "false", "EXPLICIT_CONFIRMATION_REQUIRED"),
    ]
    for label, result, can_submit, error_code in guard_cases:
        if result["can_submit"] != can_submit or result["validation_error"] != error_code:
            errors.append(f"booking guard failed: {label}: {result}")

    recovery = load_node_main(nodes_by_id, "query_recovery_policy")
    recovery_cases = [
        ({"tool_errors": []}, "continue"),
        ({"tool_errors": [{"retryable": True, "attempt": 1, "fallback_available": True}]}, "retry"),
        ({"tool_errors": [{"retryable": False, "attempt": 1, "fallback_available": True}]}, "fallback"),
        ({"tool_errors": [{"retryable": False, "attempt": 1, "fallback_available": False}]}, "degraded"),
    ]
    for payload, expected in recovery_cases:
        actual = recovery(json.dumps(payload))["recovery_action"]
        if actual != expected:
            errors.append(f"recovery policy expected {expected}, got {actual}")

    retry = load_node_main(nodes_by_id, "query_retry_executor")
    retry_result = json.loads(
        retry(json.dumps({"tool_results": {}, "tool_errors": [{"tool": "weather"}]}))["query_result_json"]
    )
    if retry_result["tool_results"]["weather"]["status"] != "MOCK_RETRY_SUCCESS":
        errors.append("retry executor did not produce recovered result")

    invalidate = load_node_main(nodes_by_id, "submit_state_builder")
    submitted = invalidate(json.dumps(pending), "{}", 7)
    if json.loads(submitted["booking_draft_json"])["status"] != "SUBMITTED":
        errors.append("submitted draft was not invalidated")
    if submitted["next_checkpoint_version"] != 8:
        errors.append("checkpoint version did not advance after submit")

    return errors


def check_models(dsl: dict, nodes_by_id: dict[str, dict]) -> tuple[Counter, list[str]]:
    models = Counter(
        node["data"]["model"]["name"]
        for node in nodes_by_id.values()
        if node.get("data", {}).get("type") == "llm"
    )
    errors: list[str] = []
    required_flash = {
        "intent_agent",
        "memory_candidate_agent",
        "clarification_agent",
        "query_presenter",
        "booking_confirmation",
    }
    required_pro = {"candidate_selector", "planner", "soft_reviewer", "revision", "modify_agent", "final_reviewer"}
    for node_id in required_flash:
        if nodes_by_id[node_id]["data"]["model"]["name"] != "deepseek-v4-flash":
            errors.append(f"{node_id} is not routed to Flash")
    for node_id in required_pro:
        if nodes_by_id[node_id]["data"]["model"]["name"] != "deepseek-v4-pro":
            errors.append(f"{node_id} is not routed to Pro")

    variable_names = {item["name"] for item in dsl["workflow"].get("conversation_variables", [])}
    required_variables = {
        "travel_checkpoint_json",
        "current_plan_json",
        "booking_draft_json",
        "checkpoint_version",
        "last_tool_errors_json",
    }
    missing = sorted(required_variables - variable_names)
    if missing:
        errors.append(f"missing conversation variables: {missing}")
    return models, errors


def main() -> None:
    dsl = yaml.safe_load(DSL_PATH.read_text(encoding="utf-8"))
    nodes_by_id, errors = check_graph(dsl)
    errors.extend(check_state_behaviour(nodes_by_id))
    models, model_errors = check_models(dsl, nodes_by_id)
    errors.extend(model_errors)

    code_nodes = sum(1 for node in nodes_by_id.values() if node.get("data", {}).get("code"))
    print(f"nodes={len(nodes_by_id)} edges={len(dsl['workflow']['graph']['edges'])} code_nodes={code_nodes}")
    print("models=" + json.dumps(models, ensure_ascii=False, sort_keys=True))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: graph, selectors, code syntax, state recovery, draft binding, failure recovery, and model routing")


if __name__ == "__main__":
    main()
