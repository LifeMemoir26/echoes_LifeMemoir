"""
待探索事件管理器
管理采访中需要深入探索的事件列表
"""
import asyncio
from typing import List, Optional, Dict, TYPE_CHECKING
import logging

from ....domain.schemas.interview import PendingEvent

if TYPE_CHECKING:
    from ....domain.schemas.interview import PendingEventCandidate

logger = logging.getLogger(__name__)

# 批量更新的位标志常量
UPDATE_PRIORITY = 0x0001    # 更新 is_priority
UPDATE_EXPLORED = 0x0002    # 更新 explored_content
UPDATE_SUMMARY = 0x0004     # 更新 summary


class PendingEventManager:
    """
    待探索事件管理器
    
    管理需要深入探索的事件列表：
    - 异步操作支持
    - 线程安全（asyncio.Lock）
    - 支持优先级管理
    - 支持探索进度跟踪
    """
    
    def __init__(self):
        """初始化待探索事件管理器"""
        self._events: List[PendingEvent] = []
        self._lock = asyncio.Lock()
        self._id_counter = 0
        
        logger.info("PendingEventManager initialized")
    
    async def add(
        self, 
        summary: str, 
        explored_content: str = "", 
        is_priority: bool = False
    ) -> str:
        """
        添加一个待探索事件
        
        Args:
            summary: 事件摘要
            explored_content: 已探索的内容
            is_priority: 是否优先
        
        Returns:
            事件ID
        """
        async with self._lock:
            self._id_counter += 1
            event_id = f"event_{self._id_counter}"
            event = PendingEvent(
                id=event_id,
                summary=summary,
                explored_content=explored_content,
                is_priority=is_priority
            )
            self._events.append(event)
            logger.debug(f"Added pending event: {event}")
            return event_id
    
    async def add_batch(self, events: List["PendingEventCandidate"]) -> List[str]:
        """
        批量添加待探索事件
        
        Args:
            events: PendingEventCandidate 对象列表
        
        Returns:
            事件ID列表
        """
        async with self._lock:
            event_ids = []
            for event in events:
                self._id_counter += 1
                event_id = f"event_{self._id_counter}"
                pending_event = PendingEvent(
                    id=event_id,
                    summary=event.summary,
                    explored_content="",  # 初始化时还未探索
                    is_priority=event.is_priority
                )
                self._events.append(pending_event)
                event_ids.append(event_id)
                logger.debug(f"Added pending event: {pending_event}")
            
            logger.info(f"Batch added {len(event_ids)} pending events")
            return event_ids
    
    async def get(self, event_id: str) -> Optional[PendingEvent]:
        """
        获取指定ID的事件
        
        Args:
            event_id: 事件ID
        
        Returns:
            事件对象，如果不存在则返回None
        """
        async with self._lock:
            for event in self._events:
                if event.id == event_id:
                    return event
            return None
    
    async def get_batch(self, event_ids: List[str]) -> Dict[str, Optional[PendingEvent]]:
        """
        批量获取事件（优化的并发友好方法）
        
        Args:
            event_ids: 事件ID列表
        
        Returns:
            事件ID到事件对象的映射字典 {event_id: PendingEvent or None}
        """
        async with self._lock:
            # 创建映射提高查找效率
            event_map = {event.id: event for event in self._events}
            # 返回所有请求的事件（存在的返回对象，不存在的返回 None）
            result = {eid: event_map.get(eid) for eid in event_ids}
            logger.debug(f"Batch get {len(result)} events, {sum(1 for v in result.values() if v is not None)} found")
            return result
    
    async def get_all(self) -> List[PendingEvent]:
        """
        获取所有待探索事件
        
        Returns:
            事件列表的副本
        """
        async with self._lock:
            return self._events.copy()
    
    async def get_priority_events(self, if_non_priority: bool = False) -> List[PendingEvent]:
        """
        获取优先或非优先事件
        
        Args:
            if_non_priority: 是否返回非优先事件（默认False，返回优先事件；True时返回非优先事件）
        
        Returns:
            事件列表（根据 if_non_priority 参数返回优先或非优先事件）
        """
        async with self._lock:
            if if_non_priority:
                return [e for e in self._events if not e.is_priority]
            else:
                return [e for e in self._events if e.is_priority]
    
    async def get_unexplored_events(self) -> List[PendingEvent]:
        """
        获取所有未探索的事件
        
        Returns:
            未探索事件列表
        """
        async with self._lock:
            return [e for e in self._events if e.is_unexplored]
    
    async def update(
        self, 
        event_id: str, 
        summary: Optional[str] = None,
        explored_content: Optional[str] = None,
        is_priority: Optional[bool] = None
    ) -> bool:
        """
        更新事件信息
        
        Args:
            event_id: 事件ID
            summary: 新的摘要（可选）
            explored_content: 新的已探索内容（可选）
            is_priority: 新的优先级状态（可选）
        
        Returns:
            是否更新成功
        """
        async with self._lock:
            for event in self._events:
                if event.id == event_id:
                    if summary is not None:
                        event.summary = summary
                    if explored_content is not None:
                        event.explored_content = explored_content
                    if is_priority is not None:
                        event.is_priority = is_priority
                    logger.debug(f"Updated event {event_id}: {event}")
                    return True
            logger.warning(f"Event {event_id} not found")
            return False
    
    async def update_batch(
        self,
        updates: List[dict],
        fields: int
    ) -> int:
        """
        批量更新事件
        
        Args:
            updates: 更新数据列表，每项包含 id 和要更新的字段
                    例如：[{"id": "event_1", "is_priority": True}, ...]
            fields: 位标志，指示要更新的字段
                   0x0001 (UPDATE_PRIORITY) - 更新 is_priority
                   0x0002 (UPDATE_EXPLORED) - 更新 explored_content
                   0x0004 (UPDATE_SUMMARY) - 更新 summary
                   可组合使用，如 0x0003 表示同时更新 is_priority 和 explored_content
        
        Returns:
            成功更新的事件数量
        
        示例：
            # 只更新优先级
            await manager.update_batch(
                [{"id": "event_1", "is_priority": True}],
                UPDATE_PRIORITY
            )
            
            # 同时更新优先级和探索内容
            await manager.update_batch(
                [{"id": "event_1", "is_priority": True, "explored_content": "已探索"}],
                UPDATE_PRIORITY | UPDATE_EXPLORED
            )
        """
        async with self._lock:
            # 创建 id 到事件的映射，提高查找效率
            event_map = {event.id: event for event in self._events}
            
            updated_count = 0
            for update_data in updates:
                event_id = update_data.get("id")
                if not event_id:
                    logger.warning("Update data missing 'id' field")
                    continue
                
                event = event_map.get(event_id)
                if not event:
                    logger.warning(f"Event {event_id} not found")
                    continue
                
                # 根据位标志更新对应字段
                if fields & UPDATE_PRIORITY and "is_priority" in update_data:
                    event.is_priority = update_data["is_priority"]
                
                if fields & UPDATE_EXPLORED and "explored_content" in update_data:
                    event.explored_content = update_data["explored_content"]
                
                if fields & UPDATE_SUMMARY and "summary" in update_data:
                    event.summary = update_data["summary"]
                
                updated_count += 1
                logger.debug(f"Updated event {event_id}: {event}")
            
            logger.info(f"Batch updated {updated_count}/{len(updates)} pending events")
            return updated_count
    
    async def reorder(self) -> None:
        """
        重新排序待探索事件列表
        
        排序规则：
        1. 优先级高的（is_priority=True）排在前面
        2. 在同一优先级内，探索内容字数少的排在前面（未探索的最前）
        
        这样可以确保：
        - 优先事件始终在前
        - 未探索的事件优先被探索
        - 已探索较少的事件排在已探索较多的前面
        """
        async with self._lock:
            self._events.sort(key=lambda e: e.order_key())
            logger.debug(f"Reordered {len(self._events)} pending events")
    
    async def remove(self, event_id: str) -> bool:
        """
        删除指定事件
        
        Args:
            event_id: 事件ID
        
        Returns:
            是否删除成功
        """
        async with self._lock:
            for i, event in enumerate(self._events):
                if event.id == event_id:
                    self._events.pop(i)
                    logger.info(f"Removed event {event_id}")
                    return True
            logger.warning(f"Event {event_id} not found")
            return False
    
    async def clear(self):
        """清空所有待探索事件"""
        async with self._lock:
            self._events.clear()
            logger.info("Cleared all pending events")
    
    async def count(self) -> int:
        """
        获取事件数量
        
        Returns:
            事件数量
        """
        async with self._lock:
            return len(self._events)
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"PendingEventManager(count={len(self._events)})"


# okk！