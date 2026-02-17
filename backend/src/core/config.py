"""
Knowledge Extraction Configuration
知识提取模块配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, computed_field, AliasChoices
from functools import lru_cache
from typing import Literal


class LLMConfig(BaseSettings):
    """LLM 配置 - 使用七牛云 AI API"""
    # 七牛云 API 配置
    api_keys_str: str = Field(
        ...,  # 必需字段
        description="七牛云 API Keys (逗号分隔，支持多个密钥实现并发)",
        validation_alias=AliasChoices("api_keys_str", "api_keys", "LLM_API_KEYS")
    )
    base_url: str = Field(
        default="https://api.qnaigc.com/v1",
        description="七牛云 API Base URL"
    )
    
    # 模型选择 (基于七牛云可用模型)
    extraction_model: str = Field(
        default="deepseek-v3",
        description="用于结构化提取的模型（深度推理，适合实体/事件/时间提取）"
    )
    conversation_model: str = Field(
        default="deepseek-v3",
        description="用于情感/风格分析的模型（安全可靠，擅长深度分析）"
    )
    fast_model: str = Field(
        default="deepseek-v3",
        description="用于快速任务的模型（统一使用deepseek）"
    )
    backup_model: str = Field(
        default="deepseek-v3",
        description="备选通用模型（统一使用deepseek）"
    )
    
    # 生成参数
    extraction_temperature: float = Field(default=0.1, description="提取任务温度（低=精确）")
    conversation_temperature: float = Field(default=0.7, description="对话任务温度")
    max_tokens: int = Field(default=16384, description="最大生成 token 数（增加到16k以支持长文本）")
    timeout: int = Field(default=180, description="API请求超时时间（秒）")
    
    # 并发控制配置（仅从配置文件读取，不可在代码中覆盖）
    concurrency_multiplier: float = Field(
        default=1.5, 
        description="并发倍率（推荐1.0-2.0）"
    )
    
    @computed_field  # type: ignore[misc]
    @property
    def api_keys(self) -> list[str]:
        """获取解析后的API密钥列表（自动缓存）"""
        keys = [key.strip() for key in self.api_keys_str.split(',') if key.strip()]
        if not keys:
            raise ValueError("至少需要配置一个API密钥")
        return keys
    
    @computed_field  # type: ignore[misc]
    @property
    def concurrency_level(self) -> int:
        """自动计算的并发级别（API密钥数 × 倍率）"""
        return max(1, int(len(self.api_keys) * self.concurrency_multiplier))
    
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=["backend/.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore"
    )


class EmbeddingConfig(BaseSettings):
    """嵌入模型配置"""
    # 使用本源量子 acge_text_embedding（实体识别优化，中文MTEB霸榜）
    model_name: str = Field(
        default="aspire/acge_text_embedding",
        description="嵌入模型名称"
    )
    dimension: int = Field(default=1792, description="嵌入维度")
    batch_size: int = Field(default=32, description="向量编码批次大小")
    
    class Config:
        env_prefix = "EMBEDDING_"


class ExtractionConfig(BaseSettings):
    """提取流程配置"""
    # 分块配置
    chunk_size: int = Field(default=1000, description="文本分块大小（字符）")
    chunk_overlap: int = Field(default=200, description="分块重叠大小")
    
    # 提取配置
    max_entities_per_chunk: int = Field(default=20, description="每块最大实体数")
    max_events_per_chunk: int = Field(default=10, description="每块最大事件数")
    confidence_threshold: float = Field(default=0.6, description="置信度阈值")
    
    max_retries: int = Field(default=3, description="失败重试次数")
    
    class Config:
        env_prefix = "EXTRACTION_"


class InterviewAssistanceConfig(BaseSettings):
    """采访辅助配置"""
    # 对话队列配置
    dialogue_queue_size: int = Field(default=5, description="对话队列容量（轮数）")
    
    # 存储缓冲区配置
    storage_threshold: int = Field(default=400, description="存储缓冲区字符数阈值")
    
    # 总结提取配置
    summary_count: int = Field(default=16, description="每次提取的总结条数")
    
    # 向量相似度阈值
    similarity_threshold: float = Field(default=0.5, description="与临时总结的向量库向量匹配相似度保留阈值")
    
    # 背景信息生成配置
    max_context_summaries: int = Field(default=50, description="用于生成背景信息的最大历史总结数")
    
    # 待探索事件初始化配置
    event_extraction_similarity_threshold: float = Field(default=0.3, description="初始化从数据库提取低相似度人生事件时的相似度阈值")
    pending_event_from_db: int = Field(default=16, description="从数据库事件中提取的待探索事件数量")
    pending_event: int = Field(default=32, description="从chunks中AI分析提取的待探索事件数量")
    
    class Config:
        env_prefix = "INTERVIEW_"


class GenerationConfig(BaseSettings):
    """生成配置 - 时间轴和回忆录生成"""
    # 时间轴生成配置
    timeline_language_sample_count: int = Field(
        default=10, 
        description="时间轴生成时的语言样本数量"
    )
    
    # 回忆录生成配置
    memoir_language_sample_count: int = Field(
        default=20, 
        description="回忆录生成时的语言样本数量"
    )
    
    class Config:
        env_prefix = "GENERATION_"


class OrchestrationConfig(BaseSettings):
    """编排引擎选择配置"""

    engine: Literal["langgraph"] = Field(
        default="langgraph",
        description="当前仅支持 langgraph 编排路径"
    )

    class Config:
        env_prefix = "ORCHESTRATION_"


class KnowledgeExtractionSettings(BaseSettings):
    """知识提取模块总配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    interview: InterviewAssistanceConfig = Field(default_factory=InterviewAssistanceConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    
    # 调试模式
    debug: bool = Field(default=False, description="调试模式")
    
    model_config = {
        "env_file": ".env",
        "env_nested_delimiter": "__",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> KnowledgeExtractionSettings:
    """获取配置单例"""
    from pathlib import Path
    from dotenv import load_dotenv
    
    # 查找并加载 .env 文件
    current_dir = Path(__file__).parent
    env_paths = [
        current_dir / ".env",
        current_dir.parent / ".env",
        current_dir.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path, override=True)
            break
    
    return KnowledgeExtractionSettings()
