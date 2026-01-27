"""
Knowledge Extraction Configuration
知识提取模块配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, AliasChoices
from functools import lru_cache
from typing import Literal


class LLMConfig(BaseSettings):
    """LLM 配置 - 使用七牛云 AI API"""
    # 七牛云 API 配置
    api_key: str = Field(
        default="sk-your-api-key-here",
        description="七牛云 API Key (单个密钥，兼容旧配置)"
    )
    api_keys_str: str = Field(
        default="sk-your-api-key-here",
        description="七牛云 API Keys 字符串 (逗号分隔，支持多个密钥实现并发)",
        validation_alias=AliasChoices("api_keys_str", "api_keys", "LLM_API_KEYS")  # 尝试多个变量名
    )
    base_url: str = Field(
        default="https://api.qnaigc.com/v1",
        description="七牛云 API Base URL"
    )
    
    # 模型选择 (基于七牛云可用模型)
    extraction_model: str = Field(
        default="claude-3.7-sonnet",
        description="用于结构化提取的模型（深度推理，适合实体/事件/时间提取）"
    )
    conversation_model: str = Field(
        default="claude-3.7-sonnet",
        description="用于情感/风格分析的模型（安全可靠，擅长深度分析）"
    )
    fast_model: str = Field(
        default="claude-3.7-sonnet",
        description="用于快速任务的模型（统一使用claude）"
    )
    backup_model: str = Field(
        default="claude-3.7-sonnet",
        description="备选通用模型（统一使用claude）"
    )
    
    # 生成参数
    extraction_temperature: float = Field(default=0.1, description="提取任务温度（低=精确）")
    conversation_temperature: float = Field(default=0.7, description="对话任务温度")
    max_tokens: int = Field(default=16384, description="最大生成 token 数（增加到16k以支持长文本）")
    timeout: int = Field(default=180, description="API请求超时时间（秒）")
    
    @property
    def api_keys(self) -> list[str]:
        """获取解析后的API密钥列表"""
        return [key.strip() for key in self.api_keys_str.split(',') if key.strip()]
    
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=["backend/.env", ".env"],  # 支持多个路径
        env_file_encoding="utf-8",
        extra="ignore"  # 忽略额外的环境变量
    )


class Neo4jConfig(BaseSettings):
    """Neo4j 配置"""
    uri: str = Field(default="bolt://localhost:7687", description="Neo4j 连接 URI")
    user: str = Field(default="neo4j", description="用户名")
    password: str = Field(default="password", description="密码")
    database: str = Field(default="neo4j", description="数据库名称")
    
    # 向量索引配置
    vector_dimension: int = Field(default=1792, description="向量维度（acge_text_embedding=1792）")
    similarity_function: Literal["cosine", "euclidean"] = Field(
        default="cosine", 
        description="向量相似度函数"
    )
    
    class Config:
        env_prefix = "NEO4J_"


class EmbeddingConfig(BaseSettings):
    """嵌入模型配置"""
    # 使用本源量子 acge_text_embedding（实体识别优化，中文MTEB霸榜）
    model_name: str = Field(
        default="aspire/acge_text_embedding",
        description="嵌入模型名称（推荐：aspire/acge_text_embedding 实体匹配最强）"
    )
    dimension: int = Field(default=1792, description="嵌入维度（acge=1792）")
    batch_size: int = Field(default=32, description="批处理大小")
    
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
    
    # 批处理配置（并发控制）
    # 注意：2GB内存建议设为1-3，4GB+可设为5-10
    batch_size: int = Field(default=15, description="并行处理的块数")
    max_retries: int = Field(default=3, description="失败重试次数")
    
    class Config:
        env_prefix = "EXTRACTION_"


class KnowledgeExtractionSettings(BaseSettings):
    """知识提取模块总配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    
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
