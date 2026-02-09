"""
测试采访辅助服务的便捷API
演示背景信息存储和轮询机制
"""
import asyncio
import logging
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.interview import (
    create_interview_session,
    add_dialogue,
    get_interview_info,
    flush_session_buffer,
    reset_interview_session,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """测试采访服务的便捷API"""
    print("=" * 80)
    print("采访辅助服务测试 - 背景信息存储和轮询机制")
    print("=" * 80)
    
    # 创建服务实例（使用便捷函数，自动处理所有配置）
    username = "特朗普"
    
    print(f"\n📝 步骤1: 创建采访服务实例（用户: {username}）")
    service = await create_interview_session(username, verbose=True)
    print("✅ 服务创建完成，待探索事件已自动初始化")
    
    # 查看待探索事件
    pending_summary = await service.get_pending_events_summary()
    print(f"\n📋 待探索事件统计:")
    print(f"   总数: {pending_summary['total']}")
    print(f"   优先事件: {pending_summary['priority_count']}")
    print(f"   未探索: {pending_summary['unexplored_count']}")
    
    if pending_summary['events']:
        print(f"\n   前3个待探索事件:")
        for i, event in enumerate(pending_summary['events'][:3], 1):
            priority_mark = "【优先】" if event['is_priority'] else ""
            print(f"   {i}. {priority_mark}{event['summary']}")
            print(f"      已探索: {event['explored_length']} 字")
    
    # 模拟添加对话
    print(f"\n\n💬 步骤2: 添加对话（模拟采访）")
    print("=" * 80)
    
    # 添加一些对话
    dialogues = [
        ("志愿者", "您好，今天我们来聊聊您的童年好吗？"),
        ("特朗普", "好啊，我的童年在皇后区度过..."),
        ("志愿者", "能详细说说您和父亲的关系吗？"),
        ("特朗普", "我父亲Fred Trump是一个非常成功的房地产开发商，从小他就教我做生意的道理..."),
        ("志愿者", "您印象最深的一件事是什么？"),
        ("特朗普", "我记得有一次跟着父亲去工地，看到工人们在建造公寓楼，那时我才10岁..."),
    ]
    
    for speaker, content in dialogues:
        await add_dialogue(service, speaker, content)
        print(f"   [{speaker}] {content[:40]}...")
    
    print(f"\n✅ 已添加 {len(dialogues)} 轮对话")
    
    # 手动刷新缓冲区（触发背景信息生成）
    print(f"\n\n🔄 步骤3: 手动刷新缓冲区（触发背景信息生成）")
    print("=" * 80)
    await flush_session_buffer(service)
    print("✅ 缓冲区已刷新，背景信息已更新")
    
    # 轮询获取背景信息
    print(f"\n\n📊 步骤4: 轮询获取背景信息（异步存储优化）")
    print("=" * 80)
    print("   💡 优化说明：AI1(事件补充)和AI2(采访建议)谁先完成谁先存储")
    print("   💡 前端可以更快获取到部分最新信息，而不必等待全部完成")
    
    # 方法1: 获取完整背景信息
    background_info = service.get_background_info()
    
    print(f"\n📌 背景信息概览:")
    print(f"   事件补充: {background_info['meta']['supplement_count']} 条")
    print(f"   正面触发点: {background_info['meta']['positive_trigger_count']} 条")
    print(f"   敏感话题: {background_info['meta']['sensitive_topic_count']} 条")
    
    # 事件补充
    if background_info['event_supplements']:
        print(f"\n📝 事件补充信息:")
        for i, supplement in enumerate(background_info['event_supplements'][:2], 1):
            print(f"\n   [{i}] {supplement['event_summary']}")
            print(f"       {supplement['event_details'][:100]}...")
    
    # 正面触发点
    if background_info['positive_triggers']:
        print(f"\n😊 正面触发点:")
        for i, trigger in enumerate(background_info['positive_triggers'][:3], 1):
            print(f"   {i}. {trigger}")
    
    # 敏感话题
    if background_info['sensitive_topics']:
        print(f"\n⚠️  敏感话题:")
        for i, topic in enumerate(background_info['sensitive_topics'][:3], 1):
            print(f"   {i}. {topic}")
    
    # 方法2: 单独获取各部分
    print(f"\n\n📌 步骤5: 单独获取背景信息各部分")
    print("=" * 80)
    
    event_supplements = service.get_event_supplements()
    print(f"   事件补充信息数量: {len(event_supplements)}")
    
    interview_suggestions = service.get_interview_suggestions()
    print(f"   正面触发点数量: {len(interview_suggestions.positive_triggers)}")
    print(f"   敏感话题数量: {len(interview_suggestions.sensitive_topics)}")
    
    # 方法3: 获取完整的采访信息（新增API）
    print(f"\n\n📌 步骤6: 获取完整的采访信息（all-in-one API）")
    print("=" * 80)
    
    interview_info = await service.get_interview_info()
    
    print(f"\n📊 采访信息总览:")
    print(f"   事件补充: {interview_info['meta']['total_supplements']} 条")
    print(f"   正面触发点: {interview_info['meta']['total_positive_triggers']} 条")
    print(f"   敏感话题: {interview_info['meta']['total_sensitive_topics']} 条")
    print(f"   待探索事件: {interview_info['meta']['total_pending_events']} 个")
    print(f"   优先事件: {interview_info['meta']['priority_pending_events']} 个")
    print(f"   未探索事件: {interview_info['meta']['unexplored_pending_events']} 个")
    print(f"   会话总结: {interview_info['meta']['total_summaries']} 条")
    
    # 查看会话总结
    print(f"\n\n📝 步骤8: 查看会话总结")
    print("=" * 80)
    summaries = await service.get_session_summaries()
    if summaries:
        print(f"   共 {len(summaries)} 条总结:")
        for i, summary in enumerate(summaries[:5], 1):
            print(f"   {i}. {summary}")
    
    # 重置会话
    print(f"\n\n🔄 步骤9: 重置会话（清空所有数据）")
    print("=" * 80)
    await service.reset_session()
    print("✅ 会话已重置")
    
    # 验证清空
    background_after_reset = service.get_background_info()
    print(f"\n   重置后的背景信息:")
    print(f"   事件补充: {background_after_reset['meta']['supplement_count']} 条")
    print(f"   正面触发点: {background_after_reset['meta']['positive_trigger_count']} 条")
    print(f"   敏感话题: {background_after_reset['meta']['sensitive_topic_count']} 条")
    
    print(f"\n\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
