"""
测试知识提取（使用客户端并发 + 文本拆分）
"""
import sys
import asyncio
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath('backend'))

from app.knowledge_extraction.pipeline import ConcurrentExtractor
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    # 读取测试文件
    sample_file = Path('backend/tests/sample_dialogue.txt')
    
    if not sample_file.exists():
        print(f"❌ 文件不存在: {sample_file}")
        return
    
    text = sample_file.read_text(encoding='utf-8')
    print(f"📄 读取文件: {sample_file}")
    print(f"📏 文本长度: {len(text)} 字符")
    print("=" * 60)
    
    # 创建提取器
    extractor = ConcurrentExtractor()
    
    # 执行提取
    print("\n🚀 开始知识提取...")
    result = await extractor.extract(
        text=text,
        user_id='test_user',
        user_birth_year=1946,
        skip_emotion=True,
        skip_style=True
    )
    
    # 显示结果
    print("\n" + "=" * 60)
    print("📊 提取结果统计")
    print("=" * 60)
    
    metrics = result.metrics
    print(f"\n⏱️  性能指标:")
    print(f"  总耗时: {metrics.total_time:.2f}s")
    print(f"  解析时间: {metrics.parse_time:.2f}s")
    print(f"  实体提取: {metrics.entity_time:.2f}s")
    print(f"  事件提取: {metrics.event_time:.2f}s")
    print(f"  时间提取: {metrics.temporal_time:.2f}s")
    
    print(f"\n📈 提取数量:")
    print(f"  实体数量: {metrics.entity_count}")
    print(f"  事件数量: {metrics.event_count}")
    print(f"  时间锚点: {metrics.anchor_count}")
    
    # 显示部分结果
    if result.entities:
        print(f"\n👤 实体示例 (前5个):")
        for i, entity in enumerate(result.entities[:5]):
            entity_dict = entity if isinstance(entity, dict) else entity.__dict__
            print(f"  {i+1}. {entity_dict.get('name', 'N/A')} - {entity_dict.get('type', 'N/A')}")
    
    if result.events:
        print(f"\n📅 事件示例 (前5个):")
        for i, event in enumerate(result.events[:5]):
            event_dict = event if isinstance(event, dict) else event.__dict__
            desc = event_dict.get('description', 'N/A')
            print(f"  {i+1}. {desc[:60]}...")
    
    if result.temporal_anchors:
        print(f"\n⏰ 时间锚点示例 (前5个):")
        for i, anchor in enumerate(result.temporal_anchors[:5]):
            anchor_dict = anchor if isinstance(anchor, dict) else anchor.__dict__
            date = anchor_dict.get('date', 'N/A')
            event = anchor_dict.get('event', 'N/A')
            print(f"  {i+1}. {date} - {event[:50]}...")
    
    print("\n✅ 测试完成!")

if __name__ == "__main__":
    asyncio.run(main())
