#!/usr/bin/env python3
"""
Process Dialogue Script - 对话处理脚本

用法：
    python scripts/process_dialogue.py --input dialogue.txt --user-id user123
    python scripts/process_dialogue.py --text "interviewer: 你好\nuser: 你好啊"
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.knowledge_extraction.pipeline import ExtractionPipeline, PipelineResult

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="处理对话文本并构建知识图谱")
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input", "-i",
        type=Path,
        help="输入文件路径"
    )
    input_group.add_argument(
        "--text", "-t",
        type=str,
        help="直接输入对话文本"
    )
    
    parser.add_argument(
        "--user-id", "-u",
        type=str,
        default="default_user",
        help="用户 ID（默认：default_user）"
    )
    parser.add_argument(
        "--birth-year", "-b",
        type=int,
        help="用户出生年份（可选，用于时间推理）"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="输出结果文件路径（JSON）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )
    
    return parser.parse_args()


def print_result(result: PipelineResult, verbose: bool = False):
    """打印处理结果"""
    print("\n" + "=" * 60)
    print("📊 处理结果")
    print("=" * 60)
    
    status = "✅ 成功" if result.success else "❌ 失败"
    print(f"状态: {status}")
    print(f"用户 ID: {result.user_id}")
    print(f"文档 ID: {result.document_id}")
    print(f"处理时间: {result.processing_time_ms}ms")
    
    print("\n📈 提取统计:")
    print(f"  - 实体: {result.entities_extracted}")
    print(f"  - 事件: {result.events_extracted}")
    print(f"  - 时间锚点: {result.temporal_anchors}")
    print(f"  - 情感片段: {result.emotions_detected}")
    print(f"  - 说话风格: {'已提取' if result.style_extracted else '未提取'}")
    
    print(f"\n📝 节点创建: {result.nodes_created}")
    
    if result.errors:
        print("\n⚠️ 错误:")
        for error in result.errors:
            print(f"  - {error}")
    
    if verbose and result.entity_result:
        print("\n🧑 提取的实体:")
        for entity in result.entity_result.entities[:10]:
            print(f"  - [{entity.entity_type.value}] {entity.name}")
    
    if verbose and result.event_result:
        print("\n📅 提取的事件:")
        for event in result.event_result.events[:10]:
            year_str = f"({event.time_expression})" if event.time_expression else ""
            print(f"  - {event.description[:50]}... {year_str}")
    
    if verbose and result.temporal_result:
        print("\n⏰ 时间推理:")
        for anchor in result.temporal_result.temporal_anchors[:5]:
            print(f"  - '{anchor.original_expression}' -> {anchor.best_year_estimate}")
    
    if verbose and result.style_result and result.style_result.style:
        style = result.style_result.style
        print(f"\n🎭 说话风格:")
        print(f"  - 主要语气: {style.primary_tone.value}")
        print(f"  - 叙事风格: {style.narrative_style.value}")
        if style.catch_phrases:
            print(f"  - 口头禅: {', '.join(cp.phrase for cp in style.catch_phrases[:3])}")
    
    print("\n" + "=" * 60)


async def main():
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 获取输入文本
    if args.input:
        if not args.input.exists():
            logger.error(f"文件不存在: {args.input}")
            sys.exit(1)
        text = args.input.read_text(encoding="utf-8")
        logger.info(f"读取文件: {args.input} ({len(text)} 字符)")
    else:
        text = args.text
    
    # 创建管道
    pipeline = ExtractionPipeline(user_birth_year=args.birth_year)
    
    try:
        # 初始化
        logger.info("初始化管道...")
        await pipeline.initialize()
        
        # 处理
        logger.info("开始处理对话...")
        result = await pipeline.process(
            text=text,
            user_id=args.user_id,
            user_birth_year=args.birth_year,
        )
        
        # 打印结果
        print_result(result, verbose=args.verbose)
        
        # 保存结果
        if args.output:
            import json
            from dataclasses import asdict
            
            # 简化结果用于 JSON 序列化
            output_data = {
                "success": result.success,
                "user_id": result.user_id,
                "document_id": result.document_id,
                "entities_extracted": result.entities_extracted,
                "events_extracted": result.events_extracted,
                "temporal_anchors": result.temporal_anchors,
                "emotions_detected": result.emotions_detected,
                "style_extracted": result.style_extracted,
                "nodes_created": result.nodes_created,
                "processing_time_ms": result.processing_time_ms,
                "errors": result.errors,
            }
            
            args.output.write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"结果已保存到: {args.output}")
        
        # 返回状态码
        sys.exit(0 if result.success else 1)
        
    except Exception as e:
        logger.exception(f"处理失败: {e}")
        sys.exit(1)
        
    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
