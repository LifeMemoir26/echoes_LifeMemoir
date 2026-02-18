## 目的
在保持行为一致的前提下，下线 legacy services 运行路径。

## 需求

### 需求：从运行路径移除 services 包
系统 应当 下线 `backend/src/services/` 作为运行时依赖，并将剩余行为迁移到 `backend/src/application/` 与 `backend/src/infra/`。

#### 场景：工作流运行仅使用迁移后模块
- **当** 执行 interview、knowledge、generate 工作流
- **则** 运行时导入 应当 不再解析到 `backend/src/services/`

### 需求：阻止 services 导入回流
系统 应当 拒绝在应用代码、接口代码、脚本与测试中新增 `src.services` 或 `backend/src/services` 导入。

#### 场景：新代码引用 legacy services
- **当** 变更后执行导入校验扫描
- **则** 校验 应当 失败，并报告每个被禁止的 `services` 导入位置

### 需求：下线过程中保持行为一致
系统 应当 在移除 legacy services 依赖时，保持外部 API 行为与工作流输出语义一致。

#### 场景：旧路径与新路径一致性对比
- **当** 在下线前后执行代表性流水线与 API 回归检查
- **则** 响应契约与核心输出语义 应当 在定义容差内等价
