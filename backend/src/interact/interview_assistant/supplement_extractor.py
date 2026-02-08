"""
补充信息提取器
生成采访辅助的背景信息
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import asyncio

from ...llm.concurrency_manager import ConcurrencyManager
from ...config import get_settings

logger = logging.getLogger(__name__)


class EventSupplement(BaseModel):
    """事件补充信息"""
    event_summary: str = Field(description="事件摘要（20-30字）")
    event_details: str = Field(description="详细补充信息（前后经过、起因、结果、背景、天气、地点人物等）")


class EventSupplementList(BaseModel):
    """事件补充列表"""
    supplements: List[EventSupplement] = Field(description="事件补充信息列表")


class InterviewSuggestions(BaseModel):
    """采访建议"""
    positive_triggers: List[str] = Field(description="让叙述者高兴的点、激发联想的人或事物")
    sensitive_topics: List[str] = Field(description="可能引发伤感的话题，需要谨慎处理")


class ContextInfo(BaseModel):
    """采访背景信息"""
    event_supplements: List[EventSupplement] = Field(description="事件补充信息列表")
    positive_triggers: List[str] = Field(description="让叙述者高兴的点、激发联想的人或事物")
    sensitive_topics: List[str] = Field(description="可能引发伤感的话题，需要谨慎处理")


class SupplementExtractor:
    """
    补充信息提取器
    
    负责生成采访辅助的背景信息和建议。
    """
    
    def __init__(self, concurrency_manager: ConcurrencyManager):
        """
        初始化补充信息提取器
        
        Args:
            concurrency_manager: 并发管理器实例
        """
        self.concurrency_manager = concurrency_manager
        
        logger.info("SupplementExtractor initialized")
    
    async def generate_context_info(
        self,
        new_summaries: List[Tuple[int, str]],  # 新总结：[(重要性, 总结), ...]
        summary_manager,  # SummaryManager 实例
        vector_store,  # VectorStore 实例
        chunk_store,  # ChunkStore 实例，用于获取完整chunk文本
        character_profile: str  # 人物侧写
    ) -> ContextInfo:
        """
        生成采访辅助的背景信息
        
        完整流程：
        1. 调用 summary_manager.put_and_set() 获取旧总结和新总结（格式化），并更新存储
        2. 分别对新总结和旧总结进行向量搜索（每个总结最多2条chunks，一次性获取完整chunk文本）
        3. 根据相似度阈值过滤 chunks
        4. 新旧 chunks 已通过分别搜索自然区分
        5. 将总结、chunks、人物侧写交给 AI 生成背景补充信息
        
        Args:
            new_summaries: 新的总结列表 [(重要性, 总结), ...]
            summary_manager: 总结管理器实例
            vector_store: 向量存储实例
            chunk_store: ChunkStore实例，用于获取完整chunk文本
            character_profile: 人物侧写文本
        
        Returns:
            采访背景信息
        """
        logger.info("Generating context information with full workflow")
        
        # 获取配置
        settings = get_settings()
        similarity_threshold = settings.interview.similarity_threshold
        
        try:
            # ==== 步骤 1: 获取旧总结和新总结，刷新总结存储区 ====
            old_formatted, new_formatted = await summary_manager.put_and_set(new_summaries)
            
            logger.info(
                f"Retrieved summaries: {len(old_formatted)} old, {len(new_formatted)} new"
            )
            
            # ==== 步骤 2-4: 对新旧总结分别进行向量搜索，找出相关 chunks ====
            new_chunks = []
            old_chunks = []
            new_chunk_texts = []
            old_chunk_texts = []
            
            # 对新总结进行批量向量搜索
            if new_formatted:
                logger.info(f"Searching chunks for {len(new_formatted)} new summaries (top 2 per summary)")
                new_chunks = vector_store.query_relevant_chunks(
                    summaries=new_formatted,
                    top_k_per_summary=2,
                    similarity_threshold=similarity_threshold,
                    return_dissimilar=False,
                    chunk_store=chunk_store  # 传入chunk_store以获取完整chunk文本
                )
                
                new_chunk_texts = [c.get('matched_chunk', '') for c in new_chunks if c.get('matched_chunk')]
                logger.info(
                    f"Found {len(new_chunks)} chunks for new summaries "
                    f"(threshold: {similarity_threshold})"
                )
            
            # 对旧总结进行批量向量搜索
            if old_formatted:
                logger.info(f"Searching chunks for {len(old_formatted)} old summaries (top 2 per summary)")
                old_chunks = vector_store.query_relevant_chunks(
                    summaries=old_formatted,
                    top_k_per_summary=2,
                    similarity_threshold=similarity_threshold,
                    return_dissimilar=False,
                    chunk_store=chunk_store  # 传入chunk_store以获取完整chunk文本
                )
                
                old_chunk_texts = [c.get('matched_chunk', '') for c in old_chunks if c.get('matched_chunk')]
                logger.info(
                    f"Found {len(old_chunks)} chunks for old summaries "
                    f"(threshold: {similarity_threshold})"
                )
            
            # 检查是否有任何总结
            if not new_formatted and not old_formatted:
                logger.warning("No summaries available, returning empty context info")
                return ContextInfo(
                    event_supplements=[],
                    positive_triggers=[],
                    sensitive_topics=[]
                )
            
            # ==== 步骤 5: 构建提示词并调用 AI ====
            return await self._generate_with_ai(
                new_formatted=new_formatted,
                old_formatted=old_formatted,
                new_chunk_texts=new_chunk_texts,
                old_chunk_texts=old_chunk_texts,
                character_profile=character_profile
            )
            
        except Exception as e:
            logger.error(f"Failed to generate context info: {e}", exc_info=True)
            # 返回空的背景信息
            return ContextInfo(
                event_supplements=[],
                positive_triggers=[],
                sensitive_topics=[]
            )
    
    async def _generate_with_ai(
        self,
        new_formatted: List[str],
        old_formatted: List[str],
        new_chunk_texts: List[str],
        old_chunk_texts: List[str],
        character_profile: str
    ) -> ContextInfo:
        """
        使用 AI 生成背景补充信息（内部方法）
        
        使用两个并发的AI调用：
        - AI1: 生成事件补充信息
        - AI2: 生成采访建议
        
        Args:
            new_formatted: 新总结列表（格式化）
            old_formatted: 旧总结列表（格式化）
            new_chunk_texts: 最新的相关chunk文本列表
            old_chunk_texts: 较旧的相关chunk文本列表
            character_profile: 人物侧写
        
        Returns:
            采访背景信息
        """
        # 获取配置
        settings = get_settings()
        max_supplements = getattr(settings.interview, 'max_event_supplements', 8)
        
        # 构建共享的信息文本
        # 构建总结文本
        new_summaries_text = "\n".join(f"- {s}" for s in new_formatted) if new_formatted else "无新总结"
        old_summaries_text = "\n".join(f"- {s}" for s in old_formatted) if old_formatted else "无旧总结"
        
        # 构建chunks文本
        def format_chunks(chunk_texts: List[str], label: str) -> str:
            if not chunk_texts:
                return f"## {label}\n暂无相关内容"
            
            result = [f"## {label}"]
            for i, chunk_text in enumerate(chunk_texts, 1):
                result.append(f"{i}. {chunk_text}")
            
            return "\n".join(result)
        
        new_chunks_text = format_chunks(new_chunk_texts, "数据库中的相关对话记录（用于信息补充）")
        old_chunks_text = format_chunks(old_chunk_texts, "历史相关信息（较早的相关背景）")
        
        # 构建本次会话历史总结
        session_history_text = "\n".join(
            f"- {s}" for s in old_formatted
        ) if old_formatted else "无历史总结"
        
        # 共享的基础信息
        base_context = f"""## 人物侧写
{character_profile}

