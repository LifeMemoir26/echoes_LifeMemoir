"""
鲁棒的JSON解析工具

为ConcurrencyManager提供JSON解析和修复的工具函数
不直接调用LLM，只提供：
1. 基础JSON解析（去markdown、解包）
2. 生成修复prompt的函数
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_json_basic(content: str) -> Optional[dict]:
    """
    基础JSON解析（去markdown、解包），不调用LLM
    
    Args:
        content: 待解析的字符串
        
    Returns:
        解析成功返回字典，失败返回None
    """
    try:
        content = content.strip()
        
        # 1. 去除markdown代码块
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # 2. 解析JSON
        parsed = json.loads(content)
        
        # 3. 自动解包常见包装格式
        if isinstance(parsed, dict):
            # {"properties": {...}} 包装
            if "properties" in parsed and len(parsed) == 1:
                logger.debug("检测到 {'properties': ...} 包装格式，自动解包")
                parsed = parsed["properties"]
            
            # {"$PARAMETER_NAME": {...}} 包装
            elif len(parsed) == 1:
                key = list(parsed.keys())[0]
                if key.startswith("$") or key.upper() == "PARAMETER_NAME":
                    logger.debug(f"检测到 {{'{key}': ...}} 包装格式，自动解包")
                    parsed = parsed[key]
        
        return parsed
        
    except json.JSONDecodeError as e:
        logger.debug(f"JSON基础解析失败: {e}")
        return None
    except Exception as e:
        logger.error(f"JSON解析异常: {e}")
        return None


def create_fix_prompt(broken_json: str) -> tuple[str, str]:
    """
    生成JSON修复的prompt（分离system和user）
    
    Args:
        broken_json: 格式错误的JSON字符串
        
    Returns:
        (system_prompt, user_prompt) 元组
    """
    system_prompt = """你是一个JSON修复专家，负责修复格式错误的JSON字符串。

你的任务：
- 修复所有未闭合的字符串（添加缺少的引号）
- 修复错误的转义字符
- 修复缺少的逗号、花括号、方括号
- 保持原有数据内容完全不变
- 输出完整的JSON，不省略任何内容
- 只输出JSON，严禁任何解释或其他文字"""
    
    user_prompt = f"""请修复下面这个格式错误的JSON：

```json
{broken_json}
```

直接输出修正后的完整JSON（不要用markdown代码块包裹）："""
    
    return system_prompt, user_prompt
