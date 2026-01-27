"""
知识图谱提取Pipeline
负责协调整个提取流程：文本切分 -> 并发提取 -> 结果合并 -> 存储
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..utils.text_splitter import TextSplitter, SplitterMode
from ..extract_info.extractor.life_event_extractor import LifeEventExtractor
from ..extract_info.extractor.character_profile_extractor import CharacterProfileExtractor
from ..llm.qiniu_client import AsyncQiniuAIClient
from ..llm.concurrency_manager import ConcurrencyManager
from ..config import LLMConfig
from ..database.sqlite_client import SQLiteClient
from ..database.event_writer import EventWriter
from ..database.character_writer import CharacterWriter

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """
    知识图谱提取Pipeline
    
    工作流程：
    1. 文本切分（8000字窗口，4000字步长）
    2. 并发提取（每个chunk并发调用两个提取器）
    3. 结果合并
    4. 写入SQLite
    """
    
    def __init__(
        self,
        username: str,
        data_base_dir: Optional[Path] = None,
        concurrency_level: int = 5,
        verbose: bool = False
    ):
        """
        初始化Pipeline
        
        Args:
            username: 用户名（用于创建独立的数据库）
            data_base_dir: 数据存储目录（默认为项目根目录/data）
            concurrency_level: 并发级别（默认5）
            verbose: 是否打印详细信息
        """
        self.username = username
        self.verbose = verbose
        
        # 配置
        self.config = LLMConfig()
        
        # 文本切分器（知识提取模式：8000字窗口，4000字步长）
        self.text_splitter = TextSplitter(
            mode=SplitterMode.KNOWLEDGE_EXTRACTION
        )
        
        # 并发管理器
        self.concurrency_manager = ConcurrencyManager(
            concurrency_level=concurrency_level,
            config=self.config
        )
        
        # SQLite客户端
        self.sqlite_client = SQLiteClient(
            username=username,
            data_base_dir=data_base_dir
        )
        
        # 写入器
        self.event_writer = EventWriter(self.sqlite_client)
        self.character_writer = CharacterWriter(self.sqlite_client)
        
        logger.info(
            f"ExtractionPipeline初始化完成: "
            f"用户={username}, 并发={concurrency_level}"
        )
    
    def _print_step(self, step: int, total: int, message: str):
        """打印步骤信息"""
        if self.verbose:
            icons = ["📄", "✂️", "🚀", "📊", "💾"]
            icon = icons[step - 1] if step <= len(icons) else "▸"
            print(f"\n{icon} 步骤 {step}/{total}: {message}")
    
    async def process_text(
        self,
        text: str,
        narrator_name: str = "叙述者"
    ) -> Dict[str, Any]:
        """
        处理文本，提取并存储到SQLite
        
        Args:
            text: 待处理的文本
            narrator_name: 叙述者名称
            
        Returns:
            处理结果统计
        """
        start_time = asyncio.get_event_loop().time()
        
        # 步骤1: 文本切分
        self._print_step(1, 5, f"文本切分 (8000字窗口, 4000字步长)")
        chunks = self.text_splitter.split(text)
        
        if self.verbose:
            print(f"   切分完成: {len(text)}字符 -> {len(chunks)}个块")
            print(f"   {self.text_splitter.get_chunk_info(chunks)}")
        
        # 步骤2: 并发提取
        self._print_step(2, 5, f"并发提取 (共{len(chunks)}个块)")
        
        all_events = []
        all_profiles = []
        
        # 创建提取任务
        tasks = []
        for i, chunk in enumerate(chunks):
            task = self._extract_from_chunk(chunk, i + 1, narrator_name)
            tasks.append(task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集结果并直接写入数据库
        total_events = 0
        total_profiles = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"块 {i+1} 提取失败: {result}")
                continue
            
            events, profile = result
            
            # 直接写入事件（不合并）
            if events:
                event_count = self.event_writer.write_events(events)
                total_events += event_count
            
            # 直接写入人物特征（不合并）
            if profile and (profile.get('personality') or profile.get('worldview') or profile.get('aliases')):
                profile_id = self.character_writer.write_profile(profile)
                total_profiles += 1
                
                # 写入别名到aliases表
                if profile.get('aliases'):
                    for alias_item in profile['aliases']:
                        try:
                            self.sqlite_client.insert_or_update_alias(
                                main_name=alias_item['formal_name'],
                                alias_names=alias_item['alias_list'],
                                entity_type=alias_item['type']
                            )
                        except Exception as e:
                            logger.error(f"写入别名失败: {alias_item}, 错误: {e}")
            
            if self.verbose:
                print(f"   块 {i+1}/{len(chunks)}: "
                      f"事件{len(events)}条已写入, "
                      f"特征档案已写入")
        
        if self.verbose:
            print(f"   原始写入: 事件{total_events}条, 人物档案{total_profiles}个")
        
        # 步骤3: LLM精炼去重
        self._print_step(3, 5, "LLM精炼去重")
        
        # 导入refiner
        from ..extract_info.refiner.refinement_pipeline import RefinementPipeline
        
        # 创建LLM客户端用于精炼
        refine_llm = self.concurrency_manager.clients[0]
        refiner = RefinementPipeline(self.sqlite_client, refine_llm)
        
        # 执行精炼流程
        refine_stats = await refiner.refine_all()
        
        if self.verbose:
            print(f"   事件精炼: {refine_stats.get('events_before', 0)} → {refine_stats.get('events_after', 0)}条")
            print(f"   年份推测: {refine_stats.get('events_year_inferred', 0)}个")
            print(f"   人物档案精炼完成")
        
        # 步骤4: 完成
        total_time = asyncio.get_event_loop().time() - start_time
        self._print_step(4, 5, f"处理完成 (耗时 {total_time:.1f}秒)")
        
        # 返回统计信息
        stats = {
            'username': self.username,
            'narrator_name': narrator_name,
            'chunks_count': len(chunks),
            'events_count': refine_stats.get('events_after', total_events),
            'events_before_refine': total_events,
            'events_year_inferred': refine_stats.get('events_year_inferred', 0),
            'total_time': total_time,
            'processed_at': datetime.now().isoformat()
        }
        
        logger.info(f"处理完成: {stats}")
        return stats
    
    async def _extract_from_chunk(
        self,
        chunk: str,
        chunk_id: int,
        narrator_name: str
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        从单个chunk中提取信息
        
        Args:
            chunk: 文本块
            chunk_id: 块编号
            narrator_name: 叙述者名称
            
        Returns:
            (事件列表, 人物特征)
        """
        try:
            # 获取可用的LLM客户端
            clients = self.concurrency_manager.clients
            
            # 为每个提取器分配不同的客户端
            event_client = clients[chunk_id % len(clients)]
            profile_client = clients[(chunk_id + 1) % len(clients)]
            
            # 创建提取器（显式传递model确保使用配置的模型）
            event_extractor = LifeEventExtractor(
                event_client, 
                model=self.config.extraction_model
            )
            profile_extractor = CharacterProfileExtractor(
                profile_client,
                model=self.config.extraction_model
            )
            
            # 并发提取两类信息
            events_task = event_extractor.extract(chunk, narrator_name)
            profile_task = profile_extractor.extract(chunk, narrator_name)
            
            events, profile = await asyncio.gather(events_task, profile_task)
            
            return events, profile
            
        except Exception as e:
            logger.error(f"块 {chunk_id} 提取失败: {e}", exc_info=True)
            return [], {}
    
    def close(self):
        """关闭资源"""
        self.sqlite_client.close()
        logger.info("Pipeline已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 保留旧名称作为别名，向后兼容
MongoExtractionPipeline = ExtractionPipeline


async def process_text_file(
    file_path: str,
    username: str,
    narrator_name: str = "叙述者",
    data_base_dir: Optional[Path] = None,
    concurrency_level: int = 5,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    处理文本文件的便捷函数
    
    Args:
        file_path: 文本文件路径
        username: 用户名
        narrator_name: 叙述者名称
        data_base_dir: 数据存储目录
        concurrency_level: 并发级别
        verbose: 是否打印详细信息
        
    Returns:
        处理结果统计
    """
    # 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    logger.info(f"读取文件: {file_path}, 长度: {len(text)}字符")
    
    # 创建Pipeline
    with ExtractionPipeline(
        username=username,
        data_base_dir=data_base_dir,
        concurrency_level=concurrency_level,
        verbose=verbose
    ) as pipeline:
        # 处理文本
        stats = await pipeline.process_text(text, narrator_name)
        stats['source_file'] = file_path
        return stats