================================================================================
## 刚讨论的内容（最新总结）
这是当前对话中最新产生的话题总结，反映了叙述者刚刚讨论的主题。

{new_summaries_text}
================================================================================

================================================================================
## 之前讨论的内容（旧总结）
这是本次会话前部分的话题总结，提供了对话的历史脉络。

{old_summaries_text}
================================================================================

================================================================================
{new_chunks_text}

**说明**：上述"数据库中的相关对话记录"是之前采访中的原始对话记录，这些记录与"刚讨论的内容"高度相关，包含了详细的时间、地点、人物、情节等具体信息，可以用来为当前讨论的总结提供血肉般的细节补充。
================================================================================

================================================================================
{old_chunks_text}

**说明**：这些是与"之前讨论的内容"相关的历史对话记录，提供了更早期的背景信息和相关细节。
================================================================================

## 本次会话的完整历史总结
{session_history_text}"""
        
        # === AI1: 事件补充提取 ===
        system_prompt_ai1 = f"""你是一个专业的采访辅助专家，负责从数据库中提取事件补充信息，为志愿者（采访者）提供有价值的背景资料。

## 核心任务
**重要**：chunks的主要目的是为"刚讨论的内容"（总结）提供详细补充，让抽象的总结变得具体、生动、有血有肉。

