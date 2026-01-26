# Echoes LifeMemoir - 图向量知识库构建模块

## 概述

本模块实现了从对话文本中提取知识并构建图向量知识库的完整流程。

### 核心功能

1. **多维度信息提取**
   - 实体提取（人物、地点、组织、时间）
   - 事件提取（人生经历、日常活动）
   - 时间推理与归一化（模糊时间 → 具体年份）
   - 情感分析（情感类别、强度、极性）
   - 说话风格分析（语气、句式、口头禅）

2. **图向量存储**
   - Neo4j 图数据库存储实体和关系
   - 向量索引支持语义搜索
   - 自动维护时间顺序链

3. **可扩展架构**
   - 适配器模式支持多种数据源
   - 插件化的提取器设计
   - LangGraph 编排的处理管道

## 快速开始

### 1. 环境准备

```bash
# 启动 Neo4j
docker-compose up -d neo4j

# 安装依赖
cd backend
pip install poetry
poetry install

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写配置
```

### 2. 处理对话

```bash
# 使用命令行脚本
python backend/scripts/process_dialogue.py \
    --input backend/.test/sample_dialogue.txt \
    --user-id 川普 \
    --verbose
```

### 3. 代码调用

```python
import asyncio
from app.knowledge_extraction.pipeline import ExtractionPipeline

async def main():
    # 创建管道
    pipeline = ExtractionPipeline(user_birth_year=1950)
    
    # 初始化
    await pipeline.initialize()
    
    # 处理对话
    dialogue = """
    志愿者: 爷爷，跟我讲讲您的故事吧。
    老人: 好啊，我1950年出生在山东...
    """
    
    result = await pipeline.process(
        text=dialogue,
        user_id="grandpa_wang",
    )
    
    print(f"提取了 {result.entities_extracted} 个实体")
    print(f"提取了 {result.events_extracted} 个事件")
    
    await pipeline.close()

asyncio.run(main())
```

## 项目结构

```
backend/
├── app/
│   └── knowledge_extraction/
│       ├── config.py              # 配置管理
│       ├── adapters/              # 数据源适配器
│       │   ├── base_adapter.py    # 适配器基类
│       │   └── dialogue_adapter.py # 对话适配器
│       ├── extractors/            # 信息提取器
│       │   ├── entity_extractor.py  # 实体提取
│       │   ├── event_extractor.py   # 事件提取
│       │   ├── temporal_extractor.py # 时间推理
│       │   ├── emotion_extractor.py  # 情感分析
│       │   └── style_extractor.py    # 风格分析
│       ├── graph_store/           # 图存储
│       │   ├── neo4j_client.py    # Neo4j 客户端
│       │   ├── graph_writer.py    # 图谱写入器
│       │   └── schema.py          # Schema 定义
│       ├── llm/                   # LLM 客户端
│       │   └── ollama_client.py   # Ollama 客户端
│       └── pipeline/              # 处理管道
│           └── extraction_pipeline.py  # 主管道
├── scripts/
│   └── process_dialogue.py        # 命令行入口
├── tests/
│   └── sample_dialogue.txt        # 测试数据
├── pyproject.toml                 # 项目配置
└── .env.example                   # 环境变量示例
```

## 图谱 Schema

### 节点类型

| 类型 | 描述 |
|------|------|
| User | 叙述者/被访谈者 |
| Person | 人物（亲人、朋友等） |
| Event | 事件 |
| TimePoint | 时间点 |
| Location | 地点 |
| Emotion | 情感 |
| SpeakingStyle | 说话风格 |
| Dialogue | 原始对话 |

### 关系类型

| 类型 | 描述 |
|------|------|
| EXPERIENCED | 用户经历了事件 |
| OCCURRED_AT | 事件发生于时间 |
| HAPPENED_IN | 事件发生于地点 |
| INVOLVED | 事件涉及人物 |
| EVOKED | 事件引发情感 |
| FOLLOWED_BY | 时间顺序链 |
| KNOWS | 用户认识某人 |
| HAS_STYLE | 用户说话风格 |

## 查询示例

```cypher
-- 获取用户的时间线
MATCH (u:User {id: 'grandpa_wang'})-[:EXPERIENCED]->(e:Event)
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(t:TimePoint)
RETURN e.description, t.year
ORDER BY t.year;

-- 查找特定年代的事件
MATCH (e:Event)-[:OCCURRED_AT]->(t:TimePoint)
WHERE t.year >= 1960 AND t.year < 1970
RETURN e.description, t.year;

-- 向量相似度搜索
CALL db.index.vector.queryNodes('event_embedding_idx', 5, $query_vector)
YIELD node, score
RETURN node.description, score;
```

## 扩展开发

### 添加新的数据源适配器

```python
from app.knowledge_extraction.adapters import BaseAdapter, StandardDocument

class WeChatAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(SourceType.WECHAT)
    
    def validate(self, raw_data: str | bytes) -> bool:
        # 验证微信导出格式
        pass
    
    def parse(self, raw_data: str | bytes, **kwargs) -> list[StandardDocument]:
        # 解析微信聊天记录
        pass
```

### 添加新的提取器

```python
from app.knowledge_extraction.extractors import BaseExtractor

class HealthExtractor(BaseExtractor):
    SYSTEM_PROMPT = "..."
    USER_PROMPT_TEMPLATE = "..."
    
    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT
    
    def get_user_prompt(self, content: str, **kwargs) -> str:
        return self.USER_PROMPT_TEMPLATE.format(content=content)
    
    async def extract(self, document: StandardDocument, **kwargs):
        # 提取健康相关信息
        pass
```

## 许可证

MIT License
