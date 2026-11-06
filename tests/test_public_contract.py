"""Public-project contract: neutral plans and defaults with backwards compatibility."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from studio_v2 import _project, plan


def test_new_project_has_generic_public_schema(tmp_path):
    root = tmp_path / "pack"
    plan("示例角色", "assets/character.png", ["好的", "收到"], root, "illustration")
    data = json.loads((root / "production.json").read_text(encoding="utf-8"))
    assert data["schema"] == "gif-sticker-v2"
    assert _project(root / "production.json")["character"]["name"] == "示例角色"


def test_historic_schema_can_be_read_without_becoming_new_default(tmp_path):
    root = tmp_path / "pack"
    plan("Example", "assets/character.png", ["Hi"], root, "illustration")
    file = root / "production.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    data["schema"] = "legacy-gif-v2"
    file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert _project(file)["schema"] == "legacy-gif-v2"


def test_skill_is_general_and_not_a_personal_ip():
    skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
    assert "name: gif-sticker-studio" in skill
    assert "≤500000" in skill
    assert "每批4个" in skill
    assert "不预设" in skill or "不要假定" in skill
