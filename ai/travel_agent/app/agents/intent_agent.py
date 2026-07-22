from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain.models import BudgetMode, BudgetScope, Intent, IntentContext, IntentDecision, TravelEntities


class IntentAgent(Protocol):
    def classify(self, query: str, *, context: IntentContext | None = None) -> IntentDecision:
        """Synchronous structured classification."""

    async def aclassify(
        self,
        query: str,
        *,
        context: IntentContext | None = None,
    ) -> IntentDecision:
        """Asynchronous structured classification."""


class LangChainIntentAgent:
    """Production adapter for any LangChain chat model with structured output."""

    def __init__(self, model: BaseChatModel) -> None:
        self._runner = model.with_structured_output(
            IntentDecision,
            method="function_calling",
            strict=True,
        )

    def classify(self, query: str, *, context: IntentContext | None = None) -> IntentDecision:
        result = self._runner.invoke(self._messages(query, context))
        return result if isinstance(result, IntentDecision) else IntentDecision.model_validate(result)

    async def aclassify(
        self,
        query: str,
        *,
        context: IntentContext | None = None,
    ) -> IntentDecision:
        result = await self._runner.ainvoke(self._messages(query, context))
        return result if isinstance(result, IntentDecision) else IntentDecision.model_validate(result)

    @staticmethod
    def _messages(
        query: str,
        context: IntentContext | None,
    ) -> list[SystemMessage | HumanMessage]:
        context_json = (context or IntentContext()).model_dump_json()
        return [
            SystemMessage(
                content=(
                    "你是‘一键游’的意图识别与槽位抽取 Agent。结合最近对话、长期偏好、当前方案和预订草稿理解指代，"
                    "但 entities 只提取用户本轮明确表达或明确补充的值，不得从记忆中伪造新槽位。"
                    "只输出结构化结果。intent 必须使用给定枚举，不要决定工作流，不要补造预算、人数、日期或选项 ID。"
                    "本轮明确表达优先于历史信息。‘想去/准备去/计划去某地’属于 trip_plan；"
                    "只问天气、酒店、交通时分别使用 weather_query、hotel_query、transport_query。"
                    "普通旅游知识问答使用 general_qa，已有信息足够回答时不得为了画像补全而改成 trip_plan。"
                    "‘把第二天…’、‘换掉上次方案…’且存在当前方案时属于 modify_plan。"
                    "‘确认提交/确认预订’且存在待确认草稿时属于 booking_confirm。"
                    "‘上次方案、第二天、确认提交’等指代必须结合 checkpoint 中的当前对象理解。"
                    f"今天的日期是 {date.today().isoformat()}，今天/明天/后天必须以这个日期为基准解析。"
                    "预算区分 total/per_person，日期分别输出 start_date/end_date/days。"
                    "用户要求系统估算预算、表示不知道预算时，不要虚构 budget 数值；budget_mode 输出 estimate。"
                    "用户强调尽可能省、最低预算或穷游时，budget_mode 输出 minimize。"
                )
            ),
            HumanMessage(content=f"会话上下文：{context_json}\n本轮用户输入：{query}"),
        ]


