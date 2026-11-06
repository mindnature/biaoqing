"""V4 pipeline tests: real imported motion, quality gate and offline review."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from studio_v4 import (FRAME_COUNT, _chroma_auto, _common_canvas, import_media,
                       pick_frames, plan_project, remove_chroma, review)


def acting_frame(i: int, bg="green") -> Image.Image:
    im=Image.new("RGBA",(240,240),(0,220,0,255) if bg=="green" else (0,0,0,0))
    p=ImageDraw.Draw(im)
    p.ellipse((82,27,159,112),fill=(244,187,150,255))
    p.ellipse((103,65,109,73),fill=(31,32,32,255))
    p.ellipse((134,63+i//6,140,71+i//6),fill=(31,32,32,255))
    p.arc((113,78,135,96+i//2),start=0,end=150,fill=(80,34,36,255),width=3)
    p.rounded_rectangle((93,112,151,173),radius=6,fill=(56,71,102,255))
    p.line((103,126,77-i*3,157-i),fill=(56,71,102,255),width=11)
    p.ellipse((70-i*3,151-i,84-i*3,165-i),fill=(244,187,150,255))
    p.line((143,126,177+i*2,153-i*2),fill=(56,71,102,255),width=11)
    p.ellipse((172+i*2,146-i*2,184+i*2,159-i*2),fill=(244,187,150,255))
    return im


def setup_project(tmp_path,actions=None):
    root=tmp_path/"workspace"
    p=plan_project("Generic Character","private/character.png",root,actions or ["好的"])
    return root,p


def test_v4_plan_preserves_16_and_writes_video_prompts(tmp_path):
    root,p=setup_project(tmp_path)
    assert p["workflow_version"]=="4.0"
    assert p["version"]=="3.1"  # current exporter compatibility
    assert p["pack"]["frames_per_sticker"] == 16
    action=p["actions"][0]
    prompt=(root/"generation"/f"{action['slug']}-video.txt").read_text(encoding="utf8")
    assert "MP4" in prompt and "chroma background" in prompt
    assert p["model_backend"]=="user-authorized-external-agent"


def test_auto_key_green_and_real_alpha():
    key=_chroma_auto([acting_frame(0)])
    assert key=="green"
    cleaned=remove_chroma(acting_frame(0),"green")
    assert cleaned.getpixel((0,0))[3]==0
    assert cleaned.getpixel((120,45))[3]>220
    assert _chroma_auto([cleaned])=="alpha"


def test_import_green_frame_folder_then_offline_review(tmp_path):
    root,p=setup_project(tmp_path)
    source=tmp_path/"input_frames";source.mkdir()
    for i in range(16):
        acting_frame(i).save(source/f"frame-{i:03d}.png")
    target=p["actions"][0]["slug"]
    result=import_media(source,root/"production.json",target)
    assert result["source_kind"]=="png-frames"
    assert result["background_mode"]=="green"
    assert result["sampling"]["source_count"]==16
    assert result["performance"]["status"]!="blocked",result["performance"]
    folder=root/"frames"/target
    assert len(list(folder.glob("[0-9][0-9][0-9].png")))==16
    with Image.open(folder/"000.png") as img:
        assert img.size==(256,256)
        assert img.getpixel((0,0))[3]==0
    result=review(root/"production.json",target)
    assert Path(result["html"]).exists()
    page=Path(result["html"]).read_text(encoding="utf8")
    assert "data:image/png;base64" in page
    assert "逐帧审核" in page
    assert result["user_acceptance"]=="pending"
    assert Path(result["contact_sheet"]).exists()
    with pytest.raises(FileExistsError):
        import_media(source,root/"production.json",target)


def test_import_static_poses_is_rejected_by_acting_gate(tmp_path):
    root,p=setup_project(tmp_path)
    source=tmp_path/"stillframes";source.mkdir()
    for i in range(16):
        acting_frame(0).save(source/f"frame-{i:03d}.png")
    result=import_media(source,root/"production.json",p["actions"][0]["slug"])
    assert result["performance"]["status"]=="blocked"
    assert any(e["code"] in ("no_real_motion","whole_sprite_only") for e in result["performance"]["issues"])


def test_dont_fabricate_frames():
    with pytest.raises(ValueError,match="cannot fabricate"):
        pick_frames([acting_frame(0)]*5,16)
    frames=[acting_frame(i%16) for i in range(40)]
    output,info=pick_frames(frames,16,"cycle")
    assert len(output)==16
    assert len(set(info["selected_indices"]))==16
    assert info["mode_requested"]=="cycle"


def test_opaque_non_chroma_requires_explicit_background_solution():
    all_opaque=Image.new("RGBA",(240,240),(143,121,97,255))
    with pytest.raises(ValueError,match="Opaque"):
        _chroma_auto([all_opaque])


def test_chroma_normalization_preserves_common_camera():
    imgs=[remove_chroma(acting_frame(i),"green") for i in range(16)]
    normalized=_common_canvas(imgs,256)
    assert all(frame.size==(256,256) for frame in normalized)
    assert all(frame.getpixel((0,0))[3]==0 for frame in normalized)


def test_real_animated_gif_source(tmp_path):
    root,p=setup_project(tmp_path)
    src=tmp_path/"generated.gif"
    frames=[acting_frame(i) for i in range(16)]
    frames[0].save(src,save_all=True,append_images=frames[1:],
                   loop=0,duration=140,disposal=2)
    res=import_media(src,root/"production.json",p["actions"][0]["slug"])
    assert res["source_kind"]=="animated-image"
    assert res["performance"]["frame_count"]==16


@pytest.mark.skipif(shutil.which("ffmpeg") is None,reason="ffmpeg is optional")
def test_real_mp4_import_with_ffmpeg(tmp_path):
    root,p=setup_project(tmp_path)
    originals=tmp_path/"video_frames";originals.mkdir()
    for i in range(32):
        acting_frame(i%16).convert("RGB").save(originals/f"frame-{i:03d}.png")
    video=tmp_path/"movie.mp4"
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-nostdin",
         "-framerate","16","-i",str(originals/"frame-%03d.png"),
         "-c:v","mpeg4","-pix_fmt","yuv420p","-y",str(video)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=45,check=False)
    assert result.returncode == 0, result.stderr
    loaded=import_media(video,root/"production.json",p["actions"][0]["slug"],
                        duration=2.0,mode="cycle")
    assert loaded["source_kind"]=="video"
    assert loaded["background_mode"]=="green"
    assert loaded["performance"]["frame_count"]==16
