"""
知识图谱相关的领域模型

LifeEvent 和 CharacterProfile 是数据链路的 single source of truth，
字段与 SQLite 表结构 + LLM 提取器输出完全对齐。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LifeEvent(BaseModel):
    """人生事件 — 对齐 life_events 表 + LLM 提取输出。"""

    id: int | None = None
    year: str = Field(description="精准年份，跨年段用 9999")
    time_detail: str | None = Field(default=None, description="季节/月日/推断信息")
    event_summary: str = Field(description="简要事件描述")
    event_details: str | None = Field(default=None, description="详细描述")
    is_merged: bool = Field(default=False, description="是否经过合并精炼")
    life_stage: str = Field(default="未知", description="人生阶段")
    event_category: list[str] = Field(default_factory=list, description="事件分类标签")
    confidence: str = Field(default="high", description="置信度 high/medium/low")
    source_material_id: str | None = Field(default=None, description="来源素材 ID")
    created_at: str | None = Field(default=None, description="数据库时间戳")


class CharacterProfile(BaseModel):
    """人物画像 — 对齐 character_profiles 表。"""

    id: int | None = None
    personality: str = Field(default="", description="性格特征")
    worldview: str = Field(default="", description="世界观")
    source_material_id: str | None = Field(default=None, description="来源素材 ID")
    created_at: str | None = Field(default=None, description="数据库时间戳")
