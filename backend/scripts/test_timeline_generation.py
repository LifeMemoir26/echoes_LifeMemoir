"""
测试时间轴生成功能
"""
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.generate import generate_timeline

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    print("=" * 60)
    print("时间轴生成测试")
    print("=" * 60)
    
    # 用户名（使用现有数据）
    username = "特朗普"  # 使用现有的测试数据
    
    # 用户输入筛选比例
    print("\n请输入事件筛选比例（0.1-1.0，例如0.3表示筛选30%的事件）：")
    try:
        ratio_input = input("比例: ").strip()
        ratio = float(ratio_input)
        if ratio < 0.1 or ratio > 1.0:
            print("⚠️  比例超出范围，使用默认值0.3")
            ratio = 0.3
    except (ValueError, EOFError):
        print("⚠️  输入无效，使用默认值0.3")
        ratio = 0.3
    
    # 用户输入生成偏好
    print("\n请输入您的生成偏好（可选，直接回车跳过）：")
    print("例如：更注重情感描述、强调职业发展、突出家庭关系等")
    try:
        user_preferences = input("偏好: ").strip()
        if not user_preferences:
            user_preferences = None
            print("使用默认生成方式")
    except EOFError:
        user_preferences = None
        print("使用默认生成方式")
    
    try:
        # 使用便捷函数生成时间轴
        result = await generate_timeline(
            username=username,
            ratio=ratio,
            user_preferences=user_preferences,
            auto_save=True,
            verbose=True
        )
        
        if result and result.get('timeline'):
            timeline = result['timeline']
            print(f"\n{'='*60}")
            print("时间轴预览")
            print('='*60)
            
            # 显示前3条
            for i, entry in enumerate(timeline[:3], 1):
                print(f"\n【{i}】{entry.get('time', '未知时间')}")
                print(f"\n客观记录：")
                print(f"{entry.get('objective_summary', '')}")
                print(f"\n个人回忆：")
                print(f"{entry.get('detailed_narrative', '')}")
                print("\n" + "-"*60)
            
            if len(timeline) > 3:
                print(f"\n...（共{len(timeline)}条记录，仅显示前3条）\n")
            
            # 显示文件路径
            print(f"\n💾 文件已保存:")
            print(f"   文本格式: {result.get('txt_path')}")
            print(f"   JSON格式: {result.get('json_path')}")
        else:
            print("\n❌ 时间轴生成失败")
        
    except Exception as e:
        logger.error(f"时间轴生成失败: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())
