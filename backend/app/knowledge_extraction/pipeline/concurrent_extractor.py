"""
高性能并发提取器

特性：
- 自动文本预处理和拆分
- 并发执行多个提取器
- 智能结果合并
"""
import asyncio
import time
import logging
import re
from typing import Optional, List
from dataclasses import dataclass, field

from ..adapters import DialogueAdapter, StandardDocument
from ..extractors import (
    EntityExtractor, EventExtractor, TemporalExtractor,
    EmotionExtractor, StyleExtractor
)
from ..llm import AsyncQiniuAIClient
from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractionMetrics:
    """提取性能指标"""
    total_time: float = 0.0
    parse_time: float = 0.0
    entity_time: float = 0.0
    event_time: float = 0.0
    temporal_time: float = 0.0
    emotion_time: float = 0.0
    style_time: float = 0.0
    
    entity_count: int = 0
    event_count: int = 0
    anchor_count: int = 0


@dataclass
class FastExtractionResult:
    """快速提取结果"""
    entities: list = field(default_factory=list)
    events: list = field(default_factory=list)
    temporal_anchors: list = field(default_factory=list)
    emotions: list = field(default_factory=list)
    style: dict = field(default_factory=dict)
    metrics: ExtractionMetrics = field(default_factory=ExtractionMetrics)


