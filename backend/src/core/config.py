"""
Knowledge Extraction Configuration
知识提取模块配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, computed_field, AliasChoices
from functools import lru_cache
from typing import Literal


class LLMConfig(BaseSettings):
    """LLM 配置 - OpenAI 兼容 API"""
    # API 配置
    api_keys_str: str = Field(
        ...,  # 必需字段
        description="API Keys (逗号分隔，支持多个密钥实现并发)",
        validation_alias=AliasChoices("api_keys_str", "api_keys", "LLM_API_KEYS")
    )
    base_url: str = Field(
        default="https://xh.v1api.cc/v1",
        description="OpenAI 兼容 API Base URL"
    )

    # 模型选择
    extraction_model: str = Field(
        default="deepseek-v3.2",
        description="知识库结构化提取 + 精炼（事件/人物/去重/年份推理）"
    )
    conversation_model: str = Field(
        default="deepseek-v3.2",
        description="采访实时分析（摘要/补充/情感/待探索事件）"
    )
    creative_model: str = Field(
        default="deepseek-v3.2",
        description="文学写作（回忆录、时间轴叙述）— 产品核心输出"
    )
    utility_model: str = Field(
        default="deepseek-v3.2",
        description="轻量机械任务（JSON修复、事件合并、别名去重）"
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
    """嵌入模型配置 — Gemini Embedding API"""
    gemini_api_keys_str: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEYS", "gemini_api_keys_str"),
        description="Gemini API Keys（逗号分隔，用于轮换）"
    )
    model_name: str = Field(
        default="models/gemini-embedding-001",
        description="嵌入模型名称"
    )
    dimension: int = Field(default=768, description="嵌入维度")
    batch_size: int = Field(default=100, description="向量编码批次大小（Gemini 限制）")
    proxy: str = Field(
        default="",
        validation_alias=AliasChoices("EMBEDDING_PROXY", "embedding_proxy", "GEMINI_PROXY"),
        description="HTTP 代理地址（如 http://127.0.0.1:7890），为空则直连"
    )

    @computed_field  # type: ignore[misc]
    @property
    def api_keys(self) -> list[str]:
        """获取所有可用的 Gemini API key 列表"""
        if self.gemini_api_keys_str:
            keys = [k.strip() for k in self.gemini_api_keys_str.split(",") if k.strip()]
            if keys:
                return keys
        return []

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        extra="ignore",
    )


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
    
    model_config = SettingsConfigDict(
        env_prefix="EXTRACTION_",
        extra="ignore",
    )


class InterviewAssistanceConfig(BaseSettings):
    """采访辅助配置"""
    # 对话队列配置（ASR 会将一段话拆成多条，队列需更大）
    dialogue_queue_size: int = Field(default=20, description="对话队列容量（轮数）")

    # 存储缓冲区配置
    storage_threshold: int = Field(default=800, description="存储缓冲区字符数阈值")
    
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

    # n 轮刷新引擎配置
    n_refresh_interval: int = Field(default=5, description="每 n 轮对话触发辅助刷新")
    summary_queue_size: int = Field(default=5, description="SummaryQueue 固定容量（批次数）")

    model_config = SettingsConfigDict(
        env_prefix="INTERVIEW_",
        extra="ignore",
    )


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
    
    model_config = SettingsConfigDict(
        env_prefix="GENERATION_",
        extra="ignore",
    )


class AsrConfig(BaseSettings):
    """科大讯飞实时语音转写 (RTASR) 配置"""
    appid: str = Field(default="", description="讯飞 APPID")
    api_key: str = Field(default="", description="讯飞 API Key")

    model_config = SettingsConfigDict(
        env_prefix="ASR_",
        extra="ignore",
    )


class OrchestrationConfig(BaseSettings):
    """编排引擎选择配置"""

    engine: Literal["langgraph"] = Field(
        default="langgraph",
        description="当前仅支持 langgraph 编排路径"
    )

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATION_",
        extra="ignore",
    )


class KnowledgeExtractionSettings(BaseSettings):
    """知识提取模块总配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    interview: InterviewAssistanceConfig = Field(default_factory=InterviewAssistanceConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    
    # 调试模式
    debug: bool = Field(default=False, description="调试模式")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )


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
