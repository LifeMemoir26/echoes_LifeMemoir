"""Cross-layer contracts for application use-cases."""

from .llm import LLMGatewayProtocol
from .migration import MigrationPhaseStatus
from .common import RequestContext, AppError, AppResult
from .errors import InfraAdapterError, InfraErrorCategory, classify_infra_exception

__all__ = [
    "LLMGatewayProtocol",
    "MigrationPhaseStatus",
    "RequestContext",
    "AppError",
    "AppResult",
    "InfraAdapterError",
    "InfraErrorCategory",
    "classify_infra_exception",
]
