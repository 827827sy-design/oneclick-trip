from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from validate_v3_dsl import check_graph, check_models, load_node_main


ROOT = Path(__file__).resolve().parent
DSL_PATH = ROOT / "oneclick-trip-multi-agent-v4.yml"


def expect(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def main() -> None:
    dsl = yaml.safe_load(DSL_PATH.read_text(encoding="utf-8"))
    nodes_by_id, errors = check_graph(dsl)
    _, model_errors = check_models(dsl, nodes_by_id)
    errors.extend(model_errors)
    edges = dsl["workflow"]["graph"]["edges"]

    quality_case = nodes_by_id["quality_router_v2"]["data"]["cases"][0]
    quality_selectors = {tuple(item["variable_selector"]) for item in quality_case["conditions"]}
    expect(errors, quality_case["logical_operator"] == "and", "first quality gate is not AND")
    expect(errors, ("hard_validator", "hard_pass") in quality_selectors, "first quality gate ignores hard_pass")
    expect(errors, ("review_parser", "verdict") in quality_selectors, "first quality gate ignores soft verdict")

    incoming = {}
    for edge in edges:
        incoming.setdefault(edge["target"], []).append((edge["source"], edge["sourceHandle"]))
    expect(
        errors,
        incoming.get("plan_checkpoint_builder") == [("quality_router_v2", "pass")],
        f"unsafe normal checkpoint inputs: {incoming.get('plan_checkpoint_builder')}",
    )
    expect(
        errors,
        incoming.get("revised_checkpoint_builder") == [("second_validation_router", "pass")],
        f"unsafe revised checkpoint inputs: {incoming.get('revised_checkpoint_builder')}",
    )
    expect(
        errors,
        incoming.get("modify_checkpoint_builder") == [("modify_validation_router", "pass")],
        f"unsafe modify checkpoint inputs: {incoming.get('modify_checkpoint_builder')}",
    )

    for builder_id, assigner_id in [
        ("plan_checkpoint_builder", "plan_checkpoint_assigner"),
        ("revised_checkpoint_builder", "revised_checkpoint_assigner"),
        ("modify_checkpoint_builder", "modify_checkpoint_assigner"),
    ]:
        builder = nodes_by_id[builder_id]
        expect(errors, "cleared_booking_draft_json" in builder["data"]["outputs"], f"{builder_id} does not clear draft")
        assignments = nodes_by_id[assigner_id]["data"]["items"]
        clears = [item for item in assignments if item["variable_selector"] == ["conversation", "booking_draft_json"]]
        expect(errors, bool(clears), f"{assigner_id} does not write cleared draft")

    tool_selector = load_node_main(nodes_by_id, "tool_selector")
    tool_result = tool_selector(
        {"intent": "weather_query", "requested_tools": ["weather", "hotel_search", "evil_admin_tool"]}
    )
    expect(errors, tool_result["selected_tools"] == ["weather"], f"tool allowlist failed: {tool_result}")
    expect(errors, set(tool_result["ignored_tools"]) == {"hotel_search", "evil_admin_tool"}, "ignored tools not audited")

    plan_guard = load_node_main(nodes_by_id, "plan_slot_guard")
    base_entities = {"destination": "成都", "people": 2, "budget": 5000, "budget_scope": "total", "currency": "CNY"}
    start_only = plan_guard({"entities": {**base_entities, "start_date": "2026-08-01"}})
    complete_range = plan_guard(
        {"entities": {**base_entities, "start_date": "2026-08-01", "end_date": "2026-08-03"}}
    )
    with_days = plan_guard({"entities": {**base_entities, "days": 3}})
    expect(errors, start_only["can_execute"] == "false", "start_date alone incorrectly passes planning guard")
    expect(errors, complete_range["can_execute"] == "true", "complete date range incorrectly fails planning guard")
    expect(errors, with_days["can_execute"] == "true", "days duration incorrectly fails planning guard")

    recovery = load_node_main(nodes_by_id, "phase1_recovery_audit")
    recovery_result = recovery(
        json.dumps({"weather": {"status": "MOCK_FAILED"}, "hotel_area": {"status": "MOCK_SUCCESS"}}),
        "模拟天气接口失败",
    )
    recovered_patch = json.loads(recovery_result["recovered_state_patch_json"])
    expect(
        errors,
        recovered_patch["tool_results"]["phase1"]["weather"]["status"] == "MOCK_RETRY_SUCCESS",
        "recovered phase-1 result was not written to state patch",
    )
    reducer_selector = next(
        item["value_selector"]
        for item in nodes_by_id["planning_state_reducer"]["data"]["variables"]
        if item["variable"] == "phase1_patch_json"
    )
    expect(
        errors,
        reducer_selector == ["phase1_recovery_audit", "recovered_state_patch_json"],
        f"reducer still consumes original phase-1 patch: {reducer_selector}",
    )

    loader = load_node_main(nodes_by_id, "current_plan_loader")
    empty_plan = loader({"current_plan_json": "{}"})
    expect(errors, empty_plan["has_current_plan"] == "false", "empty modify request received an invented plan")
    expect(errors, json.loads(empty_plan["current_plan_json"]) == {}, "current plan loader fabricated content")

    plan = {
        "plan_id": "PLAN-100",
        "plan_version": 4,
        "selected_hotels": [
            {"option_id": "HOTEL-1", "name": "酒店一", "bookable": True},
            {"option_id": "HOTEL-2", "name": "酒店二", "bookable": True},
        ],
        "selected_transport": [{"option_id": "TRAIN-1", "name": "G1", "bookable": True}],
    }
    booking_slot_guard = load_node_main(nodes_by_id, "booking_slot_guard")
    missing_option = booking_slot_guard({"booking_type": ["hotel"], "selected_option_ids": []}, json.dumps(plan))
    invalid_option = booking_slot_guard(
        {"booking_type": ["hotel"], "selected_option_ids": ["HOTEL-X"]}, json.dumps(plan)
    )
    valid_option = booking_slot_guard(
        {"booking_type": ["hotel"], "selected_option_ids": ["HOTEL-2"]}, json.dumps(plan)
    )
    wrong_type = booking_slot_guard(
        {"booking_type": ["train"], "selected_option_ids": ["HOTEL-2"]}, json.dumps(plan)
    )
    expect(errors, "MISSING_SELECTED_OPTION_IDS" in missing_option["booking_errors"], "empty booking option was accepted")
    expect(errors, "OPTION_NOT_IN_CURRENT_PLAN" in invalid_option["booking_errors"], "foreign booking option was accepted")
    expect(errors, valid_option["booking_ready"] == "true", f"valid booking selection failed: {valid_option}")
    expect(errors, "OPTION_TYPE_MISMATCH" in wrong_type["booking_errors"], "booking option type mismatch was accepted")

    draft_builder = load_node_main(nodes_by_id, "booking_draft_builder")
    quotes = {
        "hotel": {
            "quote_id": "QUOTE-HOTEL-2",
            "total_price": 916,
            "selected_option_ids": ["HOTEL-2"],
        }
    }
    state = {"selected_option_ids": ["HOTEL-2"]}
    draft_one = json.loads(draft_builder(json.dumps(quotes), state, "conv-100", "user-7", json.dumps(plan))["booking_draft_json"])
    draft_two = json.loads(draft_builder(json.dumps(quotes), state, "conv-100", "user-7", json.dumps(plan))["booking_draft_json"])
    expect(errors, draft_one["draft_id"] != draft_two["draft_id"], "draft_id is reused within one conversation")
    expect(errors, bool(draft_one["confirmation_token"]), "confirmation token was not generated")
    expect(errors, bool(draft_one["draft_hash"]), "draft hash was not generated")
    expect(errors, draft_one["idempotency_key"] == draft_one["draft_id"], "idempotency key is not bound to draft")

    confirmation_guard = load_node_main(nodes_by_id, "booking_confirmation_guard")
    confirmation = f"确认预订 {draft_one['draft_id']} {draft_one['confirmation_token']}"
    valid_confirmation = confirmation_guard(confirmation, "conv-100", "user-7", json.dumps(draft_one), json.dumps(plan))
    expect(errors, valid_confirmation["can_submit"] == "true", f"valid confirmation failed: {valid_confirmation}")
    expect(
        errors,
        confirmation_guard("确认预订", "conv-100", "user-7", json.dumps(draft_one), json.dumps(plan))["validation_error"]
        in {"DRAFT_ID_REQUIRED", "CONFIRMATION_TOKEN_MISMATCH"},
        "confirmation without token was accepted",
    )
    expect(
        errors,
        confirmation_guard(confirmation, "conv-100", "other-user", json.dumps(draft_one), json.dumps(plan))["validation_error"]
        == "DRAFT_USER_MISMATCH",
        "draft was accepted for another user",
    )
    expect(
        errors,
        confirmation_guard(
            confirmation,
            "conv-100",
            "user-7",
            json.dumps(draft_one),
            json.dumps({**plan, "plan_version": 5}),
        )["validation_error"]
        == "DRAFT_PLAN_VERSION_MISMATCH",
        "draft was accepted for another plan version",
    )
    tampered = {**draft_one, "total_price": draft_one["total_price"] + 1}
    expect(
        errors,
        confirmation_guard(confirmation, "conv-100", "user-7", json.dumps(tampered), json.dumps(plan))["validation_error"]
        == "DRAFT_HASH_MISMATCH",
        "tampered draft price passed hash verification",
    )
    expired = {**draft_one, "expires_at": int(time.time()) - 1}
    expect(
        errors,
        confirmation_guard(confirmation, "conv-100", "user-7", json.dumps(expired), json.dumps(plan))["validation_error"]
        == "DRAFT_EXPIRED",
        "expired draft was accepted",
    )

    modify_validator = load_node_main(nodes_by_id, "modify_validator")
    expect(errors, modify_validator("not json")["hard_pass"] == "false", "invalid modified plan passed hard validation")

    print(
        f"nodes={len(nodes_by_id)} edges={len(edges)} "
        f"code_nodes={sum(1 for node in nodes_by_id.values() if node.get('data', {}).get('code'))}"
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: all v4 safety gates and negative-path tests")


if __name__ == "__main__":
    main()
