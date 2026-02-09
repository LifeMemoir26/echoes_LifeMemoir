"""
待探索事件初始化器
负责在采访开始前初始化待探索事件列表
"""
import logging
from typing import List
import random

from ....infrastructure.llm.concurrency_manager import ConcurrencyManager
from ....infrastructure.database import SQLiteClient, VectorStore, ChunkStore
from ....core.config import InterviewAssistanceConfig, get_settings
from ....domain.schemas.interview import PendingEventCandidate

logger = logging.getLogger(__name__)


class PendingEventInitializer:
    """
    待探索事件初始化器
    
    负责：
    1. 从life_events中提取低相似度事件，并通过AI分析产生有意义的探索方向
    2. 从chunks中通过AI分析提取稀有但重要的事件
    3. 两个过程并发执行，结果随机交错合并
    """
    
    def __init__(
        self,
        concurrency_manager: ConcurrencyManager,
        sqlite_client: SQLiteClient,
        vector_store: VectorStore,
        config: InterviewAssistanceConfig = None
    ):
        """
        初始化待探索事件初始化器
        
        Args:
            concurrency_manager: 并发管理器
            sqlite_client: SQLite客户端
            vector_store: 向量存储
            config: 采访辅助配置
        """
        self.concurrency_manager = concurrency_manager
        self.sqlite_client = sqlite_client
        self.vector_store = vector_store
        
        # 初始化 ChunkStore（用于快速获取摘要）
        self.chunk_store = ChunkStore(
            username=sqlite_client.username,
            data_base_dir=sqlite_client.data_dir.parent
        )
        
        if config is None:
            config = get_settings().interview
        self.config = config
        
        logger.info("PendingEventInitializer initialized")
    
    async def initialize_pending_events(self) -> List[PendingEventCandidate]:
        """
        初始化待探索事件列表
        
        工作流程：
        1. 并发执行：从life_events提取低相似度事件 + 从chunks让AI分析提取事件
        2. 将两个来源的结果随机交错合并
        
        Returns:
            待探索事件候选列表（随机交错）
        """
        logger.info("开始初始化待探索事件列表")
        
        # 并发执行两个提取任务
        import asyncio
        db_events, chunk_events = await asyncio.gather(
            self._extract_from_database(),
            self._extract_from_chunks()
        )
        
        logger.info(f"从数据库提取了 {len(db_events)} 个事件")
        logger.info(f"从chunks提取了 {len(chunk_events)} 个事件")
        
        # 将两个来源的结果随机交错合并
        all_candidates = db_events + chunk_events[:self.config.pending_event - len(db_events)] 
        
        if not all_candidates:
            logger.warning("没有提取到任何待探索事件")
            return []
        
        # 随机打乱，让两个来源的事件交错
        random.shuffle(all_candidates)
        
        logger.info(f"初始化完成，共 {len(all_candidates)} 个待探索事件（已随机交错）")
        
        return all_candidates[:]
    
    async def _extract_from_database(self) -> List[PendingEventCandidate]:
        """
        从life_events数据库中提取了解较少的事件，并通过AI分析提取有意义的探索方向
        
        策略：
        1. 获取所有life_events
        2. 对每个事件的摘要进行向量编码
        3. 计算与chunks的相似度（低相似度说明了解较少）
        4. 将低相似度事件的摘要、细节和相似度交给AI
        5. AI分析提取有意义的、值得追问的探索方向
        
        Returns:
            从数据库提取的事件候选列表
        """
        logger.info("从数据库提取低相似度事件")
        
        try:
            # 获取所有life_events
            all_events = self.sqlite_client.get_all_events()
            
            if not all_events:
                logger.warning("数据库中没有life_events")
                return []
            
            logger.info(f"数据库中共有 {len(all_events)} 个事件")
            
            # 提取事件摘要
            event_summaries = [event.get('event_summary', '') for event in all_events]
            event_summaries = [s for s in event_summaries if s]  # 过滤空摘要
            
            if not event_summaries:
                logger.warning("数据库中的事件没有摘要")
                return []
            
            # 创建摘要到事件的映射（用于后续获取详细信息）
            summary_to_event = {
                event.get('event_summary', ''): event 
                for event in all_events 
                if event.get('event_summary', '')
            }
            
            # 使用 query_relevant_chunks 批量查询所有事件与chunks的相似度
            logger.info(f"批量计算 {len(event_summaries)} 个事件与chunks的相似度")
            
            # 查询每个事件最相似的chunk（用于获取相似度分数）
            matched_chunks = self.vector_store.query_relevant_chunks(
                summaries=event_summaries,
                top_k_per_summary=1,
                similarity_threshold=self.config.event_extraction_similarity_threshold,
                return_dissimilar=False  # 获取最相似的chunk
            )
            
            # 按相似度排序（从低到高，了解较少的排在前面）
            matched_chunks.sort(key=lambda x: x["similarity"])
            
            # 取前N个相似度最低的事件
            target_count = min(self.config.pending_event_from_db, len(matched_chunks))
            low_similarity_chunks = matched_chunks[:target_count]
            
            logger.info(
                f"选取相似度最低的 {len(low_similarity_chunks)} 个事件作为候选"
            )
            
            # 构建候选事件信息列表（包含摘要、细节、相似度）
            candidate_info_list = []
            for chunk in low_similarity_chunks:
                query_summary = chunk["query_summary"]
                similarity = chunk["similarity"]
                
                # 从映射中获取完整事件信息
                event = summary_to_event.get(query_summary)
                if event:
                    event_details = event.get('event_details', '无详细描述')
                    candidate_info_list.append({
                        "summary": query_summary,
                        "details": event_details,
                        "similarity": similarity
                    })
                else:
                    logger.warning(f"无法找到摘要对应的事件: {query_summary[:50]}...")
            
            if not candidate_info_list:
                logger.warning("没有找到有效的低相似度事件")
                return []
            
            # 将候选事件信息交给AI分析
            logger.info(f"将 {len(candidate_info_list)} 个低相似度事件交给AI分析")
            
            # 构建事件信息文本
            events_text = []
            for i, info in enumerate(candidate_info_list, 1):
                events_text.append(
                    f"{i}. 【摘要】{info['summary']}\n"
                    f"   【细节】{info['details']}\n"
                    f"   【相似度】{info['similarity']:.3f}（越低说明了解越少）"
                )
            events_str = "\n\n".join(events_text)
            
            # 构建系统提示词
            system_prompt = """【extract_from_database_events】

你是一个专业的采访策划专家和心理学分析师。
你的任务是分析数据库中低相似度的事件（相似度低说明现有采访中了解较少），提取出有意义的、值得继续追问的探索方向。

**三大核心要求（务必严格遵守）**：
1. 🎯 **有意义**：必须对理解人格形成、价值观、世界观有重要影响，能填补关键认知空白
2. 📝 **可独立理解**：必须完整清晰，包含足够上下文，采访者无需解释就能明白
3. 🔍 **明确询问方向**：必须精准指出探索的具体方面、时间、重点，不能模糊宽泛

**核心目标：从了解较少的事件中提取有价值的采访方向**
- 这些事件相似度低，说明现有采访中提及少、了解不足
- 但并非所有了解少的事件都值得深入探索
- 你需要判断：哪些方面虽然了解少，但对理解这个人很重要、很有意义

**分析要求**：
1. **有意义性（最高优先级）**：
   - 必须是对理解人格形成、价值观、世界观有重要影响的方面
   - 必须能够填补重要认知空白，对完整理解人生故事有显著价值
   - 不能是琐碎的、无关紧要的细节
   - ❌ 避免：日常琐事、流水账、无意义的小事件
   - ✅ 选择：关键转折、重大影响、人格塑造、价值观形成
   
2. **可独立理解性（严格要求）**：
   - 每个探索方向必须**完整、清晰、自包含**，脱离原事件也能理解
   - 必须包含时间、背景、具体方面等关键上下文
   - 采访者看到后无需询问"这是指什么"就能直接明白
   - ❌ 避免："某个决定"、"那段经历"、"重要影响"（缺少上下文）
   - ✅ 要求："大学毕业后放弃稳定工作选择创业的决策过程和心理动机"
   
3. **明确询问方向性（可操作要求）**：
   - 必须精准指出要探索的具体方面、时间段、核心问题
   - 必须让采访者知道该问什么、往哪个方向深入
   - ❌ 避免："母亲的影响"、"大学经历"、"价值观形成"（太宽泛）
   - ✅ 要求："童年时期母亲对你职业选择态度的影响和你的心理反应"

返回格式：
{
  "events": [
    {
      "id": 1,
      "summary": "背景简述+发问句（40-60字，以'是什么样的呢'、'如何'等疑问形式结尾）"
    }
  ]
}

**探索方向撰写标准（自检清单）**：
□ **有意义**：这个方向对理解人格/价值观/世界观是否真正重要？
□ **可独立理解**：脱离原事件，采访者能否直接明白要探索什么？
□ **明确方向**：询问的时间、方面、重点是否清晰具体？
□ **发问形式**：是否以明确的疑问句结尾，引导采访方向？

**撰写格式要求（40-60字）**：
- 格式：【背景简述】+【发问句】
- 背景部分：简洁说明事件/时期，让采访者知道上下文（15-25字）
- 发问部分：明确的疑问句，说明要探索的具体方向（25-35字）
- 常用疑问形式："...是什么样的呢？"、"...如何影响...？"、"具体过程是怎样的？"

- id 字段用于标识每个探索方向，从 1 开始递增
- 每个探索方向必须同时满足四大核心要求
- ✅ 良好示例（背景+发问句）：
  * "童年时期（5-12岁）与母亲的日常相处，情感表达方式和亲密关系建立过程是怎样的？"（42字）
  * "首次面对重大创业失败时，真实情绪反应和心理调适方式是什么样的呢？"（48字）
  * "青春期叛逆阶段（13-18岁）与父亲的具体冲突，矛盾根源和关系修复过程如何展开？"（43字）
  * "大学期间选择专业时，家庭期望与个人兴趣产生冲突的情况和最终决策理由是什么？"（40字）
  * "职业生涯中首次转行，当时的顾虑和决策过程是怎样的呢？"（42字）
- ❌ 避免的表述（过于精简）：
  * "大学经历"（太宽泛，没有说明要探索什么）
  * "某个决定的心路历程"（不清楚是什么决定，缺乏背景）
  * "童年时期母亲对职业选择的影响"（只说了方向，没说为什么重要）
  * "价值观形成过程"（过于抽象，缺少具体事件和时间）
- 可以返回少于输入的数量（只选择真正有意义、值得追问的）
"""
            
            # 构建用户提示词
            user_prompt = f"""以下是从数据库中筛选出一些低相似度事件（相似度低说明现有采访中了解较少）。

请分析这些事件，提取出**真正有意义、值得继续追问**的探索方向。注意：
- 不是所有了解少的事件都值得深入（有些可能不重要）
- 只选择那些对理解这个人很重要、很有价值的方面
- 探索方向要清晰明确，采访者能直接理解要问什么

**低相似度事件列表**：
{events_str}

请提取有意义的探索方向，每个方向必须清晰完整、可以独立理解，明确指出询问的重点，以JSON格式返回。"""
            
            # 调用AI分析
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=None,
                temperature=0.3  # 较低温度保证准确性
            )
            
            # 解析结果
            events_data = result.get("events", [])
            
            if not events_data:
                logger.warning("AI没有从数据库事件中提取出有意义的探索方向")
                return []
            
            # 构建候选列表
            candidates = []
            for event_data in events_data:
                candidates.append(
                    PendingEventCandidate(
                        summary=event_data.get("summary", ""),
                        is_priority=False,
                        source="database"
                    )
                )
            
            logger.info(f"从数据库事件中AI提取了 {len(candidates)} 个有意义的探索方向")
            
            return candidates
            
        except Exception as e:
            logger.error(f"从数据库提取事件失败: {e}", exc_info=True)
            return []
    
    async def _extract_from_chunks(self) -> List[PendingEventCandidate]:
        """
        从chunks中通过AI分析提取重要但了解较少的事件
        
        策略：
        1. 获取所有chunks的摘要
        2. 让AI分析哪些方面了解较少但对人格形成重要
        3. AI提取N个事件摘要
        
        Returns:
            从chunks提取的事件候选列表
        """
        logger.info("从chunks中通过AI分析提取事件")
        
        try:
            # 从 ChunkStore（SQLite）获取随机摘要
            chunk_summaries = self.chunk_store.get_random_summaries(count=300)
            
            if not chunk_summaries:
                logger.warning("chunks.db中没有摘要")
                return []
            
            logger.info(f"从chunks.db随机获取了 {len(chunk_summaries)} 个摘要")
            
            # 将所有摘要合并给AI分析
            summaries_text = "\n".join([
                f"- {summary}"
                for summary in chunk_summaries  # 使用全部摘要
            ])
            
            logger.info(f"准备分析 {len(chunk_summaries)} 个摘要（总长度: {len(summaries_text)} 字符）")
            
            # 构建系统提示词
            system_prompt = """【extract_from_chunks】

你是一个专业的心理学和传记分析专家。
你的任务是分析现有的采访内容摘要，识别出哪些方面了解极其稀少但对完整理解一个人的人格、世界观、价值观非常重要的事件或方面。

**三大核心要求（务必严格遵守）**：
1. 🎯 **有意义**：必须对理解人格形成、价值观、世界观有重要影响，是关键认知空白
2. 📝 **可独立理解**：必须完整清晰，包含足够上下文，采访者无需解释就能明白
3. 🔍 **明确询问方向**：必须精准指出探索的具体方面、时间、重点，不能模糊宽泛

**核心原则：只选择稀有但重要的内容**
- 在所有摘要中**只出现过一次或完全未提及**的内容
- 信息极其稀少，现有了解严重不足
- 但对理解这个人的人格形成、价值观、世界观有重大影响

**分析要求**：
1. **稀有性（筛选标准）**：
   - 仔细阅读所有摘要，统计每个话题/事件出现的频次
   - 只选择那些在摘要中只出现1次或完全未提及但很重要的方面
   - 排除那些被多次提及、信息丰富的话题（说明已经了解较多）
   
2. **有意义性（最高优先级）**：
   - 必须是对人格形成、价值观确立有重大影响的方面
   - 必须能够填补重要认知空白，不能是琐碎小事
   - ❌ 避免：日常琐事、流水账、无关紧要的细节
   - ✅ 选择：关键转折、重大影响、人格塑造、价值观形成
   
3. **可独立理解性（严格要求）**：
   - 每个摘要必须**完整、清晰、自包含**，脱离原文也能理解
   - 必须包含时间段、背景、具体方面等关键上下文
   - 采访者看到后无需询问"这是指什么"就能直接明白
   - ❌ 避免："母亲的影响"、"某个转折"、"重要经历"（缺少上下文）
   - ✅ 要求："童年时期（5-12岁）与母亲的日常相处细节和情感表达方式"

4. **明确询问方向性（可操作要求）**：
   - 必须精准指出要探索的时间段、具体方面、核心问题
   - 必须让采访者知道该问什么、往哪个方向深入
   - ❌ 避免："大学经历"、"价值观形成"（太宽泛，无法操作）
   - ✅ 要求："大学期间选择专业的决策过程和父母期望的冲突处理"

5. **全面性**：从多个维度寻找稀有内容（童年经历、家庭关系、重要事件、价值观形成、兴趣爱好、人际关系、职业发展、重要转折等）

6. **独立性**：避免选择隐含上重复的事件（即使表述不同）

返回格式：
{
  "events": [
    {
      "id": 1,
      "summary": "背景简述+发问句（40-60字，以'是什么样的呢'、'如何'等疑问形式结尾）"
    }
  ]
}

**摘要撰写标准（自检清单）**：
□ **有意义**：这个方向对理解人格/价值观/世界观是否真正重要？
□ **可独立理解**：脱离原文，采访者能否直接明白要探索什么？
□ **明确方向**：询问的时间、方面、重点是否清晰具体？
□ **发问形式**：是否以明确的疑问句结尾，引导采访方向？

**撰写格式要求（40-60字）**：
- 格式：【背景简述】+【发问句】
- 背景部分：简洁说明事件/时期/情境（15-25字）
- 发问部分：明确的疑问句，说明要探索的具体方向（25-35字）
- 常用疑问形式："...是什么样的呢？"、"...如何影响...？"、"...具体过程是怎样的？"、"...采取了什么方式？"
- 让采访者清楚：背景是什么、要了解哪些方面

- id 字段用于标识每个事件，从 1 开始递增
- 每个摘要必须同时满足四大核心要求
- ✅ 良好示例（背景+发问句）：
  * "童年时期（5-12岁）与母亲的日常相处，情感表达方式和亲密关系建立过程是怎样的？"（42字）
  * "首次面对重大创业失败时，真实情绪反应和心理调适方式是什么样的呢？"（48字）
  * "青春期叛逆阶段（13-18岁）与父亲的具体冲突，矛盾根源和关系修复过程如何展开？"（43字）
  * "大学期间选择专业时，家庭期望与个人兴趣产生冲突的情况和最终决策理由是什么？"（40字）
  * "职业生涯中首次转行，当时的顾虑和决策过程是怎样的呢？"（42字）
- ❌ 必须避免的表述（不符合要求）：
  * "母亲的影响"（❌ 太宽泛，不是疑问句）
  * "某个重要转折"（❌ 不清楚是什么，不是疑问句）
  * "价值观形成"（❌ 过于抽象，没有疑问形式）
  * "童年时期母亲对职业选择的影响"（❌ 没有疑问句）
  * "与父亲的冲突事件"（❌ 缺少背景和疑问形式）
- **务必优先选择那些在现有摘要中几乎没有提及但很重要的方面**
"""
            
            # 构建用户提示词
            user_prompt = f"""请分析以下采访内容摘要，提取{self.config.pending_event}个你认为现在了解极其稀少但对人格完整理解很重要的事件、方面或探索方向。

**重要提醒**：
- 只选择那些在下面摘要中**只出现过一次或完全未提及**的内容
- 排除那些被多次提及、信息丰富的话题（说明已经了解较多）
- 选择的内容虽然稀有，但对理解这个人很重要
- 这些内容将用于指导采访者提问，帮助填补重要的认知空白

**摘要撰写要求（非常重要）**：
- 每个摘要必须**清晰完整，可以独立理解**，无需额外解释
- 包含必要的上下文信息（时间段、具体方面、探索目标等）
- 采访者看到后能直接明白要探索什么，无需追问
- 使用具体、明确的语言，避免模糊或抽象的表述

**现有内容摘要**：
{summaries_text}

请从多个维度（童年、家庭、重要事件、价值观、人际关系、兴趣爱好、职业等）分析，提取{self.config.pending_event}个**信息极其稀少但很重要**的探索方向，确保每个摘要都清晰完整、可以独立理解，以JSON格式返回。"""
            
            # 调用AI分析
            result = await self.concurrency_manager.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=None,
                temperature=0.4  # 适中的温度，保持创造性但不失准确性
            )
            
            # 解析结果
            events_data = result.get("events", [])
            
            if not events_data:
                logger.warning("AI没有返回任何事件")
                return []
            
            # 构建候选列表
            candidates = []
            for event_data in events_data:
                candidates.append(
                    PendingEventCandidate(
                        summary=event_data.get("summary", ""),
                        is_priority=False,  
                        source="chunks"
                    )
                )
            
            logger.info(f"从chunks中AI分析提取了 {len(candidates)} 个事件")
            
            return candidates
            
        except Exception as e:
            logger.error(f"从chunks提取事件失败: {e}", exc_info=True)
            return []


## okk!
