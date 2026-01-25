"""
Extraction Pipeline - 知识提取管道

使用 LangGraph 编排多个提取器，完成完整的知识提取流程
"""
import logging
import asyncio
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from ..adapters.base_adapter import StandardDocument, SourceType
from ..adapters.dialogue_adapter import DialogueAdapter
from ..extractors.entity_extractor import EntityExtractor, EntityExtractionResult
from ..extractors.event_extractor import EventExtractor, EventExtractionResult
from ..extractors.temporal_extractor import TemporalExtractor, TemporalExtractionResult
from ..extractors.emotion_extractor import EmotionExtractor, EmotionExtractionResult
from ..extractors.style_extractor import StyleExtractor, StyleExtractionResult
from ..graph_store.neo4j_client import Neo4jClient
from ..graph_store.graph_writer import GraphWriter
from ..graph_store.schema import init_schema
from ..llm import AsyncOllamaClient
from ..config import get_settings

logger = logging.getLogger(__name__)


# ==================== Pipeline State ====================

class PipelineState(TypedDict):
    """LangGraph 状态定义"""
    # 输入
    user_id: str
    document: Optional[StandardDocument]
    raw_text: Optional[str]
    
    # 提取结果
    entity_result: Optional[EntityExtractionResult]
    event_result: Optional[EventExtractionResult]
    temporal_result: Optional[TemporalExtractionResult]
    emotion_result: Optional[EmotionExtractionResult]
    style_result: Optional[StyleExtractionResult]
    
    # 图谱写入结果
    entity_ids: list[str]
    event_ids: list[str]
    style_id: Optional[str]
    
    # 元数据
    errors: list[str]
    processing_time_ms: int
    

@dataclass
class PipelineResult:
    """管道执行结果"""
    success: bool
    user_id: str
    document_id: Optional[str] = None
    
    # 提取统计
    entities_extracted: int = 0
    events_extracted: int = 0
    temporal_anchors: int = 0
    emotions_detected: int = 0
    style_extracted: bool = False
    
    # 图谱写入
    nodes_created: int = 0
    relationships_created: int = 0
    
    # 元数据
    processing_time_ms: int = 0
    errors: list[str] = field(default_factory=list)
    
    # 详细结果（可选）
    entity_result: Optional[EntityExtractionResult] = None
    event_result: Optional[EventExtractionResult] = None
    temporal_result: Optional[TemporalExtractionResult] = None
    emotion_result: Optional[EmotionExtractionResult] = None
    style_result: Optional[StyleExtractionResult] = None


# ==================== Extraction Pipeline ====================

