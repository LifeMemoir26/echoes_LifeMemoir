"""
完整知识提取与向量构建流程

使用 KnowledgeService 自动化处理：
1. 读取文件
2. 阶段1：知识图谱构建（事件、人物、别名提取 + 精炼）
3. 阶段2：向量数据库构建（摘要提取 + 向量编码）

配置：
- 数据根目录：项目根目录/data
- 测试文件：backend/examples/1.txt
- 并发数：由ConcurrencyManager自动管理
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.knowledge.api import process_knowledge_file
from src.core.paths import get_project_root, get_data_root


async def main():
    print("=" * 80)
    print("知识整理完整流程")
    print("=" * 80)
    
    # ========== 配置参数 ==========
    username = "特朗普"
    
    project_root = get_project_root()
    data_root = get_data_root()
    input_file = project_root / "backend" / "examples" / "1.txt"
    
    print(f"\n📋 配置:")
    print(f"  用户名: {username}")
    print(f"  数据目录: {data_root}")
    print(f"  输入文件: {input_file.name}")
    
    # 检查文件
    if not input_file.exists():
        print(f"\n❌ 文件不存在: {input_file}")
        return
    
    print(f"  文件大小: {input_file.stat().st_size / 1024:.2f} KB")
    
    # ========== 执行完整流程 ==========
    print("\n" + "=" * 80)
    
    # 配置日志
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 调用流水线服务
    try:
        stats = await process_knowledge_file(
            file_path=input_file,
            username=username,
            data_base_dir=data_root,
            verbose=True
        )
        
        print("\n" + "=" * 80)
        print("📊 处理统计:")
        print(f"  总耗时: {stats['total_time']:.1f}s")
        print(f"  文本长度: {stats['text_length']} 字符")
        print(f"  知识图谱: {stats['knowledge_graph'].get('events_count', 0)} 事件")
        print(f"  向量数据: {stats['vector_database']['vectors_count']} 向量")
        print(f"  数据位置: {stats['data_dir']}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
