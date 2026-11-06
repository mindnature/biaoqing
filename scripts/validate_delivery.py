#!/usr/bin/env python3
"""Independent GIF delivery gate: verifies the bytes a recipient will actually get.

Pass means "technical checks complete; human visual and platform approval pending".
It never uses OCR, guesses caption glyphs, or assumes model quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from studio_v2 import _project, _save_json
from studio_v3 import MIN_OUTPUT_FRAMES, acting_report
from wechat_export import read_gif, verify


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _review_one(gif: Path, action: dict, max_bytes: int) -> dict:
    expected_duration = sum(frame["duration_ms"] for frame in action["keyframes"])
    metrics = verify(gif, max_bytes, expected_duration)
    frames, _ = read_gif(gif)
    if len(frames) < MIN_OUTPUT_FRAMES:
        raise ValueError(f"{action['slug']}: only {len(frames)} frames remain")
    acting = acting_report(frames, compressed=True)
    if acting["status"] == "blocked":
        reasons = [issue["code"] for issue in acting["issues"] if issue["severity"] == "block"]
        raise ValueError(f"{action['slug']}: exported GIF fails acting check: {reasons}")
    return {"slug": action["slug"], "caption": action["caption"],
            "filename": gif.name, **metrics,
            "sha256": sha256(gif.read_bytes()),
            "motion_status": acting["status"],
            "motion_warnings": [issue["code"] for issue in acting["issues"]
                                if issue["severity"] != "block"],
            "caption_text_verification": "requires_visual_review"}


def verify_batch(production: Path, batch_index: int, *, max_bytes: int = 500000,
                 save_report: bool = True) -> dict:
    if max_bytes <= 0:
        raise ValueError("Maximum bytes must be positive")
    plan = _project(production)
    batches = plan.get("batches", [])
    if not 1 <= batch_index <= len(batches):
        raise ValueError(f"Batch must be between 1 and {len(batches)}")
    batch = batches[batch_index-1]
    selected = [action for action in plan["actions"] if action["slug"] in batch["slugs"]]
    root = production.parent
    build = root / "build" / batch["name"]
    archive_path = build / "wechat-pack.zip"
    expected_gifs = {f"{action['slug']}.gif" for action in selected}
    issues: list[str] = []
    inspected: list[dict] = []

    for action in selected:
        path = build / "wechat" / f"{action['slug']}.gif"
        try:
            inspected.append(_review_one(path, action, max_bytes))
        except (ValueError, OSError, KeyError) as exc:
            issues.append(f"{action['slug']}: {exc}")

    try:
        with ZipFile(archive_path) as z:
            if z.testzip() is not None:
                issues.append("Batch ZIP CRC check failed")
            names = z.namelist()
            gif_names = [n for n in names if n.lower().endswith(".gif")]
            if len(gif_names) != len(set(gif_names)) or set(gif_names) != expected_gifs:
                issues.append(f"Batch ZIP GIF inventory mismatch: {gif_names} vs {sorted(expected_gifs)}")
            if "manifest.json" not in names:
                issues.append("Batch ZIP missing manifest.json")
            else:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
                listed = manifest.get("items")
                if not isinstance(listed, list) or {
                    (entry.get("slug"), entry.get("caption"))
                    for entry in listed if isinstance(entry, dict)
                } != {(act["slug"], act["caption"]) for act in selected}:
                    issues.append("ZIP manifest captions/action list do not match production plan")
            for record in inspected:
                if record["filename"] in names:
                    if sha256(z.read(record["filename"])) != record["sha256"]:
                        issues.append(f"{record['filename']}: archived GIF differs from verified file")
    except (FileNotFoundError, BadZipFile, OSError, ValueError, KeyError) as exc:
        issues.append(f"Batch ZIP could not be read: {exc}")

    status = "blocked" if issues else "technical_pass_visual_review_pending"
    report = {"version": "4.1", "batch": batch_index, "batch_name": batch["name"],
              "expected_gifs": len(selected), "verified_gifs": len(inspected),
              "status": status, "issues": issues, "files": inspected,
              "must_visually_check": ["same character in each frame", "eyes/hands/face",
                                     "true coordinated acting", "exact on-screen caption glyphs",
                                     "font design and placement", "transparent edges and loop seam"],
              "user_acceptance": "pending", "platform_acceptance": "not_checked"}
    if save_report:
        _save_json(build / "delivery-validation.json", report)
    return report


def verify_complete(production: Path, *, max_bytes: int = 500000,
                    save_report: bool = True) -> dict:
    plan = _project(production)
    root = production.parent
    issues = []
    items = []
    for batch in plan.get("batches", []):
        res = verify_batch(production, batch["index"], max_bytes=max_bytes, save_report=save_report)
        if res["status"] == "blocked":
            issues.extend(f"{batch['name']}: {err}" for err in res["issues"])
        items.extend(res["files"])

    full_zip = root / "build" / "complete-pack.zip"
    expected = {f"{i:02d}-{a['slug']}.gif": a for i, a in enumerate(plan["actions"], 1)}
    actual = {f"{i:02d}-{a['slug']}.gif": root / "build" / f"batch-{a['batch']:02d}" /
              "wechat" / f"{a['slug']}.gif" for i, a in enumerate(plan["actions"], 1)}
    try:
        with ZipFile(full_zip) as z:
            names = z.namelist()
            if z.testzip() is not None:
                issues.append("Complete ZIP CRC failed")
            actual_names = [n for n in names if n.endswith(".gif")]
            if set(actual_names) != set(expected) or len(actual_names) != len(expected):
                issues.append("Complete ZIP does not contain exactly one GIF per planned caption")
            if "manifest.json" not in names:
                issues.append("Complete ZIP manifest missing")
            else:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
                if manifest.get("count") != len(expected):
                    issues.append("Complete ZIP manifest count mismatch")
                listed = manifest.get("items", [])
                if {(x.get("slug"), x.get("caption")) for x in listed} != {
                    (a["slug"], a["caption"]) for a in plan["actions"]}:
                    issues.append("Complete ZIP manifest captions mismatch")
            for name in set(actual_names) & set(expected):
                if not actual[name].is_file() or sha256(z.read(name)) != sha256(actual[name].read_bytes()):
                    issues.append(f"{name}: complete ZIP contains unexpected or stale GIF bytes")
    except (FileNotFoundError, BadZipFile, OSError, KeyError, ValueError) as exc:
        issues.append(f"Complete pack cannot be inspected: {exc}")

    report = {"version": "4.1", "status": "blocked" if issues else "technical_pass_visual_review_pending",
              "expected_gifs": len(plan["actions"]), "verified_gifs": len(items),
              "issues": issues, "archive": str(full_zip),
              "user_acceptance": "pending", "platform_acceptance": "not_checked"}
    if save_report:
        _save_json(root / "build" / "complete-delivery-validation.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=500000)
    args = parser.parse_args(argv)
    try:
        result = (verify_complete(args.production, max_bytes=args.max_bytes) if args.all else
                  verify_batch(args.production, args.batch, max_bytes=args.max_bytes))
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
