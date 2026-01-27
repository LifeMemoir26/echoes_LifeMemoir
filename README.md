# 快速开始

## 1. 安装依赖

进入 `backend` 目录并安装项目依赖：

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install .
```

## 2. 配置环境变量

1. 复制环境配置模板：

   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件，填入核心配置：

   ```ini
   # API 密钥池 (支持多 Key 轮询以提高并发稳定性，格式: key1,key2,key3)
   LLM_API_KEYS_STR=sk-your-key-1,sk-your-key-2

   # ---------- 模型选择 ----------
   LLM_EXTRACTION_MODEL=claude-3.7-sonnet # 提取模型
   ```

## 3. 运行流程测试

运行以下命令：

```bash
python backend/scripts/run_pipeline.py
```

### 脚本说明

该脚本 (`backend/scripts/run_pipeline.py`) 会自动执行架构文档中描述的两个阶段：

1.  **阶段一 (Knowledge Graph)**:
    - 读取 `backend/examples/1.txt`。
    - 并发提取事件与侧写。
    - 执行 LLM 精炼循环 (Refinement Loop)。
    - 结果存入 `data/{用户名}/database.db`。

2.  **阶段二 (Vector Store)**:
    - 基于 `batch_size=15` 并发提取摘要。
    - 使用 `acge_text_embedding` 生成向量。
    - 串行流式写入 `data/{用户名}/chromadb`。

## 4. 验证结果

脚本运行结束后，请检查 `data/` 目录下的生成文件和`.log/`目录下的日志文件，以确认处理是否成功完成。
