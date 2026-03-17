# Echoes LifeMemoir

AI 人生回忆录生成系统 —— 交互式采访 · 知识图谱 · 时间线 · 文学化回忆录

# 快速开始

## 环境准备

需要安装 4 个工具。已装的跳过，每步安装后**重新打开终端**再验证。

> **Git**（版本不限） — 验证：`git --version`
>
> - Windows：[下载安装包](https://git-scm.com/download/win)
> - macOS：`xcode-select --install`
> - Linux：`sudo apt install git`

> **Python ≥ 3.11** — 验证：`python --version`
>
> - 下载：https://www.python.org/downloads/
> - Windows **必须勾选 Add to PATH**

> **uv**（版本不限） — 验证：`uv --version`
>
> - macOS / Linux：`curl -LsSf https://astral.sh/uv/install.sh | sh`
> - Windows：[安装说明](https://docs.astral.sh/uv/getting-started/installation/#windows)

> **Node.js ≥ 20.9** — 验证：`node --version`
>
> - 下载：https://nodejs.org/zh-cn/ （选 LTS 版）

> 需要可以在 gemini 支持的地区科学访问网络

## 获取代码

```bash
git clone https://github.com/LifeMemoir26/echoes_LifeMemoir
cd echoes_LifeMemoir
```

## 启动后端

#### 1. 进入后端目录，复制配置文件

```bash
cd backend
cp .env.example .env
```

#### 2. 编辑 .env，填写 API 密钥（见 [必须配置项注释](backend/.env)）

#### 3. 安装依赖 & 启动

```bash
cd backend

uv venv

source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate.bat       # Windows 命令提示符
# .venv\Scripts\Activate.ps1       # Windows PowerShell

uv pip install .

python -m uvicorn src.app.main:app --reload --port 8000
```

> 激活成功后提示符前会出现 `(.venv)`。
> 看到 `Uvicorn running on http://127.0.0.1:8000` 即成功，**保持该终端运行**。

## 启动前端

另开一个新的终端窗口：

```bash
# 如未安装 pnpm：npm install -g pnpm
cd frontend
pnpm install

# 启动
pnpm run dev
```

## 访问应用

- **打开浏览器访问 `http://localhost:3000` 即可访问。**
- 可以新建一个用户命名为 `测试用户`，然后从 [网盘](https://disk.pku.edu.cn/link/AA08A32540A67143FFA3DE91C17DEB9456) 下载测试数据，上传到服务进行结构化

## 开发检查（低负载，推荐日常使用）

在仓库根目录执行：

```bash
# 一键执行前后端低负载检查
./scripts/check_quick.sh

# 后端（低负载）
# ./scripts/check_backend.sh

# 前端（低负载）
# ./scripts/check_frontend.sh
```

低负载检查默认只覆盖高频问题：

- 后端：`ruff` + `mypy` + 关键契约/鉴权测试（不跑全量测试）
- 前端：`lint` + `typecheck` + 单元测试

> 说明：`check_backend.sh` 会自动使用 `backend/.venv`。

### 全量检查（提交前/合并前）

如需完整回归，请手动执行全量测试：

```bash
cd backend
uv pip install --python .venv/bin/python pytest
PYTHONPATH=. ./.venv/bin/pytest -q tests
cd ../frontend && pnpm -s check:contract
```

# 深入了解

| 文档                                                                 | 内容                                 |
| -------------------------------------------------------------------- | ------------------------------------ |
| [backend/README.md](backend/README.md)                               | 分层架构、LangGraph 工作流、API 端点 |
| [backend/docs/llm-api-call-map.md](backend/docs/llm-api-call-map.md) | 工作流与提示词指南                   |
| [frontend/README.md](frontend/README.md)                             | 路由架构、组件结构、设计系统         |
| [frontend/API_INTEGRATION.md](frontend/API_INTEGRATION.md)           | API 契约（请求/响应/SSE/错误码）     |

**技术栈：** FastAPI 0.132 · LangGraph 1.0 · SQLite + sqlite-vec · Next.js 16 · React 19 · Tailwind CSS 4.2