class ConcurrentExtractor:
    """
    高性能并发提取器
    
    特性：
    - 自动文本拆分（超过阈值自动分片）
    - 5个提取器完全并发执行
    - 智能结果合并
    - 共享LLM客户端连接池
    """
    
    # 文本拆分配置
    MAX_CHUNK_SIZE = 8000  # 单个chunk最大字符数
    OVERLAP_SIZE = 500     # chunk之间的重叠字符数
    
    def __init__(
        self,
        model: Optional[str] = None,
        fast_model: Optional[str] = None,
        max_concurrent: int = 5,
    ):
        settings = get_settings()
        self.model = model or settings.llm.extraction_model
        self.fast_model = fast_model or settings.llm.fast_model
        self.max_concurrent = max_concurrent
        
        # 共享 LLM 客户端
        self._client = AsyncQiniuAIClient()
        
        # 初始化所有提取器
        self._entity_ext = EntityExtractor(self._client, model=self.model)
        self._event_ext = EventExtractor(self._client, model=self.model)
        self._temporal_ext = TemporalExtractor(self._client, model=self.model)
        self._emotion_ext = EmotionExtractor(self._client, model=self.fast_model)
        self._style_ext = StyleExtractor(self._client, model=self.fast_model)
        
        self._adapter = DialogueAdapter()
    
    def _split_text(self, text: str) -> List[str]:
        """
        智能拆分长文本
        
        策略：
        1. 按段落拆分（保持语义完整）
        2. 控制每个chunk大小在阈值内
        3. chunk之间有重叠以保持上下文连续性
        """
        if len(text) <= self.MAX_CHUNK_SIZE:
            return [text]
        
        # 按段落分割
        paragraphs = re.split(r'\n\n+', text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_size = len(para)
            
            # 如果单个段落就超过限制，强制按句子拆分
            if para_size > self.MAX_CHUNK_SIZE:
                sentences = re.split(r'([。！？\n])', para)
                for i in range(0, len(sentences), 2):
                    sent = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
                    if current_size + len(sent) > self.MAX_CHUNK_SIZE and current_chunk:
                        chunks.append('\n\n'.join(current_chunk))
                        # 保留最后一部分作为重叠
                        overlap_text = current_chunk[-1] if current_chunk else ''
                        current_chunk = [overlap_text, sent] if overlap_text else [sent]
                        current_size = len(overlap_text) + len(sent)
                    else:
                        current_chunk.append(sent)
                        current_size += len(sent)
            # 正常段落
            elif current_size + para_size > self.MAX_CHUNK_SIZE and current_chunk:
                # 当前chunk已满，保存并创建新chunk
                chunks.append('\n\n'.join(current_chunk))
                # 保留最后一段作为重叠
                overlap_text = current_chunk[-1] if len(current_chunk[-1]) < self.OVERLAP_SIZE else ''
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_size = len(overlap_text) + para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        # 添加最后一个chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        logger.info(f"文本拆分: {len(text)}字符 -> {len(chunks)}个chunk")
        return chunks
    
    async def extract(
        self,
        text: str,
        user_id: str,
        user_birth_year: Optional[int] = None,
        skip_emotion: bool = False,
        skip_style: bool = False,
    ) -> FastExtractionResult:
        """
        并发执行所有提取任务
        
        Args:
            text: 输入文本
            user_id: 用户ID
            user_birth_year: 用户出生年份（用于时间推理）
            skip_emotion: 跳过情感分析
            skip_style: 跳过风格分析
        
        Returns:
            提取结果
        """
        start_time = time.perf_counter()
        metrics = ExtractionMetrics()
        
        # 1. 文本预处理和拆分
        chunks = self._split_text(text)
        logger.info(f"处理 {len(chunks)} 个文本片段")
        
        # 2. 对每个chunk执行提取
        all_results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"处理片段 {i+1}/{len(chunks)} ({len(chunk)} 字符)")
            result = await self._extract_single_chunk(
                chunk, user_id, user_birth_year, skip_emotion, skip_style, metrics
            )
            all_results.append(result)
        
        # 3. 合并所有结果
        final_result = self._merge_results(all_results, metrics)
        
        metrics.total_time = time.perf_counter() - start_time
        final_result.metrics = metrics
        
        logger.info(
            f"提取完成: {metrics.entity_count} 实体, "
            f"{metrics.event_count} 事件, "
            f"{metrics.anchor_count} 时间锚点 "
            f"(耗时 {metrics.total_time:.2f}s)"
        )
        
        return final_result
    
    async def _extract_single_chunk(
        self,
        text: str,
        user_id: str,
        user_birth_year: Optional[int],
        skip_emotion: bool,
        skip_style: bool,
        metrics: ExtractionMetrics,
    ) -> FastExtractionResult:
        """处理单个文本片段"""
        # 解析对话
        parse_start = time.perf_counter()
        docs = self._adapter.process(text, user_id=user_id)
        if not docs:
            return FastExtractionResult(metrics=metrics)
        doc = docs[0]
        metrics.parse_time += time.perf_counter() - parse_start
        
        # 并发执行所有提取任务
        tasks = {}
        
        # 核心任务
        tasks['entity'] = self._timed_extract(
            self._entity_ext.extract, doc, 'entity', metrics
        )
        tasks['event'] = self._timed_extract(
            self._event_ext.extract, doc, 'event', metrics
        )
        tasks['temporal'] = self._timed_extract(
            self._temporal_ext.extract, doc, 'temporal', metrics,
            user_birth_year=user_birth_year
        )
        
        # 可选任务
        if not skip_emotion:
            tasks['emotion'] = self._timed_extract(
                self._emotion_ext.extract, doc, 'emotion', metrics
            )
        if not skip_style:
            tasks['style'] = self._timed_extract(
                self._style_ext.extract, doc, 'style', metrics
            )
        
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            logger.error("提取任务超时")
            results = [TimeoutError("Pipeline timeout")] * len(tasks)
        
        # 收集结果
        result = FastExtractionResult(metrics=metrics)
        task_names = list(tasks.keys())
        
        for i, name in enumerate(task_names):
            res = results[i]
            if isinstance(res, Exception):
                logger.error(f"{name} extraction failed: {res}")
                continue
            
            self._apply_result(result, name, res, metrics)
        
        return result
    
    def _merge_results(self, results: List[FastExtractionResult], metrics: ExtractionMetrics) -> FastExtractionResult:
        """
        合并多个chunk的提取结果
        
        策略：
        1. 实体/事件：简单合并，去重
        2. 时间锚点：按时间排序
        3. 情感/风格：取最后一个（或合并）
        """
        if not results:
            return FastExtractionResult(metrics=metrics)
        
        if len(results) == 1:
            return results[0]
        
        merged = FastExtractionResult(metrics=metrics)
        
        # 合并实体（去重基于名称）
        entity_names = set()
        for res in results:
            for entity in res.entities:
                entity_dict = entity if isinstance(entity, dict) else entity.__dict__
                name = entity_dict.get('name') or entity_dict.get('entity_name')
                if name and name not in entity_names:
                    merged.entities.append(entity)
                    entity_names.add(name)
        
        # 合并事件（去重基于描述）
        event_descs = set()
        for res in results:
            for event in res.events:
                event_dict = event if isinstance(event, dict) else event.__dict__
                desc = str(event_dict.get('description', ''))
                if desc and desc not in event_descs:
                    merged.events.append(event)
                    event_descs.add(desc)
        
        # 合并时间锚点（去重）
        anchor_keys = set()
        for res in results:
            for anchor in res.temporal_anchors:
                anchor_dict = anchor if isinstance(anchor, dict) else anchor.__dict__
                key = (anchor_dict.get('date'), anchor_dict.get('event'))
                if key not in anchor_keys:
                    merged.temporal_anchors.append(anchor)
                    anchor_keys.add(key)
        
        # 情感：合并所有片段
        for res in results:
            merged.emotions.extend(res.emotions)
        
        # 风格：使用最后一个非空的
        for res in reversed(results):
            if res.style:
                merged.style = res.style
                break
        
        # 更新统计
        metrics.entity_count = len(merged.entities)
        metrics.event_count = len(merged.events)
        metrics.anchor_count = len(merged.temporal_anchors)
        
        logger.info(f"合并完成: {len(results)}个片段 -> {metrics.entity_count}实体, {metrics.event_count}事件")
        
        return merged

    def _apply_result(self, result, name, res, metrics):
        """应用单个提取结果到总结果"""
        if not res:
            return

        if name == 'entity':
            result.entities = res[0].entities
            result.entities.extend(res[0].relations)
            metrics.entity_count = len(result.entities)
        elif name == 'event':
            result.events = res[0].events
            metrics.event_count = len(result.events)
        elif name == 'temporal':
            result.temporal_anchors = res[0].temporal_anchors
            metrics.anchor_count = len(result.temporal_anchors)
        elif name == 'emotion':
            result.emotions = res[0].segments
        elif name == 'style':
            result.style = res[0].style.__dict__ if res[0].style else {}

    async def _timed_extract(self, extractor_fn, doc, name, metrics, **kwargs):
        """带计时的提取"""
        start = time.perf_counter()
        try:
            result = await extractor_fn(doc, **kwargs)
            elapsed = time.perf_counter() - start
            setattr(metrics, f'{name}_time', elapsed)
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            setattr(metrics, f'{name}_time', elapsed)
            raise


async def fast_extract(
    text: str,
    user_id: str,
    user_birth_year: Optional[int] = None,
) -> FastExtractionResult:
    """
    快速提取入口函数
    
    使用方法:
        result = await fast_extract(dialogue_text, 'user123', 1950)
    """
    extractor = ConcurrentExtractor()
    return await extractor.extract(text, user_id, user_birth_year)
