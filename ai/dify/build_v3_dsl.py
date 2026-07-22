from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

import build_v2_dsl as v2


ROOT = Path(__file__).resolve().parent
BASE_DSL = ROOT / "oneclick-trip-multi-agent.yml"
OUTPUT_DSL = ROOT / "oneclick-trip-multi-agent-v3.yml"

FLASH_MODEL = {
    "provider": "langgenius/deepseek/deepseek",
    "name": "deepseek-v4-flash",
    "mode": "chat",
    "completion_params": {"temperature": 0.1},
}
PRO_MODEL = {
    "provider": "langgenius/deepseek/deepseek",
    "name": "deepseek-v4-pro",
    "mode": "chat",
    "completion_params": {"temperature": 0.1},
}


def assigner_node(node_id: str, title: str, assignments: list[tuple[str, list[str]]], x: int, y: int) -> dict:
    return {
        "data": {
            "desc": title,
            "items": [
                {
                    "input_type": "variable",
                    "operation": "over-write",
                    "value": selector,
                    "variable_selector": ["conversation", variable_name],
                    "write_mode": "over-write",
                }
                for variable_name, selector in assignments
            ],
            "selected": False,
            "title": title,
            "type": "assigner",
            "version": "2",
        },
        "height": max(88, 55 + 30 * len(assignments)),
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 300,
    }


def conversation_variable(variable_id: str, name: str, value: object, value_type: str, description: str) -> dict:
    return {
        "description": description,
        "id": variable_id,
        "name": name,
        "selector": ["conversation", name],
        "value": value,
        "value_type": value_type,
    }


def set_model(node: dict, model: dict) -> None:
    if node.get("data", {}).get("type") == "llm":
        node["data"]["model"] = copy.deepcopy(model)


CHECKPOINT_BUILDER_CODE = """
import json

def main(state: dict, plan_json: str, conversation_id: str, checkpoint_version: float) -> dict:
    try:
        plan = json.loads(plan_json or '{}')
    except Exception:
        plan = {}
    next_version = int(checkpoint_version or 0) + 1
    checkpoint = {
        'schema_version': 1,
        'thread_id': conversation_id,
        'checkpoint_version': next_version,
        'active_plan_id': plan.get('plan_id'),
        'active_plan_version': plan.get('plan_version'),
        'current_plan_json': json.dumps(plan, ensure_ascii=False),
        'booking_draft_id': None,
        'booking_draft_status': None,
        'updated_by': 'DIFY_MOCK_CHECKPOINT_WRITER'
    }
    return {
        'checkpoint_json': json.dumps(checkpoint, ensure_ascii=False),
        'current_plan_json': json.dumps(plan, ensure_ascii=False),
        'next_checkpoint_version': next_version,
        'checkpoint_status': 'MOCK_SAVED'
    }
"""


def checkpoint_builder(node_id: str, title: str, plan_selector: list[str], x: int, y: int) -> dict:
    return v2.code_node(
        node_id,
        title,
        "把最终结构化方案绑定 thread_id 和版本号，生成可跨轮恢复的检查点。",
        CHECKPOINT_BUILDER_CODE,
        [
            ("state", ["pre_route_state", "state"]),
            ("plan_json", plan_selector),
            ("conversation_id", ["sys", "conversation_id"]),
            ("checkpoint_version", ["conversation", "checkpoint_version"]),
        ],
        {
            "checkpoint_json": "string",
            "current_plan_json": "string",
            "next_checkpoint_version": "number",
            "checkpoint_status": "string",
        },
        x,
        y,
    )


def checkpoint_assigner(node_id: str, title: str, builder_id: str, x: int, y: int) -> dict:
    return assigner_node(
        node_id,
        title,
        [
            ("travel_checkpoint_json", [builder_id, "checkpoint_json"]),
            ("current_plan_json", [builder_id, "current_plan_json"]),
            ("checkpoint_version", [builder_id, "next_checkpoint_version"]),
        ],
        x,
        y,
    )


