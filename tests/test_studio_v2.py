"""Regression tests for V2 planning, deterministic repair and actual GIF build."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from studio_v2 import analyze, atlas, build, plan, read_frames, repair


def pose(x=90, color=(240, 100, 130), size=192):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    d.ellipse((x - 26, 35, x + 26, 96), fill=(*color, 255))
    d.rectangle((x - 16, 96, x + 16, 150), fill=(*color, 255))
    return im


def save_poses(folder: Path, count=16):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        pose(90 + (i % 7) * 2).save(folder / f"{i:03d}.png")


def test_production_plan_has_separate_storyboards(tmp_path):
    root = tmp_path / "work"
    result = plan("示例角色", "my-private-character.png", ["哈哈", "委屈", "收到", "哼"], root, "illustration")
    assert [a["slug"] for a in result["actions"]] == ["laugh", "hurt", "received", "hmph"]
    assert all(len(a["keyframes"]) == 16 for a in result["actions"])
    assert all((root / "prompts" / f"{a['slug']}.txt").exists() for a in result["actions"])
    assert (root / "production.json").is_file()
    with pytest.raises(FileExistsError):
        plan("示例角色", "image.png", ["收到"], root, "illustration")
    with pytest.raises(ValueError):
        plan("示例角色", "image.png", ["收到", "收到"], tmp_path / "other", "illustration")


def test_inspection_flags_blank_or_clipped_frames():
    frames = [pose(90 + (i % 4)) for i in range(16)]
    frames[5] = Image.new("RGBA", (192, 192))
    frames[9] = pose(20)
    report = analyze(frames)
    assert report["status"] == "blocked"
    assert any(e["code"] == "empty" and 5 in e["frames"] for e in report["issues"])
    assert any(e["code"] == "clipped_or_no_gutter" and 9 in e["frames"] for e in report["issues"])
    assert report["visual_acceptance"] == "pending"


def test_inspection_detects_all_duplicate_frames_and_motion_risks():
    report = analyze([pose() for _ in range(16)])
    assert report["status"] == "blocked"
    assert any(e["code"] == "no_real_motion" for e in report["issues"])
    other = [pose(70) for _ in range(8)] + [pose(120) for _ in range(8)]
    report = analyze(other)
    assert any(e["code"] == "position_jump" for e in report["issues"])
    assert any(e["code"] == "loop_seam" for e in report["issues"])


def test_inspection_no_false_claim_of_visual_approval():
    frames = [pose(88 + i % 5 * 2) for i in range(16)]
    report = analyze(frames)
    assert report["status"] != "blocked"
    assert report["user_acceptance"] == "pending"


def test_explicit_repairs_and_no_clipping(tmp_path):
    source = tmp_path / "frames"
    save_poses(source)
    replacement = tmp_path / "replacement.png"
    pose(96, (100, 150, 250)).save(replacement)
    corrections = tmp_path / "corrections.json"
    corrections.write_text(json.dumps({"3": {"replace": "replacement.png"}, "6": {"shift": [3, -2]}}))
    output = tmp_path / "fixed"
    log = repair(source, corrections, output)
    assert len(log) == 2
    assert read_frames(output)[3].getpixel((96, 48))[2] == 250
    assert (output / "repair-log.json").exists()
    with pytest.raises(FileExistsError):
        repair(source, corrections, output)
    (tmp_path / "bad.json").write_text('{"1": {"shift": [300, 0]}}')
    with pytest.raises(ValueError, match="clipped"):
        repair(source, tmp_path / "bad.json", tmp_path / "new")


def test_atlas_maintains_exact_shared_coordinates(tmp_path):
    frames = [pose(88+i%4) for i in range(16)]
    output = tmp_path / "atlas.png"
    atlas(frames, output)
    with Image.open(output) as im:
        assert im.size == (768, 768)
        assert im.getpixel((10, 10))[3] == 0
        assert im.getpixel((192+90, 45))[3] == 255


def test_rejects_incomplete_frames(tmp_path):
    source = tmp_path / "frames"
    save_poses(source, count=15)
    with pytest.raises(ValueError, match="Missing"):
        read_frames(source, 16)


def test_batch_build_real_gif_pipeline(tmp_path):
    from studio_v2 import _project
    root = tmp_path / "studio"
    plan("Test", "reference.png", ["OK"], root, "illustration")
    action = _project(root / "production.json")["actions"][0]
    save_poses(root / action["frames_dir"])
    result = build(root / "production.json", "DejaVuSans.ttf", max_bytes=500000)
    assert result["status"] == "technical_export_complete"
    assert result["actions"][0]["export"]["bytes"] <= 500000
    assert (root / "build" / "wechat-pack.zip").is_file()
    assert (root / "build" / "reports" / "custom-01-contact.png").is_file()
    assert result["actions"][0]["visual_acceptance"] == "pending"
