"""
生成服务 - 协调时间轴和回忆录生成流程
"""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ...infrastructure.database.sqlite_client import SQLiteClient
from ...infrastructure.database import ChunkStore
from .generator.timeline_generator import TimelineGenerator
from .generator.memoir_generator import MemoirGenerator
from ...infrastructure.llm.concurrency_manager import ConcurrencyManager
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class GenerationTimelineService:
    """
    时间轴生成服务
    
    负责协调时间轴的生成流程：
    1. 从数据库提取数据（事件、人物特征、语言样本）
    2. 调用生成器生成内容
    3. 返回生成结果
    
    注：回忆录生成将在单独的类中实现
    """
    
    def __init__(
        self,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Optional[Path] = None,
        verbose: bool = False
    ):
        """
        初始化生成Pipeline
        
        Args:
            username: 用户名
            concurrency_manager: 并发管理器实例
            data_base_dir: 数据存储目录（默认为项目根目录/data）
            verbose: 是否打印详细信息
        """
        self.username = username
        self.verbose = verbose
        self.concurrency_manager = concurrency_manager
        
        # 加载配置
        self.config = get_settings().generation
        
        # 初始化数据库客户端
        self.sqlite_client = SQLiteClient(
            username=username,
            data_base_dir=data_base_dir
        )
        
        self.chunk_store = ChunkStore(
            username=username,
            data_base_dir=data_base_dir
        )
        
        # 初始化生成器
        self.timeline_generator = TimelineGenerator(
            concurrency_manager=concurrency_manager
        )
        
        logger.info(f"GenerationTimelineService初始化完成: 用户={username}")
    
    def _print_step(self, message: str):
        """打印步骤信息"""
        if self.verbose:
            print(f"\n▸ {message}")
    
    def calculate_target_event_count(
        self,
        total_events: int,
        ratio: float
    ) -> int:
        """
        计算目标事件数量
        
        Args:
            total_events: 总事件数
            ratio: 筛选比例（0.0-1.0）
            
        Returns:
            目标数量（10-30之间）
        """
        target = int(total_events * ratio)
        
        # 限制在10-30之间
        if target < 10:
            target = min(10, total_events)  # 如果总数不足10，就用总数
        elif target > 30:
            target = 30
        
        logger.info(f"计算目标数量: 总数={total_events}, 比例={ratio:.2%}, 目标={target}")
        return target
    
    async def generate_timeline(
        self,
        ratio: float = 0.3,
        language_sample_count: Optional[int] = None,
        user_preferences: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        生成时间轴
        
        Args:
            ratio: 事件筛选比例（0.0-1.0，默认0.3即30%）
            language_sample_count: 语言样本数量（None时使用配置默认值）
            user_preferences: 用户自定义偏好（如"更注重情感描述"、"强调职业发展"等）
            
        Returns:
            时间轴条目列表，每个条目包含：
            - event_id: 事件ID
            - time: 时间描述
            - objective_summary: 客观简述
            - detailed_narrative: 详细自述
        """
        # 使用配置默认值
        if language_sample_count is None:
            language_sample_count = self.config.timeline_language_sample_count
        
        self._print_step("开始生成时间轴...")
        
        # 步骤1: 从数据库按时间顺序提取life_events
        self._print_step("1/5: 从数据库提取人生事件...")
        all_events = self.sqlite_client.get_all_events(sort_by_year=True)
        
        if not all_events:
            logger.warning("数据库中没有人生事件，无法生成时间轴")
            if self.verbose:
                print("⚠️  数据库中没有人生事件")
            return []
        
        if self.verbose:
            print(f"   提取到 {len(all_events)} 个人生事件")
        
        # 步骤2: 计算目标筛选数量（10-30之间）
        self._print_step("2/5: 计算筛选目标数量...")
        target_count = self.calculate_target_event_count(len(all_events), ratio)
        
        if self.verbose:
            print(f"   目标筛选数量: {target_count} 个事件")
        
        # 步骤3: AI筛选最有意义的事件
        self._print_step("3/5: AI筛选最有意义的事件...")
        selected_ids = await self.timeline_generator.select_events(
            events=all_events,
            target_count=target_count,
            user_preferences=user_preferences
        )
        
        if not selected_ids:
            logger.warning("事件筛选失败或没有选中任何事件")
            if self.verbose:
                print("⚠️  事件筛选失败")
            return []
        
        if self.verbose:
            print(f"   筛选出 {len(selected_ids)} 个关键事件")
        
        # 提取筛选后的事件详情
        selected_events = [
            event for event in all_events 
            if event['id'] in selected_ids
        ]
        
        # 步骤4: 获取人物特征和语言样本
        self._print_step("4/5: 获取人物特征和语言样本...")
        
        # 获取人物特征
        character_profile = self.sqlite_client.get_character_profile()
        if character_profile:
            if self.verbose:
                personality_len = len(character_profile.get('personality', ''))
                worldview_len = len(character_profile.get('worldview', ''))
                print(f"   人物特征: 性格{personality_len}字, 世界观{worldview_len}字")
        else:
            if self.verbose:
                print("   ⚠️  未找到人物特征信息")
        
        # 随机选取语言样本
        random_chunks = self.chunk_store.get_random_chunks(language_sample_count)
        language_samples = [chunk['chunk_text'] for chunk in random_chunks]
        
        if self.verbose:
            print(f"   语言样本: {len(language_samples)} 个chunks")
        
        # 步骤5: 生成时间轴条目
        self._print_step("5/5: 生成时间轴条目...")
        timeline_entries = await self.timeline_generator.generate_timeline_entries(
            events=selected_events,
            character_profile=character_profile,
            language_samples=language_samples,
            user_preferences=user_preferences
        )
        
        if not timeline_entries:
            logger.warning("时间轴生成失败")
            if self.verbose:
                print("⚠️  时间轴生成失败")
            return []
        
        # 对时间轴进行排序
        sorted_timeline = self.timeline_generator.sort_timeline_entries(
            timeline_entries=timeline_entries,
            events=selected_events
        )
        
        if self.verbose:
            print(f"✅ 时间轴生成完成: {len(sorted_timeline)} 条记录")
        
        logger.info(f"时间轴生成成功: {len(sorted_timeline)} 条记录")
        
        return sorted_timeline
    
    def save_timeline(
        self,
        timeline: List[Dict[str, str]],
        output_dir: Optional[Path] = None
    ) -> tuple[Path, Path]:
        """
        将时间轴保存为文本和JSON两种格式
        
        Args:
            timeline: 时间轴数据
            output_dir: 输出目录（默认为data/{username}/output）
            
        Returns:
            (txt_path, json_path) 两个文件的路径
        """
        import json
        from datetime import datetime
        
        # 确定输出目录
        if output_dir is None:
            output_dir = self.sqlite_client.data_dir / "output"
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存文本格式
        txt_path = output_dir / "timeline.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"个人时间轴 - {self.username}\n")
            f.write("=" * 60 + "\n\n")
            
            for i, entry in enumerate(timeline, 1):
                f.write(f"【{i}】{entry.get('time', '未知时间')}\n")
                f.write(f"\n客观记录：\n{entry.get('objective_summary', '')}\n")
                f.write(f"\n个人回忆：\n{entry.get('detailed_narrative', '')}\n")
                f.write("\n" + "-" * 60 + "\n\n")
        
        # 保存JSON格式
        json_path = output_dir / "timeline.json"
        data = {
            "username": self.username,
            "generated_at": datetime.now().isoformat(),
            "total_entries": len(timeline),
            "timeline": timeline
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"时间轴已保存: TXT={txt_path}, JSON={json_path}")
        if self.verbose:
            print(f"\n💾 时间轴已保存:")
            print(f"   文本格式: {txt_path}")
            print(f"   JSON格式: {json_path}")
        
        return txt_path, json_path
    
    def close(self):
        """关闭数据库连接"""
        self.sqlite_client.close()
        self.chunk_store.close()
        logger.info("GenerationTimelinePipeline已关闭")


class GenerationMemoirService:
    """
    回忆录生成服务
    
    负责协调回忆录的生成流程：
    1. 从数据库提取所有人生事件
    2. 随机选取语言样本
    3. 调用生成器生成回忆录
    4. 保存结果
    """
    
    def __init__(
        self,
        username: str,
        concurrency_manager: ConcurrencyManager,
        data_base_dir: Optional[Path] = None,
        verbose: bool = False
    ):
        """
        初始化回忆录生成Pipeline
        
        Args:
            username: 用户名
            concurrency_manager: 并发管理器实例
            data_base_dir: 数据存储目录（默认为项目根目录/data）
            verbose: 是否打印详细信息
        """
        self.username = username
        self.verbose = verbose
        self.concurrency_manager = concurrency_manager
        
        # 加载配置
        self.config = get_settings().generation
        
        # 初始化数据库客户端
        self.sqlite_client = SQLiteClient(
            username=username,
            data_base_dir=data_base_dir
        )
        
        self.chunk_store = ChunkStore(
            username=username,
            data_base_dir=data_base_dir
        )
        
        # 初始化生成器
        self.memoir_generator = MemoirGenerator(
            concurrency_manager=concurrency_manager
        )
        
        logger.info(f"GenerationMemoirService初始化完成: 用户={username}")
    
    def _print_step(self, message: str):
        """打印步骤信息"""
        if self.verbose:
            print(f"\n▸ {message}")
    
    async def generate_memoir(
        self,
        target_length: int = 2000,
        language_sample_count: Optional[int] = None,
        user_preferences: Optional[str] = None
    ) -> str:
        """
        生成个人回忆录
        
        Args:
            target_length: 目标文本长度（默认2000字，不超过20000字）
            language_sample_count: 语言样本数量（None时使用配置默认值）
            user_preferences: 用户偏好或希望模型的侧重点
            
        Returns:
            回忆录文本（纯文本）
        """
        # 使用配置默认值
        if language_sample_count is None:
            language_sample_count = self.config.memoir_language_sample_count
        
        self._print_step("开始生成回忆录...")
        
        # 限制长度范围
        if target_length > 20000:
            target_length = 20000
            if self.verbose:
                print("   ⚠️  长度超出上限，已调整为20000字")
        elif target_length < 500:
            target_length = 500
            if self.verbose:
                print("   ⚠️  长度过短，已调整为500字")
        
        # 步骤1: 从数据库提取所有人生事件
        self._print_step("1/3: 从数据库提取人生事件...")
        all_events = self.sqlite_client.get_all_events(sort_by_year=True)
        
        if not all_events:
            logger.warning("数据库中没有人生事件，无法生成回忆录")
            if self.verbose:
                print("⚠️  数据库中没有人生事件")
            return ""
        
        if self.verbose:
            print(f"   提取到 {len(all_events)} 个人生事件")
        
        # 步骤2: 随机选取语言样本
        self._print_step("2/3: 随机选取语言样本...")
        random_chunks = self.chunk_store.get_random_chunks(language_sample_count)
        language_samples = [chunk['chunk_text'] for chunk in random_chunks]
        
        if self.verbose:
            print(f"   语言样本: {len(language_samples)} 个chunks")
        
        # 步骤3: 生成回忆录
        self._print_step("3/3: 生成回忆录...")
        if self.verbose:
            print(f"   目标长度: {target_length}字")
            if user_preferences:
                print(f"   用户偏好: {user_preferences}")
        
        memoir_text = await self.memoir_generator.generate_memoir(
            events=all_events,
            language_samples=language_samples,
            target_length=target_length,
            user_preferences=user_preferences
        )
        
        if not memoir_text:
            logger.warning("回忆录生成失败")
            if self.verbose:
                print("⚠️  回忆录生成失败")
            return ""
        
        if self.verbose:
            actual_length = len(memoir_text)
            print(f"✅ 回忆录生成完成: {actual_length}字")
        
        logger.info(f"回忆录生成成功: {len(memoir_text)}字")
        
        return memoir_text
    
    def save_memoir(
        self,
        memoir_text: str,
        output_dir: Optional[Path] = None
    ) -> tuple[Path, Path]:
        """
        将回忆录保存为文本和JSON两种格式
        
        Args:
            memoir_text: 回忆录文本
            output_dir: 输出目录（默认为data/{username}/output）
            
        Returns:
            (txt_path, json_path) 两个文件的路径
        """
        import json
        from datetime import datetime
        
        # 确定输出目录
        if output_dir is None:
            output_dir = self.sqlite_client.data_dir / "output"
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存文本格式
        txt_path = output_dir / "memoir.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"个人回忆录 - {self.username}\n")
            f.write("=" * 60 + "\n\n")
            f.write(memoir_text)
            f.write("\n\n" + "=" * 60 + "\n")
        
        # 保存JSON格式
        json_path = output_dir / "memoir.json"
        data = {
            "username": self.username,
            "generated_at": datetime.now().isoformat(),
            "length": len(memoir_text),
            "content": memoir_text
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"回忆录已保存: TXT={txt_path}, JSON={json_path}")
        if self.verbose:
            print(f"\n💾 回忆录已保存:")
            print(f"   文本格式: {txt_path}")
            print(f"   JSON格式: {json_path}")
        
        return txt_path, json_path
    
    def close(self):
        """关闭数据库连接"""
        self.sqlite_client.close()
        self.chunk_store.close()
        logger.info("GenerationMemoirPipeline已关闭")


# =======================================
# 供外部调用的接口函数
# =======================================

async def generate_timeline(
    username: str,
    ratio: float = 0.3,
    user_preferences: Optional[str] = None,
    auto_save: bool = True,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    生成时间轴
    
    Args:
        username: 用户名
        ratio: 事件筛选比例（0.0-1.0，默认0.3即30%）
        user_preferences: 用户自定义偏好
        auto_save: 是否自动保存到文件
        verbose: 是否打印详细信息
        
    Returns:
        包含时间轴内容和文件路径的字典
    """
    from ...infrastructure.llm.concurrency_manager import get_concurrency_manager
    
    logger.info(f"开始生成时间轴: user={username}, ratio={ratio}")
    
    # 获取并发管理器
    concurrency_manager = get_concurrency_manager()
    
    # 创建服务
    service = GenerationTimelineService(
        username=username,
        concurrency_manager=concurrency_manager,
        data_base_dir=None,  # 使用默认路径
        verbose=verbose
    )
    
    try:
        # 生成时间轴（使用配置的默认语言样本数量）
        timeline = await service.generate_timeline(
            ratio=ratio,
            language_sample_count=None,  # 使用配置默认值
            user_preferences=user_preferences
        )
        
        result = {
            'timeline': timeline,
            'event_count': len(timeline),
            'username': username
        }
        
        # 自动保存
        if auto_save and timeline:
            txt_path, json_path = service.save_timeline(timeline)
            result['txt_path'] = str(txt_path)
            result['json_path'] = str(json_path)
            
            if verbose:
                logger.info(f"时间轴已保存: {len(timeline)} 个事件")
        
        return result
        
    finally:
        service.close()


async def generate_memoir(
    username: str,
    target_length: int = 2000,
    user_preferences: Optional[str] = None,
    auto_save: bool = True,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    生成回忆录
    
    Args:
        username: 用户名
        target_length: 目标长度（字数，默认2000，不超过20000）
        user_preferences: 用户自定义偏好
        auto_save: 是否自动保存到文件
        verbose: 是否打印详细信息
        
    Returns:
        包含回忆录内容和文件路径的字典
    """
    from ...infrastructure.llm.concurrency_manager import get_concurrency_manager
    
    logger.info(f"开始生成回忆录: user={username}, target_length={target_length}")
    
    # 获取并发管理器
    concurrency_manager = get_concurrency_manager()
    
    # 创建服务
    service = GenerationMemoirService(
        username=username,
        concurrency_manager=concurrency_manager,
        data_base_dir=None,  # 使用默认路径
        verbose=verbose
    )
    
    try:
        # 生成回忆录（使用配置的默认语言样本数量）
        memoir_text = await service.generate_memoir(
            target_length=target_length,
            language_sample_count=None,  # 使用配置默认值
            user_preferences=user_preferences
        )
        
        result = {
            'memoir': memoir_text,
            'length': len(memoir_text) if memoir_text else 0,
            'username': username
        }
        
        # 自动保存
        if auto_save and memoir_text:
            txt_path, json_path = service.save_memoir(memoir_text)
            result['txt_path'] = str(txt_path)
            result['json_path'] = str(json_path)
            
            if verbose:
                logger.info(f"回忆录已保存: {len(memoir_text)} 字")
        
        return result
        
    finally:
        service.close()