你的任务是：
1. **首先关注总结**：仔细阅读"刚讨论的内容"中的每一条总结，理解提到了哪些事件、人物、话题
2. **然后查找chunks**：在"数据库中的相关对话记录"(chunks)中寻找与这些总结点对应的详细信息
3. **充实总结**：用chunks中的具体细节（时间、地点、人物、对话、情感等）来充实总结中的内容

**核心原则**：chunks不是用来发现新事件的，而是用来为总结中已提到的内容提供背景细节的。不要在chunks中寻找总结完全没提到的无关事件。

## 返回格式
{{
  "supplements": [
    {{
      "event_summary": "事件摘要（20-30字清晰描述事件核心）",
      "event_details": "详细补充信息（150-300字）"
    }},
    ...
  ]
}}

## 详细要求

### 1. 事件摘要（event_summary）
- **长度**：20-30字
- **内容**：用一句话说清楚"谁在什么时间/地点做了什么"
- **示例**：
  - ✓ "1978年高考复读时与同学王明的深厚友谊"
  - ✓ "1985年在工厂担任车间主任时的管理困境"
  - ✗ "过去的一些事情"（太模糊）
  - ✗ "关于工作"（不具体）

### 2. 事件详细补充（event_details）
必须包含以下维度（如果chunks中有提及）：

**时空信息**：
- 具体时间（年份、季节、月份、甚至具体日期）
- 地点（城市、街道、建筑物、房间等）
- 天气、环境氛围

**人物信息**：
- 涉及的关键人物（姓名、关系、性格特点）
- 人物之间的互动和对话
- 人物的情绪和反应

**事件经过**：
- 起因：为什么发生这件事
- 经过：事情如何发展，关键转折点
- 结果：最终的结局如何
- 影响：对叙述者或他人产生了什么影响

**情感色彩**：
- 叙述者当时的心情和感受
- 现在回忆时的情绪
- 这件事对叙述者的意义

**具体细节**（让故事生动的关键）：
- 对话片段（如果有）
- 感官描写（看到什么、听到什么、闻到什么）
- 具体的数字、名称、物品

### 3. 筛选标准
**必须提取的**：
- **总结中明确提到的事件**，且chunks中有丰富细节可以补充
- 能够充实和丰富总结内容的信息
- 总结提到的重要人物、地点、时期的具体细节
- 总结中涉及的情感色彩强的事件的详细经过

**不要提取的**：
- **总结中完全没提到的事件**（即使chunks中提到了也不要）
- chunks中只是一笔带过、没有实质细节的内容
- 与总结讨论的话题无关的事件
- 重复或相似的事件（选择最详细的一个）

