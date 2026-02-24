from pathlib import Path

from src.domain.schemas.knowledge import CharacterProfile, LifeEvent
from src.infra.database.sqlite_client import SQLiteClient


def test_sqlite_client_compat_methods_delegate_to_stores(tmp_path: Path):
    client = SQLiteClient(username="u1", data_base_dir=tmp_path)

    inserted = client.insert_events(
        [
            LifeEvent(year="2001", event_summary="入学", event_category=["教育"]),
            LifeEvent(year="2008", event_summary="毕业", event_category=["教育"]),
        ]
    )
    assert inserted == 2
    assert [e.event_summary for e in client.get_all_events()] == ["入学", "毕业"]

    pid = client.insert_character_profile(CharacterProfile(personality="内向", worldview="务实"))
    assert pid
    profile = client.get_character_profile()
    assert profile is not None
    assert "内向" in profile.personality

    assert client.insert_or_update_alias("张三", ["阿三"], "person") == 1
    aliases = client.get_all_aliases()
    assert aliases[0]["formal_name"] == "张三"

    client.insert_material(material_id="m1", filename="a.txt", material_type="document")
    row = client.get_material_by_id("m1")
    assert row is not None
    assert row["filename"] == "a.txt"

    client.update_material_status("m1", "done", events_count=2, chunks_count=3)
    row = client.get_material_by_id("m1")
    assert row is not None
    assert row["status"] == "done"
    assert row["events_count"] == 2

    assert client.delete_material("m1") is True
    assert client.get_material_by_id("m1") is None

    client.close()
