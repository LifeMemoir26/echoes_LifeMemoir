"""LLM 客户端模块"""
from .qiniu_client import QiniuAIClient, AsyncQiniuAIClient, LLMResponse

# 兼容旧接口名称
OllamaClient = QiniuAIClient
AsyncOllamaClient = AsyncQiniuAIClient

__all__ = [
    "QiniuAIClient",
    "AsyncQiniuAIClient",
    "OllamaClient",
    "AsyncOllamaClient",
    "LLMResponse",
]