**判断方法**：
1. 先读总结：这条总结在说什么？
2. 再看chunks：有没有与这个总结相关的详细信息？
3. 如果有→提取补充；如果没有→跳过
4. **绝不要**：chunks里有个很好的故事，但总结没提→不要提取

### 4. 数量和优先级
- **最多返回{max_supplements}条**
- **优先级排序**：
  1. 情感冲击力强的事件（生死、离别、重逢、失败、成功等）
  2. 对理解当前话题最有帮助的事件
  3. 细节丰富、故事性强的事件
  4. 涉及重要人物或重大决策的事件

### 5. 写作要求
- **客观记录**：忠实于chunks中的原话，不要添油加醋
- **有条理**：按照时间顺序或逻辑顺序组织信息
- **有重点**：突出最关键的细节和情感点
- **避免废话**：每句话都应该提供有价值的信息
- **字数控制**：每条补充150-300字，既要详细又要精炼

## 示例

**场景1：总结中提到了，chunks中有详细信息**
- 总结："谈到了母亲去世的经历"
- chunks中有：时间、地点、经过、情感等详细描述
- ✓ **应该提取**：用chunks充实这个总结
```
event_summary: "1976年母亲去世时的痛苦经历"
event_details: "那是1976年的冬天，母亲因肺病在县医院去世，享年58岁。我记得那天下着大雪，赶到医院时母亲已经走了。她临终前一直念叨着我的名字，但我因为在外地工作没能见到最后一面。料理后事时，父亲一句话都没说，只是一个人坐在堂屋里发呆。安葬那天，全村人都来送行，我才意识到母亲在村里帮助过那么多人。这件事成了我一生最大的遗憾，也让我明白了'子欲养而亲不待'的痛。此后我对家人格外珍惜，每个春节都一定回家。"
```

**场景2：总结中没提到，chunks中有详细信息**
- 总结：谈的是"工作经历"
- chunks中有："童年时代在农村放牛的快乐时光"（很详细，但与总结无关）
- ✗ **不要提取**：虽然chunks有详细信息，但总结没提到童年，不符合当前话题

**场景3：总结中提到了，但chunks中没有细节**
- 总结："提到了在北京工作的经历"
- chunks中只有："在北京工作过"（没有更多细节）
- ✗ **不要提取**：没有实质性的补充信息

**不好的补充示例**：
```
event_summary: "过去的一些事"
event_details: "有很多事情发生过，都挺重要的，对他的人生影响很大。"
```
（既不具体，也不清楚是在补充哪条总结）

## 特别提醒
- **工作流程**：总结→chunks→补充，永远以总结为出发点
- **主要目的**：让总结从抽象变具体，从概括变生动，为采访者提供可用的背景信息
- 如果某条总结在chunks中找不到对应的详细信息，就跳过这条总结，不要勉强
- 如果chunks中有与总结完全无关的精彩故事，也不要提取（那不是当前的讨论重点）
- 关注叙述者使用的具体词汇和表达方式，保留原汁原味
- 注意识别chunks中的情感线索（语气词、重复强调、停顿等）

**再次强调**：你的任务不是从chunks中挖掘新故事，而是用chunks为总结提供血肉！
"""
        
        user_prompt_ai1 = f"""{base_context}

请从上述信息中提取事件补充，以JSON格式返回。"""
        
        # === AI2: 采访建议 ===
        system_prompt_ai2 = """你是一个专业的采访辅助专家，负责分析叙述者的情感倾向并提供采访建议，帮助志愿者（采访者）更好地引导对话。

## 核心任务
基于当前讨论内容、数据库中的历史对话记录和人物侧写，识别：
1. 什么话题、人物、事物会让叙述者高兴、兴奋、健谈
2. 什么话题可能触发叙述者的伤感、痛苦、回避情绪

## 返回格式
{{
  "positive_triggers": [
    "让叙述者高兴的点、激发联想的人或事物",
    ...
  ],
  "sensitive_topics": [
    "可能引发伤感的话题（需要谨慎处理）",
    ...
  ]
}}

