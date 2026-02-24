"""Knowledge APIs backed by LangGraph workflows only."""

from __future__ import annotations

from pathlib import Path
from typing import Any


async def process_knowledge_file(
    file_path: Path,
    username: str,
    data_base_dir: Path | None = None,
    narrator_name: str | None = None,
    verbose: bool = False,
    material_type: str = "interview",
    material_context: str = "",
    material_id: str | None = None,
) -> dict[str, Any]:
    """Process one knowledge file via LangGraph workflow facade."""
    from ...application.workflows import WorkflowFacade

    facade = WorkflowFacade(
        username=username,
        data_base_dir=data_base_dir,
        verbose=verbose,
    )
    try:
        return await facade.process_knowledge_file(
            file_path=file_path,
            narrator_name=narrator_name,
            material_type=material_type,
            material_context=material_context,
            material_id=material_id,
        )
    finally:
        facade.close()
