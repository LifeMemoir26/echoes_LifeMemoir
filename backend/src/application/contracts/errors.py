"""Typed infra error categories shared at the application boundary."""

from __future__ import annotations

from enum import StrEnum


class InfraErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PERSISTENCE = "persistence"
    NETWORK = "network"
    UNKNOWN = "unknown"


class InfraAdapterError(Exception):
    """Typed adapter error passed from infra into application workflows."""

    def __init__(
        self,
        *,
        category: InfraErrorCategory,
        message: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def classify_infra_exception(exc: Exception) -> InfraAdapterError:
    """Normalize arbitrary runtime exceptions to typed infra categories."""
    if isinstance(exc, InfraAdapterError):
        return exc

    text = str(exc).lower()

    if "429" in text or "rate limit" in text:
        return InfraAdapterError(
            category=InfraErrorCategory.RATE_LIMIT,
            message=str(exc) or "Rate limit",
            retryable=True,
        )
    if "timeout" in text or "timed out" in text:
        return InfraAdapterError(
            category=InfraErrorCategory.TIMEOUT,
            message=str(exc) or "Timeout",
            retryable=True,
        )
    if any(token in text for token in ("connect", "connection", "network", "dns", "eai_")):
        return InfraAdapterError(
            category=InfraErrorCategory.NETWORK,
            message=str(exc) or "Network failure",
            retryable=True,
        )
    if any(token in text for token in ("sqlite", "database", "persist", "chroma", "disk", "ioerror")):
        return InfraAdapterError(
            category=InfraErrorCategory.PERSISTENCE,
            message=str(exc) or "Persistence failure",
            retryable=False,
        )
    return InfraAdapterError(
        category=InfraErrorCategory.UNKNOWN,
        message=str(exc) or exc.__class__.__name__,
        retryable=False,
    )
