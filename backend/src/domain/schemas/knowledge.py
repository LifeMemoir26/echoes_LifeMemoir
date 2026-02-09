"""
知识图谱相关的领域模型
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class LifeEvent(BaseModel):
    """人生事件"""
    event_type: str = Field(description="事件类型")
    description: str = Field(description="事件描述")
    start_time: Optional[str] = Field(default=None, description="开始时间")
    end_time: Optional[str] = Field(default=None, description="结束时间")
    location: Optional[str] = Field(default=None, description="地点")
    participants: List[str] = Field(default_factory=list, description="参与者")
    impact: Optional[str] = Field(default=None, description="影响")
    confidence: float = Field(default=1.0, description="置信度")


class CharacterProfile(BaseModel):
    """人物画像"""
    name: str = Field(description="人物姓名")
    aliases: List[str] = Field(default_factory=list, description="别名")
    description: Optional[str] = Field(default=None, description="描述")
    relationships: Dict[str, str] = Field(default_factory=dict, description="关系")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="属性")


class KnowledgeExtractionRequest(BaseModel):
    """知识提取请求"""
    username: str = Field(description="用户名")
    text: str = Field(description="待提取文本")


class KnowledgeExtractionResponse(BaseModel):
    """知识提取响应"""
    success: bool = Field(description="是否成功")
    events_count: int = Field(default=0, description="提取的事件数")
    characters_count: int = Field(default=0, description="提取的人物数")
    message: Optional[str] = Field(default=None, description="提示信息")
