"""
Concurrent Extraction Service - 并发提取服务

提供对话文本的并发知识提取服务，包含：
1. 文本切分（滑动窗口）
2. 并发提取（5种提取器）
3. 结果合并
4. 写入图数据库
5. 完整日志记录
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from ..adapters.dialogue_adapter import DialogueAdapter
from ..adapters.base_adapter import StandardDocument
from ..extractors.entity_extractor import EntityExtractor
from ..extractors.event_extractor import EventExtractor
from ..extractors.emotion_extractor import EmotionExtractor
from ..extractors.style_extractor import StyleExtractor
from ..extractors.temporal_extractor import TemporalExtractor
from ..llm.qiniu_client import AsyncQiniuAIClient
from ..pipeline.concurrent_extractor import ConcurrentExtractor
from ..config import LLMConfig
from ..graph_store.graph_writer import GraphWriter
from ..graph_store.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


@dataclass
class ExtractionTask:
    """提取任务"""
    chunk_id: int
    chunk_text: str
    extractor_name: str
    retry_count: int = 0


@dataclass
class ExtractionResult:
    """提取结果"""
    chunk_id: int
    extractor_name: str
    results: List[Any]
    duration: float = 0.0
    error: Optional[str] = None
    is_retryable: bool = False
    retry_count: int = 0


class ConcurrentExtractionService:
    """
    并发提取服务
    
    核心功能：
    - 对话文本切分
    - 并发知识提取
    - 结果聚合
    - 图数据库写入
    - 完整日志记录
    """
    
    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        log_base_dir: Optional[Path] = None,
    ):
        """
        初始化服务
        
        Args:
            neo4j_uri: Neo4j连接URI
            neo4j_user: Neo4j用户名
            neo4j_password: Neo4j密码
            log_base_dir: 日志基础目录
        """
        # 配置
        self.config = LLMConfig()
        self.entity_config = LLMConfig()
        self.entity_config.timeout = 360  # 实体提取需要更长超时
        
        # 图数据库
        if neo4j_uri and neo4j_user and neo4j_password:
            self.neo4j_client = Neo4jClient(neo4j_uri, neo4j_user, neo4j_password)
            self.graph_writer = GraphWriter(self.neo4j_client)
        else:
            self.neo4j_client = None
            self.graph_writer = None
            logger.warning("Neo4j未配置，将跳过图数据库写入")
        
        # 日志目录
        if log_base_dir:
            self.log_base_dir = Path(log_base_dir)
        else:
            # 默认在backend/.log/API_generate_database/
            backend_dir = Path(__file__).parent.parent.parent.parent
            self.log_base_dir = backend_dir / ".log" / "API_generate_database"
        
        # 对话解析器
        self.adapter = DialogueAdapter()
        
        # 文本切分器
        self.text_splitter = ConcurrentExtractor()
    
    def _create_log_directory(self) -> Path:
        """创建日志目录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = self.log_base_dir / timestamp
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def _create_extractors(self) -> Dict[str, Any]:
        """创建提取器实例（每个Worker独立使用）"""
        entity_llm_client = AsyncQiniuAIClient(self.entity_config)
        llm_client = AsyncQiniuAIClient(self.config)
        
        return {
            "实体提取": EntityExtractor(entity_llm_client),
            "事件提取": EventExtractor(llm_client),
            "情感提取": EmotionExtractor(llm_client),
            "风格分析": StyleExtractor(llm_client),
            "时间提取": TemporalExtractor(llm_client)
        }
    
    async def _process_chunk_with_extractor(
        self,
        chunk_id: int,
        chunk_text: str,
        extractor_name: str,
        extractor: Any,
        document: StandardDocument,
        user_name: str,
        retry_count: int = 0
    ) -> ExtractionResult:
        """处理单个chunk的单个提取器"""
        start_time = asyncio.get_event_loop().time()
        retry_prefix = f"[重试{retry_count}] " if retry_count > 0 else ""
        
        try:
            # 创建临时document
            temp_doc = StandardDocument(
                id=f"{document.id}_chunk_{chunk_id}",
                user_id=document.user_id,
                source_type=document.source_type,
                raw_content=chunk_text,
                turns=[],
                created_at=document.created_at
            )
            
            # 所有提取器都传递user_name参数
            if user_name:
                results = await extractor.extract(temp_doc, user_name=user_name)
            else:
                results = await extractor.extract(temp_doc)
            
            duration = asyncio.get_event_loop().time() - start_time
            logger.info(f"✅ {retry_prefix}Chunk#{chunk_id} {extractor_name}: {len(results)} 项 ({duration:.1f}s)")
            return ExtractionResult(chunk_id, extractor_name, results, duration)
            
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            error_msg = str(e)
            
            # 判断是否可重试
            is_retryable = (
                'timeout' in error_msg.lower() or 
                'json' in error_msg.lower() or
                'parse' in error_msg.lower() or
                '403' in error_msg or
                '429' in error_msg or
                '500' in error_msg or
                '502' in error_msg or
                '503' in error_msg
            )
            
            logger.error(f"❌ {retry_prefix}Chunk#{chunk_id} {extractor_name} 失败 ({duration:.1f}s): {e}")
            
            result = ExtractionResult(chunk_id, extractor_name, [], duration, error_msg)
            result.is_retryable = is_retryable
            result.retry_count = retry_count
            return result
    
    async def _process_all_chunks(
        self,
        chunks: List[str],
        document: StandardDocument,
        user_name: str,
        max_concurrency: int = 5,
        max_retries: int = 2
    ) -> Dict[str, List[Any]]:
        """并发处理所有chunks"""
        queue = asyncio.Queue()
        extractor_names = list(self._create_extractors().keys())
        
        # 填充任务队列
        for chunk_id, chunk_text in enumerate(chunks):
            for extractor_name in extractor_names:
                await queue.put((chunk_id, chunk_text, extractor_name, 0))
        
        total_tasks = queue.qsize()
        logger.info(f"📋 任务队列: {total_tasks} 个任务 ({len(chunks)} chunks × {len(extractor_names)} 提取器)")
        logger.info(f"🚀 启动 {max_concurrency} 个并发Worker")
        
        # 结果收集
        results_by_extractor = {name: [] for name in extractor_names}
        completed = 0
        retry_queue = []
        start_time = asyncio.get_event_loop().time()
        
        async def worker(worker_id: int):
            nonlocal completed
            my_extractors = self._create_extractors()
            logger.info(f"Worker#{worker_id} 已创建独立提取器")
            
            while True:
                try:
                    chunk_id, chunk_text, extractor_name, retry_count = await asyncio.wait_for(
                        queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    logger.info(f"Worker#{worker_id} 退出（队列为空）")
                    break
                
                result = await self._process_chunk_with_extractor(
                    chunk_id, chunk_text, extractor_name,
                    my_extractors[extractor_name],
                    document, user_name, retry_count
                )
                
                # 处理结果
                if result.error:
                    if result.is_retryable and retry_count < max_retries:
                        retry_queue.append((chunk_id, chunk_text, extractor_name, retry_count + 1))
                        logger.warning(f"⚠️  Chunk#{chunk_id} {extractor_name} 将重试 ({retry_count + 1}/{max_retries})")
                    else:
                        logger.error(f"⛔ Chunk#{chunk_id} {extractor_name} 达到最大重试次数或不可重试")
                else:
                    results_by_extractor[extractor_name].extend(result.results)
                
                completed += 1
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"📊 进度: {completed}/{total_tasks} ({completed/total_tasks*100:.1f}%) | 耗时: {elapsed:.1f}s")
                
                queue.task_done()
        
        # 启动Workers
        workers = [asyncio.create_task(worker(i)) for i in range(max_concurrency)]
        await asyncio.gather(*workers)
        
        # 处理重试
        if retry_queue:
            logger.info(f"🔄 开始重试 {len(retry_queue)} 个失败任务")
            for task in retry_queue:
                await queue.put(task)
            workers = [asyncio.create_task(worker(i)) for i in range(max_concurrency)]
            await asyncio.gather(*workers)
        
        total_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"✅ 所有任务完成！总耗时: {total_time:.1f}s")
        
        return results_by_extractor
    
    def _save_results_to_json(self, results: Dict[str, List[Any]], log_dir: Path):
        """保存结果到JSON文件"""
        output_file = log_dir / "extraction_results.json"
        
        # 转换结果为可序列化格式
        serializable_results = {}
        for extractor_name, items in results.items():
            serializable_results[extractor_name] = []
            for item in items:
                if hasattr(item, 'dict'):
                    serializable_results[extractor_name].append(item.dict())
                elif hasattr(item, 'model_dump'):
                    serializable_results[extractor_name].append(item.model_dump())
                elif hasattr(item, '__dict__'):
                    serializable_results[extractor_name].append(item.__dict__)
                else:
                    serializable_results[extractor_name].append(str(item))
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"💾 提取结果已保存到: {output_file}")
        return output_file
    
    async def extract_and_write(
        self,
        dialogue_text: str,
        user_name: str,
        user_id: Optional[str] = None,
        max_concurrency: int = 5,
        write_to_db: bool = True,
    ) -> Dict[str, Any]:
        """
        提取知识并写入图数据库
        
        Args:
            dialogue_text: 对话文本
            user_name: 用户名称
            user_id: 用户ID（默认使用user_name）
            max_concurrency: 最大并发数
            write_to_db: 是否写入数据库
            
        Returns:
            包含提取结果和统计信息的字典
        """
        start_time = datetime.now()
        user_id = user_id or user_name
        
        # 创建日志目录
        log_dir = self._create_log_directory()
        logger.info(f"📂 日志目录: {log_dir}")
        
        # 1. 解析对话
        logger.info("📖 步骤 1/5: 解析对话...")
        documents = self.adapter.parse(dialogue_text)
        if not documents:
            raise ValueError("解析失败：没有生成任何文档")
        
        document = documents[0]
        document.user_name = user_name
        document.user_id = user_id
        logger.info(f"   解析完成: {len(document.turns)} 轮对话")
        
        # 2. 切分文本
        logger.info("✂️  步骤 2/5: 切分文本（滑动窗口）...")
        chunks = self.text_splitter._split_text(document.raw_content)
        logger.info(f"   切分成 {len(chunks)} 个chunks")
        for i, chunk in enumerate(chunks):
            logger.info(f"     - Chunk#{i}: {len(chunk)} 字符")
        
        # 3. 并发提取
        logger.info("🚀 步骤 3/5: 开始并发提取...")
        results = await self._process_all_chunks(
            chunks=chunks,
            document=document,
            user_name=user_name,
            max_concurrency=max_concurrency
        )
        
        # 4. 保存结果
        logger.info("💾 步骤 4/5: 保存提取结果...")
        results_file = self._save_results_to_json(results, log_dir)
        
        # 5. 写入图数据库
        if write_to_db and self.graph_writer:
            logger.info("📊 步骤 5/5: 写入图数据库...")
            await self._write_to_graph(user_id, user_name, results, document)
        else:
            logger.info("⏭️  步骤 5/5: 跳过图数据库写入")
        
        # 统计信息
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        stats = {
            "user_name": user_name,
            "user_id": user_id,
            "chunks_count": len(chunks),
            "extractors_count": 5,
            "total_tasks": len(chunks) * 5,
            "results": {
                "实体提取": len(results.get("实体提取", [])),
                "事件提取": len(results.get("事件提取", [])),
                "情感提取": len(results.get("情感提取", [])),
                "风格分析": len(results.get("风格分析", [])),
                "时间提取": len(results.get("时间提取", [])),
            },
            "log_directory": str(log_dir),
            "results_file": str(results_file),
            "duration_seconds": duration,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        
        # 保存统计信息
        stats_file = log_dir / "extraction_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ 知识提取完成！")
        logger.info("-" * 80)
        logger.info(f"用户: {user_name}")
        logger.info(f"总耗时: {duration:.1f}秒")
        logger.info(f"提取结果:")
        for extractor_name, count in stats["results"].items():
            logger.info(f"  - {extractor_name}: {count} 项")
        logger.info(f"日志目录: {log_dir}")
        logger.info("=" * 80)
        
        return stats
    
    async def _write_to_graph(
        self,
        user_id: str,
        user_name: str,
        results: Dict[str, List[Any]],
        document: StandardDocument
    ):
        """写入图数据库"""
        try:
            # 创建/获取用户
            birth_year = None
            temporal_results = results.get("时间提取", [])
            if temporal_results:
                birth_year = getattr(temporal_results[0], 'user_birth_year', None)
            
            await self.graph_writer.create_or_get_user(
                user_id=user_id,
                name=user_name,
                birth_year=birth_year,
            )
            logger.info(f"✅ 创建/更新用户节点: {user_name}")
            
            # 写入对话来源
            await self.graph_writer.write_dialogue_source(
                document_id=document.id,
                source_type=document.source_type.value,
                raw_content=document.raw_content,
                session_id=document.session_id,
            )
            logger.info("✅ 写入对话来源")
            
            # 写入实体
            entity_results = results.get("实体提取", [])
            if entity_results:
                for entity_result in entity_results:
                    entity_ids = await self.graph_writer.write_entities(
                        user_id=user_id,
                        extraction_result=entity_result,
                    )
                logger.info(f"✅ 写入实体: {len(entity_results)} 个结果")
            
            # 写入事件
            event_results = results.get("事件提取", [])
            event_ids = []
            if event_results:
                for event_result in event_results:
                    ids = await self.graph_writer.write_events(
                        user_id=user_id,
                        extraction_result=event_result,
                        temporal_result=temporal_results[0] if temporal_results else None,
                        source_document_id=document.id,
                    )
                    event_ids.extend(ids)
                logger.info(f"✅ 写入事件: {len(event_results)} 个结果")
            
            # 写入情感
            emotion_results = results.get("情感提取", [])
            if emotion_results and event_ids:
                for emotion_result in emotion_results:
                    await self.graph_writer.write_emotions(
                        event_ids=event_ids,
                        extraction_result=emotion_result,
                    )
                logger.info(f"✅ 写入情感: {len(emotion_results)} 个结果")
            
            # 写入风格
            style_results = results.get("风格分析", [])
            if style_results:
                await self.graph_writer.write_speaking_style(
                    user_id=user_id,
                    extraction_result=style_results[0],
                )
                logger.info(f"✅ 写入说话风格")
            
            logger.info("🎉 所有数据已成功写入图数据库")
            
        except Exception as e:
            logger.error(f"❌ 图数据库写入失败: {e}", exc_info=True)
            raise
    
    async def close(self):
        """关闭服务"""
        if self.neo4j_client:
            await self.neo4j_client.close()
