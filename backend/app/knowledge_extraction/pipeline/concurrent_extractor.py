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
from ..llm import AsyncQiniuAIClient, ConcurrencyManager
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
    MAX_CHUNK_SIZE = 8000  # 单个 chunk 窗口大小约
    STEP_SIZE = 4000       # 滑动步长约（50%重叠）
    
    def __init__(
        self,
        model: Optional[str] = None,
        fast_model: Optional[str] = None,
        max_concurrent: int = 5,
        concurrency_level: int = 7,  # 默认7个并发
    ):
        settings = get_settings()
        self.model = model or settings.llm.extraction_model
        self.fast_model = fast_model or settings.llm.fast_model
        self.max_concurrent = max_concurrent
        
        # 使用并发管理器来管理API调用
        self._concurrency_manager = ConcurrencyManager(
            concurrency_level=concurrency_level,
            config=settings.llm,
        )
        
        # 创建多个 LLM 客户端实例以支持并发
        self._clients = self._concurrency_manager.clients
        
        # 初始化所有提取器，每个提取器使用不同的客户端
        self._entity_ext = EntityExtractor(self._clients[0], model=self.model)
        self._event_ext = EventExtractor(self._clients[1] if len(self._clients) > 1 else self._clients[0], model=self.model)
        self._temporal_ext = TemporalExtractor(self._clients[2] if len(self._clients) > 2 else self._clients[0], model=self.model)
        self._emotion_ext = EmotionExtractor(self._clients[3] if len(self._clients) > 3 else self._clients[0], model=self.fast_model)
        self._style_ext = StyleExtractor(self._clients[4] if len(self._clients) > 4 else self._clients[0], model=self.fast_model)
        
        self._adapter = DialogueAdapter()
    
    def _split_text(self, text: str) -> List[str]:
        """
        使用滑动窗口拆分对话文本
        
        对话格式：
        - [Interview]: 开始一个问题
        - [User]: 开始用户回答
        - 一个完整的对话轮次 = [Interview]: ... [User]: ...
        
        策略：
        1. 窗口大小：8000字符
        2. 步长：4000字符（50%重叠）
        3. 在窗口边缘寻找最近的 [Interview]: 标记来截断（保证从新对话轮次开始）
        4. 保持对话的完整性
        """
        text_len = len(text)
        
        if text_len <= self.MAX_CHUNK_SIZE:
            return [text]
        
        chunks = []
        start = 0
        
        # 预编译正则表达式，匹配对话开始标记（只匹配 [Interview]: 确保从完整对话开始）
        dialogue_start_pattern = re.compile(r'\[Interview\]:', re.IGNORECASE)
        
        while start < text_len:
            # 确定当前窗口的结束位置
            end = min(start + self.MAX_CHUNK_SIZE, text_len)
            
            # 如果不是最后一个窗口，寻找边缘附近最近的对话开始标记 [Interview]:
            if end < text_len:
                # 在窗口结束位置前后1000字符范围内搜索最近的 [Interview]: 标记
                search_start = max(end - 1000, start)
                search_end = min(end + 1000, text_len)
                search_text = text[search_start:search_end]
                
                # 找到所有对话开始标记的位置
                matches = list(dialogue_start_pattern.finditer(search_text))
                
                if matches:
                    # 找到距离原始end位置最近的 [Interview]: 标记
                    closest_match = min(
                        matches,
                        key=lambda m: abs((search_start + m.start()) - end)
                    )
                    # 在实际文本中的位置
                    actual_pos = search_start + closest_match.start()
                    end = actual_pos
            
            # 提取当前窗口的文本
            chunk = text[start:end].strip()
            
            if chunk:
                chunks.append(chunk)
                logger.debug(
                    f"切分窗口: start={start}, end={end}, "
                    f"size={len(chunk)}, total_progress={end}/{text_len}"
                )
            
            # 移动到下一个窗口（使用步长）
            # 如果是最后一个窗口，则结束
            if end >= text_len:
                break
            
            # 下一个窗口的起始位置
            next_start = start + self.STEP_SIZE
            
            # 在下一个窗口起始位置附近寻找 [Interview]: 标记，确保从完整对话开始
            if next_start < text_len:
                # 在步长位置前后搜索 [Interview]: 标记
                search_range_start = max(next_start - 500, start)
                search_range_end = min(next_start + 500, text_len)
                search_text = text[search_range_start:search_range_end]
                
                # 找到最接近 next_start 的 [Interview]: 标记
                matches = list(dialogue_start_pattern.finditer(search_text))
                
                if matches:
                    # 找到距离 next_start 最近的标记
                    closest_match = min(
                        matches,
                        key=lambda m: abs((search_range_start + m.start()) - next_start)
                    )
                    start = search_range_start + closest_match.start()
                else:
                    # 如果没找到标记，直接使用步长位置
                    start = next_start
            else:
                start = next_start
        
        logger.info(
            f"滑动窗口切分完成: {text_len}字符 -> {len(chunks)}个窗口 "
            f"(窗口大小={self.MAX_CHUNK_SIZE}, 步长={self.STEP_SIZE})"
        )
        
        # 输出每个窗口的详细信息
        for i, chunk in enumerate(chunks):
            logger.debug(f"窗口 {i+1}: {len(chunk)}字符, 开头={chunk[:50]}...")
        
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
