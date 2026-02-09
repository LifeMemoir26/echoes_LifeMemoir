"""
知识提取流水线编排服务
自动化完成从文件到知识图谱和向量库的全流程
"""
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio

from ...infrastructure.llm.concurrency_manager import ConcurrencyManager, get_concurrency_manager
from .extraction_application.extraction_application import ExtractionApplication
from .extraction_application.vector_application import VectorApplication

logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    知识提取流水线服务
    
    完整流程：
    1. 读取文件
    2. 阶段1：知识图谱构建（事件、人物、别名提取）
    3. 阶段2：向量数据库构建（摘要提取 + 向量编码）
    """
    
    def __init__(
        self,
        username: str,
        data_base_dir: Optional[Path] = None,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        verbose: bool = False
    ):
        """
        初始化知识整理流水线
        
        Args:
            username: 用户名
            data_base_dir: 数据存储目录
            concurrency_manager: 并发管理器（None则使用全局单例）
            verbose: 是否详细日志
        """
        self.username = username
        self.data_base_dir = Path(data_base_dir) if data_base_dir else Path("./data")
        self.verbose = verbose
        
        # 获取并发管理器
        self.concurrency_manager = concurrency_manager or get_concurrency_manager()
        
        logger.info(f"初始化知识提取流水线: user={username}")
    
    async def process_file(
        self,
        file_path: Path,
        narrator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理单个文件的完整流程
        
        Args:
            file_path: 输入文件路径
            narrator_name: 叙述者名称（默认使用username）
            
        Returns:
            处理统计信息
        """
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        narrator_name = narrator_name or self.username
        file_size_kb = file_path.stat().st_size / 1024
        
        logger.info("=" * 60)
        logger.info(f"开始知识提取流程")
        logger.info(f"  文件: {file_path.name} ({file_size_kb:.2f} KB)")
        logger.info(f"  用户: {self.username}")
        logger.info(f"  叙述者: {narrator_name}")
        logger.info("=" * 60)
        
        total_start = time.time()
        
        # 读取文件
        logger.info("📖 读取文件...")
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        logger.info(f"文件读取完成: {len(text)} 字符")
        
        # ========== 阶段1: 知识图谱构建 ==========
        logger.info("\n" + "=" * 60)
        logger.info("阶段1: 知识图谱构建（事件、人物、别名提取）")
        logger.info("=" * 60)
        
        stage1_start = time.time()
        
        # 创建知识提取应用
        extraction_service = ExtractionApplication(
            username=self.username,
            concurrency_manager=self.concurrency_manager,
            data_base_dir=self.data_base_dir,
            verbose=self.verbose
        )
        
        # 执行知识提取
        logger.info("🚀 开始提取知识图谱...")
        kg_stats = await extraction_service.process_text(text, narrator_name)
        
        stage1_time = time.time() - stage1_start
        logger.info(f"✅ 知识图谱构建完成 (耗时: {stage1_time:.1f}s)")
        logger.info(f"  文本块: {kg_stats.get('chunks_count', 0)}")
        logger.info(f"  事件数: {kg_stats.get('events_count', 0)}")
        
        # 短暂休息
        await asyncio.sleep(1)
        
        # ========== 阶段2: 向量数据库构建 ==========
        logger.info("\n" + "=" * 60)
        logger.info("阶段2: 向量数据库构建（摘要提取 + 向量编码）")
        logger.info("=" * 60)
        
        stage2_start = time.time()
        
        # 创建向量应用
        vector_service = VectorApplication(
            username=self.username,
            concurrency_manager=self.concurrency_manager,
            data_root=str(self.data_base_dir),
            model="deepseek-v3"
        )
        
        try:
            # 执行向量构建
            logger.info("🚀 开始构建向量数据库...")
            vec_stats = await vector_service.process_text(text, source_file=file_path.name)
            
            stage2_time = time.time() - stage2_start
            logger.info(f"✅ 向量数据库构建完成 (耗时: {stage2_time:.1f}s)")
            logger.info(f"  文本块: {vec_stats['chunks_count']}")
            logger.info(f"  摘要数: {vec_stats['summaries_count']}")
            logger.info(f"  向量数: {vec_stats['vectors_count']}")
        finally:
            vector_service.close()
        
        # ========== 总结 ==========
        total_time = time.time() - total_start
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 知识整理流程完成")
        logger.info("=" * 60)
        logger.info(f"总耗时: {total_time:.1f}s")
        logger.info(f"  阶段1（知识图谱）: {stage1_time:.1f}s")
        logger.info(f"  阶段2（向量库）: {stage2_time:.1f}s")
        
        user_data_dir = self.data_base_dir / self.username
        logger.info(f"\n💾 数据存储位置:")
        logger.info(f"  知识图谱: {user_data_dir / 'database.db'}")
        logger.info(f"  文本块: {user_data_dir / 'chunks.db'}")
        logger.info(f"  向量索引: {user_data_dir / 'chromadb'}/")
        
        # 返回汇总统计
        return {
            'total_time': total_time,
            'stage1_time': stage1_time,
            'stage2_time': stage2_time,
            'file_name': file_path.name,
            'file_size_kb': file_size_kb,
            'text_length': len(text),
            'knowledge_graph': kg_stats,
            'vector_database': vec_stats,
            'data_dir': str(user_data_dir)
        }

# =======================================
# 供外部调用的接口函数
# =======================================

async def process_knowledge_file(
    file_path: Path,
    username: str,
    data_base_dir: Optional[Path] = None,
    narrator_name: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    处理单个知识文件的完整流程
    
    Args:
        file_path: 输入文件路径
        username: 用户名
        data_base_dir: 数据存储目录
        narrator_name: 叙述者名称
        verbose: 是否详细日志
        
    Returns:
        处理统计信息
    """
    pipeline = KnowledgeService(
        username=username,
        data_base_dir=data_base_dir,
        verbose=verbose
    )
    
    return await pipeline.process_file(file_path, narrator_name)