## 详细要求

### 1. 正面触发点（positive_triggers）

**目标**：找出能让叙述者打开话匣子、愿意分享、情绪积极的话题

**应该包含的内容**：
- **成就时刻**：工作上的成功、获得的荣誉、克服的困难
- **温情记忆**：家庭团聚、友谊、爱情、亲情的美好时刻
- **喜欢的人物**：提到时会眉飞色舞的人（老师、朋友、子女、恩人等）
- **兴趣爱好**：热爱的活动、特长、收藏等
- **积极转折**：人生中的幸运转机、柳暗花明的经历
- **怀旧元素**：美好的时代记忆、故乡、童年等

**判断依据**：
- 数据库记录中，叙述者谈到这些话题时使用了积极的词汇（"开心"、"自豪"、"怀念"等）
- 叙述详细、生动，愿意展开讲述
- 语气轻松、会笑、会重复强调
- 人物侧写中显示的性格特点和价值观相关联

**格式要求**（3-5条，每条30-60字）：
- 具体到人名、事件、地点、时期
- 说明为什么是正面触发点
- 给出采访方向建议

**示例**：
✓ "谈到女儿考上大学的经历会非常自豪和高兴，可以询问当时的心情和如何培养孩子的【积极话题】"
✓ "提到在工厂当车间主任时带领团队攻克技术难关，会激发他对那个时代的怀念和自豪感【建议深挖】"
✓ "老战友张明是他最亲密的朋友，谈到两人的友谊会很温情，可以询问他们共同的经历【联想触发】"
✗ "家庭"（太宽泛）
✗ "一些开心的事"（不具体）

### 2. 敏感话题（sensitive_topics）

**目标**：识别可能引发叙述者负面情绪的话题，提醒采访者谨慎处理

**应该包含的内容**：
- **丧失和离别**：亲人去世、朋友离世、离婚、分离
- **创伤事件**：重大事故、疾病、灾难、受到的伤害
- **失败和遗憾**：事业失败、人生遗憾、未实现的愿望
- **冲突和矛盾**：家庭矛盾、工作冲突、被误解的经历
- **困难时期**：经济困难、被批斗、下岗失业等
- **健康问题**：自己或家人的重大疾病
- **未愈合的伤口**：至今仍然痛苦的经历

**判断依据**：
- 数据库记录中，谈到时语气沉重、用词悲伤（"痛苦"、"后悔"、"遗憾"等）
- 讲述时情绪低落、停顿、哽咽、不愿深入
- 避免谈论或快速带过
- 至今仍有影响（"一直忘不了"、"现在想起来还难受"等）

**谨慎处理的含义**：
- **不是完全回避**：这些话题往往是人生的重要部分，可以谈，但要谨慎
- **时机选择**：在信任建立、氛围良好时再深入
- **温和询问**：使用委婉的表达，给叙述者选择的空间
- **情绪关注**：随时观察叙述者情绪，适时转移话题或给予安慰
- **尊重意愿**：如果叙述者不愿深谈，不要强迫

**格式要求**（2-4条，每条40-80字）：
- 具体说明是什么话题
- 为什么敏感（基于什么证据）
- 如何谨慎处理（具体建议）

**示例**：
✓ "母亲1976年去世是他最大的遗憾，他因工作未能见最后一面。谈到时会哽咽，建议温和询问，不要追问细节，重点关注他如何走出悲伤的【谨慎话题】"
✓ "1989年工厂下岗对他打击很大，当时家里困难、四处借钱的经历让他至今心有余悸。可以询问但不要过度深挖经济细节，重点关注他如何重新站起来【敏感但可谈】"
✓ "与大哥的矛盾至今未解，提到时会沉默或回避。除非他主动提起，否则不要询问，可以谈其他兄弟姐妹【避免触碰】"
✗ "悲伤的事"（不具体）
✗ "注意情绪"（没有给出具体建议）

