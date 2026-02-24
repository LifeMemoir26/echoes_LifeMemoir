"""Cross-layer contracts for application use-cases."""

from .llm import LLMGatewayProtocol
from .common import AppError
from .errors import InfraAdapterError, InfraErrorCategory, classify_infra_exception

__all__ = [
    "LLMGatewayProtocol",
    "AppError",
    "InfraAdapterError",
    "InfraErrorCategory",
    "classify_infra_exception",
]
