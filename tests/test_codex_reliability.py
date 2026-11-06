"""Codex-oriented tests: preflight, complete delivery and deliberate corruption."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from codex_doctor import preflight
from studio_v3 import plan_v3, build_v3
from validate_delivery import verify_batch, verify_complete


def frame(i):
    art=Image.new("RGBA",(256,256))
    p=ImageDraw.Draw(art)
    p.ellipse((80,28,160,113),fill=(245,188,147,255))
    p.ellipse((102,64,110,72),fill=(22,20,20,255))
    p.ellipse((134,64,142,72),fill=(22,20,20,255))
    p.line((114,91,127+i%6,94),fill=(111,48,60,255),width=3)
    p.rounded_rectangle((90,110,152,178),radius=9,fill=(71,82,115,255))
    p.line((100,130,70-2*i,154-i),fill=(71,82,115,255),width=11)
    p.line((146,130,175+2*i,153-i),fill=(71,82,115,255),width=11)
    p.ellipse((65-2*i,147-i,79-2*i,161-i),fill=(245,188,147,255))
    return art


def ready_pack(tmp_path, captions=("OK", "YES", "NO", "HI")):
    root=tmp_path/"work"
    project=plan_v3("Example","private/character.png",list(captions),root)
    for action in project["actions"]:
        target=root/action["frames_dir"]
        target.mkdir(parents=True,exist_ok=True)
        for i in range(16):
            frame(i).save(target/f"{i:03d}.png")
    return root,project


def test_plan_preflight_does_not_claim_model_is_available():
    output=preflight(stage="plan",route="video")
    assert output["status"]=="ready_for_stage"
    model=next(x for x in output["checks"] if x["name"]=="model_generation")
    assert model["status"]=="unknown"
    assert "user-authorized" in model["detail"]


def test_import_video_only_requires_ffmpeg_at_import_stage(monkeypatch):
    import codex_doctor
    original=codex_doctor.shutil.which
    monkeypatch.setattr(codex_doctor.shutil,"which",lambda exe: None if exe=="ffmpeg" else original(exe))
    result=preflight(stage="import",route="video")
    assert result["status"]=="blocked"
    assert "ffmpeg" in result["blockers"]
    result=preflight(stage="import",route="existing")
    assert result["status"]=="ready_for_stage"


def test_build_preflight_fails_closed_on_missing_frames_and_font(tmp_path):
    root=tmp_path/"unready"
    plan_v3("Example","ref.png",["OK"],root)
    result=preflight(stage="build",project=root/"production.json")
    assert result["status"]=="blocked"
    assert "caption_font" in result["blockers"]
    assert "frames:custom-01" in result["blockers"]


def test_real_batch_passes_preflight_and_zip_validation(tmp_path):
    root,project=ready_pack(tmp_path)
    ready=preflight(stage="build",project=root/"production.json",font="DejaVuSans.ttf")
    assert ready["status"]=="ready_for_stage",ready
    result=build_v3(root/"production.json","DejaVuSans.ttf")
    assert result["v3_full_performance"]
    checked=verify_batch(root/"production.json",1)
    assert checked["status"]=="technical_pass_visual_review_pending",checked
    assert checked["expected_gifs"]==4
    assert checked["verified_gifs"]==4
    assert all(x["bytes"]<=500000 and x["frames"]>=12 for x in checked["files"])
    assert all(x["caption_text_verification"]=="requires_visual_review" for x in checked["files"])
    all_pack=verify_complete(root/"production.json")
    assert all_pack["status"]=="technical_pass_visual_review_pending",all_pack
    assert all_pack["expected_gifs"]==4
    assert (root/"build"/"batch-01"/"delivery-validation.json").exists()


def test_bad_manifest_captions_are_rejected(tmp_path):
    root,_=ready_pack(tmp_path)
    build_v3(root/"production.json","DejaVuSans.ttf")
    zip_path=root/"build"/"batch-01"/"wechat-pack.zip"
    with ZipFile(zip_path) as original:
        names={name:original.read(name) for name in original.namelist()}
    manifest=json.loads(names["manifest.json"])
    manifest["items"][0]["caption"]="WRONG"
    names["manifest.json"]=json.dumps(manifest).encode()
    with ZipFile(zip_path,"w",ZIP_DEFLATED) as z:
        for name,data in names.items():
            z.writestr(name,data)
    result=verify_batch(root/"production.json",1)
    assert result["status"]=="blocked"
    assert any("captions" in issue for issue in result["issues"])


def test_stale_gif_inside_zip_is_rejected(tmp_path):
    root,_=ready_pack(tmp_path)
    build_v3(root/"production.json","DejaVuSans.ttf")
    zip_path=root/"build"/"batch-01"/"wechat-pack.zip"
    with ZipFile(zip_path) as original:
        names={name:original.read(name) for name in original.namelist()}
    first_gif=sorted(x for x in names if x.endswith(".gif"))[0]
    names[first_gif]=names[first_gif]+b"tampered"
    with ZipFile(zip_path,"w",ZIP_DEFLATED) as z:
        for name,data in names.items():
            z.writestr(name,data)
    result=verify_batch(root/"production.json",1)
    assert result["status"]=="blocked"
    assert any("differs" in issue for issue in result["issues"])


def test_codex_repo_scope_entry_exists_and_points_to_root():
    root=Path(__file__).resolve().parents[1]
    scope=root/".agents"/"skills"/"gif-sticker-studio"/"SKILL.md"
    assert scope.exists()
    content=scope.read_text(encoding="utf8")
    assert "name: gif-sticker-studio" in content
    assert "../../../scripts/studio_v4.py" in content

def test_codex_v4_build_command_applies_full_delivery_gate(tmp_path, capsys):
    from studio_v4 import main
    root, _ = ready_pack(tmp_path)
    exit_code = main(["build", str(root / "production.json"), "--font", "DejaVuSans.ttf"])
    assert exit_code == 0
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "technical_pass_visual_review_pending"
    assert response["gif_count"] == 4
    assert response["delivery_validation"] == "technical_pass_visual_review_pending"
    assert response["platform_acceptance"] == "not_checked"
    assert Path(response["batch_zip"]).exists()
