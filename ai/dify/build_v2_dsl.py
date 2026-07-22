from __future__ import annotations

import copy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
DSL_PATH = ROOT / "oneclick-trip-multi-agent.yml"
MODEL = {
    "provider": "langgenius/deepseek/deepseek",
    "name": "deepseek-v4-pro",
    "mode": "chat",
    "completion_params": {"temperature": 0.1},
}


def edge(edge_id: str, source: str, target: str, source_type: str, target_type: str, handle: str = "source") -> dict:
    return {
        "data": {"isInIteration": False, "sourceType": source_type, "targetType": target_type},
        "id": edge_id,
        "source": source,
        "sourceHandle": handle,
        "target": target,
        "targetHandle": "target",
        "type": "custom",
    }


def code_node(node_id: str, title: str, desc: str, code: str, variables: list[tuple[str, list[str]]], outputs: dict, x: int, y: int) -> dict:
    return {
        "data": {
            "code": code.strip(),
            "code_language": "python3",
            "desc": desc,
            "outputs": {name: {"children": None, "type": kind} for name, kind in outputs.items()},
            "selected": False,
            "title": title,
            "type": "code",
            "variables": [{"variable": name, "value_selector": selector} for name, selector in variables],
        },
        "height": 120,
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 300,
    }


def llm_node(node_id: str, title: str, desc: str, prompt: str, x: int, y: int, temperature: float = 0.2, memory: bool = False) -> dict:
    model = copy.deepcopy(MODEL)
    model["completion_params"]["temperature"] = temperature
    return {
        "data": {
            "context": {"enabled": False, "variable_selector": []},
            "desc": desc,
            "memory": {
                "query_prompt_template": "{{#sys.query#}}",
                "role_prefix": {"assistant": "", "user": ""},
                "window": {"enabled": memory, "size": 20},
            },
            "model": model,
            "prompt_template": [{"id": f"{node_id}-system", "role": "system", "text": prompt.strip()}],
            "selected": False,
            "title": title,
            "type": "llm",
            "variables": [],
            "vision": {"enabled": False},
        },
        "height": 120,
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 310,
    }


def answer_node(node_id: str, title: str, selector: str, x: int, y: int) -> dict:
    return {
        "data": {"answer": selector, "desc": title, "selected": False, "title": title, "type": "answer", "variables": []},
        "height": 100,
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 280,
    }


def if_node(node_id: str, title: str, cases: list[dict], x: int, y: int) -> dict:
    return {
        "data": {"cases": cases, "desc": title, "selected": False, "title": title, "type": "if-else"},
        "height": max(180, 80 + 55 * len(cases)),
        "id": node_id,
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 300,
    }


def case(case_id: str, selector: list[str], value: str, operator: str = "is") -> dict:
    return {
        "case_id": case_id,
        "conditions": [{
            "comparison_operator": operator,
            "id": f"condition-{case_id}",
            "value": value,
            "varType": "string",
            "variable_selector": selector,
        }],
        "id": case_id,
        "logical_operator": "and",
    }


