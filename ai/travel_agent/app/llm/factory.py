from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.agents.intent_agent import LangChainIntentAgent, RuleBasedIntentAgent
from app.agents.memory_agent import (
    LangChainMemoryCandidateAgent,
    RuleBasedMemoryCandidateAgent,
)
from app.agents.direct_modify_agent import (
    LangChainDirectModifyAgent,
    RuleBasedDirectModifyAgent,
)
from app.agents.candidate_selector import (
    LangChainCandidateSelectorAgent,
    RuleBasedCandidateSelectorAgent,
)
from app.agents.clarification_agent import (
    LangChainClarificationAgent,
    RuleBasedClarificationAgent,
)
from app.agents.modify_agent import (
    LangChainModifyAnalyzerAgent,
    RuleBasedModifyAnalyzerAgent,
)
from app.agents.planner_agent import LangChainPlannerAgent, RuleBasedPlannerAgent
from app.agents.plan_presenter import (
    LangChainPlanPresenterAgent,
    RuleBasedPlanPresenterAgent,
)
from app.agents.query_presenter import (
    LangChainQueryPresenterAgent,
    RuleBasedQueryPresenterAgent,
)
from app.agents.reviewer_agent import LangChainReviewerAgent, RuleBasedReviewerAgent
from app.agents.revision_agent import LangChainRevisionAgent, RuleBasedRevisionAgent
from app.agents.research_agent import (
    LangChainPhase1ResearchAgent,
    LangChainPhase2ResearchAgent,
    RuleBasedPhase1ResearchAgent,
    RuleBasedPhase2ResearchAgent,
)
from app.config import Settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentOverrides:
    mode: str
    intent_agent: Any | None = None
    clarification_agent: Any | None = None
    memory_candidate_agent: Any | None = None
    candidate_selector: Any | None = None
    query_presenter: Any | None = None
    phase1_research_agent: Any | None = None
    phase2_research_agent: Any | None = None
    direct_modify_agent: Any | None = None
    planner_agent: Any | None = None
    plan_presenter: Any | None = None
    reviewer_agent: Any | None = None
    revision_agent: Any | None = None
    modify_analyzer_agent: Any | None = None

    def graph_kwargs(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "intent_agent": self.intent_agent,
                "clarification_agent": self.clarification_agent,
                "memory_candidate_agent": self.memory_candidate_agent,
                "candidate_selector": self.candidate_selector,
                "query_presenter": self.query_presenter,
                "phase1_research_agent": self.phase1_research_agent,
                "phase2_research_agent": self.phase2_research_agent,
                "direct_modify_agent": self.direct_modify_agent,
                "planner_agent": self.planner_agent,
                "plan_presenter": self.plan_presenter,
                "reviewer_agent": self.reviewer_agent,
                "revision_agent": self.revision_agent,
                "modify_analyzer_agent": self.modify_analyzer_agent,
            }.items()
            if value is not None
        }