### 3. 数量要求
- **positive_triggers**：3-5条
- **sensitive_topics**：2-4条
- 如果某一类证据不足，宁可少返回，不要凭空推测

### 4. 分析方法

**步骤1：扫描情感信号**
- 在当前讨论和数据库记录中寻找情感词汇
- 注意重复提及的人物、地点、时期
- 识别语气变化（从平静到激动、从兴奋到沉默）

**步骤2：结合人物侧写**
- 叙述者的性格特点（外向/内向、乐观/悲观）
- 价值观和重要经历
- 人生阶段和当前状态

**步骤3：交叉验证**
- 同一话题在不同对话中的情绪是否一致
- 是否有明确的情感表达或暗示
- 避免过度解读

**步骤4：给出可操作建议**
- 不仅指出什么话题，还要说明为什么和怎么做
- 站在采访者的角度，给出实用的引导策略

## 情感分析的细微差别

**高兴 vs. 自豪 vs. 怀念**：
- 高兴：纯粹的快乐（"那天真开心"）→ 可以轻松聊
- 自豪：带有成就感（"我很骄傲"）→ 可以请他多讲细节
- 怀念：带有失去感的美好（"那时候真好"）→ 要注意不要引发伤感

**悲伤 vs. 遗憾 vs. 愤怒**：
- 悲伤：纯粹的痛苦（"太难过了"）→ 极度谨慎
- 遗憾：后悔和惋惜（"如果当时..."）→ 可以询问他的反思
- 愤怒：不公和委屈（"太气人了"）→ 允许宣泄，但控制节奏

## 特别提醒
- 采访的目标是让叙述者舒适地分享人生，不是刻意挖掘痛苦
- 正面话题可以多聊、深聊，敏感话题点到为止
- 所有建议必须基于具体证据，不能主观臆断
- 关注叙述者的当前状态（年龄、健康、近期经历），年老体弱者更需谨慎
"""
        
        user_prompt_ai2 = f"""{base_context}

请分析情感倾向并提供采访建议，以JSON格式返回。"""
        
        try:
            # 并发调用两个AI
            logger.info("Starting concurrent AI calls: event supplements and interview suggestions")
            
            task1 = self.concurrency_manager.generate_structured(
                prompt=user_prompt_ai1,
                system_prompt=system_prompt_ai1,
                model=None,
                temperature=0.3  # 较低温度以保持准确性
            )
            
            task2 = self.concurrency_manager.generate_structured(
                prompt=user_prompt_ai2,
                system_prompt=system_prompt_ai2,
                model=None,
                temperature=0.5  # 适中温度
            )
            
            # 等待两个任务完成
            results = await asyncio.gather(task1, task2, return_exceptions=True)
            
            # 处理结果
            supplements_result = results[0]
            suggestions_result = results[1]
            
            # 检查是否有异常
            if isinstance(supplements_result, Exception):
                logger.error(f"AI1 (event supplements) failed: {supplements_result}")
                supplements_result = {"supplements": []}
            
            if isinstance(suggestions_result, Exception):
                logger.error(f"AI2 (interview suggestions) failed: {suggestions_result}")
                suggestions_result = {"positive_triggers": [], "sensitive_topics": []}
            
            # 解析结果
            supplement_list = EventSupplementList(**supplements_result)
            suggestions = InterviewSuggestions(**suggestions_result)
            
            # 组合结果
            context_info = ContextInfo(
                event_supplements=supplement_list.supplements,
                positive_triggers=suggestions.positive_triggers,
                sensitive_topics=suggestions.sensitive_topics
            )
            
            logger.info(
                f"Generated context info: "
                f"{len(context_info.event_supplements)} event supplements, "
                f"{len(context_info.positive_triggers)} positive triggers, "
                f"{len(context_info.sensitive_topics)} sensitive topics"
            )
            
            return context_info
            
        except Exception as e:
            logger.error(f"Failed to call AI for context generation: {e}", exc_info=True)
            raise
