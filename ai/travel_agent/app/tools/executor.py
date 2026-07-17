from __future__ import annotations

from app.domain.models import ToolError, ToolName, ToolRecoveryAction
from app.tools.contracts import ToolContext, ToolExecutionOutcome
from app.tools.error_handler import ToolErrorHandler
from app.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        error_handler: ToolErrorHandler | None = None,
    ) -> None:
        self._registry = registry
        self._error_handler = error_handler or ToolErrorHandler()

    def execute(self, tool_name: ToolName, context: ToolContext) -> ToolExecutionOutcome:
        errors: list[ToolError] = []
        for attempt in (1, 2):
            result = self._registry.invoke(tool_name, context)
            if result.success:
                return ToolExecutionOutcome(
                    tool_name=tool_name,
                    result=result,
                    errors=errors,
                    attempts=attempt,
                )

            errors.append(
                ToolError(
                    tool_name=tool_name,
                    error_code=result.error_code or "UNKNOWN_TOOL_ERROR",
                    message=str(result.data.get("message", "工具调用失败")),
                    retryable=result.retryable,
                    attempt=attempt,
                )
            )
            action = self._error_handler.decide(tool_name, result, attempt)
            if action is ToolRecoveryAction.RETRY:
                continue
            if action is ToolRecoveryAction.FALLBACK:
                return ToolExecutionOutcome(
                    tool_name=tool_name,
                    result=self._error_handler.fallback(tool_name, context),
                    errors=errors,
                    attempts=attempt,
                )
            return ToolExecutionOutcome(
                tool_name=tool_name,
                result=result,
                errors=errors,
                attempts=attempt,
                abort_requested=action is ToolRecoveryAction.ABORT,
            )
        raise RuntimeError("unreachable tool retry state")
