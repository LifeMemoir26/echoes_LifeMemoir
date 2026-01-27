"""
LLM客户端基类
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMClient(ABC):
    """LLM客户端基类"""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            生成的文本
        """
        pass
