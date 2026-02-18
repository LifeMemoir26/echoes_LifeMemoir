## 目的
定义并强制执行后端模块的 DDD 分层架构边界。

## 需求

### 需求：强制 DDD 分层边界
系统 应当 在 `backend/src` 下强制统一分层模型，允许的顶层包仅为 `interfaces`、`application`、`domain`、`infra`。依赖方向 应当 为 `interfaces -> application -> domain`，同时 `infra` 应当 仅依赖 `application` 契约（ports）与 `domain` 模型/契约。

#### 场景：合法分层依赖图
- **当** 对代码库执行分层依赖检查
- **则** 不得出现违反允许依赖方向的导入路径

### 需求：拒绝跨层非法导入
当 `domain` 导入 `application`、`infra`、`interfaces`，或 `application` 导入 `interfaces` 时，系统 应当 使校验失败。

#### 场景：引入被禁止的领域层依赖
- **当** `backend/src/domain/` 下模块直接导入 `backend/src/infra/`
- **则** 依赖校验 应当 失败，并输出违规文件路径与导入目标

### 需求：为维护者提供架构契约
系统 应当 提供明确的架构契约文档，定义各顶层包的分层职责、允许依赖与所有权边界。

#### 场景：新贡献者查看结构契约
- **当** 开发者需要新增模块
- **则** 开发者 应当 能从单一、持续维护的契约文档中判断正确落层与依赖规则
