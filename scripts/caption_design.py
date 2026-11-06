#!/usr/bin/env python3
"""Caption art direction for GIF stickers. Stable across every frame of one GIF.

Uses measurable color/transparency cues, not semantic image understanding.
Supports opt-in style overrides when aesthetic judgment differs.
"""
from __future__ import annotations

from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageStat

STYLE_NAMES = ("auto", "classic", "cute", "heritage", "brush")
APPEARANCES = ("auto", "photographic", "illustration", "pixel")


@dataclass(frozen=True)
class CaptionDesign:
    name: str
    fill: str
    outline: str
    outer: str
    shadow: str
    placement: str
    reason: str
    figure_saturation: float
    opaque_coverage: float


def _sample(frames: list[Image.Image]):
    """Inspect a few poses without counting transparent pixels as background."""
    if not frames:
        raise ValueError("At least one frame is required for auto art direction")
    indices = sorted({0, len(frames)//2, len(frames)-1})
    opaque = 0
    total = 0
    saturated = 0.0
    dark = 0
    warm = 0
    visible = 0
    paper = 0
    pale_paper = 0
    for idx in indices:
        im = frames[idx].convert("RGBA").resize((72, 72), Image.Resampling.BILINEAR)
        for r, g, b, a in im.getdata():
            total += 1
            if a >= 248:
                opaque += 1
            if a < 128:
                continue
            visible += 1
            if r > 198 and g > 180 and b > 160 and 0 < r-b < 65:
                paper += 1
            if r > 215 and g > 205 and b > 190:
                pale_paper += 1
            top, low = max(r, g, b), min(r, g, b)
            saturated += (top - low) / max(1, top)
            if (r * .2126 + g * .7152 + b * .0722) < 105:
                dark += 1
            if r > b * 1.12 and r > g * 1.04:
                warm += 1
    return {
        "opaque_coverage": opaque / max(1, total),
        "saturation": saturated / max(1, visible),
        "dark_fraction": dark / max(1, visible),
        "warm_fraction": warm / max(1, visible),
        "paper_fraction": paper / max(1, visible),
        "pale_paper_fraction": pale_paper / max(1, visible),
    }


_PALETTES = {
    # The cat reference: strong creamy fill and deep brown contrast, not a sticker bar.
    "classic": ("#FFF9F0", "#3A241E", "#291914", "#130D0A"),
    # Pink, thick white internal edge, dark berry outside for contrast even on white.
    "cute": ("#FF79A9", "#FFFFFF", "#8A3C59", "#4D2637"),
    # Aged golden paper/ink correspondence for dark or earth-toned traditional art.
    "heritage": ("#FBE7BA", "#47352D", "#281E1B", "#150F0D"),
    # Natural ink brushwork on creamy paper, without bulky sticker outlines.
    "brush": ("#2E2925", "#2E2925", "#2E2925", "#2E2925"),
}


def choose_caption_design(frames: list[Image.Image], *, style: str = "auto",
                          appearance: str = "auto") -> CaptionDesign:
    if style not in STYLE_NAMES:
        raise ValueError(f"Unsupported caption style {style}; expected {STYLE_NAMES}")
    if appearance not in APPEARANCES:
        raise ValueError(f"Unsupported appearance {appearance}; expected {APPEARANCES}")
    metrics = _sample(frames)
    if style != "auto":
        chosen, reason = style, "manual override"
    elif (appearance != "photographic" and metrics["opaque_coverage"] > .92
          and metrics["pale_paper_fraction"] > .41 and metrics["paper_fraction"] > .54
          and metrics["saturation"] < .22):
        chosen, reason = "brush", "warm light paper-like illustration, suitable for calligraphic typography"
    elif appearance == "photographic" or (appearance == "auto" and metrics["opaque_coverage"] >= .93):
        chosen, reason = "classic", "photographic or fully covered scene"
    elif metrics["dark_fraction"] > .22 and metrics["warm_fraction"] > .26 and metrics["saturation"] < .40:
        chosen, reason = "heritage", "dark, earth-toned illustrated character"
    elif metrics["saturation"] >= .23 or metrics["dark_fraction"] < .11:
        chosen, reason = "cute", "light or colorful illustrated character"
    else:
        chosen, reason = "classic", "neutral high-contrast fallback"
    placement = ("upper_left" if chosen == "brush" else
                 "overlay" if (appearance == "photographic" or
                               (appearance == "auto" and metrics["opaque_coverage"] >= .93))
                 else "integrated")
    return CaptionDesign(chosen, *_PALETTES[chosen], placement, reason,
                         round(metrics["saturation"], 4), round(metrics["opaque_coverage"], 4))


def layout_frame(frame: Image.Image, size: int, design: CaptionDesign, has_text: bool):
    """Place art and text as a single composition; never create a caption panel."""
    frame = frame.convert("RGBA")
    out = Image.new("RGBA", (size, size))
    if not has_text:
        art_h = int(size * .94)
    elif design.placement in ("overlay", "upper_left"):
        art_h = size
    else:
        art_h = int(size * .89)
    margin = max(3, round(size * .025))
    image = frame.copy()
    image.thumbnail((size - 2*margin, art_h - margin), Image.Resampling.LANCZOS)
    if design.placement == "upper_left":
        top = (size - image.height)//2
    elif design.placement == "overlay":
        top = (size - image.height)//2
    else:
        top = max(margin, (art_h - image.height)//2)
    out.alpha_composite(image, ((size - image.width)//2, top))
    caption_y = round(size * (.77 if design.placement == "overlay" else .80))
    return out, caption_y


def _font(path: str | None, point_size: int):
    if not path:
        raise ValueError("Chinese captions require --font with a licensed CJK font path")
    return ImageFont.truetype(path, point_size)


def draw_caption(out: Image.Image, text: str, font_path: str,
                 design: CaptionDesign, y: int, *, heart: bool = False) -> Image.Image:
    if not text:
        return out
    w, h = out.size
    draw = ImageDraw.Draw(out)
    if design.name == "brush":
        # Authentic character shape depends on the selected licensed brush font;
        # do not simulate calligraphy with the generic bold CJK font.
        if not font_path:
            raise ValueError("Brush calligraphy requires a licensed CJK calligraphy font")
        point_size = max(13, round(w * .155))
        max_width = w * .46
        while point_size > 11 and draw.textbbox((0, 0), text, font=_font(font_path, point_size))[2] > max_width:
            point_size -= 1
        font = _font(font_path, point_size)
        width = draw.textbbox((0, 0), text, font=font)[2]
        x = max(5, round(w*.045) + width//2)
        y = round(h*.15)
        # A fixed non-decorative ink inscription in the top-left paper margin.
        # Deliberately no thick border, white glow, shadow block or label panel.
        draw.text((x, y), text, font=font, anchor="mm", fill=design.fill)
        return out
    # Base size is deliberately larger than the old 15.5%, then fitted to width.
    point_size = max(13, round(w * (0.192 if len(text) <= 3 else .18)))
    margin = round(w*.055)
    while point_size > 11:
        font = _font(font_path, point_size)
        width = draw.textbbox((0, 0), text, font=font)[2]
        if width + 2*max(4, round(point_size*.22)) <= w - margin*2:
            break
        point_size -= 1

    font = _font(font_path, point_size)
    outside = max(4, round(point_size*.22))
    inside = max(2, round(point_size*.12))
    shadow_offset = max(1, round(w*.009))
    # A stable set of text layers; the outer ink edge is intentionally bold.
    # No color rectangle or translucent subtitle bar is drawn.
    anchor = (w//2, y)
    if y + point_size*.53 + outside > h - 3:
        anchor = (anchor[0], round(h - 4 - point_size*.53 - outside))
    shadow_pt = (anchor[0] + shadow_offset, anchor[1] + shadow_offset)
    draw.text(shadow_pt, text, font=font, anchor="mm", fill=design.shadow,
              stroke_width=outside+shadow_offset, stroke_fill=design.shadow)
    draw.text(anchor, text, font=font, anchor="mm", fill=design.outer,
              stroke_width=outside, stroke_fill=design.outer)
    draw.text(anchor, text, font=font, anchor="mm", fill=design.fill,
              stroke_width=inside, stroke_fill=design.outline)
    draw.text(anchor, text, font=font, anchor="mm", fill=design.fill)
    if heart:
        radius = max(4, round(point_size*.16))
        right = min(w-radius-4, round(w*.91))
        upper = max(radius+4, anchor[1] - round(point_size*.56))
        # Very small accent only; not a decorative panel.
        draw.polygon([
            (right, upper+radius), (right-radius, upper),
            (right-radius, upper-radius//2), (right-radius//2, upper-radius),
            (right, upper-radius//3), (right+radius//2, upper-radius),
            (right+radius, upper-radius//2), (right+radius, upper)],
            fill=design.fill, outline=design.outline, width=max(1, radius//4))
    return out
