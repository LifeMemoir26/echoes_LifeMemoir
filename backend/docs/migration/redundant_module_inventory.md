# 冗余模块清单（阶段 8.1）

## 权威模块与替代关系

| 范围 | 冗余模块（旧） | 权威模块（保留） | 当前状态 | 风险说明 |
|---|---|---|---|---|
| interview/dialogue_storage | `eventsupplement.py` | `event_supplement.py` | 已删除 | 若外部仍直接导入旧文件会报 ImportError |
| interview/dialogue_storage | `interviewsuggestion.py` | `interview_suggestion.py` | 已删除 | 若外部仍直接导入旧文件会报 ImportError |
| orchestration entry | `services/knowledge/knowledge_service.py` 中 legacy 手工主入口 | `application/workflows/knowledge/workflow.py` + `WorkflowFacade` | 已切换为 LangGraph 唯一入口 | legacy 路径不再参与主调用链 |
| orchestration entry | `services/generate/generation_service.py` 中 legacy 手工主入口 | `application/workflows/generate/workflow.py` + `WorkflowFacade` | 已切换为 LangGraph 唯一入口 | legacy 路径不再参与主调用链 |

## 说明

- 本清单只覆盖已迁移主流程（knowledge / generate / interview）的编排冗余。
- `KnowledgeService`、`GenerationTimelineService`、`GenerationMemoirService` 类暂保留，作为后续删除缓冲层。
