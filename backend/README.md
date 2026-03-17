# Backend

## 分层架构

项目采用 DDD 分层结构，层间依赖严格单向：

```
┌──────────────────────────────────────┐
│  app/                                │  HTTP 路由、FastAPI 启动、请求校验
│  ├── api/v1/                         │  各 endpoint 模块
│  └── main.py                         │  ASGI 入口
├──────────────────────────────────────┤
│  application/                        │  业务逻辑层
│  ├── contracts/                      │  跨层协议（LLM Gateway 接口等）
│  ├── workflows/                      │  LangGraph 工作流编排
│  │   ├── core/                       │  工作流基础设施（state、checkpointing、errors、tracing）
│  │   ├── knowledge/                  │  知识提取工作流
│  │   ├── interview/                  │  采访上下文构建工作流
│  │   ├── generate/                   │  时间线/回忆录生成工作流
│  │   └── facade.py                   │  统一入口（WorkflowFacade）
│  ├── interview/                      │  采访 session 管理、对话存储
│  ├── knowledge/                      │  知识提取/精炼 application 逻辑
│  └── generate/                       │  生成 application 逻辑
├──────────────────────────────────────┤
│  domain/                             │  领域模型
│  ├── schemas/                        │  Pydantic 模型（事件、对话、知识）
│  └── events.py                       │  领域事件定义
├──────────────────────────────────────┤
│  infra/                              │  基础设施适配
│  ├── database/                       │  SQLite 客户端 + Store 模块
│  ├── embedding/                      │  Gemini 嵌入（sqlite-vec 向量检索）
│  ├── llm/                            │  LLM 网关（七牛云 API + 并发管理）
│  ├── storage/                        │  文件存储（MaterialStore）
│  ├── factories/                      │  LangGraph Runtime 构建器
│  └── utils/                          │  JSON 解析、文本分割等工具
├──────────────────────────────────────┤
│  core/                               │  横切关注
│  ├── config.py                       │  Pydantic Settings 配置
│  ├── security.py                     │  JWT 认证
│  └── paths.py                        │  数据路径管理
└──────────────────────────────────────┘
```

**层间规则：** `app` → `application` → `domain` ← `infra`。`infra` 实现 `application/contracts` 中定义的协议。

## LangGraph 工作流

系统通过 `WorkflowFacade`（[facade.py](src/application/workflows/facade.py)）统一调度三条 LangGraph 工作流：

| 工作流      | 触发方式                   | 功能                                    |
| ----------- | -------------------------- | --------------------------------------- |
| `knowledge` | 素材上传 / 重新处理        | 文件分块 → 事件提取 → 精炼 → 向量化    |
| `interview` | 采访 session 对话积累溢出  | 构建上下文（补充事件、情感锚点、建议）  |
| `generate`  | 用户手动触发               | 时间线生成 / 回忆录生成                 |

## API 端点

所有端点前缀 `/api/v1`，路由注册在 [app/api/v1/\_\_init\_\_.py](src/app/api/v1/__init__.py)。

### 认证

| 方法   | 路径               | 说明         | 认证 |
| ------ | ------------------ | ------------ | ---- |
| POST   | `/auth/register`   | 用户注册     | 无   |
| POST   | `/auth/login`      | 用户登录，写入 HttpOnly Session Cookie | 无   |
| GET    | `/auth/me`         | 获取当前登录用户 | Session Cookie / Bearer |
| POST   | `/auth/logout`     | 清空 Session Cookie | 无   |

### 采访 Session

| 方法   | 路径                              | 说明                   | 认证 |
| ------ | --------------------------------- | ---------------------- | ---- |
| POST   | `/session/create`                 | 创建采访会话           | Session Cookie / Bearer |
| POST   | `/session/{id}/message`           | 发送对话消息           | Session Cookie / Bearer |
| POST   | `/session/{id}/flush`             | 强制冲刷对话缓冲       | Session Cookie / Bearer |
| DELETE | `/session/{id}`                   | 关闭会话               | Session Cookie / Bearer |
| PATCH  | `/session/{id}/pending-event/{eid}/priority` | 切换待定事件优先级 | Session Cookie / Bearer |
| GET    | `/session/{id}/events`            | SSE 事件流             | Session Cookie / Bearer |

### 知识管理

| 方法   | 路径                                          | 说明                          | 认证 |
| ------ | --------------------------------------------- | ----------------------------- | ---- |
| POST   | `/knowledge/process`                          | 上传并处理素材（旧接口）      | Session Cookie / Bearer |
| POST   | `/knowledge/upload-material`                  | 批量上传素材                  | Session Cookie / Bearer |
| GET    | `/knowledge/materials`                        | 列出所有素材                  | Session Cookie / Bearer |
| GET    | `/knowledge/materials/{id}/content`           | 获取素材原文                  | Session Cookie / Bearer |
| DELETE | `/knowledge/materials/{id}`                   | 删除素材及关联数据            | Session Cookie / Bearer |
| POST   | `/knowledge/materials/{id}/reprocess`         | 触发重新结构化（异步）        | Session Cookie / Bearer |
| POST   | `/knowledge/materials/{id}/cancel`            | 取消进行中的结构化任务        | Session Cookie / Bearer |
| GET    | `/knowledge/materials/{id}/events`            | SSE 结构化进度流              | Session Cookie / Bearer |
| GET    | `/knowledge/records`                          | 列出文本 chunks               | Session Cookie / Bearer |
| GET    | `/knowledge/events`                           | 列出已提取事件                | Session Cookie / Bearer |
| GET    | `/knowledge/profiles`                         | 获取人物侧写                  | Session Cookie / Bearer |

### 生成

| 方法   | 路径                  | 说明           | 认证 |
| ------ | --------------------- | -------------- | ---- |
| POST   | `/generate/timeline`  | 生成时间线     | Session Cookie / Bearer |
| POST   | `/generate/memoir`    | 生成回忆录     | Session Cookie / Bearer |
| GET    | `/generate/timeline/saved` | 读取已保存时间线 | Session Cookie / Bearer |
| GET    | `/generate/memoir/saved`   | 读取已保存回忆录 | Session Cookie / Bearer |

### ASR（语音识别）

| 方法   | 路径          | 说明                          | 认证 |
| ------ | ------------- | ----------------------------- | ---- |
| GET    | `/asr/sign`   | 获取讯飞 RTASR WebSocket 签名 | Session Cookie / Bearer |

## 启动

```bash
cp .env.example .env          # 填入 JWT_SECRET_KEY、TRUSTED_HOSTS 与 API 密钥
uv venv && source .venv/bin/activate
uv pip install .
uvicorn src.app.main:app --reload --port 8000
```

环境变量说明见 [.env.example](.env.example)。

## 部署约束

- 当前后端的 interview session 与 material SSE registry 仍是内存态，因此生产环境默认强制单实例锁，避免多 worker / 多实例把状态打散。
- 需要横向扩容前，应先把这些状态迁到 Redis 等共享存储，再关闭 `ECHOES_ENABLE_SINGLE_INSTANCE_LOCK`。
- 前端默认通过 `HttpOnly` Session Cookie 鉴权；如前后端跨站点部署且浏览器需携带 cookie，必须在 TLS 下配置 `SESSION_COOKIE_SAMESITE=none` 和 `SESSION_COOKIE_SECURE=true`。

## 开发检查

从仓库根目录执行统一检查命令：

```bash
./scripts/check_backend.sh
```

如果只想在 backend 目录内运行测试：

```bash
cd backend
.venv/bin/pytest -q tests
```

> 已通过 `tests/conftest.py` 统一导入路径，无需手动设置 `PYTHONPATH`。