class RuleBasedIntentAgent:
    """Deterministic development adapter used until an LLM is configured."""

    DESTINATION_NAMES = (
        "北京", "上海", "天津", "重庆", "成都", "西安", "杭州", "大理", "广州", "深圳", "南京", "苏州",
        "新疆", "乌鲁木齐", "喀什", "伊犁", "阿勒泰", "西藏", "拉萨", "云南", "昆明", "丽江", "香格里拉",
        "四川", "贵州", "贵阳", "海南", "三亚", "海口", "青海", "西宁", "甘肃", "兰州", "敦煌", "内蒙古",
        "呼和浩特", "广西", "桂林", "福建", "厦门", "泉州", "长沙", "武汉", "哈尔滨", "长春", "沈阳",
        "济南", "青岛", "威海", "郑州", "洛阳", "合肥", "南昌", "福州",
    )
    PREFERENCE_TAGS = (
        "自然景观", "历史文化", "美食", "海鲜", "徒步", "摄影", "亲子", "购物",
        "夜生活", "高铁", "飞机",
    )
    CHINESE_NUMBERS = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def classify(self, query: str, *, context: IntentContext | None = None) -> IntentDecision:
        del context
        text = query.strip()
        intent = self._detect_intent(text)
        entities = self._extract_entities(text, intent)
        confidence = 0.99 if intent is not Intent.GENERAL_QA else 0.75
        return IntentDecision(intent=intent, entities=entities, confidence=confidence)

    async def aclassify(
        self,
        query: str,
        *,
        context: IntentContext | None = None,
    ) -> IntentDecision:
        return self.classify(query, context=context)

    def _detect_intent(self, text: str) -> Intent:
        if any(word in text for word in ("记住", "旅游偏好", "我的偏好", "修改偏好", "删除偏好")):
            return Intent.MEMORY_MANAGE
        if any(word in text for word in ("确认预订", "确认下单", "确认购买", "确认提交")):
            return Intent.BOOKING_CONFIRM
        if any(word in text for word in ("预订", "下单", "购买", "订酒店", "订票")):
            return Intent.BOOKING
        # 明确提出新规划时，句子里的“不要购物”等内容属于本次偏好，
        # 不能被误判为对旧方案的修改。
        if any(word in text for word in ("规划", "旅游方案", "几日游", "日游", "天游")):
            return Intent.TRIP_PLAN
        if any(
            word in text
            for word in (
                "换成",
                "调整",
                "修改",
                "降低",
                "提高",
                "删掉",
                "不要购物",
                "交换",
                "调换",
            )
        ):
            return Intent.MODIFY_PLAN
        if "行程" in text:
            return Intent.TRIP_PLAN
        if re.search(r".+?(?:去|到|前往).+", text) and any(
            marker in text for marker in ("天", "预算", "出发", "旅游", "旅行")
        ):
            return Intent.TRIP_PLAN
        if any(word in text for word in ("天气", "下雨", "温度", "气温")):
            return Intent.WEATHER_QUERY
        if any(word in text for word in ("酒店", "住宿", "住哪里")):
            return Intent.HOTEL_QUERY
        if any(word in text for word in ("高铁", "火车", "飞机", "机票", "怎么去", "交通")):
            return Intent.TRANSPORT_QUERY
        if any(place in text for place in self.DESTINATION_NAMES) and any(
            phrase in text for phrase in ("想去", "想要去", "准备去", "打算去", "计划去", "要去", "去玩")
        ):
            return Intent.TRIP_PLAN
        return Intent.GENERAL_QA

    def _extract_entities(self, text: str, intent: Intent) -> TravelEntities:
        values: dict = {}
        cities = sorted((city for city in self.DESTINATION_NAMES if city in text), key=text.index)
        has_explicit_direction = bool(
            len(cities) >= 2
            and re.search(r".+?(?:去|到|前往).+", text)
        )
        # "从北京出发" sets origin without needing a direction word to destination
        explicit_origin_match = re.search(r"从\s*(" + "|".join(self.DESTINATION_NAMES) + r")\s*(?:出发|走|离开)", text)
        if explicit_origin_match:
            origin_city = explicit_origin_match.group(1)
            if cities and cities[0] == origin_city and len(cities) >= 2:
                # "从北京出发，去成都" → origin=北京, dest=成都
                values["origin"], values["destination"] = cities[0], cities[1]
            elif origin_city in cities:
                # 北京 is both in text, mark it as origin
                values["origin"] = origin_city
                remaining = [c for c in cities if c != origin_city]
                if remaining:
                    values["destination"] = remaining[-1]
            else:
                values["origin"] = origin_city
        elif len(cities) >= 2 and (intent is Intent.TRANSPORT_QUERY or has_explicit_direction):
            values["origin"], values["destination"] = cities[0], cities[-1]
        elif cities:
            values["destination"] = cities[-1]

        duration_number = r"(\d{1,2}|[一二两三四五六七八九十])"
        days_match = re.search(rf"{duration_number}\s*(?:天|日)游", text)
        if not days_match and intent in {Intent.TRIP_PLAN, Intent.GENERAL_QA}:
            # 裸写“3 天”常用于回答规划追问；日期中的“8 月 1 日”不会命中。
            days_match = re.search(rf"{duration_number}\s*天", text)
        if days_match:
            raw_days = days_match.group(1)
            values["days"] = int(raw_days) if raw_days.isdigit() else self.CHINESE_NUMBERS[raw_days]

        people_match = re.search(r"(\d{1,3}|[一二两三四五六七八九十])\s*(?:个)?人", text)
        if people_match:
            raw_people = people_match.group(1)
            values["people"] = int(raw_people) if raw_people.isdigit() else self.CHINESE_NUMBERS[raw_people]

        budget_match = re.search(r"(人均|每人|总预算|预算)\s*(\d+(?:\.\d+)?)\s*(?:元)?", text)
        if budget_match:
            values["budget"] = Decimal(budget_match.group(2))
            values["budget_scope"] = (
                BudgetScope.PER_PERSON if budget_match.group(1) in {"人均", "每人"} else BudgetScope.TOTAL
            )
        if re.search(
            r"(?:估计|估算|算算|帮我算).{0,8}(?:预算|费用|多少钱)|"
            r"(?:预算|费用).{0,8}(?:估|算|多少)|需要多少(?:预算|钱)",
            text,
        ):
            values["budget_mode"] = (
                BudgetMode.MINIMIZE
                if re.search(r"尽可能少|越少越好|越省越好|最低预算|最省|穷游", text)
                else BudgetMode.ESTIMATE
            )

        parsed_dates = self._extract_dates(text)
        if parsed_dates:
            values["start_date"] = parsed_dates[0]
        if len(parsed_dates) > 1:
            values["end_date"] = parsed_dates[1]

        liked: list[str] = []
        disliked: list[str] = []
        for tag in self.PREFERENCE_TAGS:
            if not re.search(rf"(?:不要|不喜欢|避开|拒绝)[^，。；]{{0,8}}{re.escape(tag)}", text) and (
                re.search(
                    rf"(?:喜欢|偏爱|想看|想吃|爱好|爱吃|多安排)[^，。；]{{0,8}}{re.escape(tag)}",
                    text,
                )
                or (tag == "美食" and "吃货" in text)
            ):
                liked.append(tag)
            if re.search(rf"(?:不要|不喜欢|避开|拒绝)[^，。；]{{0,8}}{re.escape(tag)}", text):
                disliked.append(tag)
        if liked:
            values["explicit_preferences"] = liked
        if disliked:
            values["explicit_dislikes"] = disliked

        booking_types = [
            kind
            for keyword, kind in (("酒店", "hotel"), ("火车", "train"), ("高铁", "train"), ("飞机", "flight"), ("门票", "ticket"))
            if keyword in text
        ]
        if booking_types and intent in {Intent.BOOKING, Intent.BOOKING_CONFIRM}:
            values["booking_types"] = list(dict.fromkeys(booking_types))
        option_ids = re.findall(
            r"\b(?:AREA|HOTEL|TRAIN|FLIGHT|TRANSPORT|TICKET)-[A-Z0-9-]+\b",
            text.upper(),
        )
        if option_ids:
            values["selected_option_ids"] = option_ids
        return TravelEntities(**values)

    @staticmethod
    def _extract_dates(text: str) -> list[date]:
        result: list[date] = []
        for marker, offset in (("今天", 0), ("明天", 1), ("后天", 2)):
            if marker in text:
                result.append(date.fromordinal(date.today().toordinal() + offset))
                break
        for year, month, day in re.findall(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]", text):
            result.append(date(int(year) if year else date.today().year, int(month), int(day)))
        return result
