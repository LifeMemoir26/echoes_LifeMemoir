"""
Refinement Pipeline
数据库结果优化流程 - 协调三个优化器完成完整的优化工作
"""
import logging
from typing import Dict, Any
from ....infrastructure.database.sqlite_client import SQLiteClient
from .refiner.event_refiner import EventRefiner
from .refiner.uncertain_event_refiner import UncertainEventRefiner
from .refiner.event_details_refiner import EventDetailsRefiner
from .refiner.character_profile_refiner import CharacterProfileRefiner
from ....infrastructure.llm.concurrency_manager import ConcurrencyManager

logger = logging.getLogger(__name__)


class RefinementPipeline:
    """数据库结果优化流程"""
    
    def __init__(self, db_client: SQLiteClient, concurrency_manager: ConcurrencyManager):
        """
        初始化
        
        Args:
            db_client: 数据库客户端
            concurrency_manager: 全局并发管理器
        """
        self.db_client = db_client
        self.event_refiner = EventRefiner(concurrency_manager)
        self.uncertain_refiner = UncertainEventRefiner(concurrency_manager)
        self.details_refiner = EventDetailsRefiner(concurrency_manager)
        self.profile_refiner = CharacterProfileRefiner(concurrency_manager)
        
    async def refine_all(self) -> Dict[str, Any]:
        """
        执行完整的优化流程
        
        Returns:
            优化统计信息
        """
        logger.info("=" * 60)
        logger.info("开始数据库结果优化流程")
        logger.info("=" * 60)
        
        stats = {
            "events_before": 0,
            "events_after": 0,
            "events_precise_before": 0,
            "events_precise_after": 0,
            "events_uncertain_before": 0,
            "events_uncertain_after": 0,
            "events_year_inferred": 0,
            "profile_refined": False
        }
        
        # 三个打包任务并发执行
        async def refine_events_task():
            """打包1：事件优化流程（顺序执行）"""
            # 步骤1：优化精准年份事件
            logger.info("\n[1] 步骤1：优化精准年份事件")
            logger.info("-" * 60)
            refined_precise_events = await self._refine_precise_events(stats)
            
            # 步骤2：优化不确定年份事件
            logger.info("\n[1] 步骤2：优化不确定年份事件（基于步骤1的上下文）")
            logger.info("-" * 60)
            refined_uncertain_events = await self._refine_uncertain_events(
                refined_precise_events, stats
            )
            
            # 步骤3：覆写所有事件到数据库
            logger.info("\n[1] 步骤3：写回优化后的事件到数据库")
            logger.info("-" * 60)
            await self._write_events(refined_precise_events, refined_uncertain_events, stats)
        
        async def refine_profile_task():
            """打包2：优化人物档案"""
            logger.info("\n[2] 优化人物档案")
            logger.info("-" * 60)
            await self._refine_profile(stats)
        
        async def refine_aliases_task():
            """打包3：优化别名关联"""
            logger.info("\n[3] 优化别名关联")
            logger.info("-" * 60)
            await self._refine_aliases(stats)
        
        # 并发执行三个打包任务
        import asyncio
        try:
            results = await asyncio.gather(
                refine_events_task(),
                refine_profile_task(),
                refine_aliases_task(),
                return_exceptions=True
            )
            
            # 检查是否有异常
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    task_names = ["事件优化", "人物档案优化", "别名优化"]
                    logger.error(f"{task_names[i]}任务失败: {result}")
                    raise result
                    
        except Exception as e:
            logger.error(f"优化流程异常: {e}")
            raise
        
        # 输出统计
        logger.info("\n" + "=" * 60)
        logger.info("优化流程完成！")
        logger.info("=" * 60)
        logger.info(f"事件总数：{stats['events_before']} → {stats['events_after']}")
        logger.info(f"精准年份事件：{stats['events_precise_before']} → {stats['events_precise_after']}")
        logger.info(f"不确定年份事件：{stats['events_uncertain_before']} → {stats['events_uncertain_after']}")
        logger.info(f"推测出年份的事件：{stats['events_year_inferred']}")
        logger.info(f"人物档案已优化：{stats['profile_refined']}")
        
        return stats
        
    async def _refine_precise_events(self, stats: Dict[str, Any]) -> list:
        """优化精准年份事件（结果1）"""
        # 从数据库读取精准年份事件
        all_events = self.db_client.get_all_events()
        precise_events = [e for e in all_events if e.get("year") != "9999"]
        
        stats["events_precise_before"] = len(precise_events)
        
        if not precise_events:
            logger.warning("数据库中没有精准年份事件")
            return []
            
        logger.info(f"从数据库读取 {len(precise_events)} 条精准年份事件")
        
        # 调用优化器
        refined = await self.event_refiner.refine_events(precise_events)
        
        stats["events_precise_after"] = len(refined)
        
        return refined
        
    async def _refine_uncertain_events(
        self, 
        context_events: list, 
        stats: Dict[str, Any]
    ) -> list:
        """优化不确定年份事件（基于结果1'的上下文）"""
        # 从数据库读取不确定年份事件
        all_events = self.db_client.get_all_events()
        uncertain_events = [e for e in all_events if e.get("year") == "9999"]
        
        stats["events_uncertain_before"] = len(uncertain_events)
        stats["events_before"] = len(all_events)
        
        if not uncertain_events:
            logger.warning("数据库中没有不确定年份事件")
            return context_events  # 只返回结果1'
            
        logger.info(f"从数据库读取 {len(uncertain_events)} 条不确定年份事件")
        
        # 调用优化器（使用精准事件作为上下文）
        refined = await self.uncertain_refiner.refine_uncertain_events(
            uncertain_events, context_events
        )
        
        # 统计推测出年份的数量
        inferred = sum(1 for e in refined if e.get("year") != "9999")
        stats["events_year_inferred"] = inferred
        stats["events_uncertain_after"] = len(refined) - inferred
        
        return refined
        
    async def _write_events(
        self, 
        precise_events: list, 
        uncertain_events: list,
        stats: Dict[str, Any]
    ):
        """清空并写回优化后的所有事件（只写入结果2）"""
        # 结果2 = 结果1' + 推测后的不确定事件
        # uncertain_events 已经包含了所有需要的事件（因为 uncertain_refiner 会合并 context_events）
        all_refined_events = uncertain_events  # 只使用结果2
        
        # 统计精准年份事件数量（结果2中的非9999事件）
        stats["events_precise_after"] = sum(1 for e in all_refined_events if e.get("year") != "9999")
        stats["events_after"] = len(all_refined_events)
        
        logger.info(f"准备写回 {len(all_refined_events)} 条优化后的事件（结果2）")
        
        # 在写入前，统一处理 event_details 拼接和 is_merged 设置
        logger.info("开始处理 event_details 拼接和 is_merged 标记...")
        
        # 从数据库读取所有原始事件的 id -> event_details 映射
        all_original_events = self.db_client.get_all_events()
        id_to_details = {e.get('id'): e.get('event_details', '') for e in all_original_events}
        
        for event in all_refined_events:
            merged_ids = event.get('merged_from_ids', [])
            
            # 拼接 event_details
            details_parts = []
            for event_id in merged_ids:
                detail = id_to_details.get(event_id, '')
                if detail:
                    details_parts.append(detail)
            
            event['event_details'] = '\n---\n'.join(details_parts) if details_parts else ''
            
            # 设置 is_merged
            event['is_merged'] = len(merged_ids) > 1
        
        merged_count = sum(1 for e in all_refined_events if e.get('is_merged'))
        logger.info(f"完成拼接：共 {merged_count} 条合并事件")
        
        # 对合并事件的 event_details 进行AI总结
        if merged_count > 0:
            logger.info(f"开始对 {merged_count} 条合并事件的event_details进行AI总结...")
            all_refined_events = await self.details_refiner.refine_merged_event_details(
                all_refined_events
            )
            logger.info("event_details总结完成")
        
        # 清空原有事件
        self.db_client.clear_events()
        logger.info("已清空数据库中的原有事件")
        
        # 批量写入
        if all_refined_events:
            self.db_client.insert_events(all_refined_events)
            logger.info(f"已写入 {len(all_refined_events)} 条优化后的事件")
        else:
            logger.warning("没有事件需要写入")
            
    async def _refine_profile(self, stats: Dict[str, Any]):
        """优化人物档案（结果2）"""
        # 从数据库读取档案
        profile = self.db_client.get_character_profile()
        
        if not profile:
            logger.warning("数据库中没有人物档案")
            stats["profile_refined"] = False
            return
            
        logger.info("从数据库读取人物档案")
        
        # 调用优化器
        refined_profile = await self.profile_refiner.refine_profile(profile)
        
        # 写回数据库
        self.db_client.clear_character_profile()
        self.db_client.insert_character_profile(refined_profile)
        
        logger.info("人物档案已优化并写回数据库")
        stats["profile_refined"] = True
    
    async def _refine_aliases(self, stats: Dict[str, Any]):
        """优化别名关联"""
        # 从数据库读取所有别名
        aliases = self.db_client.get_all_aliases()
        
        if not aliases:
            logger.warning("数据库中没有别名记录")
            stats["aliases_refined"] = False
            return
        
        logger.info(f"从数据库读取 {len(aliases)} 条别名记录")
        
        # 调用优化器
        refined_aliases = await self.profile_refiner._refine_aliases(aliases)
        
        # 写回数据库
        self.db_client.clear_aliases()
        logger.info("已清空数据库中的原有别名")
        
        for alias_item in refined_aliases:
            self.db_client.insert_or_update_alias(
                main_name=alias_item['formal_name'],
                alias_names=alias_item['alias_list'],
                entity_type=alias_item['type']
            )
        
        logger.info(f"别名已优化并写回数据库: {len(aliases)} → {len(refined_aliases)} 条")
        stats["aliases_refined"] = True
        stats["aliases_before"] = len(aliases)
        stats["aliases_after"] = len(refined_aliases)
