"""
项目路径管理
提供项目根目录的智能识别
"""
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """
    获取项目根目录（通过向上查找标记文件）
    
    标记文件优先级：
    1. .git/ 目录（版本控制根目录）
    2. README.md + backend/ 组合（项目结构标识）
    
    Returns:
        项目根目录的绝对路径
        
    Raises:
        RuntimeError: 如果无法找到项目根目录
    """
    current = Path(__file__).resolve()
    
    # 向上查找，最多查找10层
    for _ in range(10):
        current = current.parent

        # 检查标记：有 backend/ 子目录
        if (current / "backend").is_dir():
            return current    
        # 检查标记：有 .gitgnore 文件
        if (current / ".gitignore").is_file():
            return current
    
    raise RuntimeError(
        "无法找到项目根目录。请确保：\n"
        "1. 项目包含 backend/ 目录 \n"
        "2. 项目包含 .gitignore 文件 \n"
    )


@lru_cache(maxsize=1)
def get_backend_root() -> Path:
    """
    获取 backend 目录（包含 src/, scripts/, pyproject.toml）
    
    Returns:
        backend 目录的绝对路径
    """
    project_root = get_project_root()
    backend_dir = project_root / "backend"
    
    if not backend_dir.exists():
        raise RuntimeError(f"Backend 目录不存在: {backend_dir}")
    
    return backend_dir


@lru_cache(maxsize=1)
def get_data_root() -> Path:
    """
    获取数据存储根目录
    
    Returns:
        data/ 目录的绝对路径
    """
    project_root = get_project_root()
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@lru_cache(maxsize=1)
def get_log_root() -> Path:
    """
    获取日志根目录
    
    Returns:
        .log/ 目录的绝对路径
    """
    project_root = get_project_root()
    log_dir = project_root / ".log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
