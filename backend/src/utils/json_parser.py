"""
鲁棒的JSON解析工具
从qiniu_client.py的实现中提取并增强
"""
import json
import logging
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


def parse_json_robust(
    content: str,
    *,
    strip_markdown: bool = True,
    auto_unwrap: bool = True,
    return_error_dict: bool = True
) -> Union[Any, dict]:
    """
    鲁棒地解析JSON响应
    
    处理以下情况：
    1. Markdown代码块包装（```json ... ```）
    2. 常见的包装格式（如 {"properties": {...}}）
    3. 解析失败时返回错误信息
    
    Args:
        content: 待解析的字符串
        strip_markdown: 是否移除markdown代码块标记
        auto_unwrap: 是否自动解包常见包装格式
        return_error_dict: 解析失败时是否返回包含错误的字典（False则抛出异常）
        
    Returns:
        解析后的Python对象（通常是dict或list）
        
    Raises:
        json.JSONDecodeError: 当return_error_dict=False且解析失败时
    """
    try:
        content = content.strip()
        
        # 1. 处理可能的markdown代码块包装
        if strip_markdown:
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        
        # 2. 解析JSON
        parsed = json.loads(content)
        
        # 3. 自动解包常见的包装格式
        if auto_unwrap and isinstance(parsed, dict):
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
        logger.warning(f"JSON解析失败: {e}")
        logger.debug(f"原始内容前500字符: {content[:500]}")
        
        if return_error_dict:
            return {
                "raw_content": content,
                "parse_error": str(e),
                "error_type": "JSONDecodeError"
            }
        else:
            raise


async def parse_json_robust_async(
    content: str,
    *,
    strip_markdown: bool = True,
    auto_unwrap: bool = True,
    llm_fix: bool = False,
    llm_client: Optional[Any] = None,
    fix_timeout: float = 120.0,
    return_error_dict: bool = True
) -> Union[Any, dict]:
    """
    鲁棒地解析JSON响应（异步版本，支持LLM修复）
    
    处理以下情况：
    1. Markdown代码块包装（```json ... ```）
    2. 常见的包装格式（如 {"properties": {...}}）
    3. 解析失败时可选用LLM修复
    4. 解析失败时返回错误信息或抛出异常
    
    Args:
        content: 待解析的字符串
        strip_markdown: 是否移除markdown代码块标记
        auto_unwrap: 是否自动解包常见包装格式
        llm_fix: 是否在解析失败时尝试用LLM修复
        llm_client: LLM客户端实例（需要有generate方法），llm_fix=True时必需
        fix_timeout: LLM修复的超时时间（秒）
        return_error_dict: 解析失败时是否返回包含错误的字典（False则抛出异常）
        
    Returns:
        解析后的Python对象（通常是dict或list）
        
    Raises:
        json.JSONDecodeError: 当return_error_dict=False且解析失败时
        ValueError: 当llm_fix=True但未提供llm_client时
    """
    try:
        content = content.strip()
        
        # 1. 处理可能的markdown代码块包装
        if strip_markdown:
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        
        # 2. 解析JSON
        parsed = json.loads(content)
        
        # 3. 自动解包常见的包装格式
        if auto_unwrap and isinstance(parsed, dict):
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
        logger.warning(f"JSON解析失败: {e}")
        logger.debug(f"原始内容前500字符: {content[:500]}")
        
        # 尝试用LLM修复
        if llm_fix:
            if not llm_client:
                raise ValueError("llm_fix=True时必须提供llm_client参数")
            
            try:
                import asyncio
                
                logger.info("🔧 尝试使用LLM修复JSON格式...")
                
                # 构建修复prompt
                fix_prompt = f"""你是一个JSON修复专家。下面有一个格式错误的JSON字符串，错误信息是：{e}

请你修复这个JSON，遵循以下规则：
1. 修复所有未闭合的字符串（添加缺少的引号）
2. 修复错误的转义字符（如 \\" 应该是 "）
3. 修复缺少的逗号、花括号、方括号
4. **非常重要**：保持原有的数据内容不变，不要删除任何字段
5. **非常重要**：输出完整的JSON，不要省略任何内容
6. **只输出JSON**，不要有任何其他文字或解释

错误的JSON：
```json
{content}
```

请直接输出修正后的完整JSON（不要用markdown代码块包裹）："""

                # 调用LLM修复
                fixed_content = await asyncio.wait_for(
                    llm_client.generate(prompt=fix_prompt, temperature=0.1),
                    timeout=fix_timeout
                )
                
                # 递归解析修复后的JSON（不再尝试LLM修复，避免无限递归）
                parsed = await parse_json_robust_async(
                    fixed_content,
                    strip_markdown=strip_markdown,
                    auto_unwrap=auto_unwrap,
                    llm_fix=False,
                    return_error_dict=False  # 修复后如果还失败就抛异常
                )
                
                logger.info("✅ LLM成功修复JSON格式")
                return parsed
                
            except asyncio.TimeoutError:
                logger.error(f"LLM修复JSON超时（{fix_timeout}秒）")
                if return_error_dict:
                    return {
                        "raw_content": content,
                        "parse_error": str(e),
                        "error_type": "JSONDecodeError",
                        "fix_timeout": True
                    }
                else:
                    raise
                    
            except json.JSONDecodeError as fix_e:
                logger.error(f"LLM修复后的JSON仍然无法解析: {fix_e}")
                if return_error_dict:
                    return {
                        "raw_content": content,
                        "parse_error": str(e),
                        "error_type": "JSONDecodeError",
                        "fix_error": str(fix_e)
                    }
                else:
                    raise
                    
            except Exception as fix_error:
                logger.error(f"LLM修复JSON失败: {fix_error}")
                if return_error_dict:
                    return {
                        "raw_content": content,
                        "parse_error": str(e),
                        "error_type": "JSONDecodeError",
                        "fix_exception": str(fix_error)
                    }
                else:
                    raise
        
        # 不使用LLM修复或修复失败
        if return_error_dict:
            return {
                "raw_content": content,
                "parse_error": str(e),
                "error_type": "JSONDecodeError"
            }
        else:
            raise
