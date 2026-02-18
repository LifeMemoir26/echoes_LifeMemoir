"""Workflow error mapping utilities."""

from __future__ import annotations

from typing import Any

from ...contracts.common import AppError
from ...contracts.errors import InfraAdapterError, InfraErrorCategory


_RETRYABLE_KEYWORDS = (
    "timeout",
    "temporarily",
    "network",
    "connection",
    "rate limit",
    "429",
    "503",
    "502",
)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, InfraAdapterError):
        return exc.retryable
    text = str(exc).lower()
    return any(k in text for k in _RETRYABLE_KEYWORDS)


def _infra_error_code(exc: InfraAdapterError) -> str:
    if exc.category == InfraErrorCategory.TIMEOUT:
        return "INFRA_TIMEOUT"
    if exc.category == InfraErrorCategory.RATE_LIMIT:
        return "INFRA_RATE_LIMIT"
    if exc.category == InfraErrorCategory.NETWORK:
        return "INFRA_NETWORK"
    if exc.category == InfraErrorCategory.PERSISTENCE:
        return "INFRA_PERSISTENCE"
    return "INFRA_UNKNOWN"


def map_exception_to_app_error(
    exc: Exception,
    *,
    trace_id: str,
    failed_node: str | None = None,
    error_code: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AppError:
    """Map runtime exception to stable application error."""
    retryable = _is_retryable(exc)
    if error_code:
        code = error_code
    elif isinstance(exc, InfraAdapterError):
        code = _infra_error_code(exc)
    else:
        code = "WORKFLOW_RETRYABLE_ERROR" if retryable else "WORKFLOW_FATAL_ERROR"
    message = str(exc) or exc.__class__.__name__

    if extra:
        message = f"{message} | context={extra}"

    return AppError(
        error_code=code,
        error_message=message,
        retryable=retryable,
        failed_node=failed_node,
        trace_id=trace_id,
    )
