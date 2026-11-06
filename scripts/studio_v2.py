#!/usr/bin/env python3
"""GIF Sticker Studio V2: plan, inspect, repair and build real keyframe GIFs.

No generative model is bundled: frames must be created by an authorized image
model, artist or animation tool. Only reproducible image operations run here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from math import hypot
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw, ImageStat

FRAME_COUNT = 16
GRID = 4
PHASES = (
    "静止初态", "注意到信息", "目光聚焦", "起势", "蓄力过渡", "情绪预备",
    "动作启动", "主体运动中段", "动作高潮", "高潮延续", "动作回收开始", "回收过渡",
    "恢复重心", "余韵呼吸", "接近初态", "循环衔接",
)
ACTION_LIBRARY = {
    "收到": ("received", "抬头听到消息，身体转向镜头，手势确认，干脆点头，微笑回位"),
    "哈哈": ("laugh", "由忍俊不禁到开怀大笑，眼睛弯起，肩膀随笑起伏，身体前倾再回正"),
    "委屈": ("hurt", "从忍住难过到嘴角下垂、眼眶湿润，轻轻垂头，擦泪后回位"),
    "哼": ("hmph", "鼓起腮帮、双臂抱胸，傲娇转头，保持一拍再偷偷回望"),
    "嗯？": ("huh", "先侧耳，再歪头眨眼，眉毛上挑，靠近一点又缩回去"),
    "晚安": ("good-night", "揉眼打哈欠，抱住小枕头，轻轻挥手，道晚安并合眼"),
    "早安": ("good-morning", "伸懒腰醒来，睁眼看到对方，开心挥手，身体轻弹"),
    "加油": ("cheer", "双拳在胸前蓄力，奋力挥拳加油，肩膀与重心同步，开心回位"),
    "拜拜": ("bye", "发现对方要走，抬手，连续招手，身体轻轻前倾，放手回位"),
    "抱抱": ("hug", "双手缓慢张开，身体前倾迎接，手臂合拢拥抱，温柔松开"),
    "送你小心心": ("heart", "双手从胸前抬起，比出爱心，向外递送，再收回胸前"),
    "忧愁": ("sad", "缓慢低头叹气，眼神黯淡，肩膀垮下，轻轻抬头"),
    "666": ("awesome", "眼睛一亮，竖起大拇指，身体前倾认可，开心点头"),
    "无语": ("speechless", "缓慢侧目，眉毛微挑，双手摊开，长叹后恢复表情"),
    "谢谢": ("thanks", "双手并拢致意，低头表达感谢，抬头带笑，回归站姿"),
    "哇": ("wow", "眼睛逐步睁大，惊讶张嘴，双手抬到脸边，惊喜后回位"),
}


def _save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _project(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    # New plans use the neutral schema; accept historic *-gif-v2 plans for
    # backwards compatibility without encoding any former project branding.
    schema = data.get("schema")
    valid_schema = (schema == "gif-sticker-v2" or
                    isinstance(schema, str) and bool(re.fullmatch(r"[a-z][a-z0-9-]*-gif-v2", schema)))
    if not valid_schema or not isinstance(data.get("actions"), list):
        raise ValueError("Not a GIF Sticker Studio V2 production.json")
    if not data["actions"]:
        raise ValueError("Production plan has no actions")
    seen = set()
    for action in data["actions"]:
        slug = action.get("slug", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) or slug in seen:
            raise ValueError("Invalid or duplicate action slug")
        seen.add(slug)
    return data


def plan(character: str, reference: str, captions: list[str], output: Path, appearance: str):
    if not character.strip() or not reference.strip():
        raise ValueError("Character name and reference image path must be non-empty")
    if not captions or len(captions) != len(set(captions)):
        raise ValueError("Action captions must be non-empty and unique")
    if output.exists() and (output / "production.json").exists():
        raise FileExistsError("A production plan already exists: refuse to overwrite it")
    output.mkdir(parents=True, exist_ok=True)
    actions = []
    for index, caption in enumerate(captions, 1):
        caption = caption.strip()
        if not caption:
            raise ValueError("Empty action caption")
        slug, gesture = ACTION_LIBRARY.get(caption, (f"custom-{index:02d}", f"围绕“{caption}”设计明确、独立的情绪与身体动作"))
        keyframes = [{"index": i, "phase": PHASES[i], "duration_ms": 120,
                      "direction": f"{gesture}；此帧为「{PHASES[i]}」，相邻帧须有实际动作连续性"}
                     for i in range(FRAME_COUNT)]
        actions.append({"caption": caption, "slug": slug, "gesture": gesture,
                        "frames_dir": f"frames/{slug}", "frame_count": FRAME_COUNT,
                        "keyframes": keyframes})
        task_dir = output / "prompts"
        task_dir.mkdir(exist_ok=True)
        prompt = f"""角色：{character}
