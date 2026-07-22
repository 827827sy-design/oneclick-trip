from __future__ import annotations

import json
from pathlib import Path

import yaml

import build_v2_dsl as v2
import build_v3_dsl as v3


ROOT = Path(__file__).resolve().parent
BASE_DSL = ROOT / "oneclick-trip-multi-agent-v3.yml"
OUTPUT_DSL = ROOT / "oneclick-trip-multi-agent-v4.yml"


def and_case(case_id: str, conditions: list[tuple[list[str], str]]) -> dict:
    return {
        "case_id": case_id,
        "conditions": [
            {
                "comparison_operator": "is",
                "id": f"condition-{case_id}-{index}",
                "value": value,
                "varType": "string",
                "variable_selector": selector,
            }
            for index, (selector, value) in enumerate(conditions, start=1)
        ],
        "id": case_id,
        "logical_operator": "and",
    }


def append_assigner_item(node: dict, variable_name: str, selector: list[str]) -> None:
    node["data"]["items"].append(
        {
            "input_type": "variable",
            "operation": "over-write",
            "value": selector,
            "variable_selector": ["conversation", variable_name],
            "write_mode": "over-write",
        }
    )


def main() -> None:
    v3.main()
    dsl = yaml.safe_load(BASE_DSL.read_text(encoding="utf-8"))
    workflow = dsl["workflow"]
    graph = workflow["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    by_id = {node["id"]: node for node in nodes}

    # A plan may be persisted only when deterministic validation passes.
    by_id["quality_router_v2"]["data"]["cases"] = [
        and_case(
            "pass",
            [
                (["hard_validator", "hard_pass"], "true"),
                (["review_parser", "verdict"], "pass"),
            ],
        )
    ]

    second_validator = by_id["second_hard_validator"]
    second_validator["data"]["code"] = second_validator["data"]["code"].replace(
        "return {'validation_errors':errors,'plan_json':json.dumps(plan,ensure_ascii=False),'revision_count':1}",
        "return {'hard_pass':'true' if not errors else 'false','validation_errors':errors,'plan_json':json.dumps(plan,ensure_ascii=False),'revision_count':1}",
    )
    second_validator["data"]["outputs"]["hard_pass"] = {"children": None, "type": "string"}

    modify_validator = by_id["modify_validator"]
    modify_validator["data"]["code"] = modify_validator["data"]["code"].replace(
        "return {'plan_json':json.dumps(plan,ensure_ascii=False),'validation_errors':errors}",
        "return {'hard_pass':'true' if not errors else 'false','plan_json':json.dumps(plan,ensure_ascii=False),'validation_errors':errors}",
    )
    modify_validator["data"]["outputs"]["hard_pass"] = {"children": None, "type": "string"}

    second_validation_router = v2.if_node(
        "second_validation_router",
        "第二轮硬校验写入闸门",
        [v2.case("pass", ["second_hard_validator", "hard_pass"], "true")],
        8320,
        700,
    )
    second_validation_failure_answer = v2.answer_node(
        "second_validation_failure_answer",
        "回复 - 修订仍未通过硬校验",
        "修订后的方案仍存在硬错误，因此没有保存为当前方案。错误：{{#second_hard_validator.validation_errors#}}。请调整需求后重新生成。",
        8680,
        840,
    )
    modify_validation_router = v2.if_node(
        "modify_validation_router",
        "修改方案硬校验写入闸门",
        [v2.case("pass", ["modify_validator", "hard_pass"], "true")],
        5400,
        980,
    )
    modify_validation_failure_answer = v2.answer_node(
        "modify_validation_failure_answer",
        "回复 - 修改失败并保留旧方案",
        "修改结果未通过硬校验，旧方案保持不变。错误：{{#modify_validator.validation_errors#}}。",
        5760,
        1120,
    )
    nodes.extend(
        [
            second_validation_router,
            second_validation_failure_answer,
            modify_validation_router,
            modify_validation_failure_answer,
        ]
    )

    # Saving any new plan invalidates every draft created from an older plan version.
    for builder_id, assigner_id in [
        ("plan_checkpoint_builder", "plan_checkpoint_assigner"),
        ("revised_checkpoint_builder", "revised_checkpoint_assigner"),
        ("modify_checkpoint_builder", "modify_checkpoint_assigner"),
    ]:
        builder = by_id[builder_id]
        builder["data"]["code"] = builder["data"]["code"].replace(
            "'checkpoint_status': 'MOCK_SAVED'\n    }",
            "'checkpoint_status': 'MOCK_SAVED',\n        'cleared_booking_draft_json': '{}'\n    }",
        )
        builder["data"]["outputs"]["cleared_booking_draft_json"] = {"children": None, "type": "string"}
        append_assigner_item(by_id[assigner_id], "booking_draft_json", [builder_id, "cleared_booking_draft_json"])

    normalizer = by_id["state_normalizer"]
    normalizer["data"]["code"] = normalizer["data"]["code"].replace(
        "    state = {\n",
        """    entities = dict(data.get('entities') or {})
    if entities.get('budget') is not None:
        if not entities.get('budget_scope'):
            entities['budget_scope'] = 'per_person' if any(word in text for word in ['人均', '每人']) else 'total'
        entities['currency'] = entities.get('currency') or 'CNY'
    state = {
""",
    )
    normalizer["data"]["code"] = normalizer["data"]["code"].replace(
        "        'entities': data.get('entities', {}),",
        "        'entities': entities,",
    )
    by_id["intent_agent"]["data"]["prompt_template"][0]["text"] += """
日期槽位必须分别输出 days、start_date、end_date；只有 start_date 时不得把完整规划标为就绪。
预算必须输出 budget、budget_scope=total|per_person、currency=CNY。预订必须提取 booking_type 和用户明确选择的 selected_option_ids，不得凭空选择。"""

    by_id["tool_selector"]["data"]["code"] = """
def main(state: dict) -> dict:
    intent = (state or {}).get('intent', 'general_qa')
    requested = list(dict.fromkeys((state or {}).get('requested_tools') or []))
    allowlist = {
        'weather_query': {'weather'},
        'hotel_query': {'hotel_search'},
        'transport_query': {'route', 'train_search', 'flight_search'},
        'general_qa': {'poi_rag'},
        'trip_plan': {'weather', 'intercity_transport', 'hotel_area', 'poi_candidates'},
        'modify_plan': set()
    }
    defaults = {
        'weather_query':['weather'], 'hotel_query':['hotel_search'],
        'transport_query':['route','train_search','flight_search'],
        'general_qa':['poi_rag'],
        'trip_plan':['weather','intercity_transport','hotel_area','poi_candidates'],
        'modify_plan':[]
    }
    allowed = allowlist.get(intent, set())
    approved = [tool for tool in requested if tool in allowed]
    ignored = [tool for tool in requested if tool not in allowed]
    selected = approved or defaults.get(intent, [])
    if intent == 'trip_plan':
        # Complete planning always performs the four dependency-free phase-1 queries.
        phase1 = defaults['trip_plan']
        selected = list(dict.fromkeys(phase1 + approved))
    else:
        phase1 = selected
    return {'intent':intent,'selected_tools':selected,'phase1_tools':phase1,'ignored_tools':ignored}
""".strip()
    by_id["tool_selector"]["data"]["outputs"]["ignored_tools"] = {"children": None, "type": "array[string]"}

    by_id["plan_slot_guard"]["data"]["code"] = """
def main(state: dict) -> dict:
    entities=(state or {}).get('entities') or {}
    missing=[]
    if not entities.get('destination'): missing.append('destination')
    has_duration=bool(entities.get('days')) or bool(entities.get('start_date') and entities.get('end_date'))
    if not has_duration: missing.append('days_or_complete_date_range')
    if not entities.get('people'): missing.append('people')
    if entities.get('budget') is None: missing.append('budget')
    if entities.get('budget') is not None and entities.get('budget_scope') not in {'total','per_person'}:
        missing.append('budget_scope')
    if entities.get('budget') is not None and not entities.get('currency'):
        missing.append('currency')
    return {'can_execute':'true' if not missing else 'false','missing_fields':missing}
""".strip()

    for validator_id in ["hard_validator", "second_hard_validator"]:
        validator = by_id[validator_id]
        validator["data"]["code"] = validator["data"]["code"].replace(
            "budget=(state or {}).get('entities',{}).get('budget')",
            "entities=(state or {}).get('entities',{}); budget=entities.get('budget'); scope=entities.get('budget_scope','total'); people=entities.get('people',1); budget=(budget*people if scope=='per_person' and isinstance(people,(int,float)) and isinstance(budget,(int,float)) else budget)",
        )

    by_id["planner"]["data"]["prompt_template"][0]["text"] += """
预算必须携带 budget_scope=total|per_person 和 currency=CNY。所有可预订项必须有唯一 option_id、bookable=true|false；汇总输出 bookable_option_ids。"""

    # Recovery output must be the exact state patch consumed by the reducer.
    recovery_audit = by_id["phase1_recovery_audit"]
    recovery_audit["data"]["code"] = """
import json

def main(phase1_results_json: str, query: str) -> dict:
    try: results=json.loads(phase1_results_json or '{}')
    except Exception: results={}
    trace=[]
    if '模拟天气接口失败' in (query or '') and 'weather' in results:
        results['weather']['status']='MOCK_RETRY_SUCCESS'
        results['weather']['attempt']=2
        trace.append({'tool':'weather','action':'retry','result':'success','attempt':2})
    if '模拟酒店接口失败' in (query or '') and 'hotel_area' in results:
        results['hotel_area']['status']='MOCK_FALLBACK_SUCCESS'
        results['hotel_area']['data_mode']='MOCK_CACHE'
        trace.append({'tool':'hotel_area','action':'fallback','source':'cached_area_snapshot'})
    patch={'tool_results':{'phase1':results},'tool_errors':[],'recovery_trace':trace}
    return {
        'phase1_results_json':json.dumps(results,ensure_ascii=False),
        'recovery_trace_json':json.dumps(trace,ensure_ascii=False),
        'recovered_state_patch_json':json.dumps(patch,ensure_ascii=False)
    }
""".strip()
    recovery_audit["data"]["outputs"]["recovered_state_patch_json"] = {"children": None, "type": "string"}
    reducer = by_id["planning_state_reducer"]
    for variable in reducer["data"]["variables"]:
        if variable["variable"] == "phase1_patch_json":
            variable["value_selector"] = ["phase1_recovery_audit", "recovered_state_patch_json"]

    # A modify request never receives an invented plan.
    by_id["current_plan_loader"]["data"]["code"] = """
import json

def main(state: dict) -> dict:
    raw=(state or {}).get('current_plan_json') or '{}'
    try: plan=json.loads(raw)
    except Exception: plan={}
    exists=bool(plan.get('plan_id') and plan.get('plan_version'))
    return {
        'current_plan_json':json.dumps(plan if exists else {},ensure_ascii=False),
        'current_plan_id':plan.get('plan_id') or '',
        'plan_version':plan.get('plan_version') or 0,
        'has_current_plan':'true' if exists else 'false'
    }
""".strip()
    by_id["current_plan_loader"]["data"]["outputs"]["has_current_plan"] = {"children": None, "type": "string"}
    current_plan_existence_guard = v2.code_node(
        "current_plan_existence_guard",
        "当前方案存在性守卫",
        "只有真实保存过的结构化方案可以进入局部修改。",
        """
import json
def main(current_plan_json: str) -> dict:
    try: plan=json.loads(current_plan_json or '{}')
    except Exception: plan={}
    exists=bool(plan.get('plan_id') and plan.get('plan_version'))
    return {'can_modify':'true' if exists else 'false','reason':'' if exists else 'NO_CURRENT_PLAN'}
""",
        [("current_plan_json", ["current_plan_loader", "current_plan_json"])],
        {"can_modify": "string", "reason": "string"},
        4680,
        980,
    )
    current_plan_existence_router = v2.if_node(
        "current_plan_existence_router",
        "当前方案存在性路由",
        [v2.case("exists", ["current_plan_existence_guard", "can_modify"], "true")],
        4860,
        980,
    )
    no_current_plan_answer = v2.answer_node(
        "no_current_plan_answer",
        "回复 - 当前没有可修改方案",
        "当前对话中没有已保存的行程方案，因此不能执行修改。请先生成一份行程，再告诉我需要调整哪一天。",
        5220,
        1120,
    )
    nodes.extend([current_plan_existence_guard, current_plan_existence_router, no_current_plan_answer])

    booking_slot_guard = v2.code_node(
        "booking_slot_guard",
        "预订槽位与选项归属守卫",
        "预订前验证当前方案、预订类型、选项 ID、选项归属和可预订状态。",
        """
import json

def main(state: dict, current_plan_json: str) -> dict:
    state=state or {}
    try: plan=json.loads(current_plan_json or '{}')
    except Exception: plan={}
    booking_types=state.get('booking_type') or []
    selected=state.get('selected_option_ids') or []
    if isinstance(booking_types,str): booking_types=[booking_types]
    if isinstance(selected,str): selected=[selected]
    allowed_types={'hotel','train','flight','ticket'}
    all_items=[]
    type_by_id={}
    for field in ['selected_hotels','selected_transport','selected_tickets','bookable_options']:
        values=plan.get(field) or []
        if isinstance(values,dict): values=[values]
        for item in values:
            if not isinstance(item,dict): continue
            all_items.append(item)
            option_id=item.get('option_id')
            inferred_type=item.get('booking_type') or item.get('type')
            if not inferred_type and field == 'selected_hotels': inferred_type='hotel'
            if not inferred_type and field == 'selected_tickets': inferred_type='ticket'
            if option_id and inferred_type: type_by_id[str(option_id)]=str(inferred_type)
    explicit_ids=plan.get('bookable_option_ids') or []
    option_by_id={str(item.get('option_id')):item for item in all_items if item.get('option_id')}
    all_ids=set(option_by_id) | {str(value) for value in explicit_ids}
    bookable_ids={option_id for option_id in all_ids if option_by_id.get(option_id,{}).get('bookable',True) is not False}
    errors=[]
    if not plan.get('plan_id') or not plan.get('plan_version'): errors.append('NO_CURRENT_PLAN')
    if not booking_types: errors.append('MISSING_BOOKING_TYPE')
    if any(item not in allowed_types for item in booking_types): errors.append('UNSUPPORTED_BOOKING_TYPE')
    if not selected: errors.append('MISSING_SELECTED_OPTION_IDS')
    if selected and not set(map(str,selected)).issubset(all_ids): errors.append('OPTION_NOT_IN_CURRENT_PLAN')
    if selected and not set(map(str,selected)).issubset(bookable_ids): errors.append('OPTION_NOT_BOOKABLE')
    if selected and any(type_by_id.get(str(option_id)) and type_by_id[str(option_id)] not in booking_types for option_id in selected):
        errors.append('OPTION_TYPE_MISMATCH')
    available=[{'option_id':option_id,'name':option_by_id.get(option_id,{}).get('name'),'bookable':option_id in bookable_ids} for option_id in sorted(all_ids)]
    return {
        'booking_ready':'true' if not errors else 'false',
        'booking_errors':errors,
        'available_options_json':json.dumps(available,ensure_ascii=False),
        'plan_id':plan.get('plan_id') or '',
        'plan_version':plan.get('plan_version') or 0
    }
""",
        [
            ("state", ["pre_route_state", "state"]),
            ("current_plan_json", ["conversation", "current_plan_json"]),
        ],
        {
            "booking_ready": "string",
            "booking_errors": "array[string]",
            "available_options_json": "string",
            "plan_id": "string",
            "plan_version": "number",
        },
        3800,
        1260,
    )
    booking_readiness_router = v2.if_node(
        "booking_readiness_router",
        "预订就绪路由",
        [v2.case("ready", ["booking_slot_guard", "booking_ready"], "true")],
        4160,
        1260,
    )
    booking_slot_answer = v2.answer_node(
        "booking_slot_answer",
        "回复 - 补全预订选项",
        "还不能生成订单草稿。缺少或无效信息：{{#booking_slot_guard.booking_errors#}}。当前方案可选项：{{#booking_slot_guard.available_options_json#}}。请明确选择要预订的 option_id。",
        4520,
        1400,
    )
    nodes.extend([booking_slot_guard, booking_readiness_router, booking_slot_answer])

    draft_builder = by_id["booking_draft_builder"]
    draft_builder["data"]["code"] = """
import hashlib
import json
import secrets
import time
import uuid

def calculate_hash(plan_id, plan_version, quote_ids, total_price, expires_at, selected_option_ids):
    material={
        'plan_id':plan_id,'plan_version':plan_version,
        'quote_ids':sorted(quote_ids or []),'total_price':total_price,
        'expires_at':expires_at,'selected_option_ids':sorted(selected_option_ids or [])
    }
    canonical=json.dumps(material,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def main(quotes_json: str, state: dict, conversation_id: str, user_id: str, current_plan_json: str) -> dict:
    try: quotes=json.loads(quotes_json or '{}')
    except Exception: quotes={}
    try: plan=json.loads(current_plan_json or '{}')
    except Exception: plan={}
    total=sum((item or {}).get('total_price',0) for item in (quotes or {}).values())
    quote_ids=[item.get('quote_id') for item in (quotes or {}).values() if item.get('quote_id')]
    selected=(state or {}).get('selected_option_ids') or []
    if isinstance(selected,str): selected=[selected]
    created_at=int(time.time()); expires_at=created_at+900
    draft_id='MOCK-DRAFT-'+str(uuid.uuid4())
    confirmation_token=secrets.token_urlsafe(18)
    plan_id=plan.get('plan_id'); plan_version=plan.get('plan_version')
    draft_hash=calculate_hash(plan_id,plan_version,quote_ids,total,expires_at,selected)
    draft={
        'status':'PENDING_CONFIRMATION','data_mode':'MOCK','draft_id':draft_id,
        'creator_user_id':user_id,'thread_id':conversation_id,
        'plan_id':plan_id,'plan_version':plan_version,
        'booking_types':list((quotes or {}).keys()),'selected_option_ids':selected,
        'items':quotes or {},'quote_ids':quote_ids,'total_price':total,
        'created_at':created_at,'expires_at':expires_at,
        'confirmation_token':confirmation_token,'draft_hash':draft_hash,
        'idempotency_key':draft_id,'requires_confirmation':True
    }
    return {'booking_draft_json':json.dumps(draft,ensure_ascii=False)}
""".strip()
    draft_builder["data"]["variables"] = [
        {"variable": "quotes_json", "value_selector": ["booking_quote_refresher", "quotes_json"]},
        {"variable": "state", "value_selector": ["pre_route_state", "state"]},
        {"variable": "conversation_id", "value_selector": ["sys", "conversation_id"]},
        {"variable": "user_id", "value_selector": ["sys", "user_id"]},
        {"variable": "current_plan_json", "value_selector": ["conversation", "current_plan_json"]},
    ]
    by_id["booking_confirmation"]["data"]["prompt_template"][0]["text"] = """
展示订单草稿并明确标注“演示订单，不会真实扣款或下单”。
用户确认时必须原样发送：确认预订 <draft_id> <confirmation_token>。
订单草稿：{{#booking_draft_builder.booking_draft_json#}}
""".strip()

    confirmation_guard = by_id["booking_confirmation_guard"]
    confirmation_guard["data"]["code"] = """
import hashlib
import json
import time

def calculate_hash(draft):
    material={
        'plan_id':draft.get('plan_id'),'plan_version':draft.get('plan_version'),
        'quote_ids':sorted(draft.get('quote_ids') or []),'total_price':draft.get('total_price'),
        'expires_at':draft.get('expires_at'),'selected_option_ids':sorted(draft.get('selected_option_ids') or [])
    }
    canonical=json.dumps(material,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def main(query: str, conversation_id: str, user_id: str, persisted_draft_json: str, current_plan_json: str) -> dict:
    try: draft=json.loads(persisted_draft_json or '{}')
    except Exception: draft={}
    try: plan=json.loads(current_plan_json or '{}')
    except Exception: plan={}
    error=''
    if not draft.get('draft_id'): error='NO_PENDING_DRAFT'
    elif draft.get('creator_user_id') != user_id: error='DRAFT_USER_MISMATCH'
    elif draft.get('thread_id') != conversation_id: error='DRAFT_THREAD_MISMATCH'
    elif draft.get('status') != 'PENDING_CONFIRMATION': error='DRAFT_NOT_CONFIRMABLE'
    elif int(draft.get('expires_at') or 0) < int(time.time()): error='DRAFT_EXPIRED'
    elif draft.get('plan_id') != plan.get('plan_id') or draft.get('plan_version') != plan.get('plan_version'): error='DRAFT_PLAN_VERSION_MISMATCH'
    elif calculate_hash(draft) != draft.get('draft_hash'): error='DRAFT_HASH_MISMATCH'
    elif not any(word in (query or '') for word in ['确认提交','确认下单','确认预订','确认购买']): error='EXPLICIT_CONFIRMATION_REQUIRED'
    elif str(draft.get('draft_id')) not in (query or ''): error='DRAFT_ID_REQUIRED'
    elif str(draft.get('confirmation_token')) not in (query or ''): error='CONFIRMATION_TOKEN_MISMATCH'
    return {
        'can_submit':'true' if not error else 'false','validation_error':error,
        'draft_json':json.dumps(draft,ensure_ascii=False),
        'booking_type':draft.get('booking_types') or [],
        'idempotency_key':draft.get('idempotency_key') or ''
    }
""".strip()
    confirmation_guard["data"]["variables"] = [
        {"variable": "query", "value_selector": ["sys", "query"]},
        {"variable": "conversation_id", "value_selector": ["sys", "conversation_id"]},
        {"variable": "user_id", "value_selector": ["sys", "user_id"]},
        {"variable": "persisted_draft_json", "value_selector": ["conversation", "booking_draft_json"]},
        {"variable": "current_plan_json", "value_selector": ["conversation", "current_plan_json"]},
    ]
    confirmation_guard["data"]["outputs"]["idempotency_key"] = {"children": None, "type": "string"}

    gateway = by_id["booking_submit_gateway"]
    gateway["data"]["code"] = """
import json
def main(draft_json: str, idempotency_key: str) -> dict:
    try: draft=json.loads(draft_json or '{}')
    except Exception: draft={}
    return {
        'submit_status':'MOCK_SUCCESS','data_mode':'MOCK',
        'mock_order_id':'MOCK-ORDER-'+str(draft.get('draft_id','UNKNOWN'))[-12:],
        'draft_id':draft.get('draft_id'),'idempotency_key':idempotency_key,
        'endpoint':'MOCK POST /bookings/submit','requires_valid_confirmation_token':True,
        'booking_type':draft.get('booking_types') or []
    }
""".strip()
    gateway["data"]["variables"] = [
        {"variable": "draft_json", "value_selector": ["booking_confirmation_guard", "draft_json"]},
        {"variable": "idempotency_key", "value_selector": ["booking_confirmation_guard", "idempotency_key"]},
    ]
    gateway["data"]["outputs"]["idempotency_key"] = {"children": None, "type": "string"}

    remove_edge_ids = {"hard2-checkpoint", "modify-checkpoint", "supervisor-booking", "load-modify"}
    edges = [edge for edge in edges if edge["id"] not in remove_edge_ids]
    edges.extend(
        [
            v2.edge("hard2-validation-route", "second_hard_validator", "second_validation_router", "code", "if-else"),
            v2.edge("hard2-valid-checkpoint", "second_validation_router", "revised_checkpoint_builder", "if-else", "code", "pass"),
            v2.edge("hard2-invalid-answer", "second_validation_router", "second_validation_failure_answer", "if-else", "answer", "false"),
            v2.edge("modify-validation-route", "modify_validator", "modify_validation_router", "code", "if-else"),
            v2.edge("modify-valid-checkpoint", "modify_validation_router", "modify_checkpoint_builder", "if-else", "code", "pass"),
            v2.edge("modify-invalid-answer", "modify_validation_router", "modify_validation_failure_answer", "if-else", "answer", "false"),
            v2.edge("load-current-plan-guard", "current_plan_loader", "current_plan_existence_guard", "code", "code"),
            v2.edge("current-plan-existence-route", "current_plan_existence_guard", "current_plan_existence_router", "code", "if-else"),
            v2.edge("current-plan-exists-modify", "current_plan_existence_router", "modify_agent", "if-else", "llm", "exists"),
            v2.edge("current-plan-missing-answer", "current_plan_existence_router", "no_current_plan_answer", "if-else", "answer", "false"),
            v2.edge("supervisor-booking-slot-guard", "supervisor", "booking_slot_guard", "if-else", "code", "booking"),
            v2.edge("booking-slot-readiness", "booking_slot_guard", "booking_readiness_router", "code", "if-else"),
            v2.edge("booking-ready-quote", "booking_readiness_router", "booking_quote_refresher", "if-else", "code", "ready"),
            v2.edge("booking-not-ready-answer", "booking_readiness_router", "booking_slot_answer", "if-else", "answer", "false"),
        ]
    )

    graph["nodes"] = nodes
    graph["edges"] = edges
    dsl["version"] = "0.4.0"
    dsl["app"]["name"] = "一键游 Multi-Agent 安全主骨架 v4"
    dsl["app"]["description"] = "增加校验写入闸门、方案版本草稿失效、确认令牌、预订槽位守卫、工具白名单和恢复状态回写。"
    workflow["features"]["opening_statement"] = "一键游 v4 安全架构演示：校验失败不写入状态，新方案自动清除旧草稿；预订必须选择当前方案中的 option_id，并使用短时确认令牌。所有外部数据和提交仍为 Mock。"
    OUTPUT_DSL.write_text(yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


if __name__ == "__main__":
    main()
