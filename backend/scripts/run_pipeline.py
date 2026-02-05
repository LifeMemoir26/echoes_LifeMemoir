"""
完整知识提取与向量构建流程

两阶段流程：

【阶段1：知识图谱构建】
1. 文本切分（8000字窗口，4000字步长）
2. 并发提取：
   - "精准年份-时间补充-事件说明"
   - 人物性格 + 世界观 + 别名关联
3. 存入SQLite数据库
4. LLM总结去重与精准化

【阶段2：向量数据库构建】
1. 文本切分（1000字窗口，900字滑动）
2. 加载别名对应表
3. 并发提取对话概要
4. 存入SQLite（chunks.db）+ ChromaDB向量库

配置：
- 数据根目录：项目根目录/data
- 测试文件：backend/examples/1.txt
- 并发数：由ConcurrencyManager.concurrency_level控制
- 向量编码批次：由EmbeddingConfig.batch_size控制
"""

import sys
import time
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipelines.extraction_pipeline import ExtractionPipeline
from src.pipelines.vector_pipeline import VectorPipeline
from src.llm.concurrency_manager import get_concurrency_manager
from src.config import get_settings


async def main():
    print("=" * 80)
    print("完整知识提取与向量构建流程")
    print("=" * 80)
    
    # ========== 配置参数 ==========
    username = "特朗普"
    project_root = Path(__file__).parent.parent.parent
    data_root = project_root / "data"
    input_file = project_root / "backend" / "examples" / "1.txt"
    
    print(f"\n📋 配置信息:")
    print(f"  用户名: {username}")
    print(f"  数据根目录: {data_root.absolute()}")
    print(f"  输入文件: {input_file.absolute()}")
    
    # 检查文件
    if not input_file.exists():
        print(f"\n❌ 错误：输入文件不存在: {input_file}")
        return
    
    print(f"  文件大小: {input_file.stat().st_size / 1024:.2f} KB")
    
    # ========== 读取文本 ==========
    print(f"\n📖 读取对话内容...")
    with open(input_file, 'r', encoding='utf-8') as f:
        dialogue = f.read()
    
    print(f"  原始文本: {len(dialogue)} 字符")
    print(f"  预览前150字: {dialogue[:150]}...")
    
    total_start = time.time()
    
    # ========================================================================
    # 阶段1：知识图谱构建（事件+性格+别名提取）
    # ========================================================================
    print("\n" + "=" * 80)
    print("【阶段1：知识图谱构建】")
    print("=" * 80)
    
    print(f"\n🔧 初始化知识提取Pipeline...")
    stage1_start = time.time()
    
    # 加载配置
    config = get_settings()
    num_keys = len(config.llm.api_keys)
    
    # 并发级别：根据密钥数量智能设置（每个密钥轮流使用）
    recommended_concurrency = int(num_keys * config.llm.concurrency_multiplier)
    
    print(f"  检测到 {num_keys} 个API密钥")
    print(f"  推荐并发级别: {recommended_concurrency} (全局轮询模式)")
    
    # 获取全局并发管理器单例
    concurrency_manager = get_concurrency_manager()
    
    # 创建知识提取Pipeline
    extraction_pipeline = ExtractionPipeline(
        username=username,
        concurrency_manager=concurrency_manager,
        data_base_dir=data_root,
        verbose=True
    )
    
    # 配置日志显示详细信息
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print(f"  ✅ Pipeline初始化完成")
    print(f"  切分模式: 8000字窗口 / 4000字步长")
    print(f"  并发架构: 全局密钥池轮询")
    print(f"  并发级别: {recommended_concurrency}")
    
    # 执行知识提取
    print(f"\n🚀 执行知识提取流程...")
    try:
        kg_stats = await extraction_pipeline.process_text(
            text=dialogue,
            narrator_name=username
        )
        
        stage1_time = time.time() - stage1_start
        
        print(f"\n✅ 知识图谱构建完成！")
        print(f"\n📊 阶段1统计:")
        print(f"  总耗时: {stage1_time:.2f}秒")
        print(f"  文本块数: {kg_stats.get('chunks_count', 0)}")
        print(f"  原始事件: {kg_stats.get('events_before_refine', 0)}条")
        print(f"  精炼后事件: {kg_stats.get('events_count', 0)}条")
        print(f"  推测年份: {kg_stats.get('events_year_inferred', 0)}个")
        
        # 显示数据存储位置
        user_data_dir = data_root / username
        print(f"\n💾 知识图谱存储:")
        print(f"  数据库: {user_data_dir / 'database.db'}")
        
    except Exception as e:
        print(f"\n❌ 阶段1执行失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 短暂休息
    await asyncio.sleep(1)
    
    # ========================================================================
    # 阶段2：向量数据库构建（摘要提取+向量编码）
    # ========================================================================
    print("\n" + "=" * 80)
    print("【阶段2：向量数据库构建】")
    print("=" * 80)
    
    print(f"\n🔧 初始化向量构建Pipeline...")
    stage2_start = time.time()
    
    print(f"  ✅ 复用配置: {num_keys} 个API密钥")
    
    # 获取全局ConcurrencyManager
    concurrency_manager = get_concurrency_manager()
    print(f"  ✅ 获取全局ConcurrencyManager")
    
    # 创建向量Pipeline
    # 注意：新架构使用 concurrency_manager.generate_structured() 自动处理系统提示词分离
    vector_pipeline = VectorPipeline(
        username=username,
        concurrency_manager=concurrency_manager,
        data_root=str(data_root),
        model="deepseek-v3"
    )
    
    print(f"  ✅ Pipeline初始化完成")
    print(f"  切分模式: 1000字窗口 / 900字滑动")
    print(f"  向量模型: aspire/acge_text_embedding (1792维)")
    print(f"  并发级别: {recommended_concurrency}")
    
    # 执行向量构建
    print(f"\n🚀 执行向量构建流程...")
    print(f"  步骤: 分块 → 加载别名 → 提取摘要 → 存储 → 向量编码")
    
    try:
        vec_stats = await vector_pipeline.process_text(dialogue)
        
        stage2_time = time.time() - stage2_start
        
        print(f"\n✅ 向量数据库构建完成！")
        print(f"\n📊 阶段2统计:")
        print(f"  总耗时: {stage2_time:.2f}秒")
        print(f"  文本块数: {vec_stats['chunks_count']}")
        print(f"  摘要数量: {vec_stats['summaries_count']}")
        print(f"  向量数量: {vec_stats['vectors_count']}")
        print(f"  使用别名: {vec_stats['aliases_count']}个")
        print(f"  平均处理: {stage2_time / vec_stats['chunks_count']:.2f}秒/块")
        
        print(f"\n💾 向量数据存储:")
        print(f"  SQLite: {user_data_dir / 'chunks.db'}")
        print(f"  ChromaDB: {user_data_dir / 'chromadb'}/")
        
    except Exception as e:
        print(f"\n❌ 阶段2执行失败: {e}")
        import traceback
        traceback.print_exc()
        vector_pipeline.close()
        return
    
    # ========================================================================
    # 测试搜索功能
    # ========================================================================
    print("\n" + "=" * 80)
    print("【测试向量搜索】")
    print("=" * 80)
    
    test_queries = [
        "特朗普对风车和环境的看法",
        "沃尔曼溜冰场的修复故事",
        "与金正恩的外交关系",
        "2020年选举舞弊指控",
        "西点军校演讲后的坡道事件"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 查询 {i}: {query}")
        results = vector_pipeline.search_similar(query, top_k=2)
        
        if results:
            for j, result in enumerate(results, 1):
                score = result.get('score', 0)
                summary = result.get('summary', '')
                chunk_text = result.get('chunk_text', '')
                
                print(f"  结果 {j} (相似度: {score:.4f}):")
                print(f"    摘要: {summary[:120]}...")
                if chunk_text:
                    print(f"    原文: {chunk_text[:120]}...")
        else:
            print(f"  ⚠️  未找到相关结果")
    
    # ========================================================================
    # 总结
    # ========================================================================
    total_time = time.time() - total_start
    
    print("\n" + "=" * 80)
    print("【测试完成】")
    print("=" * 80)
    
    print(f"\n⏱️  总耗时: {total_time:.2f}秒")
    print(f"  阶段1（知识图谱）: {stage1_time:.2f}秒")
    print(f"  阶段2（向量库）: {stage2_time:.2f}秒")
    
    print(f"\n📦 数据文件:")
    print(f"  知识图谱: {user_data_dir / 'database.db'}")
    print(f"  向量块: {user_data_dir / 'chunks.db'}")
    print(f"  向量索引: {user_data_dir / 'chromadb'}/")
    
    print(f"\n✅ 所有数据已保存至: {user_data_dir.absolute()}")
    print("=" * 80)
    
    # 清理
    vector_pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
