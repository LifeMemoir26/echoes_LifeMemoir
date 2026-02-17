# Interview 旧编排节点边界清单

## 迁移目标
将 `InterviewService._process_chunk` 中的串行/并发编排，拆分为 LangGraph 节点，保持行为等价。

## 节点列表（旧逻辑 -> 新节点）

1. `ingest`
- 旧逻辑位置：`InterviewService.add_dialogue` / `flush_buffer`
- 输入：`speaker/content/timestamp` 或 `flush=true`
- 输出：`chunk`（若达到阈值或主动 flush）
- 副作用：写入 `DialogueStorage` 队列与临时存储

2. `split_or_buffer`
- 旧逻辑位置：`if chunk is not None: await _process_chunk(chunk)`
- 输入：`chunk`
- 输出：路由决策（继续处理或结束）
- 副作用：无

3. `summarize`
- 旧逻辑位置：`_process_chunk` 步骤 1.1
- 输入：`chunk`
- 输出：`summary_tuples=[(importance, summary), ...]`
- 副作用：无（仅返回提取结果）

4. `enrich_pending_events`
- 旧逻辑位置：`_process_chunk` -> `_process_pending_events`
- 输入：`chunk`
- 输出：`pending_update_count`
- 副作用：更新 `pending_events.explored_content`

5. `build_context`
- 旧逻辑位置：`_process_chunk` 步骤 1.3（`SupplementExtractor.generate_context_info`）
- 输入：`summary_tuples`、人物侧写、向量检索结果
- 输出：`context_info`
- 副作用：更新 `event_supplements` 与 `interview_suggestions`

6. `persist`
- 旧逻辑位置：`_process_chunk` 收尾与日志
- 输入：并行分支结果
- 输出：`status/metadata`
- 副作用：记录失败补偿路径（仅状态标记，不改变对外 API）

## 并行关系
- `summarize -> enrich_pending_events`
- `summarize -> build_context`
- `enrich_pending_events` 与 `build_context` 并行，随后 fan-in 到 `persist`

## 状态契约关键字段
- `chunk`
- `summary_tuples`
- `context_info`
- `pending_update_count`
- `parallel_updates`（reducer 追加，用于并行分支无覆盖合并）
- `errors/failed_node/trace_id`
