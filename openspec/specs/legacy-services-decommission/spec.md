## 目的
在保持行为一致的前提下，下线 legacy services 运行路径。

## 需求

### 需求：从运行路径移除 services 包
系统应当下线 `backend/src/services/` 作为运行时依赖，并将剩余行为迁移到 `backend/src/application/` 与 `backend/src/infra/`。

#### 场景：工作流运行仅使用迁移后模块
- **当** 执行 interview、knowledge、generate 工作流
- **则** 运行时导入应当不再解析到 `backend/src/services/`

### 需求：阻止 services 导入回流
系统应当拒绝在应用代码、接口代码、脚本与测试中新增 `src.services` 或 `backend/src/services` 导入。

#### 场景：新代码引用 legacy services
- **当** 变更后执行导入校验扫描
- **则** 校验应当失败，并报告每个被禁止的 `services` 导入位置

### 需求：下线过程中保持行为一致
系统应当在移除 legacy services 依赖并新增前端 API 包装层时，保持应用层 workflow 输出语义一致，且对外接口变化仅限协议封装与传输方式，不改变核心业务含义；前端工作台化与参考代码大规模引入只能影响展示层与交互组织，不得改变 backend application 语义。

#### 场景：旧应用层语义在新 API 包装下保持一致
- **当** 通过 `/api/v1` 调用 knowledge、interview、generate 对应能力
- **则** 结果语义应当与 `backend/src/application/*` 直接调用路径保持一致（在字段包装允许范围内）

#### 场景：SSE 与同步接口的错误语义一致
- **当** 同一类 workflow 错误分别通过同步响应或 SSE error 事件返回
- **则** `error_code`、`retryable`、`trace_id` 的业务语义应当保持一致，前端重试策略不应因传输通道不同而改变

#### 场景：回忆录能力在前端消费下保持语义一致
- **当** 前端通过 `/api/v1/generate/memoir` 调用回忆录生成功能
- **则** 结果语义应当与 `backend/src/application/generate/api.py` 直接调用路径一致（在响应包裹与字段命名范围内）

#### 场景：错误语义在前端展示与 API 返回一致
- **当** 回忆录生成失败并返回结构化错误
- **则** 前端展示的 `error_code`、`retryable`、`trace_id` 业务语义应当与 API 返回保持一致，不可重写为冲突含义

#### 场景：参考实现迁移不引入后端语义漂移
- **当** 前端从 `.reference/echoes_-life-memoir-&-replica` 引入新的页面结构或组件逻辑
- **则** 任何适配层必须仅做字段映射与状态呈现，不得新增依赖 legacy services 语义或重定义后端业务判定规则
