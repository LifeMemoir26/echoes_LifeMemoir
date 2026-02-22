"""
MaterialStore — 原始材料文件持久化与元数据管理
"""

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    """将文件名中的非 ASCII 安全字符替换为下划线，保留中文和常见字符。"""
    # 只替换路径分隔符和控制字符
    return re.sub(r'[/\\:\*\?"<>|\x00-\x1f]', "_", name)


class MaterialStore:
    """
    原始材料文件存储与 materials 元数据管理。

    文件命名规范：
    - 用户上传文档：{原始文件名}-{时间戳}（如 1990年日记.txt-20260220T143052）
    - 采访记录：采访记录-{时间戳}
    """

    def __init__(self, data_base_dir: Path):
        """
        Args:
            data_base_dir: 数据根目录（data/），各用户子目录在此下创建。
        """
        self.data_base_dir = Path(data_base_dir)

    def save_file(
        self,
        username: str,
        filename: str,
        content_bytes: bytes,
        material_type: str = "document",
    ) -> Tuple[str, str]:
        """
        将上传的文件写入 data/{username}/materials/ 目录。

        Args:
            username: 用户名
            filename: 原始文件名（如 "1990年日记.txt"）
            content_bytes: 文件内容（UTF-8 字节）
            material_type: "interview" | "document"

        Returns:
            (material_id, relative_file_path)
            material_id: UUID 前 8 位
            relative_file_path: 相对于 data/{username}/ 的路径字符串
        """
        material_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

        if material_type == "interview":
            stored_name = f"采访记录-{timestamp}"
        else:
            safe_name = _safe_filename(filename)
            stored_name = f"{safe_name}-{timestamp}"

        user_materials_dir = self.data_base_dir / username / "materials"
        user_materials_dir.mkdir(parents=True, exist_ok=True)

        file_path = user_materials_dir / stored_name
        file_path.write_bytes(content_bytes)

        relative_path = f"materials/{stored_name}"
        logger.info(f"材料文件已保存: {file_path} ({len(content_bytes)} 字节)")
        return material_id, relative_path