class ExtractionPipeline:
    """
    知识提取管道
    
    完整流程：
    1. 解析输入 -> StandardDocument
    2. 并行提取实体、事件、情感、风格
    3. 时间推理（基于提取的实体和事件）
    4. 写入图数据库
    """
    
    def __init__(
        self,
        neo4j_client: Optional[Neo4jClient] = None,
        llm_client: Optional[AsyncOllamaClient] = None,
        user_birth_year: Optional[int] = None,
    ):
        self.settings = get_settings()
        
        # 初始化客户端
        self.neo4j_client = neo4j_client or Neo4jClient()
        self.llm_client = llm_client or AsyncOllamaClient()
        
        # 初始化提取器
        self.entity_extractor = EntityExtractor(self.llm_client)
        self.event_extractor = EventExtractor(self.llm_client)
        self.temporal_extractor = TemporalExtractor(
            self.llm_client, 
            user_birth_year=user_birth_year
        )
        self.emotion_extractor = EmotionExtractor(self.llm_client)
        self.style_extractor = StyleExtractor(self.llm_client)
        
        # 初始化适配器
        self.dialogue_adapter = DialogueAdapter()
        
        # 初始化图谱写入器
        self.graph_writer: Optional[GraphWriter] = None
        
        # 构建 LangGraph
        self._graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 工作流"""
        workflow = StateGraph(PipelineState)
        
        # 添加节点
        workflow.add_node("parse_input", self._parse_input)
        workflow.add_node("extract_entities", self._extract_entities)
        workflow.add_node("extract_events", self._extract_events)
        workflow.add_node("extract_temporal", self._extract_temporal)
        workflow.add_node("extract_emotion", self._extract_emotion)
        workflow.add_node("extract_style", self._extract_style)
        workflow.add_node("write_to_graph", self._write_to_graph)
        
        # 定义边
        workflow.set_entry_point("parse_input")
        
        # 解析后并行提取
        workflow.add_edge("parse_input", "extract_entities")
        workflow.add_edge("parse_input", "extract_events")
        workflow.add_edge("parse_input", "extract_emotion")
        workflow.add_edge("parse_input", "extract_style")
        
        # 实体和事件提取完成后进行时间推理
        workflow.add_edge("extract_entities", "extract_temporal")
        workflow.add_edge("extract_events", "extract_temporal")
        
        # 所有提取完成后写入图谱
        workflow.add_edge("extract_temporal", "write_to_graph")
        workflow.add_edge("extract_emotion", "write_to_graph")
        workflow.add_edge("extract_style", "write_to_graph")
        
        workflow.add_edge("write_to_graph", END)
        
        return workflow.compile()
    
    async def initialize(self) -> None:
        """初始化（连接数据库、创建 Schema）"""
        await self.neo4j_client.connect()
        self.graph_writer = GraphWriter(self.neo4j_client)
        
        # 初始化 Schema
        await init_schema(
            self.neo4j_client, 
            self.settings.embedding.dimension
        )
        
        logger.info("ExtractionPipeline initialized")
    
    async def close(self) -> None:
        """关闭连接"""
        await self.neo4j_client.close()
        logger.info("ExtractionPipeline closed")
    
    # ==================== Pipeline 节点 ====================
    
    async def _parse_input(self, state: PipelineState) -> PipelineState:
        """解析输入"""
        try:
            if state.get("document"):
                # 已有文档，跳过
                return state
            
            raw_text = state.get("raw_text", "")
            if not raw_text:
                state["errors"].append("No input text provided")
                return state
            
            # 使用对话适配器解析
            documents = self.dialogue_adapter.process(
                raw_text,
                user_id=state["user_id"],
            )
            
            if documents:
                state["document"] = documents[0]
            else:
                state["errors"].append("Failed to parse input text")
            
            return state
            
        except Exception as e:
            logger.error(f"Parse input error: {e}")
            state["errors"].append(f"Parse error: {str(e)}")
            return state
    
    async def _extract_entities(self, state: PipelineState) -> PipelineState:
        """提取实体"""
        try:
            document = state.get("document")
            if not document:
                return state
            
            results = await self.entity_extractor.extract(document)
            if results:
                state["entity_result"] = results[0]
                logger.info(f"Extracted {len(results[0].entities)} entities")
            
            return state
            
        except Exception as e:
            logger.error(f"Entity extraction error: {e}")
            state["errors"].append(f"Entity extraction error: {str(e)}")
            return state
    
    async def _extract_events(self, state: PipelineState) -> PipelineState:
        """提取事件"""
        try:
            document = state.get("document")
            if not document:
                return state
            
            results = await self.event_extractor.extract(document)
            if results:
                state["event_result"] = results[0]
                logger.info(f"Extracted {len(results[0].events)} events")
            
            return state
            
        except Exception as e:
            logger.error(f"Event extraction error: {e}")
            state["errors"].append(f"Event extraction error: {str(e)}")
            return state
    
    async def _extract_temporal(self, state: PipelineState) -> PipelineState:
        """时间推理"""
        try:
            document = state.get("document")
            if not document:
                return state
            
            results = await self.temporal_extractor.extract(document)
            if results:
                state["temporal_result"] = results[0]
                logger.info(f"Extracted {len(results[0].temporal_anchors)} temporal anchors")
            
            return state
            
        except Exception as e:
            logger.error(f"Temporal extraction error: {e}")
            state["errors"].append(f"Temporal extraction error: {str(e)}")
            return state
    
    async def _extract_emotion(self, state: PipelineState) -> PipelineState:
        """情感分析"""
        try:
            document = state.get("document")
            if not document:
                return state
            
            results = await self.emotion_extractor.extract(document)
            if results:
                state["emotion_result"] = results[0]
                logger.info(f"Extracted {len(results[0].segments)} emotion segments")
            
            return state
            
        except Exception as e:
            logger.error(f"Emotion extraction error: {e}")
            state["errors"].append(f"Emotion extraction error: {str(e)}")
            return state
    
    async def _extract_style(self, state: PipelineState) -> PipelineState:
        """风格提取"""
        try:
            document = state.get("document")
            if not document:
                return state
            
            results = await self.style_extractor.extract(document)
            if results:
                state["style_result"] = results[0]
                logger.info("Extracted speaking style")
            
            return state
            
        except Exception as e:
            logger.error(f"Style extraction error: {e}")
            state["errors"].append(f"Style extraction error: {str(e)}")
            return state
    
    async def _write_to_graph(self, state: PipelineState) -> PipelineState:
        """写入图数据库"""
        try:
            if not self.graph_writer:
                state["errors"].append("Graph writer not initialized")
                return state
            
            user_id = state["user_id"]
            document = state.get("document")
            
            # 创建/获取用户
            birth_year = None
            if state.get("temporal_result"):
                birth_year = state["temporal_result"].user_birth_year
            
            await self.graph_writer.create_or_get_user(
                user_id=user_id,
                name=document.user_name if document else None,
                birth_year=birth_year,
            )
            
            # 写入对话来源
            if document:
                await self.graph_writer.write_dialogue_source(
                    document_id=document.id,
                    source_type=document.source_type.value,
                    raw_content=document.raw_content,
                    session_id=document.session_id,
                )
            
            # 写入实体
            if state.get("entity_result"):
                entity_ids = await self.graph_writer.write_entities(
                    user_id=user_id,
                    extraction_result=state["entity_result"],
                )
                state["entity_ids"] = entity_ids
            
            # 写入事件
            if state.get("event_result"):
                event_ids = await self.graph_writer.write_events(
                    user_id=user_id,
                    extraction_result=state["event_result"],
                    temporal_result=state.get("temporal_result"),
                    source_document_id=document.id if document else None,
                )
                state["event_ids"] = event_ids
            
            # 写入情感
            if state.get("emotion_result") and state.get("event_ids"):
                await self.graph_writer.write_emotions(
                    event_ids=state["event_ids"],
                    extraction_result=state["emotion_result"],
                )
            
            # 写入风格
            if state.get("style_result"):
                style_id = await self.graph_writer.write_speaking_style(
                    user_id=user_id,
                    extraction_result=state["style_result"],
                )
                state["style_id"] = style_id
            
            logger.info("Successfully wrote extraction results to graph")
            return state
            
        except Exception as e:
            logger.error(f"Graph write error: {e}")
            state["errors"].append(f"Graph write error: {str(e)}")
            return state
    
    # ==================== 公共接口 ====================
    
    async def process(
        self,
        text: str,
        user_id: str,
        user_birth_year: Optional[int] = None,
    ) -> PipelineResult:
        """
        处理对话文本
        
        Args:
            text: 对话文本（interviewer:/user: 格式）
            user_id: 用户 ID
            user_birth_year: 用户出生年份（可选）
            
        Returns:
            PipelineResult 处理结果
        """
        start_time = datetime.utcnow()
        
        # 更新时间推理器的出生年份
        if user_birth_year:
            self.temporal_extractor.user_birth_year = user_birth_year
        
        # 初始状态
        initial_state: PipelineState = {
            "user_id": user_id,
            "document": None,
            "raw_text": text,
            "entity_result": None,
            "event_result": None,
            "temporal_result": None,
            "emotion_result": None,
            "style_result": None,
            "entity_ids": [],
            "event_ids": [],
            "style_id": None,
            "errors": [],
            "processing_time_ms": 0,
        }
        
        # 执行管道（由于 LangGraph 的并行性可能有问题，这里使用顺序执行）
        state = await self._execute_sequential(initial_state)
        
        # 计算处理时间
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # 构建结果
        return PipelineResult(
            success=len(state["errors"]) == 0,
            user_id=user_id,
            document_id=state["document"].id if state.get("document") else None,
            entities_extracted=len(state["entity_result"].entities) if state.get("entity_result") else 0,
            events_extracted=len(state["event_result"].events) if state.get("event_result") else 0,
            temporal_anchors=len(state["temporal_result"].temporal_anchors) if state.get("temporal_result") else 0,
            emotions_detected=len(state["emotion_result"].segments) if state.get("emotion_result") else 0,
            style_extracted=state.get("style_result") is not None,
            nodes_created=len(state["entity_ids"]) + len(state["event_ids"]) + (1 if state["style_id"] else 0),
            relationships_created=0,  # TODO: 统计关系数
            processing_time_ms=int(processing_time),
            errors=state["errors"],
            entity_result=state.get("entity_result"),
            event_result=state.get("event_result"),
            temporal_result=state.get("temporal_result"),
            emotion_result=state.get("emotion_result"),
            style_result=state.get("style_result"),
        )
    
    async def _execute_sequential(self, state: PipelineState) -> PipelineState:
        """顺序执行管道（更稳定）"""
        # 1. 解析输入
        state = await self._parse_input(state)
        if not state.get("document"):
            return state
        
        # 2. 并行提取
        entity_task = self._extract_entities(state.copy())
        event_task = self._extract_events(state.copy())
        emotion_task = self._extract_emotion(state.copy())
        style_task = self._extract_style(state.copy())
        
        results = await asyncio.gather(
            entity_task, event_task, emotion_task, style_task,
            return_exceptions=True
        )
        
        # 合并结果
        for result in results:
            if isinstance(result, Exception):
                state["errors"].append(str(result))
            elif isinstance(result, dict):
                for key in ["entity_result", "event_result", "emotion_result", "style_result"]:
                    if result.get(key):
                        state[key] = result[key]
                state["errors"].extend(result.get("errors", []))
        
        # 3. 时间推理
        state = await self._extract_temporal(state)
        
        # 4. 写入图谱
        state = await self._write_to_graph(state)
        
        return state
    
    async def process_batch(
        self,
        texts: list[str],
        user_id: str,
        user_birth_year: Optional[int] = None,
    ) -> list[PipelineResult]:
        """批量处理多个对话文本"""
        results = []
        for text in texts:
            result = await self.process(text, user_id, user_birth_year)
            results.append(result)
        return results
