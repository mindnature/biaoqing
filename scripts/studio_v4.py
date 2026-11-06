#!/usr/bin/env python3
"""GIF Sticker Studio V4.0: video/GIF/PNG -> real poses -> review -> existing GIF pipeline.

Model generation is provided by a connected, user-authorized image/video agent.
This local CLI NEVER silently launches or bills an external model. Video ingest
requires ffmpeg, but PNG/GIF ingest and offline review only require Pillow.
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from PIL import Image, ImageChops, ImageDraw, ImageSequence, ImageStat

from studio_v2 import FRAME_COUNT, _project, _save_json, contact_sheet, read_frames
from studio_v3 import acting_report, build_v3, plan_v3, pack_progress

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
FRAME_SIZE = 256


def plan_project(character: str, reference: str, output: Path,
                 captions: list[str] | None = None, count: int | None = None):
    project = plan_v3(character, reference, captions, output, count=count)
    project["workflow_version"] = "4.0"
    project["source_routes"] = ["image-poses", "video", "existing-frames"]
    project["model_backend"] = "user-authorized-external-agent"
    _save_json(output / "production.json", project)
    prompts_dir = output / "generation"
    prompts_dir.mkdir(exist_ok=True)
    for action in project["actions"]:
        label = action["caption"]
        gesture = action["gesture"]
        prompt = (
            f"Reference image: {reference}\n"
            f"Emotion/caption: {label}\nAction: {gesture}\n"
            "Produce a short, genuine, coordinated character performance: "
            "eyes, mouth, head, shoulders, arms and body should move naturally. "
            "Hold one fixed camera view. Keep the character's identity, outfit, "
            "accessories, proportions and number of limbs consistent throughout. "
            "Use a flat saturated green or magenta chroma background with no green "
            "elements on the character, or output a real alpha channel if supported. "
            "Avoid subtitles, text, logos, extra characters, camera shake and cuts. "
            "Start and finish near the resting pose for a natural GIF loop. "
            "Aim for about 2-3 seconds and clear legible acting. "
            "Return a real MP4 or GIF, not a single still frame.\n"
        )
        (prompts_dir / f"{action['slug']}-video.txt").write_text(prompt, encoding="utf-8")
    return project


def _load_gif(path: Path) -> list[Image.Image]:
    with Image.open(path) as gif:
        if not getattr(gif, "is_animated", False):
            raise ValueError("Input GIF is static; genuine moving poses are required")
        return [frame.convert("RGBA").copy() for frame in ImageSequence.Iterator(gif)]


def _load_directory(path: Path) -> list[Image.Image]:
    paths = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not paths:
        raise ValueError("Folder contains no PNG/JPG/WebP frames")
    frames = []
    for frame in paths:
        with Image.open(frame) as im:
            frames.append(im.convert("RGBA").copy())
    return frames


def _load_video(path: Path, start: float, duration: float) -> list[Image.Image]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Video import requires ffmpeg on PATH; PNG and GIF imports do not")
    if start < 0 or duration <= 0 or duration > 20:
        raise ValueError("Video start must be >=0 and duration 0..20 seconds")
    with TemporaryDirectory(prefix="gif-sticker-video-") as tmp:
        dest = Path(tmp)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-ss", str(start), "-i", str(path), "-t", str(duration),
                   "-vf", "fps=16,scale=w='min(640,iw)':h=-2:flags=lanczos",
                   "-frames:v", "320", "-y", str(dest / "frame-%05d.png")]
        run = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        if run.returncode:
            raise RuntimeError(f"ffmpeg could not extract video: {run.stderr[-700:]}")
        return _load_directory(dest)


def _chroma_auto(frames: list[Image.Image]) -> str:
    sample = frames[len(frames)//2].convert("RGBA")
    if sample.getchannel("A").getextrema()[0] < 240:
        return "alpha"
    w, h = sample.size
    points = [(x, y) for x in (0, min(10, w-1), max(0, w-11), w-1)
              for y in (0, min(10, h-1), max(0, h-11), h-1)]
    colors = [sample.getpixel(p) for p in points]
    green = sum(1 for r, g, b, _ in colors if g > r*1.30 and g > b*1.25 and g > 90)
    magenta = sum(1 for r, g, b, _ in colors if r > g*1.35 and b > g*1.35 and min(r,b) > 90)
    if green >= len(colors)*.75:
        return "green"
    if magenta >= len(colors)*.75:
        return "magenta"
    raise ValueError("Opaque input has no recognizable green/magenta chroma background. "
                     "Provide a keyed or transparent clip; external segmentation is not bundled.")


def remove_chroma(image: Image.Image, key: str) -> Image.Image:
    """Conservative hue-based alpha mask with a narrow antialias transition."""
    im = image.convert("RGBA")
    if key == "alpha":
        return im
    if key not in ("green", "magenta"):
        raise ValueError("Chroma mode must be alpha, green or magenta")
    rgba = []
    for r, g, b, a in im.getdata():
        if key == "green":
            chroma = g - max(r, b)
            strength = (g - 70)/3
        else:
            chroma = min(r, b) - g
            strength = (min(r,b)-70)/3
        score = min(chroma, strength)
        if score >= 48:
            opacity = 0
        elif score <= 20:
            opacity = a
        else:
            opacity = round(a * (48 - score) / 28)
        rgba.append((r,g,b,opacity))
    im.putdata(rgba)
    return im


def _common_canvas(frames: list[Image.Image], canvas: int) -> list[Image.Image]:
    if canvas < 64 or canvas > 1024:
        raise ValueError("Canvas size must be 64..1024 px")
    widths, heights = {f.width for f in frames}, {f.height for f in frames}
    if len(widths) > 1 or len(heights) > 1:
        raise ValueError("Source frames must have matching dimensions")
    union = None
    for image in frames:
        box = image.getchannel("A").point(lambda p: 255 if p>=96 else 0).getbbox()
        if box:
            if union is None:
                union = list(box)
            else:
                union = [min(union[0],box[0]),min(union[1],box[1]),
                         max(union[2],box[2]),max(union[3],box[3])]
    if not union:
        raise ValueError("No visible character after background removal")
    pad = max(4, round(max(union[2]-union[0],union[3]-union[1])*.055))
    left=max(0,union[0]-pad); upper=max(0,union[1]-pad)
    right=min(frames[0].width,union[2]+pad); bottom=min(frames[0].height,union[3]+pad)
    crop=(left,upper,right,bottom)
    width,height=right-left,bottom-upper
    scale=min((canvas-24)/width,(canvas-24)/height)
    out_w=max(1,round(width*scale));out_h=max(1,round(height*scale))
    result=[]
    for frame in frames:
        cut=frame.crop(crop).resize((out_w,out_h),Image.Resampling.LANCZOS)
        output=Image.new("RGBA",(canvas,canvas))
        output.alpha_composite(cut,((canvas-out_w)//2,(canvas-out_h)//2))
        result.append(output)
    return result


def _pose_difference(a: Image.Image, b: Image.Image) -> float:
    # Small thumbs are adequate for robust seam warnings, never for identity QA.
    a=a.convert("RGBA").resize((64,64))
    b=b.convert("RGBA").resize((64,64))
    a_rgb=Image.new("RGBA",a.size,(250,250,250,255)); a_rgb.alpha_composite(a)
    b_rgb=Image.new("RGBA",b.size,(250,250,250,255)); b_rgb.alpha_composite(b)
    d=ImageChops.difference(a_rgb.convert("RGB"),b_rgb.convert("RGB"))
    return sum(ImageStat.Stat(d).mean)/(255*3)


def pick_frames(frames: list[Image.Image], count: int = FRAME_COUNT,
                mode: str = "auto") -> tuple[list[Image.Image], dict]:
    if not 2 <= count <= 64:
        raise ValueError("Requested frames must be 2..64")
    if len(frames) < count:
        raise ValueError(f"Only {len(frames)} genuine source frames; cannot fabricate {count} by duplication")
    if mode not in ("auto", "cycle", "one-shot"):
        raise ValueError("Mode must be auto, cycle or one-shot")
    n=len(frames)
    if mode == "cycle" and n >= count+3:
        # Best genuine contiguous duration with low seam discontinuity. Never
        # interpolate/reverse/duplicate a held pose just to satisfy a frame count.
        windows=[min(n, round(n*k)) for k in (.55,.70,.85,1.0)]
        candidate=[]
        for width in sorted(set(max(count,w) for w in windows)):
            for start in range(0,n-width+1,max(1,(n-width)//16 or 1)):
                indices=[start + round(i*(width-1)/(count-1)) for i in range(count)]
                seam=_pose_difference(frames[indices[0]],frames[indices[-1]])
                internal=sum(_pose_difference(frames[indices[i-1]],frames[indices[i]]) for i in range(1,count))
                if internal > .04:
                    candidate.append((seam, -internal, indices))
        indices=min(candidate,key=lambda x:(x[0],x[1]))[2] if candidate else [
            round(i*(n-1)/(count-1)) for i in range(count)]
    else:
        indices=[round(i*(n-1)/(count-1)) for i in range(count)]
    selected=[frames[i].copy() for i in indices]
    seam=_pose_difference(selected[0],selected[-1])
    return selected, {"source_count":len(frames), "selected_indices":indices,
                      "mode_requested":mode, "seam_difference":round(seam,5),
                      "loop_review_required":seam>.11,
                      "note":"Seam score is heuristic. Review the actual playback; one-shot actions need a natural return pose."}


def _target_path(project_file: Path, action: str) -> tuple[Path, dict]:
    project=_project(project_file)
    options={a["slug"]:a for a in project["actions"]}
    if action not in options:
        raise ValueError(f"Unknown action slug '{action}', choose from {', '.join(options)}")
    return project_file.parent / options[action]["frames_dir"], options[action]


def import_media(source: Path, project: Path, action: str, *, bg: str = "auto",
                 start: float = 0.0, duration: float = 2.8, mode: str = "auto",
                 canvas: int = FRAME_SIZE) -> dict:
    if not source.exists():
        raise FileNotFoundError(source)
    dest,act=_target_path(project,action)
    if any(dest.glob("[0-9][0-9][0-9].png")):
        raise FileExistsError(f"{dest} already has action frames; will not overwrite user art")
    if source.is_dir():
        frames=_load_directory(source)
        origin="png-frames"
    elif source.suffix.lower() in VIDEO_SUFFIXES:
        frames=_load_video(source,start,duration)
        origin="video"
    elif source.suffix.lower() in (".gif",".webp"):
        frames=_load_gif(source)
        origin="animated-image"
    else:
        raise ValueError("Accepted input: MP4/MOV/MKV/WebM, animated GIF/WebP, or a directory of PNG/JPG/WebP frames")
    if bg not in ("auto","alpha","green","magenta"):
        raise ValueError("Background must be auto, alpha, green, magenta")
    key = _chroma_auto(frames) if bg=="auto" else bg
    keyed=[remove_chroma(frame,key) for frame in frames]
    normalized=_common_canvas(keyed,canvas)
    poses,sampling=pick_frames(normalized, FRAME_COUNT, mode)
    assessment=acting_report(poses)
    dest.mkdir(parents=True,exist_ok=True)
    for i,im in enumerate(poses):
        im.save(dest/f"{i:03d}.png")
    report={"workflow_version":"4.0","action":action,"caption":act["caption"],
            "source":str(source),"source_kind":origin,"background_mode":key,
            "sampling":sampling,"performance":assessment,
            "user_acceptance":"pending",
            "note":"Action frames are extracted; no claim of identity/style validation or platform approval."}
    _save_json(dest/"v4-ingest-report.json",report)
    return report


def _png_data_uri(frame: Image.Image, size: int=160) -> str:
    image=frame.copy();image.thumbnail((size,size), Image.Resampling.LANCZOS)
    stream=io.BytesIO();image.save(stream,format="PNG")
    return "data:image/png;base64,"+base64.b64encode(stream.getvalue()).decode("ascii")


def review(project: Path, action: str, *, output: Path | None = None) -> dict:
    dest,_=_target_path(project,action)
    frames=read_frames(dest)
    report=acting_report(frames)
    output=output or project.parent/"review"/f"{action}.html"
    output.parent.mkdir(parents=True,exist_ok=True)
    contact_sheet(frames, output.with_name(output.stem+"-contact.png"))
    flagged=sorted({j for issue in report["issues"] for j in issue.get("frames",[])})
    cards=[]
    for i,frame in enumerate(frames):
        uri=_png_data_uri(frame)
        cls="flagged" if i in flagged else ""
        cards.append(f'<button class="frame {cls}" data-index="{i}" onclick="selectFrame({i})">'
                     f'<img src="{uri}" alt="Frame {i:03d}"><span>{i:03d}</span></button>')
    issues=html.escape(json.dumps(report["issues"],ensure_ascii=False,indent=2))
    # All frame URLs are inlined. Review page works offline and never transmits
    # original character content to a remote service.
    sources=json.dumps([_png_data_uri(f,256) for f in frames])
    page='''<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8">
<title>GIF Sticker Studio · Frame Review</title><style>
body{font-family:system-ui,sans-serif;margin:24px auto;max-width:1100px;background:#f4f2ef;color:#222;padding:0 20px}
main{display:grid;grid-template-columns:310px 1fr;gap:20px}
.preview,.sheet{background:#fff;border-radius:16px;padding:20px}
.preview img{width:270px;height:270px;object-fit:contain;background:repeating-conic-gradient(#eee 0 25%,white 0 50%) 50%/22px 22px}
.sheet{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.frame{background:#f5f5f5;border:2px solid transparent;border-radius:8px;padding:5px;cursor:pointer}
.frame img{width:100%;aspect-ratio:1;object-fit:contain}
.frame span{display:block}.frame.flagged{border-color:#c17e42}.frame.active{border-color:#3267c8}
pre{white-space:pre-wrap;font-size:12px}button{cursor:pointer}small{color:#666}
</style></head><body><h1>GIF Sticker Studio · 逐帧审核</h1>
<p>动作：ACTION，状态：STATUS；橙色标记代表需检查的帧。技术筛查不等于人工验收。</p>
<main><div class="preview"><img id="player" alt="Current frame"><p id="counter"></p>
<button onclick="toggle()">播放 / 暂停</button><button onclick="step(-1)">上一帧</button>
<button onclick="step(1)">下一帧</button><p><small>离线本地预览，不上传任何图片。</small></p></div>
<div class="sheet">CARDS</div></main>
<h2>自动检查问题</h2><pre>ISSUES</pre>
<script>
const frames=FRAMES;let i=0,playing=false,timer=null;
function selectFrame(n){i=(n+frames.length)%frames.length;document.getElementById('player').src=frames[i];
document.getElementById('counter').textContent='帧 '+String(i).padStart(3,'0')+' / '+frames.length;
document.querySelectorAll('.frame').forEach((el,k)=>el.classList.toggle('active',k===i));}
function step(delta){selectFrame(i+delta)}
function toggle(){playing=!playing;if(timer){clearInterval(timer);timer=null}
if(playing)timer=setInterval(()=>step(1),140)}
selectFrame(0);
</script></body></html>'''
    page=page.replace("ACTION",html.escape(action)).replace("STATUS",html.escape(report["status"]))
    page=page.replace("CARDS","".join(cards)).replace("ISSUES",issues)
    page=page.replace("FRAMES",sources.replace("</","<\\/"))
    output.write_text(page,encoding="utf-8")
    _save_json(output.with_suffix(".json"),report)
    return {"html":str(output),"contact_sheet":str(output.with_name(output.stem+"-contact.png")),
            "report":str(output.with_suffix(".json")),"status":report["status"],
            "issues":len(report["issues"]),"user_acceptance":"pending"}


def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    sub=cli.add_subparsers(dest="command",required=True)
    p=sub.add_parser("plan",help="Create 16-sticker project and provider-neutral video prompts")
    p.add_argument("--character",required=True);p.add_argument("--reference",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--actions",help="Optional comma-separated captions");p.add_argument("--count",type=int)
    p=sub.add_parser("import",help="Import generated MP4/GIF or real PNG frame sequence")
    p.add_argument("project",type=Path);p.add_argument("action")
    p.add_argument("source",type=Path);p.add_argument("--background",default="auto",
                   choices=["auto","alpha","green","magenta"])
    p.add_argument("--start",type=float,default=0);p.add_argument("--duration",type=float,default=2.8)
    p.add_argument("--mode",default="auto",choices=["auto","cycle","one-shot"])
    p.add_argument("--canvas",type=int,default=256)
    p=sub.add_parser("review",help="Generate private offline frame-curation HTML")
    p.add_argument("project",type=Path);p.add_argument("action");p.add_argument("--output",type=Path)
    p=sub.add_parser("build",help="Build next batch via the existing verified V3 exporter")
    p.add_argument("project",type=Path);p.add_argument("--font",required=True)
    p.add_argument("--brush-font");p.add_argument("--caption-style",default="auto",
                   choices=["auto","classic","cute","heritage","brush"])
    p.add_argument("--heart",action="store_true")
    p=sub.add_parser("status",help="Show production batch progress")
    p.add_argument("project",type=Path)
    p=sub.add_parser("doctor",help="Check dependencies and next-batch readiness before spending model calls")
    p.add_argument("--stage",choices=["plan","import","build"],default="plan")
    p.add_argument("--route",choices=["auto","video","image","existing"],default="auto")
    p.add_argument("--project",type=Path);p.add_argument("--font");p.add_argument("--brush-font")
    p=sub.add_parser("verify",help="Validate actual exported GIFs and ZIP content")
    p.add_argument("project",type=Path)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch",type=int);group.add_argument("--all",action="store_true")
    args=cli.parse_args(argv)
    if args.command=="plan":
        captions=[v.strip() for v in args.actions.split(",")] if args.actions else None
        result=plan_project(args.character,args.reference,args.output,captions,args.count)
        response={"status":"planned","project":str(args.output/"production.json"),
                  "count":len(result["actions"]),"batch_count":len(result["batches"]),
                  "provider":"external user-authorized model, not bundled"}
    elif args.command=="import":
        response=import_media(args.source,args.project,args.action,bg=args.background,
                              start=args.start,duration=args.duration,mode=args.mode,canvas=args.canvas)
    elif args.command=="review":
        response=review(args.project,args.action,output=args.output)
    elif args.command=="status":
        response=pack_progress(args.project)
    elif args.command=="doctor":
        from codex_doctor import preflight
        response=preflight(stage=args.stage,route=args.route,project=args.project,
                           font=args.font,brush_font=args.brush_font)
    elif args.command=="verify":
        from validate_delivery import verify_batch,verify_complete
        response=(verify_complete(args.project) if args.all else
                  verify_batch(args.project,args.batch))
    else:
        # Fail before rendering if the next batch is missing art or a usable font.
        from codex_doctor import preflight
        from validate_delivery import verify_batch,verify_complete
        ready=preflight(stage="build",project=args.project,font=args.font,
                        brush_font=args.brush_font)
        if ready["status"]=="blocked":
            raise ValueError("Preflight failed: "+", ".join(ready["blockers"])+
                             ". Run studio_v4.py doctor --stage build for details")
        result=build_v3(args.project,args.font,heart=args.heart,
                        caption_style=args.caption_style,brush_font=args.brush_font)
        final_check=verify_batch(args.project,result["batch"])
        if final_check["status"]=="blocked":
            raise ValueError("Delivery verification failed: "+
                             "; ".join(final_check["issues"]))
        if result.get("complete_pack"):
            complete=verify_complete(args.project)
            if complete["status"]=="blocked":
                raise ValueError("Complete pack verification failed: "+
                                 "; ".join(complete["issues"]))
        response={"status":"technical_pass_visual_review_pending",
                  "batch":result["batch"],"batch_zip":result["zip"],
                  "gif_count":len(result["actions"]),
                  "delivery_validation":final_check["status"],
                  "complete_pack":result.get("complete_pack"),
                  "user_acceptance":"pending","platform_acceptance":"not_checked"}
    print(json.dumps(response,ensure_ascii=False,indent=2))
    return 2 if response.get("status")=="blocked" else 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ValueError,FileNotFoundError,FileExistsError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(2)
