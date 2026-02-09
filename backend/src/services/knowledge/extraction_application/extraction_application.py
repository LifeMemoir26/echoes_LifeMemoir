"""
知识图谱提取服务
负责协调整个提取流程：文本切分 -> 并发提取 -> 结果合并 -> 存储
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from ....infrastructure.utils.text_splitter import TextSplitter, SplitterMode
from .extractor.life_event_extractor import LifeEventExtractor
from .extractor.character_profile_extractor import CharacterProfileExtractor
from ....infrastructure.llm.client.qiniu_client import AsyncQiniuAIClient
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager
from ....core.config import LLMConfig
from ....infrastructure.database.sqlite_client import SQLiteClient
from ....infrastructure.database import EventStore, CharacterStore
from ..refinement_application.refinement_application import RefinementPipeline

logger = logging.getLogger(__name__)


class KnowledgeService:
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
        concurrency_manager,
        data_base_dir: Optional[Path] = None,
        verbose: bool = False
    ):
        """
        初始化Pipeline
        
        Args:
            username: 用户名（用于创建独立的数据库）
            concurrency_manager: ConcurrencyManager实例（全局单例）
            data_base_dir: 数据存储目录（默认为项目根目录/data）
            verbose: 是否打印详细信息
        """
        self.username = username
        self.verbose = verbose
        
        # 并发管理器和配置
        self.concurrency_manager = concurrency_manager
        self.config = concurrency_manager.config
        
        # 文本切分器（知识提取模式：8000字窗口，4000字步长）
        self.text_splitter = TextSplitter(
            mode=SplitterMode.KNOWLEDGE_EXTRACTION
        )
        
        # SQLite客户端
        self.sqlite_client = SQLiteClient(
            username=username,
            data_base_dir=data_base_dir
        )
        
        # 存储
        self.event_store = EventStore(self.sqlite_client)
        self.character_store = CharacterStore(self.sqlite_client)
        
        logger.info(
            f"KnowledgeService初始化完成: "
            f"用户={username}, 并发={self.concurrency_manager.concurrency_level}"
        )
    
    def _print_step(self, step: int, total: int, message: str):
        """打印步骤信息"""
        if self.verbose:
            icons = ["📄", "✂️", "🚀", "📊", "💾"]
            icon = icons[step - 1] if step <= len(icons) else "▸"
            print(f"\n{icon} 步骤 {step}/{total}: {message}")
    
    async def _extract_and_write_events(
        self,
        chunk: str,
        chunk_id: int,
        narrator_name: str,
        total_chunks: int
    ) -> tuple[str, int, int]:
        """提取事件并立即写入"""
        try:
            event_extractor = LifeEventExtractor(
                self.concurrency_manager, 
                model=self.config.extraction_model
            )
            events = await event_extractor.extract(chunk, narrator_name)
            if events:
                count = self.event_store.write_events(events)
                if self.verbose:
                    print(f"   块 {chunk_id}/{total_chunks}: 事件{count}条已写入")
                return ('events', chunk_id, count)
            return ('events', chunk_id, 0)
        except Exception as e:
            logger.error(f"块 {chunk_id} 事件提取失败: {e}", exc_info=True)
            return ('events', chunk_id, 0)
    
    async def _extract_and_write_profile(
        self,
        chunk: str,
        chunk_id: int,
        narrator_name: str,
        total_chunks: int
    ) -> tuple[str, int, int]:
        """提取特征并立即写入"""
        try:
            profile_extractor = CharacterProfileExtractor(
                self.concurrency_manager,
                model=self.config.extraction_model
            )
            profile = await profile_extractor.extract(chunk, narrator_name)
            if profile and (profile.get('personality') or profile.get('worldview') or profile.get('aliases')):
                profile_id = self.character_store.write_profile(profile)
                
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
                    print(f"   块 {chunk_id}/{total_chunks}: 特征档案已写入")
                return ('profile', chunk_id, 1)
            return ('profile', chunk_id, 0)
        except Exception as e:
            logger.error(f"块 {chunk_id} 特征提取失败: {e}", exc_info=True)
            return ('profile', chunk_id, 0)
    
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
        
        # 步骤2: 并发提取与写入（提取完立即写入，无需等待所有块）
        self._print_step(2, 5, f"并发提取与写入 (共{len(chunks)}个块)")
        
        # 创建所有提取+写入任务（每个chunk有2个独立任务）
        tasks = []
        for i, chunk in enumerate(chunks):
            chunk_id = i + 1
            tasks.append(self._extract_and_write_events(chunk, chunk_id, narrator_name, len(chunks)))
            tasks.append(self._extract_and_write_profile(chunk, chunk_id, narrator_name, len(chunks)))
        
        # 并发执行所有任务（ConcurrencyManager内部自动排队和轮询）
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        total_events = 0
        total_profiles = 0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务执行失败: {result}")
                continue
            
            task_type, chunk_id, count = result
            if task_type == 'events':
                total_events += count
            else:
                total_profiles += count
        
        if self.verbose:
            print(f"   完成写入: 事件{total_events}条, 人物档案{total_profiles}个")
        
        # 步骤3: LLM精炼去重
        self._print_step(3, 5, "LLM精炼去重")
        
        # 使用全局并发管理器进行精炼
        refiner = RefinementPipeline(self.sqlite_client, self.concurrency_manager)
        
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
    
    def close(self):
        """关闭资源"""
        self.sqlite_client.close()
        logger.info("Pipeline已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


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
    
    # 创建Service
    with KnowledgeService(
        username=username,
        data_base_dir=data_base_dir,
        concurrency_level=concurrency_level,
        verbose=verbose
    ) as service:
        # 处理文本
        stats = await service.process_text(text, narrator_name)
        stats['source_file'] = file_path
        return stats
