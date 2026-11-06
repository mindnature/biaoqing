#!/usr/bin/env python3
"""Codex preflight: real local prerequisites and actual production readiness.

No inference about Codex account model access, permissions, quota or billing:
those must be discovered by the executing agent.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import PIL
from PIL import ImageFont

from studio_v2 import FRAME_COUNT, _project, read_frames
from studio_v3 import acting_report, pack_progress


def preflight(*, stage: str = "plan", route: str = "auto",
              project: Path | None = None, font: str | None = None,
              brush_font: str | None = None) -> dict:
    if stage not in ("plan", "import", "build"):
        raise ValueError("stage must be plan, import, or build")
    if route not in ("auto", "video", "image", "existing"):
        raise ValueError("route must be auto, video, image or existing")

    checks: list[dict] = []
    def add(name: str, ok: bool | None, *, required: bool, detail: str):
        checks.append({"name": name, "status": "unknown" if ok is None else
                       "pass" if ok else "block" if required else "optional_missing",
                       "required": required, "detail": detail})

    add("pillow", True, required=True, detail=f"Pillow {PIL.__version__}")
    ffmpeg = shutil.which("ffmpeg")
    add("ffmpeg", bool(ffmpeg), required=(route == "video" and stage == "import"),
        detail=(f"Executable: {ffmpeg}" if ffmpeg else
                "Required only for MP4/MOV/WebM input; GIF/PNG input works without it"))
    add("model_generation", None, required=False,
        detail="No image/video model included. Codex must discover and confirm an actually available, user-authorized media-generation tool before claiming automatic generation.")

    def font_probe(path: str | None, name: str, required: bool):
        if not path:
            add(name, False, required=required,
                detail="Specify the path to a local, licensed Chinese-capable font. Typeface aesthetics and glyph coverage require visual confirmation.")
            return
        try:
            test = ImageFont.truetype(path, 20)
            test.getbbox("收到 OK")
        except (OSError, ValueError) as exc:
            add(name, False, required=required, detail=f"Font could not be loaded: {exc}")
        else:
            add(name, True, required=required,
                detail="Font load succeeded; licensing, glyph completeness, and appearance NOT automatically verified.")

    if stage == "build":
        font_probe(font, "caption_font", True)
    elif font:
        font_probe(font, "caption_font", False)
    if brush_font:
        font_probe(brush_font, "brush_font", stage == "build")

    if stage == "build":
        if project is None:
            add("production_manifest", False, required=True,
                detail="Pass --project path/to/production.json")
        elif not project.is_file():
            add("production_manifest", False, required=True,
                detail=f"Production plan not found: {project}")
        else:
            try:
                plan = _project(project)
                progress = pack_progress(project)
            except (ValueError, KeyError, OSError, TypeError) as exc:
                add("production_manifest", False, required=True, detail=str(exc))
            else:
                add("production_manifest", True, required=True,
                    detail=f"{len(plan['actions'])} actions; next batch {progress['next_batch']}")
                next_batch = progress["next_batch"]
                if next_batch is None:
                    add("pending_batch", False, required=True,
                        detail="All batches are built; use verify instead of rebuilding")
                else:
                    for act in plan["actions"]:
                        if act["batch"] != next_batch:
                            continue
                        path = project.parent / act["frames_dir"]
                        try:
                            frames = read_frames(path, FRAME_COUNT)
                            qa = acting_report(frames)
                            reason = "; ".join(x["code"] for x in qa["issues"]
                                               if x["severity"] == "block")
                            add(f"frames:{act['slug']}", qa["status"] != "blocked",
                                required=True, detail=(f"{len(frames)} decoded poses, {qa['status']}" +
                                                       (f" (blocked: {reason})" if reason else "")))
                        except (ValueError, OSError) as exc:
                            add(f"frames:{act['slug']}", False, required=True, detail=str(exc))

    blockers = [item["name"] for item in checks if item["status"] == "block"]
    return {"stage": stage, "route": route,
            "status": "blocked" if blockers else "ready_for_stage",
            "blockers": blockers, "checks": checks,
            "safety": "Do not claim successful model generation or platform approval from this report. Media generation availability is unknown until checked in the active Codex environment.",
            "visual_review_required": True}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--stage", choices=("plan","import","build"), default="plan")
    cli.add_argument("--route", choices=("auto","video","image","existing"), default="auto")
    cli.add_argument("--project", type=Path)
    cli.add_argument("--font")
    cli.add_argument("--brush-font")
    args = cli.parse_args(argv)
    report = preflight(stage=args.stage, route=args.route,
                       project=args.project, font=args.font, brush_font=args.brush_font)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