def main() -> None:
    # Always rebuild the verified v2 base before applying v3 transformations.
    v2.main()
    dsl = yaml.safe_load(BASE_DSL.read_text(encoding="utf-8"))
    workflow = dsl["workflow"]
    graph = workflow["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    by_id = {node["id"]: node for node in nodes}

    workflow["conversation_variables"] = [
        conversation_variable(
            "1a7a1d8e-4c3e-4e48-bbf2-001001001001",
            "travel_checkpoint_json",
            "{}",
            "string",
            "当前对话的轻量检查点；正式 LangGraph 由 MySQL CheckpointRepository 持久化。",
        ),
        conversation_variable(
            "2b8b2e9f-5d4f-4f59-cc03-002002002002",
            "current_plan_json",
            "{}",
            "string",
            "当前结构化行程及版本，用于修改方案和预订引用。",
        ),
        conversation_variable(
            "3c9c3fa0-6e50-406a-dd14-003003003003",
            "booking_draft_json",
            "{}",
            "string",
            "等待用户确认的订单草稿；绑定 conversation_id、计划和过期时间。",
        ),
        conversation_variable(
            "4dad40b1-7f61-417b-ee25-004004004004",
            "checkpoint_version",
            0,
            "number",
            "会话状态乐观版本号。",
        ),
        conversation_variable(
            "5ebe51c2-8072-428c-ff36-005005005005",
            "last_tool_errors_json",
            "[]",
            "string",
            "最近一次工具错误及恢复决策。",
        ),
    ]

    # Cheap deterministic tasks use Flash; planning and quality decisions retain Pro.
    flash_nodes = {
        "intent_agent",
        "memory_candidate_agent",
        "clarification_agent",
        "memory_management_agent",
        "query_presenter",
        "booking_confirmation",
        "modify_reviewer",
    }
    pro_nodes = {
        "candidate_selector",
        "planner",
        "soft_reviewer",
        "revision",
        "modify_agent",
        "final_reviewer",
    }
    for node_id in flash_nodes:
        set_model(by_id[node_id], FLASH_MODEL)
    for node_id in pro_nodes:
        set_model(by_id[node_id], PRO_MODEL)

    checkpoint_hydrator = v2.code_node(
        "checkpoint_hydrator",
        "状态检查点读取 / Checkpoint Hydrator",
        "每轮开始读取 conversation_id 对应的方案、草稿和版本；正式实现替换为 MySQL CheckpointRepository。",
        """
import json

def main(conversation_id: str, checkpoint_json: str, current_plan_json: str, booking_draft_json: str, checkpoint_version: float) -> dict:
    try: checkpoint = json.loads(checkpoint_json or '{}')
    except Exception: checkpoint = {}
    try: plan = json.loads(current_plan_json or '{}')
    except Exception: plan = {}
    try: draft = json.loads(booking_draft_json or '{}')
    except Exception: draft = {}
    summary = {
        'thread_id': conversation_id,
        'checkpoint_version': int(checkpoint_version or 0),
        'active_plan_id': plan.get('plan_id') or checkpoint.get('active_plan_id'),
        'active_plan_version': plan.get('plan_version') or checkpoint.get('active_plan_version'),
        'booking_draft_id': draft.get('draft_id'),
        'booking_draft_status': draft.get('status'),
        'has_resumable_state': bool(plan or draft or checkpoint)
    }
    return {'checkpoint_context_json':json.dumps(summary,ensure_ascii=False),'has_resumable_state':'true' if summary['has_resumable_state'] else 'false'}
""",
        [
            ("conversation_id", ["sys", "conversation_id"]),
            ("checkpoint_json", ["conversation", "travel_checkpoint_json"]),
            ("current_plan_json", ["conversation", "current_plan_json"]),
            ("booking_draft_json", ["conversation", "booking_draft_json"]),
            ("checkpoint_version", ["conversation", "checkpoint_version"]),
        ],
        {"checkpoint_context_json": "string", "has_resumable_state": "string"},
        1120,
        680,
    )
    nodes.append(checkpoint_hydrator)

    intent_prompt = by_id["intent_agent"]["data"]["prompt_template"][0]["text"]
    by_id["intent_agent"]["data"]["prompt_template"][0]["text"] = intent_prompt + """
当前会话检查点：{{#checkpoint_hydrator.checkpoint_context_json#}}
当用户说“上次方案”“第二天”“确认提交”时，必须结合检查点识别 modify_plan 或 booking_confirm，不允许只从本轮文本猜测。"""

    normalizer = by_id["state_normalizer"]
    normalizer["data"]["code"] = normalizer["data"]["code"].replace(
        "def main(query: str, intent_raw: str, memory_context: str) -> dict:",
        "def main(query: str, intent_raw: str, memory_context: str, conversation_id: str, checkpoint_json: str, current_plan_json: str, booking_draft_json: str, checkpoint_version: float) -> dict:",
    )
    return_line = "    return {'intent':state['intent'], 'ready':'true' if state['ready_for_execution'] else 'false', 'state':state, 'state_json':json.dumps(state,ensure_ascii=False)}"
    persisted_state_code = """
    try: persisted_plan = json.loads(current_plan_json or '{}')
    except Exception: persisted_plan = {}
    try: persisted_draft = json.loads(booking_draft_json or '{}')
    except Exception: persisted_draft = {}
    state['thread_id'] = conversation_id
    state['checkpoint_version'] = int(checkpoint_version or 0)
    state['checkpoint_json'] = checkpoint_json or '{}'
    state['current_plan_json'] = current_plan_json or '{}'
    state['booking_draft_json'] = booking_draft_json or '{}'
    if persisted_plan:
        state['current_plan_id'] = persisted_plan.get('plan_id') or state.get('current_plan_id')
        state['plan_version'] = persisted_plan.get('plan_version')
    if persisted_draft:
        state['booking_draft_id'] = persisted_draft.get('draft_id')
        state['booking_draft_status'] = persisted_draft.get('status')
        state['quote_ids'] = persisted_draft.get('quote_ids') or state.get('quote_ids') or []
""" + return_line
    normalizer["data"]["code"] = normalizer["data"]["code"].replace(return_line, persisted_state_code)
    normalizer["data"]["variables"].extend([
        {"variable": "conversation_id", "value_selector": ["sys", "conversation_id"]},
        {"variable": "checkpoint_json", "value_selector": ["conversation", "travel_checkpoint_json"]},
        {"variable": "current_plan_json", "value_selector": ["conversation", "current_plan_json"]},
        {"variable": "booking_draft_json", "value_selector": ["conversation", "booking_draft_json"]},
        {"variable": "checkpoint_version", "value_selector": ["conversation", "checkpoint_version"]},
    ])

    # Prefer the persisted structured plan; use the Mock fixture only when no checkpoint exists.
    by_id["current_plan_loader"]["data"]["code"] = """
import json

def main(state: dict) -> dict:
    raw = (state or {}).get('current_plan_json') or '{}'
    try: plan = json.loads(raw)
    except Exception: plan = {}
    if not plan:
        plan_id=(state or {}).get('current_plan_id') or 'CURRENT_SESSION_PLAN'
        plan={
            'status':'MOCK_SUCCESS','data_mode':'MOCK','plan_id':plan_id,'plan_version':1,
            'days':[
                {'day_id':'DAY-1','title':'熊猫与市井成都','items':[{'item_id':'ITEM-PANDA','poi_id':'POI-PANDA','name':'成都大熊猫繁育研究基地','visit_start':'08:00','visit_end':'12:00'}]},
                {'day_id':'DAY-2','title':'人文成都','items':[{'item_id':'ITEM-DU','poi_id':'POI-DU','name':'杜甫草堂','visit_start':'14:00','visit_end':'16:30'}]}
            ],
            'selected_hotels':[{'option_id':'HOTEL-CD-001','name':'春熙路轻居酒店'}],
            'selected_transport':[{'option_id':'TRAIN-G89','name':'G89'}]
        }
    return {'current_plan_json':json.dumps(plan,ensure_ascii=False),'current_plan_id':plan.get('plan_id'),'plan_version':plan.get('plan_version',1)}
""".strip()

    plan_checkpoint_builder = checkpoint_builder("plan_checkpoint_builder", "保存校验通过的方案检查点", ["hard_validator", "plan_json"], 7740, 360)
    plan_checkpoint_assigner = checkpoint_assigner("plan_checkpoint_assigner", "写入会话方案状态", "plan_checkpoint_builder", 8100, 360)
    revised_checkpoint_builder = checkpoint_builder("revised_checkpoint_builder", "保存修订后的方案检查点", ["second_hard_validator", "plan_json"], 8460, 640)
    revised_checkpoint_assigner = checkpoint_assigner("revised_checkpoint_assigner", "写入修订方案状态", "revised_checkpoint_builder", 8820, 640)
    modify_checkpoint_builder = checkpoint_builder("modify_checkpoint_builder", "保存局部修改后的方案", ["modify_validator", "plan_json"], 5580, 920)
    modify_checkpoint_assigner = checkpoint_assigner("modify_checkpoint_assigner", "写入修改方案状态", "modify_checkpoint_builder", 5940, 920)
    nodes.extend([
        plan_checkpoint_builder,
        plan_checkpoint_assigner,
        revised_checkpoint_builder,
        revised_checkpoint_assigner,
        modify_checkpoint_builder,
        modify_checkpoint_assigner,
    ])

    # The draft is bound to the current conversation and expires after 15 minutes.
    draft_builder = by_id["booking_draft_builder"]
    draft_builder["data"]["code"] = """
import json
import time

def main(quotes_json: str, state: dict, conversation_id: str) -> dict:
    try: quotes=json.loads(quotes_json or '{}')
    except Exception: quotes={}
    total=sum((item or {}).get('total_price',0) for item in (quotes or {}).values())
    quote_ids=[item.get('quote_id') for item in (quotes or {}).values() if item.get('quote_id')]
    draft={
        'status':'PENDING_CONFIRMATION','data_mode':'MOCK','draft_id':'MOCK-DRAFT-'+conversation_id[-8:],
        'thread_id':conversation_id,'plan_id':(state or {}).get('current_plan_id'),
        'plan_version':(state or {}).get('plan_version'),'booking_types':list((quotes or {}).keys()),
        'items':quotes or {},'quote_ids':quote_ids,'total_price':total,'requires_confirmation':True,
        'created_at':int(time.time()),'expires_at':int(time.time())+900
    }
    return {'booking_draft_json':json.dumps(draft,ensure_ascii=False)}
""".strip()
    draft_builder["data"]["variables"].append({"variable": "conversation_id", "value_selector": ["sys", "conversation_id"]})

    draft_checkpoint_builder = v2.code_node(
        "draft_checkpoint_builder",
        "订单草稿检查点构建",
        "把订单草稿绑定当前 conversation_id、计划版本和过期时间。",
        """
import json

def main(draft_json: str, checkpoint_json: str, checkpoint_version: float) -> dict:
    try: draft=json.loads(draft_json or '{}')
    except Exception: draft={}
    try: checkpoint=json.loads(checkpoint_json or '{}')
    except Exception: checkpoint={}
    next_version=int(checkpoint_version or 0)+1
    checkpoint.update({
        'checkpoint_version':next_version,
        'booking_draft_id':draft.get('draft_id'),
        'booking_draft_status':draft.get('status'),
        'booking_draft_expires_at':draft.get('expires_at')
    })
    return {'checkpoint_json':json.dumps(checkpoint,ensure_ascii=False),'booking_draft_json':json.dumps(draft,ensure_ascii=False),'next_checkpoint_version':next_version}
""",
        [
            ("draft_json", ["booking_draft_builder", "booking_draft_json"]),
            ("checkpoint_json", ["conversation", "travel_checkpoint_json"]),
            ("checkpoint_version", ["conversation", "checkpoint_version"]),
        ],
        {"checkpoint_json": "string", "booking_draft_json": "string", "next_checkpoint_version": "number"},
        4520,
        1260,
    )
    draft_checkpoint_assigner = assigner_node(
        "draft_checkpoint_assigner",
        "保存待确认订单草稿",
        [
            ("travel_checkpoint_json", ["draft_checkpoint_builder", "checkpoint_json"]),
            ("booking_draft_json", ["draft_checkpoint_builder", "booking_draft_json"]),
            ("checkpoint_version", ["draft_checkpoint_builder", "next_checkpoint_version"]),
        ],
        4880,
        1260,
    )

    booking_confirmation_guard = v2.code_node(
        "booking_confirmation_guard",
        "预订确认绑定校验",
        "只有同一 conversation_id 下、未过期且状态为 PENDING_CONFIRMATION 的上一轮草稿可以提交。",
        """
import json
import time

def main(query: str, conversation_id: str, persisted_draft_json: str) -> dict:
    try: draft=json.loads(persisted_draft_json or '{}')
    except Exception: draft={}
    error=''
    if not draft.get('draft_id'): error='NO_PENDING_DRAFT'
    elif draft.get('thread_id') != conversation_id: error='DRAFT_THREAD_MISMATCH'
    elif draft.get('status') != 'PENDING_CONFIRMATION': error='DRAFT_NOT_CONFIRMABLE'
    elif int(draft.get('expires_at') or 0) < int(time.time()): error='DRAFT_EXPIRED'
    elif not any(word in (query or '') for word in ['确认提交','确认下单','确认预订','确认购买']): error='EXPLICIT_CONFIRMATION_REQUIRED'
    return {
        'can_submit':'true' if not error else 'false',
        'validation_error':error,
        'draft_json':json.dumps(draft,ensure_ascii=False),
        'booking_type':draft.get('booking_types') or []
    }
""",
        [
            ("query", ["sys", "query"]),
            ("conversation_id", ["sys", "conversation_id"]),
            ("persisted_draft_json", ["conversation", "booking_draft_json"]),
        ],
        {"can_submit": "string", "validation_error": "string", "draft_json": "string", "booking_type": "array[string]"},
        3800,
        1540,
    )
    booking_confirmation_router = v2.if_node(
        "booking_confirmation_router",
        "预订草稿有效性路由",
        [v2.case("valid_draft", ["booking_confirmation_guard", "can_submit"], "true")],
        4160,
        1540,
    )
    invalid_draft_answer = v2.answer_node(
        "invalid_draft_answer",
        "回复 - 无有效草稿",
        "没有找到可确认的上一轮订单草稿，或者草稿已经过期/提交。请先重新选择要预订的酒店、交通或门票。错误码：{{#booking_confirmation_guard.validation_error#}}",
        4520,
        1680,
    )

    gateway = by_id["booking_submit_gateway"]
    gateway["data"]["code"] = """
import json

def main(draft_json: str) -> dict:
    try: draft=json.loads(draft_json or '{}')
    except Exception: draft={}
    return {
        'submit_status':'MOCK_SUCCESS','data_mode':'MOCK',
        'mock_order_id':'MOCK-ORDER-'+str(draft.get('draft_id','UNKNOWN'))[-8:],
        'draft_id':draft.get('draft_id'),'endpoint':'MOCK POST /bookings/submit',
        'requires_valid_confirmation_token':True,'booking_type':draft.get('booking_types') or []
    }
""".strip()
    gateway["data"]["variables"] = [{"variable": "draft_json", "value_selector": ["booking_confirmation_guard", "draft_json"]}]
    gateway["data"]["outputs"]["draft_id"] = {"children": None, "type": "string"}

    submit_state_builder = v2.code_node(
        "submit_state_builder",
        "提交后草稿失效",
        "提交成功后把草稿状态改为 SUBMITTED，防止重复确认。",
        """
import json

def main(draft_json: str, checkpoint_json: str, checkpoint_version: float) -> dict:
    try: draft=json.loads(draft_json or '{}')
    except Exception: draft={}
    try: checkpoint=json.loads(checkpoint_json or '{}')
    except Exception: checkpoint={}
    draft['status']='SUBMITTED'
    next_version=int(checkpoint_version or 0)+1
    checkpoint.update({'checkpoint_version':next_version,'booking_draft_id':draft.get('draft_id'),'booking_draft_status':'SUBMITTED'})
    return {'booking_draft_json':json.dumps(draft,ensure_ascii=False),'checkpoint_json':json.dumps(checkpoint,ensure_ascii=False),'next_checkpoint_version':next_version}
""",
        [
            ("draft_json", ["booking_confirmation_guard", "draft_json"]),
            ("checkpoint_json", ["conversation", "travel_checkpoint_json"]),
            ("checkpoint_version", ["conversation", "checkpoint_version"]),
        ],
        {"booking_draft_json": "string", "checkpoint_json": "string", "next_checkpoint_version": "number"},
        4880,
        1540,
    )
    submit_state_assigner = assigner_node(
        "submit_state_assigner",
        "写回已提交草稿状态",
        [
            ("booking_draft_json", ["submit_state_builder", "booking_draft_json"]),
            ("travel_checkpoint_json", ["submit_state_builder", "checkpoint_json"]),
            ("checkpoint_version", ["submit_state_builder", "next_checkpoint_version"]),
        ],
        5240,
        1540,
    )
    nodes.extend([
        draft_checkpoint_builder,
        draft_checkpoint_assigner,
        booking_confirmation_guard,
        booking_confirmation_router,
        invalid_draft_answer,
        submit_state_builder,
        submit_state_assigner,
    ])

    # Explicit tool failure envelope and recovery decision.
    executor = by_id["query_executor"]
    executor["data"]["code"] = executor["data"]["code"].replace(
        "    payload = {'tool_results':results,'tool_errors':[]}",
        """    errors=[]
    query=(state or {}).get('query','')
    if selected_tools and ('模拟工具失败' in query or '模拟天气接口失败' in query or '模拟不可恢复错误' in query):
        failed_tool=selected_tools[0]
        retryable='模拟不可恢复错误' not in query
        results[failed_tool]={'status':'MOCK_FAILED','data_mode':'MOCK','tool':failed_tool,'request_context':resolved_context,'data':{}}
        errors.append({'tool':failed_tool,'error_code':'MOCK_TIMEOUT' if retryable else 'MOCK_AUTH_ERROR','retryable':retryable,'attempt':1,'fallback_available':failed_tool in ['weather','hotel_search','poi_rag']})
    payload = {'tool_results':results,'tool_errors':errors}""",
    )

    query_recovery_policy = v2.code_node(
        "query_recovery_policy",
        "统一工具失败恢复策略",
        "根据错误类型、重试次数和降级能力选择继续、一次重试、缓存降级或明确失败。",
        """
import json

def main(query_result_json: str) -> dict:
    try: payload=json.loads(query_result_json or '{}')
    except Exception: payload={}
    errors=payload.get('tool_errors') or []
    action='continue'
    if errors:
        if any(e.get('retryable') and int(e.get('attempt') or 0)<2 for e in errors): action='retry'
        elif all(e.get('fallback_available') for e in errors): action='fallback'
        else: action='degraded'
    return {'recovery_action':action,'tool_errors_json':json.dumps(errors,ensure_ascii=False),'original_result_json':json.dumps(payload,ensure_ascii=False)}
""",
        [("query_result_json", ["query_executor", "query_result_json"])],
        {"recovery_action": "string", "tool_errors_json": "string", "original_result_json": "string"},
        5580,
        40,
    )
    tool_error_assigner = assigner_node(
        "tool_error_assigner",
        "记录最近工具错误",
        [("last_tool_errors_json", ["query_recovery_policy", "tool_errors_json"])],
        5940,
        40,
    )
    query_recovery_router = v2.if_node(
        "query_recovery_router",
        "工具恢复动作路由",
        [
            v2.case("retry", ["query_recovery_policy", "recovery_action"], "retry"),
            v2.case("fallback", ["query_recovery_policy", "recovery_action"], "fallback"),
            v2.case("degraded", ["query_recovery_policy", "recovery_action"], "degraded"),
        ],
        6300,
        40,
    )
    query_retry_executor = v2.code_node(
        "query_retry_executor",
        "工具限次重试（最多 1 次）",
        "只重试 retryable 工具，第二次失败不再循环。",
        """
import json

def main(original_result_json: str) -> dict:
    try: payload=json.loads(original_result_json or '{}')
    except Exception: payload={}
    results=payload.get('tool_results') or {}
    for error in payload.get('tool_errors') or []:
        tool=error.get('tool')
        results[tool]={'status':'MOCK_RETRY_SUCCESS','data_mode':'MOCK','tool':tool,'attempt':2,'data':{'message':'第二次调用成功','recovered':True}}
    return {'query_result_json':json.dumps({'tool_results':results,'tool_errors':[],'recovery_trace':['RETRY_ATTEMPT_2_SUCCESS']},ensure_ascii=False)}
""",
        [("original_result_json", ["query_recovery_policy", "original_result_json"])],
        {"query_result_json": "string"},
        6660,
        -80,
    )
    query_fallback_executor = v2.code_node(
        "query_fallback_executor",
        "工具缓存/替代源降级",
        "不可重试但存在缓存或替代数据源时，返回带时效声明的降级结果。",
        """
import json

def main(original_result_json: str) -> dict:
    try: payload=json.loads(original_result_json or '{}')
    except Exception: payload={}
    results=payload.get('tool_results') or {}
    for error in payload.get('tool_errors') or []:
        tool=error.get('tool')
        results[tool]={'status':'MOCK_FALLBACK_SUCCESS','data_mode':'MOCK_CACHE','tool':tool,'data':{'message':'使用最近缓存快照','freshness':'15 minutes ago'}}
    return {'query_result_json':json.dumps({'tool_results':results,'tool_errors':[],'recovery_trace':['CACHE_FALLBACK_USED']},ensure_ascii=False)}
""",
        [("original_result_json", ["query_recovery_policy", "original_result_json"])],
        {"query_result_json": "string"},
        6660,
        120,
    )
    query_retry_presenter = v2.llm_node(
        "query_retry_presenter",
        "Flash - 重试结果整理",
        "将恢复后的实时查询结果整理成简洁答复。",
        "工具经过一次重试后成功。简洁回答用户，标注演示数据和已恢复，不生成完整行程。结果：{{#query_retry_executor.query_result_json#}}",
        7020,
        -80,
        0.1,
        True,
    )
    set_model(query_retry_presenter, FLASH_MODEL)
    query_fallback_presenter = v2.llm_node(
        "query_fallback_presenter",
        "Flash - 降级结果整理",
        "将缓存或替代数据源结果整理成带时效声明的答复。",
        "实时工具不可用，当前使用缓存/替代源。必须说明数据时效，简洁回答。结果：{{#query_fallback_executor.query_result_json#}}",
        7020,
        120,
        0.1,
        True,
    )
    set_model(query_fallback_presenter, FLASH_MODEL)
    query_retry_answer = v2.answer_node("query_retry_answer", "回复 - 工具重试成功", "{{#query_retry_presenter.text#}}", 7380, -80)
    query_fallback_answer = v2.answer_node("query_fallback_answer", "回复 - 工具降级结果", "{{#query_fallback_presenter.text#}}", 7380, 120)
    query_failure_answer = v2.answer_node(
        "query_failure_answer",
        "回复 - 工具暂不可用",
        "实时查询暂时不可用，系统已停止继续重试，避免重复调用。你可以稍后重试或改用不依赖实时数据的攻略建议。错误：{{#query_recovery_policy.tool_errors_json#}}",
        6660,
        260,
    )
    nodes.extend([
        query_recovery_policy,
        tool_error_assigner,
        query_recovery_router,
        query_retry_executor,
        query_fallback_executor,
        query_retry_presenter,
        query_fallback_presenter,
        query_retry_answer,
        query_fallback_answer,
        query_failure_answer,
    ])

    phase1_recovery_audit = v2.code_node(
        "phase1_recovery_audit",
        "规划工具恢复与降级审计",
        "在候选选择前统一处理规划阶段的超时、重试和缓存降级，并留下恢复轨迹。",
        """
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
    return {'phase1_results_json':json.dumps(results,ensure_ascii=False),'recovery_trace_json':json.dumps(trace,ensure_ascii=False)}
""",
        [("phase1_results_json", ["phase1_research", "phase1_results_json"]), ("query", ["sys", "query"])],
        {"phase1_results_json": "string", "recovery_trace_json": "string"},
        5580,
        470,
    )
    nodes.append(phase1_recovery_audit)
    by_id["candidate_selector"]["data"]["prompt_template"][0]["text"] = by_id["candidate_selector"]["data"]["prompt_template"][0]["text"].replace(
        "{{#phase1_research.phase1_results_json#}}",
        "{{#phase1_recovery_audit.phase1_results_json#}}\n恢复轨迹：{{#phase1_recovery_audit.recovery_trace_json#}}",
    )

    remove_edge_ids = {
        "context-intent",
        "supervisor-booking-confirm",
        "submit-answer",
        "draft-confirm",
        "quality-pass",
        "hard2-final",
        "modify-review",
        "query-present",
        "phase1-candidates",
    }
    edges = [item for item in edges if item["id"] not in remove_edge_ids]
    edges.extend([
        v2.edge("context-checkpoint", "memory_context_builder", "checkpoint_hydrator", "code", "code"),
        v2.edge("checkpoint-intent", "checkpoint_hydrator", "intent_agent", "code", "llm"),
        v2.edge("quality-pass-checkpoint", "quality_router_v2", "plan_checkpoint_builder", "if-else", "code", "pass"),
        v2.edge("plan-checkpoint-assign", "plan_checkpoint_builder", "plan_checkpoint_assigner", "code", "assigner"),
        v2.edge("plan-assign-answer", "plan_checkpoint_assigner", "plan_answer", "assigner", "answer"),
        v2.edge("hard2-checkpoint", "second_hard_validator", "revised_checkpoint_builder", "code", "code"),
        v2.edge("revised-checkpoint-assign", "revised_checkpoint_builder", "revised_checkpoint_assigner", "code", "assigner"),
        v2.edge("revised-assign-final", "revised_checkpoint_assigner", "final_reviewer", "assigner", "llm"),
        v2.edge("modify-checkpoint", "modify_validator", "modify_checkpoint_builder", "code", "code"),
        v2.edge("modify-checkpoint-assign", "modify_checkpoint_builder", "modify_checkpoint_assigner", "code", "assigner"),
        v2.edge("modify-assign-review", "modify_checkpoint_assigner", "modify_reviewer", "assigner", "llm"),
        v2.edge("draft-checkpoint", "booking_draft_builder", "draft_checkpoint_builder", "code", "code"),
        v2.edge("draft-checkpoint-assign", "draft_checkpoint_builder", "draft_checkpoint_assigner", "code", "assigner"),
        v2.edge("draft-assign-confirm", "draft_checkpoint_assigner", "booking_confirmation", "assigner", "llm"),
        v2.edge("supervisor-booking-confirm-guard", "supervisor", "booking_confirmation_guard", "if-else", "code", "booking_confirm"),
        v2.edge("booking-guard-router", "booking_confirmation_guard", "booking_confirmation_router", "code", "if-else"),
        v2.edge("booking-valid-submit", "booking_confirmation_router", "booking_submit_gateway", "if-else", "code", "valid_draft"),
        v2.edge("booking-invalid-answer", "booking_confirmation_router", "invalid_draft_answer", "if-else", "answer", "false"),
        v2.edge("submit-invalidate", "booking_submit_gateway", "submit_state_builder", "code", "code"),
        v2.edge("submit-state-assign", "submit_state_builder", "submit_state_assigner", "code", "assigner"),
        v2.edge("submit-assign-answer", "submit_state_assigner", "booking_submit_answer", "assigner", "answer"),
        v2.edge("query-recovery-policy", "query_executor", "query_recovery_policy", "code", "code"),
        v2.edge("query-error-assign", "query_recovery_policy", "tool_error_assigner", "code", "assigner"),
        v2.edge("query-recovery-route", "tool_error_assigner", "query_recovery_router", "assigner", "if-else"),
        v2.edge("query-continue-present", "query_recovery_router", "query_presenter", "if-else", "llm", "false"),
        v2.edge("query-retry-execute", "query_recovery_router", "query_retry_executor", "if-else", "code", "retry"),
        v2.edge("query-retry-present", "query_retry_executor", "query_retry_presenter", "code", "llm"),
        v2.edge("query-retry-answer", "query_retry_presenter", "query_retry_answer", "llm", "answer"),
        v2.edge("query-fallback-execute", "query_recovery_router", "query_fallback_executor", "if-else", "code", "fallback"),
        v2.edge("query-fallback-present", "query_fallback_executor", "query_fallback_presenter", "code", "llm"),
        v2.edge("query-fallback-answer", "query_fallback_presenter", "query_fallback_answer", "llm", "answer"),
        v2.edge("query-degraded-answer", "query_recovery_router", "query_failure_answer", "if-else", "answer", "degraded"),
        v2.edge("phase1-recovery-audit", "phase1_research", "phase1_recovery_audit", "code", "code"),
        v2.edge("recovery-candidates", "phase1_recovery_audit", "candidate_selector", "code", "llm"),
    ])

    dsl["app"]["name"] = "一键游 Multi-Agent 主骨架 v3"
    dsl["app"]["description"] = "Flash/Pro 模型分层、跨轮检查点、草稿绑定确认、工具限次重试与缓存降级的 LangGraph 主骨架。"
    workflow["features"]["opening_statement"] = "当前为一键游 v3 架构演示：简单任务使用 Flash，复杂规划使用 Pro；方案与订单草稿可跨轮恢复，所有预订仍为 Mock。"
    graph["nodes"] = nodes
    graph["edges"] = edges
    OUTPUT_DSL.write_text(yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


if __name__ == "__main__":
    main()
