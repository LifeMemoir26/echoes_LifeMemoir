# 冗余清理回滚方案（阶段 8.5）

## 变更点 A
- 操作：删除 `backend/src/services/interview/dialogue_storage/eventsupplement.py`
- 影响范围：`dialogue_storage` 内部导入路径统一到 `event_supplement.py`
- 回滚步骤：
  1. 从最近提交恢复该文件
  2. 将 `__init__.py` 和 `dialogue_storage.py` 导入改回 `eventsupplement`
  3. 执行 `python3 -m py_compile` 校验

## 变更点 B
- 操作：删除 `backend/src/services/interview/dialogue_storage/interviewsuggestion.py`
- 影响范围：`dialogue_storage` 内部导入路径统一到 `interview_suggestion.py`
- 回滚步骤：
  1. 从最近提交恢复该文件
  2. 将 `__init__.py` 和 `dialogue_storage.py` 导入改回 `interviewsuggestion`
  3. 执行 `python3 -m py_compile` 校验

## 变更点 C
- 操作：`process_knowledge_file` 切换为 LangGraph 唯一入口
- 影响范围：knowledge 主编排由 `WorkflowFacade` 驱动
- 回滚步骤：
  1. 恢复 `is_langgraph_enabled()` 分支
  2. 恢复 legacy `KnowledgeService.process_file` 主路径调用
  3. 使用 `backend/scripts/migration/main_workflows_ab_parity.py` 复验

## 变更点 D
- 操作：`generate_timeline` / `generate_memoir` 切换为 LangGraph 唯一入口
- 影响范围：generate 主编排由 `WorkflowFacade` 驱动
- 回滚步骤：
  1. 恢复 `is_langgraph_enabled()` 分支
  2. 恢复 legacy `GenerationTimelineService` / `GenerationMemoirService` 主路径调用
  3. 使用 `backend/scripts/migration/main_workflows_ab_parity.py` 复验