def build_agent_overrides(settings: Settings) -> AgentOverrides:
    """Build DeepSeek agents only when a key is configured."""
    api_key = (settings.deepseek_api_key or "").strip()
    if not api_key:
        return AgentOverrides(mode="rules")

    flash_model = ChatOpenAI(
        model=settings.deepseek_flash_model,
        api_key=SecretStr(api_key),
        base_url=settings.deepseek_base_url,
        temperature=0.1,
        max_tokens=4096,
        timeout=30,
        max_retries=1,
        extra_body={"thinking": {"type": "disabled"}},
    )
    pro_model = ChatOpenAI(
        model=settings.deepseek_pro_model,
        api_key=SecretStr(api_key),
        base_url=settings.deepseek_base_url,
        temperature=0.1,
        timeout=60,
        max_tokens=12000,
        max_retries=1,
        # Structured output forces a tool choice; DeepSeek thinking mode rejects
        # that combination, so planning uses V4 Pro in non-thinking mode.
        extra_body={"thinking": {"type": "disabled"}},
    )

    return AgentOverrides(
        mode="deepseek",
        intent_agent=_FallbackIntentAgent(
            LangChainIntentAgent(flash_model),
            RuleBasedIntentAgent(),
        ),
        clarification_agent=_FallbackClarificationAgent(
            LangChainClarificationAgent(flash_model),
            RuleBasedClarificationAgent(),
        ),
        memory_candidate_agent=_FallbackMemoryCandidateAgent(
            LangChainMemoryCandidateAgent(flash_model),
            RuleBasedMemoryCandidateAgent(),
        ),
        phase1_research_agent=_FallbackPhase1ResearchAgent(
            LangChainPhase1ResearchAgent(flash_model),
            RuleBasedPhase1ResearchAgent(),
        ),
        phase2_research_agent=_FallbackPhase2ResearchAgent(
            LangChainPhase2ResearchAgent(pro_model),
            RuleBasedPhase2ResearchAgent(),
        ),
        candidate_selector=_FallbackCandidateSelectorAgent(
            LangChainCandidateSelectorAgent(pro_model),
            RuleBasedCandidateSelectorAgent(),
        ),
        query_presenter=_FallbackQueryPresenterAgent(
            LangChainQueryPresenterAgent(flash_model),
            RuleBasedQueryPresenterAgent(),
        ),
        direct_modify_agent=_FallbackDirectModifyAgent(
            LangChainDirectModifyAgent(pro_model),
            RuleBasedDirectModifyAgent(),
        ),
        planner_agent=_FallbackPlannerAgent(
            LangChainPlannerAgent(pro_model),
            RuleBasedPlannerAgent(),
        ),
        plan_presenter=_FallbackPlanPresenterAgent(
            LangChainPlanPresenterAgent(flash_model),
            RuleBasedPlanPresenterAgent(),
        ),
        reviewer_agent=_FallbackReviewerAgent(
            LangChainReviewerAgent(pro_model),
            RuleBasedReviewerAgent(),
        ),
        revision_agent=_FallbackRevisionAgent(
            LangChainRevisionAgent(pro_model),
            RuleBasedRevisionAgent(),
        ),
        modify_analyzer_agent=_FallbackModifyAnalyzerAgent(
            LangChainModifyAnalyzerAgent(flash_model),
            RuleBasedModifyAnalyzerAgent(),
        ),
    )


def _log_fallback(stage: str, error: Exception) -> None:
    logger.warning("DeepSeek %s failed; using rule fallback (%s)", stage, type(error).__name__)


class _FallbackIntentAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def classify(self, query: str, *, context=None):
        try:
            decision = self._primary.classify(query, context=context)
            return self._guard_route(query, decision)
        except Exception as error:
            _log_fallback("intent", error)
            return self._fallback.classify(query, context=context)

    async def aclassify(self, query: str, *, context=None):
        try:
            decision = await self._primary.aclassify(query, context=context)
            return self._guard_route(query, decision)
        except Exception as error:
            _log_fallback("intent", error)
            return await self._fallback.aclassify(query, context=context)

    def _guard_route(self, query: str, decision):
        rule_decision = self._fallback.classify(query)
        uncertain = decision.intent.value in {"unknown", "general_qa"}
        explicit_route = rule_decision.intent.value not in {"unknown", "general_qa"}
        return rule_decision if uncertain and explicit_route else decision


class _FallbackClarificationAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def compose(self, **kwargs):
        try:
            return self._primary.compose(**kwargs)
        except Exception as error:
            _log_fallback("clarification", error)
            return self._fallback.compose(**kwargs)

    async def acompose(self, **kwargs):
        try:
            return await self._primary.acompose(**kwargs)
        except Exception as error:
            _log_fallback("clarification", error)
            return await self._fallback.acompose(**kwargs)


class _FallbackMemoryCandidateAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract(self, query, entities, preferences):
        try:
            return self._primary.extract(query, entities, preferences)
        except Exception as error:
            _log_fallback("memory candidate", error)
            return self._fallback.extract(query, entities, preferences)

    async def aextract(self, query, entities, preferences):
        try:
            return await self._primary.aextract(query, entities, preferences)
        except Exception as error:
            _log_fallback("memory candidate", error)
            return await self._fallback.aextract(query, entities, preferences)


class _FallbackPlannerAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def plan(self, **kwargs):
        try:
            return self._primary.plan(**kwargs)
        except Exception as error:
            _log_fallback("planner", error)
            return self._fallback.plan(**kwargs)

    async def aplan(self, **kwargs):
        try:
            return await self._primary.aplan(**kwargs)
        except Exception as error:
            _log_fallback("planner", error)
            return await self._fallback.aplan(**kwargs)


class _FallbackPhase1ResearchAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def research(self, **kwargs):
        try:
            return self._primary.research(**kwargs)
        except Exception as error:
            _log_fallback("phase 1 research", error)
            return self._fallback.research(**kwargs)

    async def aresearch(self, **kwargs):
        try:
            return await self._primary.aresearch(**kwargs)
        except Exception as error:
            _log_fallback("phase 1 research", error)
            return await self._fallback.aresearch(**kwargs)


