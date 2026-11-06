"""V3.1: 16 stickers by default, 16 actual poses each, batches of four."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from sticker_pack_v31 import ALL_CAPTIONS, DEFAULT_CAPTIONS, choose_captions
from studio_v3 import assemble_v31, build_v3, main, pack_progress, plan_v3


def animated_frame(step: int):
    canvas = Image.new("RGBA", (256, 256))
    artist = ImageDraw.Draw(canvas)
    artist.ellipse((80, 32, 161, 112), fill="#F5BA91")
    artist.ellipse((101, 67, 109, 75), fill="#222222")
    artist.ellipse((134, 67, 142, 75), fill="#222222")
    artist.line((110, 88, 121 + step % 6, 94), fill="#953E3E", width=3)
    artist.rounded_rectangle((92, 114, 150, 174), radius=8, fill="#41516C")
    artist.line((103, 130, 69 - 2*step, 158-step), fill="#41516C", width=11)
    artist.line((146, 132, 178 + 2*step, 151 + step), fill="#41516C", width=11)
    artist.ellipse((64 - 2*step, 151-step, 76 - 2*step, 165-step), fill="#F5BA91")
    return canvas


def fill_action_frames(root, action):
    folder = root / action["frames_dir"]
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(16):
        animated_frame(i).save(folder / f"{i:03d}.png")


def test_exact_default_16_and_four_batches(tmp_path):
    root = tmp_path / "pack"
    project = plan_v3("角色", "private/reference.png", None, root)
    assert project["version"] == "3.1"
    assert [a["caption"] for a in project["actions"]] == list(DEFAULT_CAPTIONS)
    assert len(project["actions"]) == 16
    assert project["pack"]["count"] == 16
    assert project["pack"]["total_planned_frames"] == 256
    assert [b["count"] for b in project["batches"]] == [4, 4, 4, 4]
    assert [b["captions"] for b in project["batches"]][0] == list(DEFAULT_CAPTIONS[:4])
    assert (root / "batches" / "batch-04.json").is_file()
    assert "64 张" in (root / "batches" / "batch-01.md").read_text(encoding="utf8")
    assert project["actions"][0]["gesture"] != project["actions"][4]["gesture"]
    assert pack_progress(root / "production.json")["next_batch"] == 1


@pytest.mark.parametrize("count,batches", [(1, [1]), (4, [4]), (8, [4, 4]),
                                         (16, [4,4,4,4]), (24, [4]*6), (32, [4]*8)])
def test_count_overrides_default(count, batches, tmp_path):
    project = plan_v3("角色", "ref.png", None, tmp_path / f"pack-{count}", count=count)
    assert [b["count"] for b in project["batches"]] == batches
    assert len(project["actions"]) == count
    assert project["pack"]["total_planned_frames"] == 16 * count
    assert len(set(a["slug"] for a in project["actions"])) == count


def test_user_captions_override_and_partial_batch(tmp_path):
    custom = ["发财啦", "摸摸头", "来了", "抱抱", "周末快乐"]
    project = plan_v3("角色", "ref.png", custom, tmp_path / "custom")
    assert [a["caption"] for a in project["actions"]] == custom
    assert [b["count"] for b in project["batches"]] == [4, 1]
    assert project["pack"]["preset"] == "user-captions"
    assert len(ALL_CAPTIONS) == 32


def test_reject_duplicate_and_count_mismatch(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        choose_captions(["好的", "好的"])
    with pytest.raises(ValueError, match="must match"):
        choose_captions(["好的", "收到"], count=4)
    with pytest.raises(ValueError, match="between"):
        choose_captions(count=33)
    with pytest.raises(ValueError, match="empty"):
        choose_captions([])


def test_cli_without_actions_creates_default_16(tmp_path, capsys):
    root = tmp_path / "default"
    assert main(["plan", "--character", "自创IP",
                 "--reference", "private.png", "--output", str(root)]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["count"] == 16
    assert obj["frames_per_sticker"] == 16
    assert [b["count"] for b in obj["batches"]] == [4, 4, 4, 4]


def test_next_batch_only_needs_its_four_animations(tmp_path):
    root = tmp_path / "sample"
    project = plan_v3("Test", "private.png", ["A", "B", "C", "D", "E", "F", "G", "H"], root)
    with pytest.raises(ValueError, match="earlier batches"):
        build_v3(root / "production.json", "DejaVuSans.ttf", batch=2)
    for action in project["actions"][:4]:
        fill_action_frames(root, action)
    result = build_v3(root / "production.json", "DejaVuSans.ttf", batch=1)
    assert result["batch"] == 1
    assert len(result["actions"]) == 4
    assert (root / "build" / "batch-01" / "wechat-pack.zip").is_file()
    progress = pack_progress(root / "production.json")
    assert progress["next_batch"] == 2
    assert progress["batches"][0]["status"] == "technical_built"
    assert progress["batches"][1]["status"] == "planned"
    with pytest.raises(ValueError, match="Unfinished batch"):
        assemble_v31(root / "production.json")


def test_single_full_batch_automatically_assembles(tmp_path):
    root = tmp_path / "one-batch"
    project = plan_v3("Test", "private.png", ["A", "B", "C", "D"], root)
    for action in project["actions"]:
        fill_action_frames(root, action)
    result = build_v3(root / "production.json", "DejaVuSans.ttf")
    assert result["batch"] == 1
    assert result["complete_pack"]["count"] == 4
    with ZipFile(root / "build" / "complete-pack.zip") as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len([name for name in names if name.endswith(".gif")]) == 4
        assert "manifest.json" in names
    assert pack_progress(root / "production.json")["all_batches_built"] is True
