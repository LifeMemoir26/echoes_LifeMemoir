"""
测试回忆录生成功能
"""
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.generate import generate_memoir

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    print("=" * 60)
    print("回忆录生成测试")
    print("=" * 60)
    
    # 用户名（使用现有数据）
    username = "特朗普"  # 使用现有的测试数据
    
    # 用户输入目标长度
    print("\n请输入回忆录目标长度（字数，默认2000，不超过20000）：")
    try:
        length_input = input("长度: ").strip()
        if length_input:
            target_length = int(length_input)
        else:
            target_length = 2000
            print("使用默认长度: 2000字")
    except (ValueError, EOFError):
        target_length = 2000
        print("使用默认长度: 2000字")
    
    # 用户输入生成偏好
    print("\n请输入您的偏好或希望模型的侧重点（可选，直接回车跳过）：")
    print("例如：注重情感细节、强调成长历程、突出重要决策等")
    try:
        user_preferences = input("偏好: ").strip()
        if not user_preferences:
            user_preferences = None
            print("使用默认生成方式")
    except EOFError:
        user_preferences = None
        print("使用默认生成方式")
    
    try:
        # 使用便捷函数生成回忆录
        result = await generate_memoir(
            username=username,
            target_length=target_length,
            user_preferences=user_preferences,
            auto_save=True,
            verbose=True
        )
        
        if result and result.get('memoir'):
            memoir = result['memoir']
            print(f"\n{'='*60}")
            print("回忆录预览（前500字）")
            print('='*60)
            print(memoir[:500])
            if len(memoir) > 500:
                print(f"\n...（共{len(memoir)}字，仅显示前500字）\n")
            
            # 显示文件路径
            print(f"\n💾 文件已保存:")
            print(f"   文本格式: {result.get('txt_path')}")
            print(f"   JSON格式: {result.get('json_path')}")
        else:
            print("\n❌ 回忆录生成失败")
        
    except Exception as e:
        logger.error(f"回忆录生成失败: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())