def main() -> None:
    dsl = yaml.safe_load(DSL_PATH.read_text(encoding="utf-8"))
    old = {node["id"]: node for node in dsl["workflow"]["graph"]["nodes"]}

    keep_ids = [
        "start", "short_memory_loader", "long_memory_reader", "memory_context_builder",
        "intent_agent", "state_normalizer", "memory_candidate_agent", "memory_policy_guard",
        "long_memory_writer", "clarification_agent", "clarification_answer",
        "memory_management_agent", "memory_management_answer",
    ]
    nodes = [copy.deepcopy(old[node_id]) for node_id in keep_ids]

    old["intent_agent"]["data"]["prompt_template"][0]["text"] = """你是“一键游”的意图识别与槽位抽取 Agent，只输出 JSON。
intent 只能是 trip_plan、modify_plan、weather_query、hotel_query、transport_query、general_qa、booking、booking_confirm、memory_manage。
输出 intent、confidence、ready_for_execution、missing_fields、entities、preference_tags、requested_tools、booking_type、selected_option_ids、current_plan_id。
按意图判断必填字段，但不要用完整行程条件阻塞单项查询。weather_query 没有显式城市时允许使用设备当前定位；general_qa 直接就绪；trip_plan 才要求目的地、日期/天数、人数和预算；modify_plan 需要 current_plan_id 或当前会话方案；booking 需要 booking_type 和选项；booking_confirm 必须有订单草稿或 quote_id。
当前明确要求优先于历史记忆。记忆上下文：{{#memory_context_builder.memory_context#}}"""
    old["memory_management_agent"]["data"]["prompt_template"][0]["text"] = """你是用户旅游记忆管理 Agent。向用户简洁说明识别到的偏好新增、修改、删除或查询结果。
当前为 Mock 演示模式：写入状态为 MOCK_WRITTEN 时，说明“演示记忆已更新”，同时明确不会永久保存到真实数据库。
用户可以随时说“查看我的旅行偏好”“忘掉我喜欢早起”“以后优先高铁”。
已有画像：{{#memory_context_builder.memory_context#}}
记忆操作：{{#memory_policy_guard.memory_operations_json#}}
写入状态：{{#long_memory_writer.write_status#}}"""

    old["state_normalizer"]["data"]["code"] = """import json

def main(query: str, intent_raw: str, memory_context: str) -> dict:
    raw = (intent_raw or '').strip().replace('```json', '').replace('```', '')
    if '</think>' in raw:
        raw = raw.split('</think>', 1)[1].strip()
    json_start, json_end = raw.find('{'), raw.rfind('}')
    if json_start >= 0 and json_end >= json_start:
        raw = raw[json_start:json_end + 1]
    try:
        data = json.loads(raw)
    except Exception:
        data = {'intent':'general_qa','confidence':0.0,'ready_for_execution':False,'missing_fields':['clarify_request']}

    # 对高确定性的产品指令做代码兜底，避免 LLM 偶发误分类导致调用错误工具。
    # 复杂语义仍由意图 Agent 负责；这里只覆盖天气、预订等明显关键词。
    text = (query or '').strip().lower()
    deterministic_intent = None
    if any(word in text for word in ['确认提交', '确认下单', '确认预订', '确认购买']):
        deterministic_intent = 'booking_confirm'
    elif any(word in text for word in ['预订', '购买', '下单', '订酒店', '订票']):
        deterministic_intent = 'booking'
    elif any(word in text for word in ['记住', '忘掉', '忘记我的', '旅行偏好', '旅游偏好', '旅行习惯']):
        deterministic_intent = 'memory_manage'
    elif any(word in text for word in ['修改行程', '调整行程', '换成', '改成', '把第']) and any(word in text for word in ['行程', '第', '上午', '下午', '晚上']):
        deterministic_intent = 'modify_plan'
    elif any(word in text for word in ['规划', '攻略', '行程', '安排']) or ('玩' in text and any(word in text for word in ['天', '周末'])):
        deterministic_intent = 'trip_plan'
    elif any(word in text for word in ['天气', '下雨', '温度', '气温']):
        deterministic_intent = 'weather_query'
    elif any(word in text for word in ['酒店', '住宿', '住哪里']):
        deterministic_intent = 'hotel_query'
    elif any(word in text for word in ['高铁', '火车', '飞机', '机票', '交通怎么走']):
        deterministic_intent = 'transport_query'

    if deterministic_intent:
        data['intent'] = deterministic_intent
        data['confidence'] = max(float(data.get('confidence', 0) or 0), 0.99)
        tool_defaults = {
            'weather_query':['weather'],
            'hotel_query':['hotel_search'],
            'transport_query':['route','train_search','flight_search'],
            'trip_plan':['weather','intercity_transport','hotel_area','poi_candidates']
        }
        if deterministic_intent in tool_defaults:
            data['requested_tools'] = tool_defaults[deterministic_intent]
        data['ready_for_execution'] = deterministic_intent not in {'trip_plan', 'booking', 'booking_confirm', 'modify_plan'}
        data['missing_fields'] = []

    def ensure_list(value):
        if value is None:
            return []
        return value if isinstance(value, list) else [value]
    state = {
        'query': query,
        'intent': data.get('intent', 'general_qa'),
        'confidence': float(data.get('confidence', 0) or 0),
        'ready_for_execution': bool(data.get('ready_for_execution', False)),
        'missing_fields': ensure_list(data.get('missing_fields')),
        'entities': data.get('entities', {}),
        'preference_tags': ensure_list(data.get('preference_tags')),
        'requested_tools': ensure_list(data.get('requested_tools')),
        'booking_type': ensure_list(data.get('booking_type')),
        'selected_option_ids': ensure_list(data.get('selected_option_ids')),
        'current_plan_id': data.get('current_plan_id'),
        'current_plan': None,
        'plan_version': None,
        'quote_ids': [],
        'tool_results': {},
        'tool_errors': [],
        'validation_errors': [],
        'revision_count': 0,
        'booking_draft': None,
        'memory_context': memory_context,
        'memory_write_status': 'PENDING'
    }
    return {'intent':state['intent'], 'ready':'true' if state['ready_for_execution'] else 'false', 'state':state, 'state_json':json.dumps(state,ensure_ascii=False)}"""
    old["state_normalizer"]["data"]["outputs"] = {
        "intent": {"children": None, "type": "string"},
        "ready": {"children": None, "type": "string"},
        "state": {"children": None, "type": "object"},
        "state_json": {"children": None, "type": "string"},
    }

    old["long_memory_writer"]["data"]["code"] = """import json

def main(user_id: str, memory_operations_json: str) -> dict:
    try:
        operations = json.loads(memory_operations_json or '{}').get('accepted', [])
    except Exception:
        operations = []
    status = 'NO_CHANGE' if not operations else 'MOCK_WRITTEN'
    return {
        'write_status': status,
        'operation_count': len(operations),
        'memory_patch': {'memory_write_status':status, 'memory_operations':operations},
        'data_mode':'MOCK',
        'upsert_endpoint':'MOCK /tools/memory/profile/upsert',
        'delete_endpoint':'MOCK /tools/memory/profile/item/{memory_id}'
    }"""
    old["long_memory_writer"]["data"]["outputs"]["memory_patch"] = {"children": None, "type": "object"}
    old["long_memory_writer"]["data"]["outputs"]["data_mode"] = {"children": None, "type": "string"}

    nodes = [copy.deepcopy(old[node_id]) for node_id in keep_ids]
    nodes += [
        code_node("pre_route_state", "结构化状态合并 / State Reducer", "将记忆节点的增量补丁合并进 TravelState。", """
def main(state: dict, memory_patch: dict) -> dict:
    merged = dict(state or {})
    merged.update(memory_patch or {})
    return {'state':merged}
""", [("state", ["state_normalizer", "state"]), ("memory_patch", ["long_memory_writer", "memory_patch"])], {"state": "object"}, 3100, 680),
        if_node("supervisor", "总控路由 / Supervisor v2", [
            case("memory_manage", ["state_normalizer", "intent"], "memory_manage"),
            case("booking_confirm", ["state_normalizer", "intent"], "booking_confirm"),
            case("booking", ["state_normalizer", "intent"], "booking"),
        ], 3440, 650),
        code_node("tool_selector", "ToolSelector / 精确工具选择", "依据 intent 和 requested_tools 生成分阶段工具计划，不执行无关工具。", """
def main(state: dict) -> dict:
    intent = (state or {}).get('intent', 'general_qa')
    requested = list(dict.fromkeys((state or {}).get('requested_tools') or []))
    defaults = {
        'weather_query':['weather'], 'hotel_query':['hotel_search'],
        'transport_query':['route','train_search','flight_search'],
        'general_qa':['poi_rag'],
        'trip_plan':['weather','intercity_transport','hotel_area','poi_candidates'],
        'modify_plan':[]
    }
    selected = requested or defaults.get(intent, [])
    if intent == 'trip_plan':
        phase1 = defaults['trip_plan']
        selected = list(dict.fromkeys(phase1 + selected))
    else:
        phase1 = selected
    return {'intent':intent, 'selected_tools':selected, 'phase1_tools':phase1}
""", [("state", ["pre_route_state", "state"])], {"intent":"string", "selected_tools":"array[string]", "phase1_tools":"array[string]"}, 3800, 680),
        if_node("task_router", "任务类型路由", [
            case("trip_plan", ["tool_selector", "intent"], "trip_plan"),
            case("modify_plan", ["tool_selector", "intent"], "modify_plan"),
        ], 4140, 680),
        code_node("query_slot_resolver", "单项查询槽位解析 / LocationResolver", "按当前请求、会话、画像和设备定位解析查询槽位。", """
import json

def main(state: dict) -> dict:
    state = state or {}
    intent = state.get('intent', 'general_qa')
    entities = dict(state.get('entities') or {})
    try:
        memory = json.loads(state.get('memory_context') or '{}')
    except Exception:
        memory = {}
    profile = memory.get('long_term_profile') or {}
    location = (entities.get('location') or entities.get('city') or entities.get('destination')
                or entities.get('current_city') or profile.get('current_city') or profile.get('home_city'))
    location_source = 'context'
    missing = []
    can_execute = True
    if intent in {'weather_query', 'hotel_query'} and not location:
        # 正式小程序由前端 wx.getLocation/城市选择器注入 current_city。
        location = 'DEVICE_CURRENT_CITY'
        location_source = 'device_location'
    if intent == 'transport_query':
        departure = entities.get('departure') or location or 'DEVICE_CURRENT_CITY'
        destination = entities.get('destination')
        entities['departure'] = departure
        if not destination:
            missing.append('destination')
            can_execute = False
    if location:
        entities['resolved_location'] = location
    resolved = {
        'intent': intent,
        'entities': entities,
        'location': location,
        'location_source': location_source,
        'missing_fields': missing,
        'can_execute': can_execute
    }
    return {'can_execute':'true' if can_execute else 'false', 'resolved_context':resolved}
""", [("state", ["pre_route_state", "state"])], {"can_execute":"string", "resolved_context":"object"}, 4500, 80),
        if_node("query_readiness_router", "单项查询专用槽位守卫", [case("execute", ["query_slot_resolver", "can_execute"], "true")], 4860, 80),
        code_node("query_executor", "单项查询执行器", "仅执行 ToolSelector 选中的查询工具；深层结果以 JSON 字符串跨节点传输。", """
import json
def main(state: dict, selected_tools: list, resolved_context: dict) -> dict:
    location=(resolved_context or {}).get('location')
    city='成都' if not location or location == 'DEVICE_CURRENT_CITY' else location
    mock_data = {
        'weather': {
            'city':city, 'observed_at':'2026-07-15 12:00', 'weather':'多云',
            'temperature':28, 'apparent_temperature':30, 'humidity':72,
            'forecast':[{'date':'今天','weather':'多云转阵雨','min':24,'max':31}, {'date':'明天','weather':'小雨','min':23,'max':29}]
        },
        'hotel_search': {
            'city':city,
            'hotels':[
                {'option_id':'HOTEL-CD-001','name':'春熙路轻居酒店','area':'春熙路','nightly_price':458,'rating':4.7,'quote_id':'HQ-001'},
                {'option_id':'HOTEL-CD-002','name':'宽窄巷子漫居酒店','area':'宽窄巷子','nightly_price':389,'rating':4.6,'quote_id':'HQ-002'}
            ]
        },
        'route': {'origin':'当前位置','destination':city,'distance_km':12.6,'duration_minutes':35,'mode':'地铁+步行'},
        'train_search': {'trains':[{'option_id':'TRAIN-G89','train_no':'G89','departure':'08:00','arrival':'12:18','duration_minutes':258,'second_class_price':263,'quote_id':'TQ-G89'}]},
        'flight_search': {'flights':[{'option_id':'FLIGHT-MU2801','flight_no':'MU2801','departure':'09:10','arrival':'11:45','price':720,'quote_id':'FQ-MU2801'}]},
        'poi_rag': {
            'spots':[{'poi_id':'POI-PANDA','name':'成都大熊猫繁育研究基地','tags':['熊猫','亲子']},{'poi_id':'POI-KZ','name':'宽窄巷子','tags':['街区','美食']}],
            'foods':['火锅','担担面','钟水饺'], 'source_titles':['成都景点攻略演示库','成都美食演示库']
        }
    }
    results = {}
    for tool in selected_tools or []:
        results[tool] = {
            'status':'MOCK_SUCCESS', 'data_mode':'MOCK', 'tool':tool,
            'request_context':resolved_context, 'data':mock_data.get(tool, {'message':'演示数据'})
        }
    payload = {'tool_results':results,'tool_errors':[]}
    return {'query_result_json':json.dumps(payload,ensure_ascii=False)}
""", [("state", ["pre_route_state", "state"]), ("selected_tools", ["tool_selector", "selected_tools"]), ("resolved_context", ["query_slot_resolver", "resolved_context"])], {"query_result_json":"string"}, 5220, 80),
        llm_node("query_presenter", "单项查询结果整理 Agent", "天气、酒店、交通或普通问答只整理对应结果，不生成完整行程。", """
根据用户意图和工具结果直接回答问题，不要强行生成多日行程。
意图：{{#tool_selector.intent#}}
工具结果：{{#query_executor.query_result_json#}}
所有工具结果均为 MOCK 演示数据。回答开头简短标注“演示数据”，然后像真实产品一样整理结果，不要说接口待接入。
""", 5580, 80, 0.2, True),
        answer_node("query_answer", "回复 - 单项查询", "{{#query_presenter.text#}}", 5940, 80),
        code_node("plan_slot_guard", "完整行程专用必填字段守卫", "只有 trip_plan 才检查完整规划所需字段。", """
def main(state: dict) -> dict:
    entities=(state or {}).get('entities') or {}
    missing=[]
    if not entities.get('destination'): missing.append('destination')
    if not (entities.get('days') or entities.get('start_date')): missing.append('days_or_start_date')
    if not entities.get('people'): missing.append('people')
    if entities.get('budget') is None: missing.append('budget')
    return {'can_execute':'true' if not missing else 'false','missing_fields':missing}
""", [("state", ["pre_route_state", "state"])], {"can_execute":"string", "missing_fields":"array[string]"}, 4500, 520),
        if_node("plan_readiness_router", "完整行程必填字段路由", [case("execute", ["plan_slot_guard", "can_execute"], "true")], 4860, 520),
        code_node("phase1_research", "规划阶段 1 - 候选检索", "并行执行天气、城际交通、酒店区域和景点候选检索；深层结果使用 JSON 字符串。", """
import json
def main(state: dict, phase1_tools: list) -> dict:
    destination=((state or {}).get('entities') or {}).get('destination') or '成都'
    dataset={
        'weather':{'city':destination,'summary':'多云转阵雨','min_temperature':24,'max_temperature':31,'rain_probability':60},
        'intercity_transport':{
            'options':[
                {'option_id':'TRAIN-G89','type':'train','name':'G89','departure':'08:00','arrival':'12:18','price':263,'quote_id':'TQ-G89'},
                {'option_id':'FLIGHT-MU2801','type':'flight','name':'MU2801','departure':'09:10','arrival':'11:45','price':720,'quote_id':'FQ-MU2801'}
            ]
        },
        'hotel_area':{
            'recommended_area':'春熙路','reason':'餐饮密集且地铁换乘方便',
            'hotels':[{'option_id':'HOTEL-CD-001','name':'春熙路轻居酒店','nightly_price':458,'rating':4.7,'quote_id':'HQ-001'}]
        },
        'poi_candidates':{
            'items':[
                {'poi_id':'POI-PANDA','name':'成都大熊猫繁育研究基地','longitude':104.145,'latitude':30.739,'duration_minutes':240,'ticket_price':55},
                {'poi_id':'POI-KZ','name':'宽窄巷子','longitude':104.059,'latitude':30.670,'duration_minutes':120,'ticket_price':0},
                {'poi_id':'POI-DU','name':'杜甫草堂','longitude':104.028,'latitude':30.660,'duration_minutes':150,'ticket_price':50},
                {'poi_id':'POI-JL','name':'锦里古街','longitude':104.049,'latitude':30.645,'duration_minutes':120,'ticket_price':0}
            ]
        }
    }
    results={tool:{'status':'MOCK_SUCCESS','data_mode':'MOCK','data':dataset.get(tool,{})} for tool in (phase1_tools or [])}
    payload={'tool_results':{'phase1':results},'tool_errors':[]}
    return {'phase1_results_json':json.dumps(results,ensure_ascii=False),'state_patch_json':json.dumps(payload,ensure_ascii=False)}
""", [("state", ["pre_route_state", "state"]), ("phase1_tools", ["tool_selector", "phase1_tools"])], {"phase1_results_json":"string", "state_patch_json":"string"}, 5220, 520),
        llm_node("candidate_selector", "候选景点与住宿区域选择 Agent", "先选候选项，再为第二阶段提供 poi_id 和 destinations。", """
只输出 JSON，字段包含 selected_pois（每项必须有 poi_id、visit_date、estimated_duration）、hotel_area、intercity_option、destinations。没有真实日期时 visit_date 使用 DAY_1、DAY_2。
不得在没有 poi_id 时请求门票，不得在没有 destinations 时请求路线矩阵。
TravelState：{{#pre_route_state.state#}}
第一阶段结果：{{#phase1_research.phase1_results_json#}}
""", 4860, 520),
        code_node("phase2_research", "规划阶段 2 - 精查与路线矩阵", "使用候选 poi_id 查询路线矩阵、开放时间和门票余量。", """
import json
def main(candidate_raw: str, state: dict) -> dict:
    raw=(candidate_raw or '').replace('```json','').replace('```','').strip()
    if '</think>' in raw: raw=raw.split('</think>',1)[1].strip()
    json_start,json_end=raw.find('{'),raw.rfind('}')
    if json_start>=0 and json_end>=json_start: raw=raw[json_start:json_end+1]
    try: candidates=json.loads(raw)
    except Exception: candidates={}
    pois=candidates.get('selected_pois',[])
    destinations=candidates.get('destinations',[])
    errors=[]
    if not pois: errors.append('NO_SELECTED_POI')
    if not destinations: errors.append('NO_ROUTE_DESTINATIONS')
    ticket_prices={'POI-PANDA':55,'POI-KZ':0,'POI-DU':50,'POI-JL':0}
    opening={'POI-PANDA':'07:30-18:00','POI-KZ':'全天开放','POI-DU':'09:00-18:00','POI-JL':'全天开放'}
    details={
        'route_matrix':{'status':'MOCK_SUCCESS','data_mode':'MOCK','destinations':destinations,'legs':[{'from':'春熙路','to':'成都大熊猫繁育研究基地','distance_km':14.2,'duration_minutes':42},{'from':'杜甫草堂','to':'宽窄巷子','distance_km':3.6,'duration_minutes':18}]},
        'opening_hours':{'status':'MOCK_SUCCESS','data_mode':'MOCK','items':[{'poi_id':p.get('poi_id'),'hours':opening.get(p.get('poi_id'),'09:00-18:00')} for p in pois]},
        'ticket_quotes':{'status':'MOCK_SUCCESS','data_mode':'MOCK','items':[{'poi_id':p.get('poi_id'),'visit_date':p.get('visit_date'),'price':ticket_prices.get(p.get('poi_id'),0),'available':True,'quote_id':'MOCK-TICKET-'+str(p.get('poi_id'))} for p in pois]}
    }
    patch={'tool_results':{'phase2':details},'tool_errors':errors}
    return {'candidates_json':json.dumps(candidates,ensure_ascii=False),'phase2_results_json':json.dumps(details,ensure_ascii=False),'state_patch_json':json.dumps(patch,ensure_ascii=False)}
""", [("candidate_raw", ["candidate_selector", "text"]), ("state", ["pre_route_state", "state"])], {"candidates_json":"string", "phase2_results_json":"string", "state_patch_json":"string"}, 5220, 520),
        code_node("planning_state_reducer", "规划状态合并 / State Reducer", "将两阶段工具补丁和候选项合并为结构化规划状态。", """
import json
def main(state: dict, phase1_patch_json: str, phase2_patch_json: str, candidates_json: str) -> dict:
    merged=dict(state or {})
    try: phase1_patch=json.loads(phase1_patch_json or '{}')
    except Exception: phase1_patch={}
    try: phase2_patch=json.loads(phase2_patch_json or '{}')
    except Exception: phase2_patch={}
    try: candidates=json.loads(candidates_json or '{}')
    except Exception: candidates={}
    tool_results=dict(merged.get('tool_results') or {})
    tool_results.update((phase1_patch or {}).get('tool_results') or {})
    tool_results.update((phase2_patch or {}).get('tool_results') or {})
    merged['tool_results']=tool_results
    merged['tool_errors']=list(dict.fromkeys((merged.get('tool_errors') or []) + ((phase1_patch or {}).get('tool_errors') or []) + ((phase2_patch or {}).get('tool_errors') or [])))
    merged['selected_candidates']=candidates or {}
    return {'planning_state_json':json.dumps(merged,ensure_ascii=False)}
""", [("state", ["pre_route_state", "state"]), ("phase1_patch_json", ["phase1_research", "state_patch_json"]), ("phase2_patch_json", ["phase2_research", "state_patch_json"]), ("candidates_json", ["phase2_research", "candidates_json"])], {"planning_state_json":"string"}, 5580, 520),
        llm_node("planner", "完整行程规划 Agent", "仅 trip_plan 进入，使用两阶段研究结果生成结构化行程。", """
只输出 JSON 行程，包含 data_mode="MOCK"、plan_id="MOCK-PLAN-001"、plan_version、hotel_nights、days、selected_hotels、selected_transport、selected_tickets、quote_ids、budget_items、total_cost。
days 中每个项目包含 day_id、item_id、visit_start、visit_end、travel_minutes、visit_minutes、available_minutes。使用给定 Mock 价格，不要再生成其他价格。规划状态：{{#planning_state_reducer.planning_state_json#}}
""", 5940, 520),
        code_node("hard_validator", "代码硬校验", "用代码检查天数、住宿晚数、预算、时间和必要标识。", """
import json
def main(plan_raw: str, planning_state_json: str) -> dict:
    raw=(plan_raw or '').replace('```json','').replace('```','').strip()
    if '</think>' in raw: raw=raw.split('</think>',1)[1].strip()
    json_start,json_end=raw.find('{'),raw.rfind('}')
    if json_start>=0 and json_end>=json_start: raw=raw[json_start:json_end+1]
    errors=[]
    try: plan=json.loads(raw)
    except Exception: plan={}; errors.append('PLAN_NOT_JSON')
    try: state=json.loads(planning_state_json or '{}')
    except Exception: state={}
    days=plan.get('days') or []
    expected=(state or {}).get('entities',{}).get('days')
    if isinstance(expected,int) and len(days)!=expected: errors.append('DAY_COUNT_MISMATCH')
    nights=plan.get('hotel_nights')
    if isinstance(expected,int) and nights is not None and nights!=max(expected-1,0): errors.append('HOTEL_NIGHTS_MISMATCH')
    budget=(state or {}).get('entities',{}).get('budget')
    total=plan.get('total_cost')
    if isinstance(budget,(int,float)) and isinstance(total,(int,float)) and total>budget: errors.append('BUDGET_EXCEEDED')
    if not plan.get('plan_id'): errors.append('MISSING_PLAN_ID')
    for day in days:
        for item in day.get('items',[]) if isinstance(day,dict) else []:
            available=item.get('available_minutes')
            required=(item.get('travel_minutes') or 0)+(item.get('visit_minutes') or 0)
            if isinstance(available,(int,float)) and required>available: errors.append('TIME_WINDOW_EXCEEDED')
            start=item.get('visit_start'); end=item.get('visit_end')
            if start and end and start>=end: errors.append('INVALID_VISIT_TIME')
    return {'hard_pass':'true' if not errors else 'false','validation_errors':errors,'plan_json':json.dumps(plan,ensure_ascii=False)}
""", [("plan_raw", ["planner", "text"]), ("planning_state_json", ["planning_state_reducer", "planning_state_json"])], {"hard_pass":"string", "validation_errors":"array[string]", "plan_json":"string"}, 6300, 520),
        llm_node("soft_reviewer", "LLM 软评审", "只判断节奏、体验、偏好匹配和表达质量。", """
只输出 JSON：{"verdict":"pass|revise","issues":[],"suggestions":[]}。
代码硬校验错误：{{#hard_validator.validation_errors#}}
行程：{{#hard_validator.plan_json#}}
判断是否太赶、是否符合偏好、体验是否均衡；不要重新计算预算和时间公式。存在任何硬错误时 verdict 必须为 revise。
""", 6660, 520),
        code_node("review_parser", "评审结果解析", "解析软评审并形成循环条件。", """
import json
def main(review_raw: str) -> dict:
    raw=(review_raw or '').replace('```json','').replace('```','').strip()
    if '</think>' in raw: raw=raw.split('</think>',1)[1].strip()
    json_start,json_end=raw.find('{'),raw.rfind('}')
    if json_start>=0 and json_end>=json_start: raw=raw[json_start:json_end+1]
    try: data=json.loads(raw)
    except Exception: data={'verdict':'revise','issues':['REVIEW_NOT_JSON']}
    return {'verdict':data.get('verdict','revise'),'review':data}
""", [("review_raw", ["soft_reviewer", "text"])], {"verdict":"string", "review":"object"}, 7020, 520),
        if_node("quality_router_v2", "自检循环路由", [case("pass", ["review_parser", "verdict"], "pass")], 7380, 520),
        answer_node("plan_answer", "最终行程（校验通过）", "{{#planner.text#}}", 7740, 400),
        llm_node("revision", "行程修订 Agent", "根据硬错误和软评审做一次局部修订。", """
只输出修订后的完整 JSON 行程。不得删除 plan_id，plan_version 加 1。
原计划：{{#hard_validator.plan_json#}}
硬错误：{{#hard_validator.validation_errors#}}
软评审：{{#review_parser.review#}}
""", 7740, 700),
        code_node("second_hard_validator", "第二轮代码硬校验", "修订后再次执行确定性规则，最多两轮。", """
import json
def main(plan_raw: str, planning_state_json: str) -> dict:
    raw=(plan_raw or '').replace('```json','').replace('```','').strip(); errors=[]
    if '</think>' in raw: raw=raw.split('</think>',1)[1].strip()
    json_start,json_end=raw.find('{'),raw.rfind('}')
    if json_start>=0 and json_end>=json_start: raw=raw[json_start:json_end+1]
    try: plan=json.loads(raw)
    except Exception: plan={}; errors.append('PLAN_NOT_JSON')
    try: state=json.loads(planning_state_json or '{}')
    except Exception: state={}
    if not plan.get('plan_id'): errors.append('MISSING_PLAN_ID')
    budget=(state or {}).get('entities',{}).get('budget'); total=plan.get('total_cost')
    if isinstance(budget,(int,float)) and isinstance(total,(int,float)) and total>budget: errors.append('BUDGET_EXCEEDED')
    days=plan.get('days') or []; expected=(state or {}).get('entities',{}).get('days')
    if isinstance(expected,int) and len(days)!=expected: errors.append('DAY_COUNT_MISMATCH')
    nights=plan.get('hotel_nights')
    if isinstance(expected,int) and nights is not None and nights!=max(expected-1,0): errors.append('HOTEL_NIGHTS_MISMATCH')
    for day in days:
        for item in day.get('items',[]) if isinstance(day,dict) else []:
            available=item.get('available_minutes'); required=(item.get('travel_minutes') or 0)+(item.get('visit_minutes') or 0)
            if isinstance(available,(int,float)) and required>available: errors.append('TIME_WINDOW_EXCEEDED')
            if item.get('visit_start') and item.get('visit_end') and item['visit_start']>=item['visit_end']: errors.append('INVALID_VISIT_TIME')
    return {'validation_errors':errors,'plan_json':json.dumps(plan,ensure_ascii=False),'revision_count':1}
""", [("plan_raw", ["revision", "text"]), ("planning_state_json", ["planning_state_reducer", "planning_state_json"])], {"validation_errors":"array[string]", "plan_json":"string", "revision_count":"number"}, 8100, 700),
        llm_node("final_reviewer", "第二轮终审", "结合第二轮硬校验给出最终可用性说明。", """
输出最终行程及简短风险提示。不得隐藏仍存在的硬错误。
修订计划：{{#second_hard_validator.plan_json#}}
剩余硬错误：{{#second_hard_validator.validation_errors#}}
""", 8460, 700),
        answer_node("revised_plan_answer", "最终行程（修订后）", "{{#final_reviewer.text#}}", 8820, 700),
        code_node("current_plan_loader", "加载结构化当前方案", "按 plan_id/version 读取可修改的结构化行程，深层计划使用 JSON 字符串。", """
import json
def main(state: dict) -> dict:
    plan_id=(state or {}).get('current_plan_id') or 'CURRENT_SESSION_PLAN'
    plan={
        'status':'MOCK_SUCCESS','data_mode':'MOCK','plan_id':plan_id,'plan_version':1,
        'days':[
            {'day_id':'DAY-1','title':'熊猫与市井成都','items':[{'item_id':'ITEM-PANDA','poi_id':'POI-PANDA','name':'成都大熊猫繁育研究基地','visit_start':'08:00','visit_end':'12:00'},{'item_id':'ITEM-KZ','poi_id':'POI-KZ','name':'宽窄巷子','visit_start':'15:00','visit_end':'17:00'}]},
            {'day_id':'DAY-2','title':'人文成都','items':[{'item_id':'ITEM-DU','poi_id':'POI-DU','name':'杜甫草堂','visit_start':'09:30','visit_end':'12:00'}]}
        ],
        'selected_hotels':[{'option_id':'HOTEL-CD-001','name':'春熙路轻居酒店'}],
        'selected_transport':[{'option_id':'TRAIN-G89','name':'G89'}]
    }
    return {'current_plan_json':json.dumps(plan,ensure_ascii=False),'current_plan_id':plan_id,'plan_version':1}
""", [("state", ["pre_route_state", "state"])], {"current_plan_json":"string", "current_plan_id":"string", "plan_version":"number"}, 4500, 980),
        llm_node("modify_agent", "局部行程修改 Agent", "根据结构化计划定位具体日期和选项，不从聊天文本猜。", """
只输出修改后的完整 JSON 行程，保留 plan_id，plan_version 加 1。
当前计划：{{#current_plan_loader.current_plan_json#}}
修改要求：{{#sys.query#}}
必须使用 day_id、option_id 或时间段定位修改对象。
""", 4860, 980, 0.2, True),
        code_node("modify_validator", "修改方案代码校验", "修改后执行确定性完整性检查。", """
import json
def main(plan_raw: str) -> dict:
    raw=(plan_raw or '').replace('```json','').replace('```','').strip(); errors=[]
    if '</think>' in raw: raw=raw.split('</think>',1)[1].strip()
    json_start,json_end=raw.find('{'),raw.rfind('}')
    if json_start>=0 and json_end>=json_start: raw=raw[json_start:json_end+1]
    try: plan=json.loads(raw)
    except Exception: plan={}; errors.append('PLAN_NOT_JSON')
    if not plan.get('plan_id'): errors.append('MISSING_PLAN_ID')
    if not plan.get('plan_version'): errors.append('MISSING_PLAN_VERSION')
    return {'plan_json':json.dumps(plan,ensure_ascii=False),'validation_errors':errors}
""", [("plan_raw", ["modify_agent", "text"])], {"plan_json":"string", "validation_errors":"array[string]"}, 5220, 980),
        llm_node("modify_reviewer", "修改结果软评审", "检查局部修改后的节奏和偏好匹配。", """
简洁输出修改后的行程和变更摘要；如有硬错误必须明确提示。
计划：{{#modify_validator.plan_json#}}
硬错误：{{#modify_validator.validation_errors#}}
""", 5580, 980),
        answer_node("modify_answer", "回复 - 修改后的方案", "{{#modify_reviewer.text#}}", 5940, 980),
        code_node("booking_quote_refresher", "预订 1 - 刷新所选项报价", "只查询 booking_type 指定的产品，不创建订单；报价列表使用 JSON 字符串。", """
import json
def main(state: dict) -> dict:
    types=(state or {}).get('booking_type') or []
    selected=(state or {}).get('selected_option_ids') or []
    if isinstance(types,str): types=[types]
    if isinstance(selected,str): selected=[selected]
    catalog={
        'hotel':{'item_name':'春熙路轻居酒店','unit_price':458,'quantity':2,'total_price':916,'quote_id':'MOCK-HQ-001'},
        'train':{'item_name':'G89 二等座','unit_price':263,'quantity':1,'total_price':263,'quote_id':'MOCK-TQ-G89'},
        'flight':{'item_name':'MU2801 经济舱','unit_price':720,'quantity':1,'total_price':720,'quote_id':'MOCK-FQ-MU2801'},
        'ticket':{'item_name':'成都大熊猫繁育研究基地门票','unit_price':55,'quantity':1,'total_price':55,'quote_id':'MOCK-PQ-PANDA'}
    }
    quotes={t:{'status':'MOCK_QUOTED','data_mode':'MOCK','selected_option_ids':selected,**catalog.get(t,{'item_name':'演示产品','unit_price':0,'quantity':1,'total_price':0,'quote_id':'MOCK-QUOTE'})} for t in types}
    return {'quotes_json':json.dumps(quotes,ensure_ascii=False),'quote_types':types}
""", [("state", ["pre_route_state", "state"])], {"quotes_json":"string", "quote_types":"array[string]"}, 3800, 1260),
        code_node("booking_draft_builder", "预订 2 - 生成订单草稿", "生成无副作用 DRAFT，等待用户确认。", """
import json
def main(quotes_json: str, state: dict) -> dict:
    try: quotes=json.loads(quotes_json or '{}')
    except Exception: quotes={}
    total=sum((item or {}).get('total_price',0) for item in (quotes or {}).values())
    draft={'status':'MOCK_DRAFT','data_mode':'MOCK','draft_id':'MOCK-DRAFT-001','booking_types':list((quotes or {}).keys()),'items':quotes or {},'total_price':total,'requires_confirmation':True,'confirmation_token':None}
    return {'booking_draft_json':json.dumps(draft,ensure_ascii=False)}
""", [("quotes_json", ["booking_quote_refresher", "quotes_json"]), ("state", ["pre_route_state", "state"])], {"booking_draft_json":"string"}, 4160, 1260),
        llm_node("booking_confirmation", "预订 3 - 草稿确认 Agent", "展示草稿，要求用户明确确认，不调用真实预订。", """
向用户展示订单草稿，只包含 booking_type 指定的项目。明确标注“演示订单，不会真实扣款或下单”，然后询问是否确认演示提交。
订单草稿：{{#booking_draft_builder.booking_draft_json#}}
""", 4520, 1260, 0.1, True),
        answer_node("booking_draft_answer", "回复 - 等待预订确认", "{{#booking_confirmation.text#}}", 4880, 1260),
        code_node("booking_submit_gateway", "预订 4 - 确认后提交网关", "仅 booking_confirm 意图可进入；原型仍不产生真实订单。", """
def main(state: dict) -> dict:
    booking_type=(state or {}).get('booking_type') or []
    if isinstance(booking_type,str): booking_type=[booking_type]
    return {'submit_status':'MOCK_SUCCESS','data_mode':'MOCK','mock_order_id':'MOCK-ORDER-001','endpoint':'MOCK POST /bookings/submit','requires_valid_confirmation_token':True,'booking_type':booking_type}
""", [("state", ["pre_route_state", "state"])], {"submit_status":"string", "data_mode":"string", "mock_order_id":"string", "endpoint":"string", "requires_valid_confirmation_token":"boolean", "booking_type":"array[string]"}, 3800, 1540),
        answer_node("booking_submit_answer", "回复 - 预订提交状态", "演示提交状态：{{#booking_submit_gateway.submit_status#}}；演示订单号：{{#booking_submit_gateway.mock_order_id#}}。这是 Mock 结果，不会创建真实订单。", 4160, 1540),
    ]

    # Restore modified kept nodes from old map.
    kept = {node["id"]: node for node in nodes}
    for node_id in keep_ids:
        if node_id in old:
            kept[node_id] = copy.deepcopy(old[node_id])
    nodes = [kept[node_id] for node_id in keep_ids] + [node for node in nodes if node["id"] not in keep_ids]

    supervisor_cases = [
        case("memory_manage", ["state_normalizer", "intent"], "memory_manage"),
        case("booking_confirm", ["state_normalizer", "intent"], "booking_confirm"),
        case("booking", ["state_normalizer", "intent"], "booking"),
    ]
    for node in nodes:
        if node["id"] == "supervisor":
            node["data"]["cases"] = supervisor_cases

    edges = [
        edge("start-short", "start", "short_memory_loader", "start", "code"),
        edge("short-long", "short_memory_loader", "long_memory_reader", "code", "code"),
        edge("long-context", "long_memory_reader", "memory_context_builder", "code", "code"),
        edge("context-intent", "memory_context_builder", "intent_agent", "code", "llm"),
        edge("intent-state", "intent_agent", "state_normalizer", "llm", "code"),
        edge("state-memory-candidate", "state_normalizer", "memory_candidate_agent", "code", "llm"),
        edge("candidate-policy", "memory_candidate_agent", "memory_policy_guard", "llm", "code"),
        edge("policy-writer", "memory_policy_guard", "long_memory_writer", "code", "code"),
        edge("writer-state", "long_memory_writer", "pre_route_state", "code", "code"),
        edge("state-supervisor", "pre_route_state", "supervisor", "code", "if-else"),
        edge("supervisor-memory", "supervisor", "memory_management_agent", "if-else", "llm", "memory_manage"),
        edge("memory-answer", "memory_management_agent", "memory_management_answer", "llm", "answer"),
        edge("supervisor-booking-confirm", "supervisor", "booking_submit_gateway", "if-else", "code", "booking_confirm"),
        edge("submit-answer", "booking_submit_gateway", "booking_submit_answer", "code", "answer"),
        edge("supervisor-booking", "supervisor", "booking_quote_refresher", "if-else", "code", "booking"),
        edge("quote-draft", "booking_quote_refresher", "booking_draft_builder", "code", "code"),
        edge("draft-confirm", "booking_draft_builder", "booking_confirmation", "code", "llm"),
        edge("confirm-answer", "booking_confirmation", "booking_draft_answer", "llm", "answer"),
        edge("supervisor-tool-selector", "supervisor", "tool_selector", "if-else", "code", "false"),
        edge("clarify-answer", "clarification_agent", "clarification_answer", "llm", "answer"),
        edge("selector-task-router", "tool_selector", "task_router", "code", "if-else"),
        edge("task-trip", "task_router", "plan_slot_guard", "if-else", "code", "trip_plan"),
        edge("plan-slots-route", "plan_slot_guard", "plan_readiness_router", "code", "if-else"),
        edge("plan-ready-phase1", "plan_readiness_router", "phase1_research", "if-else", "code", "execute"),
        edge("plan-missing-clarify", "plan_readiness_router", "clarification_agent", "if-else", "llm", "false"),
        edge("phase1-candidates", "phase1_research", "candidate_selector", "code", "llm"),
        edge("candidates-phase2", "candidate_selector", "phase2_research", "llm", "code"),
        edge("phase2-reducer", "phase2_research", "planning_state_reducer", "code", "code"),
        edge("reducer-planner", "planning_state_reducer", "planner", "code", "llm"),
        edge("planner-hard", "planner", "hard_validator", "llm", "code"),
        edge("hard-soft", "hard_validator", "soft_reviewer", "code", "llm"),
        edge("soft-parser", "soft_reviewer", "review_parser", "llm", "code"),
        edge("parser-quality", "review_parser", "quality_router_v2", "code", "if-else"),
        edge("quality-pass", "quality_router_v2", "plan_answer", "if-else", "answer", "pass"),
        edge("quality-revise", "quality_router_v2", "revision", "if-else", "llm", "false"),
        edge("revision-hard2", "revision", "second_hard_validator", "llm", "code"),
        edge("hard2-final", "second_hard_validator", "final_reviewer", "code", "llm"),
        edge("final-revised-answer", "final_reviewer", "revised_plan_answer", "llm", "answer"),
        edge("task-modify", "task_router", "current_plan_loader", "if-else", "code", "modify_plan"),
        edge("load-modify", "current_plan_loader", "modify_agent", "code", "llm"),
        edge("modify-validate", "modify_agent", "modify_validator", "llm", "code"),
        edge("modify-review", "modify_validator", "modify_reviewer", "code", "llm"),
        edge("modify-answer", "modify_reviewer", "modify_answer", "llm", "answer"),
        edge("task-query", "task_router", "query_slot_resolver", "if-else", "code", "false"),
        edge("query-slots-route", "query_slot_resolver", "query_readiness_router", "code", "if-else"),
        edge("query-ready-execute", "query_readiness_router", "query_executor", "if-else", "code", "execute"),
        edge("query-missing-clarify", "query_readiness_router", "clarification_agent", "if-else", "llm", "false"),
        edge("query-present", "query_executor", "query_presenter", "code", "llm"),
        edge("query-answer", "query_presenter", "query_answer", "llm", "answer"),
    ]

    dsl["app"]["name"] = "一键游 Multi-Agent 演示原型 v2"
    dsl["app"]["description"] = "纯 Mock 演示模式：按意图精确分流、两阶段研究、结构化状态、预订草稿、代码硬校验与 LLM 软评审。"
    dsl["workflow"]["features"]["opening_statement"] = "当前为一键游 Multi-Agent 架构演示，天气、酒店、交通、景点、门票和预订均使用结构化 Mock 数据，不会产生真实查询、扣款或订单。"
    dsl["workflow"]["graph"]["nodes"] = nodes
    dsl["workflow"]["graph"]["edges"] = edges
    DSL_PATH.write_text(yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


if __name__ == "__main__":
    main()
