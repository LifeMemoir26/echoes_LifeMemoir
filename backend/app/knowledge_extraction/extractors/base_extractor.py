"""
Base Extractor - 提取器抽象基类
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..llm import AsyncOllamaClient
from ..adapters.base_adapter import StandardDocument


@dataclass
class ExtractionResult:
    """提取结果基类"""
    source_document_id: str
    extractor_name: str
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    confidence_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseExtractor(ABC):
    """
    提取器抽象基类
    
    所有提取器必须继承此类并实现 extract 方法
    """
    
    def __init__(
        self,
        llm_client: Optional[AsyncOllamaClient] = None,
        model: Optional[str] = None,
    ):
        self.llm_client = llm_client or AsyncOllamaClient()
        self.model = model
        self.name = self.__class__.__name__
    
    @abstractmethod
    def prepare_llm_request(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> dict:
        """
        准备 LLM 请求参数
        
        用于批量处理场景
        """
        pass

    @abstractmethod
    def parse_llm_response(
        self,
        response: dict,
        document: StandardDocument,
        **kwargs,
    ) -> list[ExtractionResult]:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 返回的结构化数据 (JSON/Dict)
            document: 原始文档
        """
        pass

    async def extract(
        self,
        document: StandardDocument,
        **kwargs,
    ) -> list[ExtractionResult]:
        """
        从文档中提取信息 (默认实现)
        """
        # 1. 准备请求
        request_params = self.prepare_llm_request(document, **kwargs)
        if not request_params:
            return []
            
        # 2. 调用 LLM
        system_prompt = request_params.get("system_prompt")
        user_prompt = request_params.get("user_prompt")
        
        if not user_prompt:
            return []
            
        result = await self.llm_client.generate_structured(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self.model,
        )
        
        # 3. 解析响应
        return self.parse_llm_response(result, document, **kwargs)
    
    async def _call_llm(
        self,
        content: str,
        **kwargs,
    ) -> dict:
        """Deprecated: use generate_structured directly"""
        pass