角色参考图（唯一身份基线）：{reference}
画风：{appearance}
目标：设计“{caption}”的16帧连续角色表演。
动作叙事：{gesture}

制作一张4×4透明PNG动作图集；从左至右、自上而下共16格。
必须锁定同一张脸、头身比例、轮廓、主色、耳朵/发饰/服装和材质；相机固定、光线固定、足够透明留白。
每格保持完整角色，所有格采用同一坐标和缩放。禁止文字、字幕、背景、邻格溢出、多余肢体、融化形变。
分镜：
"""
        prompt += "\n".join(f"{k['index']:02d}. {k['direction']}" for k in keyframes)
        prompt += "\n先审核第0、5、8、15帧的身份一致性，再生成中间帧。合成最终16张独立透明PNG，命名000.png—015.png。\n"
        (task_dir / f"{slug}.txt").write_text(prompt, encoding="utf-8")
    production = {"schema": "gif-sticker-v2", "character": {"name": character.strip(),
                  "reference": reference, "appearance": appearance,
                  "identity_anchors": ["轮廓/头身比", "眼睛间距和脸型", "配色与材质", "标志性配饰"]},
                  "frame_size": [512, 512], "actions": actions,
                  "quality_note": "自动指标只标出风险；不代表已判断眼睛、嘴、手指或角色真实性。"}
    _save_json(output / "production.json", production)
    for action in actions:
        (output / action["frames_dir"]).mkdir(parents=True, exist_ok=True)
    return production


def read_frames(folder: Path, count: int = FRAME_COUNT) -> list[Image.Image]:
    expected = [folder / f"{i:03d}.png" for i in range(count)]
    absent = [p.name for p in expected if not p.is_file()]
    if absent:
        raise ValueError(f"Missing {len(absent)} frame(s) in {folder}: {', '.join(absent[:6])}")
    frames = []
    size = None
    for p in expected:
        with Image.open(p) as im:
            frame = im.convert("RGBA").copy()
        if size is None:
            size = frame.size
        elif frame.size != size:
            raise ValueError(f"Frame dimensions differ: {p.name}: {frame.size} != {size}")
        frames.append(frame)
    return frames


def _mask_stats(image: Image.Image):
    alpha = image.getchannel("A")
    fg = alpha.point(lambda v: 255 if v >= 128 else 0)
    bbox = fg.getbbox()
    if bbox is None:
        return None
    pixels = ImageStat.Stat(fg).sum[0] / 255
    w, h = image.size
    cx = (bbox[0] + bbox[2]) / (2 * w)
    cy = (bbox[1] + bbox[3]) / (2 * h)
    rgb = ImageStat.Stat(image.convert("RGB"), mask=fg).mean
    return {"bbox": bbox, "center": (round(cx, 4), round(cy, 4)),
            "foreground_fraction": round(pixels / (w * h), 5),
            "mean_rgb": tuple(round(v, 1) for v in rgb),
            "fully_opaque": alpha.getextrema() == (255, 255)}


def analyze(frames: list[Image.Image], *, motion_required: bool = True):
    if len(frames) < 2:
        raise ValueError("At least two frames are required")
    size = frames[0].size
    if any(f.size != size for f in frames):
        raise ValueError("All frames must share the same canvas dimensions")
    issues = []
    stats = [_mask_stats(f) for f in frames]
    for i, s in enumerate(stats):
        if s is None:
            issues.append({"severity": "block", "code": "empty", "frames": [i],
                           "reason": "No visible character"})
            continue
        l, t, r, b = s["bbox"]
        if l <= 1 or t <= 1 or r >= size[0] - 1 or b >= size[1] - 1:
            issues.append({"severity": "block", "code": "clipped_or_no_gutter", "frames": [i],
                           "reason": "Character touches canvas edge"})
        if s["fully_opaque"]:
            issues.append({"severity": "block", "code": "opaque_background", "frames": [i],
                           "reason": "Frame has no transparency"})
    hashes = [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]
    uniq = len(set(hashes))
    if motion_required and uniq < 2:
        issues.append({"severity": "block", "code": "no_real_motion", "frames": list(range(len(frames))),
                       "reason": "All supplied poses are identical"})
    for i in range(1, len(frames)):
        a, b = stats[i - 1], stats[i]
        if not a or not b:
            continue
        if hashes[i] == hashes[i - 1]:
            issues.append({"severity": "inspect", "code": "duplicate_hold", "frames": [i-1, i],
                           "reason": "Adjacent identical frames; may be intentional hold"})
        drift = hypot(b["center"][0]-a["center"][0], b["center"][1]-a["center"][1])
        ratio = (b["foreground_fraction"] + 1e-9) / (a["foreground_fraction"] + 1e-9)
        color = hypot(*(b["mean_rgb"][k] - a["mean_rgb"][k] for k in (0, 1)))
        color = hypot(color, b["mean_rgb"][2] - a["mean_rgb"][2])
        if drift > 0.115:
            issues.append({"severity": "inspect", "code": "position_jump", "frames": [i-1, i],
                           "score": round(drift, 4), "reason": "Foreground bounding-box center jumped"})
        if ratio > 1.65 or ratio < 0.60:
            issues.append({"severity": "inspect", "code": "size_or_silhouette_change", "frames": [i-1, i],
                           "score": round(ratio, 3), "reason": "Sudden foreground area change"})
        if color > 72:
            issues.append({"severity": "inspect", "code": "palette_shift", "frames": [i-1, i],
                           "score": round(color, 2), "reason": "Large mean foreground color change"})
    a, b = stats[-1], stats[0]
    if a and b and hypot(b["center"][0]-a["center"][0], b["center"][1]-a["center"][1]) > .115:
        issues.append({"severity": "inspect", "code": "loop_seam", "frames": [len(frames)-1, 0],
                       "reason": "Last-to-first bounding center jump"})
    counts = Counter(x["severity"] for x in issues)
    return {"status": "blocked" if counts["block"] else ("review_required" if issues else "technical_pass"),
            "frame_count": len(frames), "canvas": list(size), "unique_frames": uniq,
            "issue_count": dict(counts), "issues": issues,
            "per_frame": [{"index": i, **(s or {"empty": True})} for i, s in enumerate(stats)],
            "visual_acceptance": "pending", "user_acceptance": "pending",
            "note": "Heuristic warnings require visual review; this tool cannot verify facial identity/anatomy."}


def contact_sheet(frames: list[Image.Image], dest: Path):
    if not frames:
        return
    cell = 192
    thumb = Image.new("RGBA", (cell * GRID, cell * ((len(frames) + GRID - 1)//GRID)), "#F6F3F6")
    d = ImageDraw.Draw(thumb)
    for i, f in enumerate(frames):
        im = f.copy()
        im.thumbnail((cell-18, cell-28), Image.Resampling.LANCZOS)
        x, y = i % GRID * cell, i // GRID * cell
        thumb.alpha_composite(im, (x+(cell-im.width)//2, y+4))
        d.text((x+8, y+cell-21), f"{i:03d}", fill="#263238")
    dest.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(dest)


def atlas(frames: list[Image.Image], dest: Path):
    if len(frames) != FRAME_COUNT:
        raise ValueError("HD exporter requires exactly 16 poses (4x4 atlas)")
    w, h = frames[0].size
    result = Image.new("RGBA", (w*GRID, h*GRID), (0, 0, 0, 0))
    for i, im in enumerate(frames):
        result.alpha_composite(im, ((i%GRID)*w, (i//GRID)*h))
    dest.parent.mkdir(parents=True, exist_ok=True)
    result.save(dest)


def repair(source: Path, corrections: Path, dest: Path, count: int = FRAME_COUNT):
    if source.resolve() == dest.resolve():
        raise ValueError("Source and repair destination must differ")
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Repair output directory must be empty")
    changes = json.loads(corrections.read_text(encoding="utf-8"))
    if not isinstance(changes, dict):
        raise ValueError("Corrections must be a JSON mapping from frame index to correction")
    frames = read_frames(source, count)
    log = []
    for key, op in changes.items():
        idx = int(key)
        if idx < 0 or idx >= len(frames) or not isinstance(op, dict):
            raise ValueError(f"Invalid correction index or data: {key}")
        current = frames[idx]
        if "replace" in op:
            replacement = Path(op["replace"])
            if not replacement.is_absolute():
                replacement = corrections.parent / replacement
            with Image.open(replacement) as im:
                current = im.convert("RGBA").copy()
            if current.size != frames[idx].size:
                raise ValueError("Replacement pose size must match original canvas")
            log.append({"frame": idx, "operation": "replace", "source": str(replacement)})
        if "shift" in op:
            delta = op["shift"]
            if not isinstance(delta, list) or len(delta) != 2 or any(not isinstance(d, int) or isinstance(d, bool) for d in delta):
                raise ValueError("shift must be [integer dx, integer dy]")
            dx, dy = delta
            box = current.getchannel("A").getbbox()
            if box and (box[0] + dx < 0 or box[1] + dy < 0 or
                        box[2] + dx > current.width or box[3] + dy > current.height):
                raise ValueError(f"Frame {idx} would be clipped by shift {delta}")
            canvas = Image.new("RGBA", current.size, (0, 0, 0, 0))
            canvas.alpha_composite(current, (dx, dy))
            current = canvas
            log.append({"frame": idx, "operation": "shift", "delta": delta})
        if not any(k in op for k in ("replace", "shift")):
            raise ValueError("Correction requires replace or shift")
        frames[idx] = current
    dest.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        frame.save(dest / f"{i:03d}.png")
    _save_json(dest / "repair-log.json", {"changes": log, "technical_review": analyze(frames)})
    return log


def build(project_file: Path, font: str, *, strict: bool = False, max_bytes: int = 500000, heart: bool = False, min_output_frames: int = 4, selected_slugs: set[str] | None = None, build_dir: Path | None = None, caption_style: str = "auto", appearance: str = "auto", brush_font: str | None = None):
    from export_keyframes import make_frames, save_and_verify
    from wechat_export import export_one

    project = _project(project_file)
    root = project_file.parent
    destination = build_dir if build_dir is not None else root / "build"
    actions = project["actions"]
    if selected_slugs is not None:
        valid = {entry["slug"] for entry in actions}
        if not selected_slugs or selected_slugs - valid:
            raise ValueError(f"Invalid selected action slugs: {selected_slugs - valid}")
        actions = [entry for entry in actions if entry["slug"] in selected_slugs]
    compiled = []
    for action in actions:
        frames = read_frames(root / action["frames_dir"], action.get("frame_count", FRAME_COUNT))
        report = analyze(frames)
        compiled.append((action, frames, report))
    reports = destination / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for action, frames, report in compiled:
        _save_json(reports / f"{action['slug']}.json", report)
        contact_sheet(frames, reports / f"{action['slug']}-contact.png")
    blocked = [a["slug"] for a, _, r in compiled if r["status"] == "blocked"]
    warnings = [a["slug"] for a, _, r in compiled if r["status"] == "review_required"]
    if blocked:
        raise ValueError(f"Blocked invalid source frames: {', '.join(blocked)}; see build/reports")
    if strict and warnings:
        raise ValueError(f"Strict review gate found potential jumps: {', '.join(warnings)}; see build/reports")
    output = []
    for action, frames, report in compiled:
        slug = action["slug"]
        atlas_path = destination / "atlases" / f"{slug}.png"
        atlas(frames, atlas_path)
        entry = {"text": action["caption"], "render_caption": False,
                 "frames": [{"cell": [i % GRID, i//GRID], "duration": action.get("keyframes", [{}] * len(frames))[i].get("duration_ms", 120)}
                            for i in range(len(frames))]}
        with Image.open(atlas_path) as source:
            raw_frames, durations = make_frames(source.convert("RGBA"), [GRID, GRID], entry, font, 0)
        raw_path = destination / "raw" / f"{slug}.gif"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        save_and_verify(raw_path, raw_frames, durations)
        done_path = destination / "wechat" / f"{slug}.gif"
        export = export_one(raw_path, done_path, max_bytes,
                            text=action["caption"], font=font, heart=heart, min_frames=min_output_frames,
                            caption_style=caption_style, appearance=appearance, brush_font=brush_font)
        output.append({"caption": action["caption"], "slug": slug, "gif": str(done_path),
                       "export": export, "quality": report["status"],
                       "visual_acceptance": "pending"})
    zip_path = destination / "wechat-pack.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        for entry in output:
            archive.write(entry["gif"], arcname=Path(entry["gif"]).name)
        archive.writestr("manifest.json", json.dumps({"character": project["character"]["name"],
                          "items": [{k:v for k,v in x.items() if k!="export"} for x in output],
                          "user_acceptance": "pending"}, ensure_ascii=False, indent=2))
    with ZipFile(zip_path) as archive:
        if archive.testzip():
            raise ValueError("ZIP integrity check failed")
    record = {"status": "technical_export_complete", "actions": output, "zip": str(zip_path),
              "warnings": warnings, "user_acceptance": "pending"}
    _save_json(destination / "summary.json", record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Create action storyboards and 16-frame prompts")
    p.add_argument("--character", required=True)
    p.add_argument("--reference", required=True, help="Path to the user's authorized character image")
    p.add_argument("--actions", required=True, help="Comma-separated captions, e.g. 收到,哈哈,委屈,哼")
    p.add_argument("--appearance", choices=["illustration", "pixel", "photographic"], default="illustration")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("inspect", help="Inspect consecutive PNG frames")
    p.add_argument("frames", type=Path)
    p.add_argument("--count", type=int, default=FRAME_COUNT)
    p.add_argument("--report", type=Path)
    p = sub.add_parser("repair", help="Apply explicitly approved frame replacements or shifts")
    p.add_argument("frames", type=Path)
    p.add_argument("corrections", type=Path)
    p.add_argument("output", type=Path)
    p = sub.add_parser("build", help="Build all 16-pose animations with quality gate and WeChat export")
    p.add_argument("production", type=Path)
    p.add_argument("--font", required=True, help="Installed CJK font path")
    p.add_argument("--strict", action="store_true", help="Stop if there are any heuristic warnings")
    p.add_argument("--heart", action="store_true")
    p.add_argument("--max-bytes", type=int, default=500000)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = plan(args.character, args.reference, [s.strip() for s in args.actions.split(",")],
                      args.output, args.appearance)
        print(json.dumps({"project": str(args.output / "production.json"),
                          "actions": [a["slug"] for a in result["actions"]]}, ensure_ascii=False))
    elif args.command == "inspect":
        result = analyze(read_frames(args.frames, args.count))
        if args.report:
            _save_json(args.report, result)
        print(json.dumps({"status": result["status"], "issues": result["issues"]}, ensure_ascii=False))
    elif args.command == "repair":
        result = repair(args.frames, args.corrections, args.output)
        print(json.dumps({"repaired_frames": len(result), "destination": str(args.output)}, ensure_ascii=False))
    elif args.command == "build":
        result = build(args.production, args.font, strict=args.strict, max_bytes=args.max_bytes, heart=args.heart)
        print(json.dumps({"status": result["status"], "zip": result["zip"],
                          "warnings": result["warnings"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
