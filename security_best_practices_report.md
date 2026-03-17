# Security / Deployment Review

## Executive Summary

当前代码不能保证“文件不泄露”和“2~3 个用户同时在线也不崩溃”。

我没有在现有 HTTP 处理链里看到明显的“跨用户直接读到别人文件”的接口漏洞：大多数读写接口都会先从 JWT 中取当前用户名，再访问 `data/{username}` 下的数据库和文件。

但我确认了 5 个会直接影响上线安全性和稳定性的风险。其中 1 个是可导致任意伪造登录的严重问题，2 个会在部署成多进程或并发任务增多后导致会话/SSE 失效或 SQLite 锁冲突，另外 2 个会增加令牌泄露和内存打爆的概率。

## Critical

### CRIT-001 已知默认 JWT 密钥可在“未显式声明生产环境”时生效

- Rule ID: FASTAPI-AUTH-001 / FASTAPI-AUTH-002
- Severity: Critical
- Location: `backend/src/core/security.py:18-30`, `backend/.env.example:1-64`
- Evidence:
  - `backend/src/core/security.py:18-26` 默认把未设置环境视为 `development`，并在未配置 `JWT_SECRET_KEY` 时回退到固定值 `dev-insecure-secret-change-me-in-production`
  - `backend/.env.example` 里没有 `JWT_SECRET_KEY` 或 `ECHOES_ENV=production` 的部署模板项
- Impact:
  - 如果你按当前模板部署、但没有显式设置 `ECHOES_ENV=production` 和 `JWT_SECRET_KEY`，公网任何人都可以用已知密钥伪造任意用户名的 JWT，直接读取该用户的素材、事件、时间线和回忆录。
- Fix:
  - 启动时无条件要求 `JWT_SECRET_KEY` 存在，不要依赖“环境名是否是 production”才开启校验。
  - 在部署模板、README、启动脚本里明确要求设置强随机 `JWT_SECRET_KEY`。
  - 为已暴露环境轮换现有 JWT 密钥。
- Mitigation:
  - 上线前先在运行环境注入强随机 32+ 字节密钥，并确认日志中不再出现 fallback warning。
- False positive notes:
  - 只有在部署环境已经显式设置了强随机 `JWT_SECRET_KEY` 时，这个风险才会被消除。

## High

### HIGH-001 会话与素材处理状态都放在进程内内存，不能安全扩成多 worker

- Rule ID: FASTAPI-DEPLOY-001
- Severity: High
- Location: `backend/src/application/interview/session_registry.py:39-149`, `backend/src/app/api/v1/material_registry.py:13-99`, `backend/src/app/api/v1/interview.py:121-151`, `backend/src/application/knowledge/query_service.py:329-331`
- Evidence:
  - `SessionRegistry` 和 `MaterialProcessingRegistry` 都是模块级单例，状态只存在当前 Python 进程内
  - `send_message` / `flush` / `reprocess` 都用 `asyncio.create_task(...)` 把任务挂在当前进程事件循环
- Impact:
  - 只要你为了并发或稳定性开多个 Uvicorn worker、或者容器被重启/滚动发布，同一用户的活跃 session、SSE 订阅、素材重处理任务状态就会丢失或分叉。
  - 结果通常不是“慢一点”，而是会出现重复 session、SSE 收不到事件、前端一直卡住、任务无法取消等线上故障。
- Fix:
  - 把 session registry / material registry / 后台任务元数据迁到 Redis 或数据库。
  - 如果短期内不改架构，就只能明确限制为单 worker 单实例部署，并接受单点故障。
- Mitigation:
  - 在生产入口固定 `workers=1`，并关闭自动扩缩容；这只能降低风险，不能解决进程重启后的状态丢失。
- False positive notes:
  - 如果你确认永远只跑一个进程，这条不会立刻触发分布式一致性问题，但重启丢状态仍然存在。

### HIGH-002 用户级 SQLite / Chunk DB 未做 WAL 与 busy_timeout，后台任务并发下容易锁库

- Rule ID: FASTAPI-DEPLOY-001
- Severity: High
- Location: `backend/src/infra/database/sqlite_client.py:30-35`, `backend/src/infra/database/store/material_store.py:21-68`, `backend/src/infra/database/store/chunk_store.py:71-89`, `backend/src/app/api/v1/interview.py:121-151`, `backend/src/application/knowledge/query_service.py:222-242`, `backend/src/application/knowledge/query_service.py:329-412`
- Evidence:
  - `GlobalDB` 启用了 `PRAGMA journal_mode=WAL` 和 `busy_timeout=30000`，但用户级 `SQLiteClient` 与 `ChunkStore` 没有同样设置
  - 采访消息处理、flush、知识重处理都在后台任务里并发运行，并且会落盘到用户数据库/向量库
- Impact:
  - 2~3 个用户同时上传、重处理、生成或对话时，很容易出现 `database is locked`、状态写入失败、处理链中断。
  - 这类问题通常表现为“偶发崩溃/失败重试”，最难排查。
