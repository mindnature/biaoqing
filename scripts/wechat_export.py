#!/usr/bin/env python3
"""Make independently verified transparent WeChat-size GIFs from finished GIFs.

This exporter preserves frame order, looping and total duration. It is not a
character animation generator: give it a real multi-frame GIF first.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont, ImageSequence
from caption_design import CaptionDesign, choose_caption_design, draw_caption, layout_frame

DEFAULT_MAX_BYTES = 500_000
CANVASES = (240, 220, 200, 180, 160, 144, 128)
PALETTES = (128, 96, 64, 48, 32, 24, 16)


def read_gif(path: Path):
    with Image.open(path) as gif:
        if gif.format != "GIF":
            raise ValueError(f"Not a GIF: {path}")
        frames = []
        durations = []
        for frame in ImageSequence.Iterator(gif):
            frames.append(frame.convert("RGBA").copy())
            durations.append(int(frame.info.get("duration", gif.info.get("duration", 100)) or 100))
        if not frames:
            raise ValueError("GIF contains no frames")
        return frames, durations


def _font(path: str | None, size: int, text: str):
    if not text:
        return None
    if not path:
        raise ValueError("Chinese captions require --font pointing to an installed CJK font")
    return ImageFont.truetype(path, size)


def _heart(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int):
    x, y = center
    points = [
        (x, y + radius), (x - radius, y), (x - radius, y - radius // 2),
        (x - radius // 2, y - radius), (x, y - radius // 3),
        (x + radius // 2, y - radius), (x + radius, y - radius // 2),
        (x + radius, y),
    ]
    draw.polygon(points, fill="#FF79AD", outline="white", width=max(1, radius // 5))


def render_frame(frame: Image.Image, canvas: int, text: str, font_path: str | None,
                 pink_caption: bool = True, heart: bool = False, *,
                 design: CaptionDesign | None = None) -> Image.Image:
    """Compose a stable caption; when called standalone, respect legacy pink flag."""
    if design is None:
        design = choose_caption_design([frame], style="cute" if pink_caption else "classic")
    out, anchor_y = layout_frame(frame, canvas, design, bool(text))
    if text:
        draw_caption(out, text, font_path, design, anchor_y, heart=heart)
    return out


def choose_frames(frames, durations, stride: int):
    selected, times = [], []
    for start in range(0, len(frames), stride):
        selected.append(frames[start])
        times.append(sum(durations[start:start + stride]))
    return selected, times


def _encode(frames: list[Image.Image], durations: list[int], colors: int) -> bytes:
    # Shared palette avoids frame-to-frame shimmer; index 255 is reserved for alpha.
    w, h = frames[0].size
    sample = Image.new("RGB", (w * min(4, len(frames)), h), "white")
    for i, frame in enumerate(frames[:4]):
        sample.paste(frame, (i * w, 0), frame.getchannel("A"))
    palette = sample.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    indexed = []
    for frame in frames:
        rgb = Image.new("RGB", (w, h), "white")
        rgb.paste(frame, (0, 0), frame.getchannel("A"))
        p = rgb.quantize(palette=palette, dither=Image.Dither.NONE)
        transparent = frame.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
        p.paste(255, (0, 0, w, h), transparent)
        indexed.append(p)
    out = io.BytesIO()
    indexed[0].save(out, format="GIF", save_all=True, append_images=indexed[1:],
                    duration=durations, loop=0, transparency=255, disposal=2, optimize=False)
    return out.getvalue()


def verify(path: Path, max_bytes: int, expected_duration: int):
    if path.stat().st_size > max_bytes:
        raise ValueError("GIF exceeds requested byte limit")
    with Image.open(path) as gif:
        if gif.width != gif.height or gif.info.get("loop") != 0:
            raise ValueError("Invalid square canvas or loop")
        durations = [int(f.info.get("duration", 0)) for f in ImageSequence.Iterator(gif)]
        if not durations or abs(sum(durations) - expected_duration) > 20 * len(durations):
            raise ValueError("Decoded GIF has incorrect duration")
        return {"bytes": path.stat().st_size, "canvas": gif.width,
                "frames": len(durations), "duration_ms": sum(durations), "loop": 0}


def export_one(src: Path, dest: Path, max_bytes: int, text: str = "",
               font: str | None = None, heart: bool = False, min_frames: int = 4,
               caption_style: str = "auto", appearance: str = "auto"):
    frames, durations = read_gif(src)
    if len(frames) < 2:
        raise ValueError(f"Source is static (one frame): {src}")
    if text and not font:
        raise ValueError("--font is required when adding Chinese captions")
    total = sum(durations)
    # Detect the style once per animation; never change colors/layout between frames.
    design = choose_caption_design(frames, style=caption_style, appearance=appearance)
    attempts = 0
    for canvas in CANVASES:
        resized = [render_frame(frame, canvas, text, font, heart=heart, design=design) for frame in frames]
        for stride in (1, 2, 3, 4):
            selected, times = choose_frames(resized, durations, stride)
            if len(selected) < min(min_frames, len(frames)):
                continue
            for colors in PALETTES:
                attempts += 1
                data = _encode(selected, times, colors)
                if len(data) <= max_bytes:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    stats = verify(dest, max_bytes, total)
                    stats.update({"source": str(src), "output": str(dest),
                                  "colors": colors, "stride": stride,
                                  "original_frames": len(frames), "text": text,
                                  "caption_style": design.name,
                                  "caption_placement": design.placement,
                                  "caption_style_reason": design.reason,
                                  "appearance_hint": appearance,
                                  "attempts": attempts})
                    return stats
    raise ValueError(f"Unable to fit {src.name} under {max_bytes} bytes without unacceptable degradation; try a simpler action")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export transparent looping square GIFs under strict byte limit")
    parser.add_argument("source", type=Path, help="Source GIF or directory containing GIFs")
    parser.add_argument("output", type=Path, help="Destination GIF or directory")
    parser.add_argument("--text", default="", help="Fixed caption for single GIF or whole batch")
    parser.add_argument("--captions", type=Path, help="JSON mapping input stems to captions")
    parser.add_argument("--font", help="Path to a licensed installed Chinese-capable font")
    parser.add_argument("--heart", action="store_true", help="Add a small heart next to caption")
    parser.add_argument("--caption-style", choices=("auto", "classic", "cute", "heritage"),
                        default="auto", help="Auto art direction by frame colors/coverage (default)")
    parser.add_argument("--appearance", choices=("auto", "photographic", "illustration", "pixel"),
                        default="auto", help="Optional appearance hint if automatic classification differs")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--min-frames", type=int, default=4)
    parser.add_argument("--zip", type=Path, help="Optional ZIP path when batch exporting")
    args = parser.parse_args(argv)
    if args.max_bytes <= 0 or args.min_frames < 2:
        parser.error("--max-bytes must be positive and --min-frames at least 2")
    captions = json.loads(args.captions.read_text(encoding="utf-8")) if args.captions else {}
    if not isinstance(captions, dict) or any(not isinstance(x, str) for x in captions.values()):
        parser.error("--captions must be a JSON object with string values")
    if args.source.is_dir():
        sources = sorted(args.source.glob("*.gif"))
        if not sources:
            parser.error("No GIF files found in source directory")
        args.output.mkdir(parents=True, exist_ok=True)
        results = [export_one(src, args.output / src.name, args.max_bytes,
                              text=captions.get(src.stem, args.text), font=args.font,
                              heart=args.heart, min_frames=args.min_frames,
                              caption_style=args.caption_style, appearance=args.appearance) for src in sources]
        if args.zip:
            args.zip.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(args.zip, "w", ZIP_DEFLATED) as archive:
                for entry in results:
                    archive.write(entry["output"], arcname=Path(entry["output"]).name)
                archive.writestr("manifest.json", json.dumps(results, ensure_ascii=False, indent=2))
    else:
        results = [export_one(args.source, args.output, args.max_bytes,
                              text=captions.get(args.source.stem, args.text), font=args.font,
                              heart=args.heart, min_frames=args.min_frames,
                              caption_style=args.caption_style, appearance=args.appearance)]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
