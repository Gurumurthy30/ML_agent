"""
utils.exceptions — Typed domain exceptions for the ML Pipeline.
Each carries structured context (node, iteration, tier, raw payload)
so that errors are never silently swallowed and can be logged/surfaced.
"""
from typing import Any, Optional


class PipelineError(Exception):
    """Base exception for all pipeline errors with structured context."""

    def __init__(
        self,
        message: str,
        node: Optional[str] = None,
        iteration: Optional[int] = None,
        tier: Optional[int] = None,
        raw_payload: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.node = node
        self.iteration = iteration
        self.tier = tier
        self.raw_payload = raw_payload

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "node": self.node,
            "iteration": self.iteration,
            "tier": self.tier,
            "raw_payload": str(self.raw_payload)[:500] if self.raw_payload is not None else None,
        }


class LLMParseError(PipelineError):
    """Raised when an LLM response cannot be parsed into the expected schema or valid JSON."""
    pass


class CodeExecutionError(PipelineError):
    """Raised when generated code execution fails in subprocess or MCP server."""

    def __init__(
        self,
        message: str,
        node: Optional[str] = None,
        iteration: Optional[int] = None,
        tier: Optional[int] = None,
        raw_payload: Any = None,
        exit_code: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, node=node, iteration=iteration, tier=tier, raw_payload=raw_payload)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "exit_code": self.exit_code,
            "stdout": self.stdout[:500] if self.stdout else None,
            "stderr": self.stderr[:500] if self.stderr else None,
        })
        return d


class MetricUnavailableError(PipelineError):
    """Raised when code or an evaluation step finishes without producing a usable numeric metric."""
    pass


class StateError(PipelineError):
    """Raised when required state keys are missing, None, or violated."""

    def __init__(
        self,
        key: str,
        node: str,
        message: Optional[str] = None,
        iteration: Optional[int] = None,
        tier: Optional[int] = None,
    ):
        msg = message or f"Node '{node}' requires non-None state key '{key}', but it was missing or None."
        super().__init__(msg, node=node, iteration=iteration, tier=tier)
        self.key = key