- Fix:
  - 给 `SQLiteClient` 和 `ChunkStore` 统一开启 WAL、busy_timeout，并评估事务边界。
  - 避免多条后台任务同时写同一用户数据库；必要时加用户级写队列/锁。
  - 增加并发集成测试，至少覆盖“同一用户同时 message/flush/reprocess”和“两个用户同时上传”。
- Mitigation:
  - 上线初期限制每个用户同一时刻只能跑一个重任务，降低锁竞争概率。
- False positive notes:
  - 单用户低频操作时可能暂时不出现，但这不是安全边界，只是未触发。

## Medium

### MED-001 Bearer Token 存在 localStorage，前端没有看到 CSP / 安全头配置

- Rule ID: REACT-CONFIG-001 / REACT-XSS-002
- Severity: Medium
- Location: `frontend/lib/auth/token.ts:1-20`, `frontend/next.config.ts:3-13`, `frontend/app/layout.tsx:10-22`
- Evidence:
  - `frontend/lib/auth/token.ts` 把访问令牌和用户名直接写入 `localStorage`
  - `frontend/next.config.ts` 只有 rewrite，没有任何安全响应头
  - 仓库里没有看到 CSP、`X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy` 的应用层配置
- Impact:
  - 一旦前端出现 XSS、恶意浏览器扩展或第三方脚本污染，攻击者可以直接拿走 JWT，随后读取该用户全部受保护文件与内容。
- Fix:
  - 最稳妥的是改成后端签发 `HttpOnly` Cookie，前端不直接持有 Bearer Token。
  - 同时补上 CSP 和基础安全头；如果这些头在 Nginx/Ingress 里下发，需要把配置纳入部署文档。
- Mitigation:
  - 在切换鉴权方式前，至少先补 CSP，并确保前端不渲染任何未净化 HTML。
- False positive notes:
  - 这条不代表当前已经存在 XSS，只是说明一旦有 XSS，损失会直接升级成账户与文件泄露。

### MED-002 批量上传接口一次性把整文件读进内存，缺少总量限制与边缘层限流

- Rule ID: FASTAPI-DEPLOY-001
- Severity: Medium
- Location: `backend/src/application/knowledge/query_service.py:180-193`, `backend/src/app/api/v1/knowledge.py:179-218`
- Evidence:
  - `upload_materials()` 对每个文件直接 `content = await upload.read()`
  - 只限制了“单文件 10MB”，没有限制批量文件数、总请求体积，也没看到 Nginx/Caddy/Ingress 侧的请求大小限制
- Impact:
  - 2~3 个用户同时批量上传时，内存占用会叠加到应用进程里，容易触发 OOM、长 GC 停顿或请求超时。
- Fix:
  - 改成流式落盘，不要把整文件一次性读到内存。
  - 增加单请求总字节数、单次文件数上限。
  - 在反向代理层补 `client_max_body_size` / 请求超时 / 限流。
- Mitigation:
  - 运营上先限制上传行为，只允许单文件或极小批次。
- False positive notes:
  - 小文件测试通常没事，但这类问题在真实上传峰值时才会暴露。

### MED-003 旧上传接口会把服务器绝对存储路径返回给客户端

- Rule ID: FASTAPI-OPENAPI-001
- Severity: Medium
- Location: `backend/src/application/knowledge/query_service.py:138-143`, `backend/src/app/api/v1/knowledge.py:132-141`
- Evidence:
  - `process_uploaded_knowledge_file()` 返回 `stored_path=str(stored_path)`
  - `/knowledge/process` 直接把该字段透传给客户端
- Impact:
  - 这会向客户端暴露服务器文件系统布局，属于不必要的信息泄露；单独看不一定能直接读文件，但会降低后续攻击成本。
- Fix:
  - 不返回物理路径，只返回 `material_id` 或逻辑资源路径。
- Mitigation:
  - 如果旧接口已不再使用，至少在网关层下线它。
- False positive notes:
  - 这是信息泄露，不是直接任意文件读取；但没必要保留。

## Verification Performed

- Backend quick check: `./scripts/check_backend.sh` 通过
- Backend targeted tests: `test_security_env_guard.py`, `test_session_registry_cleanup.py`, `test_sqlite_client_boundary.py`, `test_api_error_contracts.py`, `test_unhandled_exception_handler.py` 通过
- Frontend unit tests: `token`, `api-client`, `interview-sse` 等 11 个测试文件通过

## Recommended Deployment Decision

当前状态不建议直接公网部署。

最少应先完成以下 4 项再上线：

1. 强制配置 `JWT_SECRET_KEY`，移除默认固定 JWT 密钥。
2. 明确部署为单实例单 worker，或者把 session/material 状态迁到 Redis。
3. 给用户级 SQLite / chunk DB 加 WAL、busy_timeout，并做并发写测试。
4. 限制上传总量，避免整文件读入内存。
