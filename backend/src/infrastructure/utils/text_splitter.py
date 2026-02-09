"""
文本切分器 - 滑动窗口切分
支持两种预设配置：
1. KNOWLEDGE_EXTRACTION: 8000字窗口，4000字步长（用于知识提取）
2. VECTOR_BUILDING: 1000字窗口，900字步长（用于向量构建）
"""
import re
import logging
from typing import List
from enum import Enum

logger = logging.getLogger(__name__)


class SplitterMode(Enum):
    """切分器模式"""
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"  # 知识提取模式：8000/4000
    VECTOR_BUILDING = "vector_building"            # 向量构建模式：1000/900
    CUSTOM = "custom"                              # 自定义模式


class TextSplitter:
    """
    滑动窗口文本切分器
    
    支持两种预设模式：
    1. KNOWLEDGE_EXTRACTION: 8000字窗口，4000字步长，搜索范围±500字
    2. VECTOR_BUILDING: 1000字窗口，900字步长，搜索范围±200字
    """
    
    # 知识提取模式配置（大窗口）
    KNOWLEDGE_WINDOW_SIZE = 8000
    KNOWLEDGE_STEP_SIZE = 4000
    KNOWLEDGE_SEARCH_RANGE = 1000
    
    # 向量构建模式配置（小窗口）
    VECTOR_WINDOW_SIZE = 1000
    VECTOR_STEP_SIZE = 900
    VECTOR_SEARCH_RANGE = 300
    
    def __init__(
        self, 
        mode: SplitterMode = SplitterMode.KNOWLEDGE_EXTRACTION,
        window_size: int = None,
        step_size: int = None,
        search_range: int = None
    ):
        """
        初始化切分器
        
        Args:
            mode: 切分模式（KNOWLEDGE_EXTRACTION/VECTOR_BUILDING/CUSTOM）
            window_size: 自定义窗口大小（CUSTOM模式时必填）
            step_size: 自定义步长（CUSTOM模式时必填）
            search_range: 自定义搜索范围（CUSTOM模式时必填）
        """
        self.mode = mode
        
        # 根据模式设置参数
        if mode == SplitterMode.KNOWLEDGE_EXTRACTION:
            self.window_size = self.KNOWLEDGE_WINDOW_SIZE
            self.step_size = self.KNOWLEDGE_STEP_SIZE
            self.search_range = self.KNOWLEDGE_SEARCH_RANGE
        elif mode == SplitterMode.VECTOR_BUILDING:
            self.window_size = self.VECTOR_WINDOW_SIZE
            self.step_size = self.VECTOR_STEP_SIZE
            self.search_range = self.VECTOR_SEARCH_RANGE
        elif mode == SplitterMode.CUSTOM:
            if window_size is None or step_size is None or search_range is None:
                raise ValueError("CUSTOM模式需要提供window_size, step_size, search_range参数")
            self.window_size = window_size
            self.step_size = step_size
            self.search_range = search_range
        else:
            raise ValueError(f"不支持的切分模式: {mode}")
        
        logger.info(
            f"初始化TextSplitter - 模式: {mode.value}, "
            f"窗口: {self.window_size}, 步长: {self.step_size}, "
            f"搜索范围: ±{self.search_range}"
        )
        
        if self.step_size >= self.window_size:
            logger.warning(
                f"步长({self.step_size})>=窗口大小({self.window_size})，将不会有重叠区域"
            )
    
    def split(self, text: str) -> List[str]:
        """
        使用滑动窗口拆分对话文本
        
        对话格式：
        - [Interviewer]: 开始一个问题
        - [User]: 开始用户回答
        - 一个完整的对话轮次 = [Interviewer]: ... [User]: ...
        
        策略：
        1. 窗口大小：根据模式设置（知识提取8000/向量构建1000）
        2. 步长：根据模式设置（知识提取4000/向量构建900）
        3. 在窗口边缘寻找最近的 [Interviewer]: 标记来截断（保证从新对话轮次开始）
        4. 保持对话的完整性
        """
        text = text.strip()
        text_len = len(text)
        
        if text_len <= self.window_size:
            logger.info(f"文本长度({text_len})<=窗口大小({self.window_size})，无需切分")
            return [text]
        
        chunks = []
        start = 0
        
        # 预编译正则表达式，匹配对话开始标记（[Interviewer]: 确保从完整对话开始）
        dialogue_start_pattern = re.compile(r'\[Interviewer\]:', re.IGNORECASE)
        
        while start < text_len:
            # 确定当前窗口的结束位置
            end = min(start + self.window_size, text_len)
            
            # 如果不是最后一个窗口，在结束位置寻找最近的[Interviewer]:标记来切断
            # 确保不会在对话中间截断
            if end < text_len:
                # 先向后搜索（在搜索范围内）
                search_start = end
                search_end = min(end + self.search_range, text_len)
                search_text = text[search_start:search_end]
                
                # 找到第一个对话开始标记
                match = dialogue_start_pattern.search(search_text)
                
                if match:
                    # 在下一个[Interviewer]:处切断
                    end = search_start + match.start()
                else:
                    # 如果向后没找到，在当前窗口范围内向前寻找最近的标记
                    search_start = max(end - self.search_range, start)
                    search_end = end
                    search_text = text[search_start:search_end]
                    
                    # 找到最后一个[Interviewer]:标记
                    matches = list(dialogue_start_pattern.finditer(search_text))
                    if matches:
                        end = search_start + matches[-1].start()
            
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
            next_start = start + self.step_size
            
            # 在下一个窗口起始位置附近寻找 [Interviewer]: 标记，确保从完整对话开始
            if next_start < text_len:
                # 在步长位置向后搜索 [Interviewer]: 标记（优先向后查找）
                # 使用搜索范围而不是整个窗口
                search_range_start = next_start
                search_range_end = min(next_start + self.search_range, text_len)
                search_text = text[search_range_start:search_range_end]
                
                # 找到第一个 [Interviewer]: 标记
                match = dialogue_start_pattern.search(search_text)
                
                if match:
                    # 使用找到的标记位置作为下一个窗口的起点
                    start = search_range_start + match.start()
                else:
                    # 如果向后没找到，向前搜索
                    search_range_start = max(next_start - self.search_range, start)
                    search_range_end = next_start
                    search_text = text[search_range_start:search_range_end]
                    
                    # 找到最后一个 [Interviewer]: 标记
                    matches = list(dialogue_start_pattern.finditer(search_text))
                    if matches:
                        start = search_range_start + matches[-1].start()
                    else:
                        # 如果都没找到，直接使用步长位置
                        start = next_start
            else:
                start = next_start
        
        logger.info(
            f"滑动窗口切分完成: {text_len}字符 -> {len(chunks)}个窗口 "
            f"(窗口大小={self.window_size}, 步长={self.step_size}, "
            f"重叠率={100-self.step_size*100//self.window_size}%)"
        )
        
        return chunks
    
    def get_chunk_info(self, chunks: List[str]) -> str:
        """
        获取切分信息摘要
        
        Args:
            chunks: 切分后的文本块列表
            
        Returns:
            信息摘要字符串
        """
        if not chunks:
            return "无切分块"
        
        total_chars = sum(len(c) for c in chunks)
        avg_size = total_chars // len(chunks)
        
        info = [
            f"切分块数量: {len(chunks)}",
            f"总字符数: {total_chars}",
            f"平均大小: {avg_size}字符",
            f"最小块: {min(len(c) for c in chunks)}字符",
            f"最大块: {max(len(c) for c in chunks)}字符"
        ]
        
        return "\n".join(info)
