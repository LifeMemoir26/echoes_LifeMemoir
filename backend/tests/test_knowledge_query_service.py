from pathlib import Path

from src.application.knowledge.query_service import KnowledgeQueryService


def test_read_material_content_not_found(tmp_path: Path):
    svc = KnowledgeQueryService()
    username = "u1"
    try:
        svc.read_material_content(username, "missing.txt")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        assert True