class _FallbackPhase2ResearchAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def research(self, **kwargs):
        try:
            return self._primary.research(**kwargs)
        except Exception as error:
            _log_fallback("phase 2 research", error)
            return self._fallback.research(**kwargs)

    async def aresearch(self, **kwargs):
        try:
            return await self._primary.aresearch(**kwargs)
        except Exception as error:
            _log_fallback("phase 2 research", error)
            return await self._fallback.aresearch(**kwargs)


class _FallbackDirectModifyAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def modify(self, **kwargs):
        try:
            return self._primary.modify(**kwargs)
        except Exception as error:
            _log_fallback("direct modifier", error)
            return self._fallback.modify(**kwargs)

    async def amodify(self, **kwargs):
        try:
            return await self._primary.amodify(**kwargs)
        except Exception as error:
            _log_fallback("direct modifier", error)
            return await self._fallback.amodify(**kwargs)


class _FallbackCandidateSelectorAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def select(self, research, entities, preferences):
        try:
            return self._primary.select(research, entities, preferences)
        except Exception as error:
            _log_fallback("candidate selector", error)
            return self._fallback.select(research, entities, preferences)

    async def aselect(self, research, entities, preferences):
        try:
            return await self._primary.aselect(research, entities, preferences)
        except Exception as error:
            _log_fallback("candidate selector", error)
            return await self._fallback.aselect(research, entities, preferences)


class _FallbackQueryPresenterAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def present(
        self,
        query,
        intent,
        entities,
        results,
        conversation_context=None,
    ):
        try:
            return self._primary.present(
                query,
                intent,
                entities,
                results,
                conversation_context,
            )
        except Exception as error:
            _log_fallback("query presenter", error)
            return self._fallback.present(
                query,
                intent,
                entities,
                results,
                conversation_context,
            )

    async def apresent(
        self,
        query,
        intent,
        entities,
        results,
        conversation_context=None,
    ):
        try:
            return await self._primary.apresent(
                query,
                intent,
                entities,
                results,
                conversation_context,
            )
        except Exception as error:
            _log_fallback("query presenter", error)
            return await self._fallback.apresent(
                query,
                intent,
                entities,
                results,
                conversation_context,
            )


class _FallbackRevisionAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def revise(self, *args):
        try:
            return self._primary.revise(*args)
        except Exception as error:
            _log_fallback("revision", error)
            return self._fallback.revise(*args)

    async def arevise(self, *args):
        try:
            return await self._primary.arevise(*args)
        except Exception as error:
            _log_fallback("revision", error)
            return await self._fallback.arevise(*args)


class _FallbackPlanPresenterAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def present(self, **kwargs):
        try:
            return self._primary.present(**kwargs)
        except Exception as error:
            _log_fallback("plan presenter", error)
            return self._fallback.present(**kwargs)

    async def apresent(self, **kwargs):
        try:
            return await self._primary.apresent(**kwargs)
        except Exception as error:
            _log_fallback("plan presenter", error)
            return await self._fallback.apresent(**kwargs)


class _FallbackReviewerAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def review(self, plan, entities, preferences, phase1, hard_validation):
        try:
            return self._primary.review(plan, entities, preferences, phase1, hard_validation)
        except Exception as error:
            _log_fallback("reviewer", error)
            return self._fallback.review(plan, entities, preferences, phase1, hard_validation)

    async def areview(self, plan, entities, preferences, phase1, hard_validation):
        try:
            return await self._primary.areview(
                plan,
                entities,
                preferences,
                phase1,
                hard_validation,
            )
        except Exception as error:
            _log_fallback("reviewer", error)
            return await self._fallback.areview(
                plan,
                entities,
                preferences,
                phase1,
                hard_validation,
            )


class _FallbackModifyAnalyzerAgent:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def analyze(self, query, current_plan, entities):
        try:
            return self._primary.analyze(query, current_plan, entities)
        except Exception as error:
            _log_fallback("modify analyzer", error)
            return self._fallback.analyze(query, current_plan, entities)

    async def aanalyze(self, query, current_plan, entities):
        try:
            return await self._primary.aanalyze(query, current_plan, entities)
        except Exception as error:
            _log_fallback("modify analyzer", error)
            return await self._fallback.aanalyze(query, current_plan, entities)
