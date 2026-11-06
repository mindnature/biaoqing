"""Caption V3.2: visually differentiated, stable palettes and project-level style lock."""
import json
from pathlib import Path
import sys

import pytest
from PIL import Image, ImageDraw, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from caption_design import choose_caption_design, draw_caption, layout_frame
from studio_v3 import _locked_caption_style
from wechat_export import export_one, render_frame


def photo():
    im = Image.new("RGBA", (240, 240), "#D8CCC1")
    p = ImageDraw.Draw(im)
    p.ellipse((35, 18, 200, 205), fill="#F4E8E0")
    p.ellipse((70, 65, 85, 85), fill="#4B3936")
    p.ellipse((155, 65, 170, 85), fill="#4B3936")
    return im


def traditional():
    im = Image.new("RGBA", (240, 240))
    pen = ImageDraw.Draw(im)
    pen.ellipse((65, 20, 173, 130), fill=(225, 174, 132, 255))
    pen.rounded_rectangle((52, 127, 183, 219), radius=12, fill=(50, 45, 41, 255))
    pen.line((90, 62, 111, 68), fill=(20, 20, 19, 255), width=5)
    return im


def pastel():
    im = Image.new("RGBA", (240, 240))
    p = ImageDraw.Draw(im)
    p.ellipse((50, 30, 195, 205), fill="#FBA5CA")
    p.ellipse((90, 100, 115, 125), fill="#623647")
    return im


def test_photo_selects_readable_high_contrast_classic():
    design = choose_caption_design([photo()])
    assert design.name == "classic"
    assert design.placement == "overlay"
    assert design.fill == "#FFF9F0"
    assert design.outline == "#3A241E"


def test_warm_dark_illustration_selects_heritage():
    design = choose_caption_design([traditional()])
    assert design.name == "heritage", design
    assert design.placement == "integrated"


def test_pastel_character_selects_cute():
    design = choose_caption_design([pastel()])
    assert design.name == "cute"
    assert design.placement == "integrated"


def test_manual_style_override_is_supported_and_stable():
    design = choose_caption_design([photo(), pastel()], style="cute")
    assert design.name == "cute"
    assert design.reason == "manual override"
    with pytest.raises(ValueError):
        choose_caption_design([pastel()], style="unknown")
    with pytest.raises(ValueError):
        choose_caption_design([pastel()], appearance="wrong")


def test_caption_is_bold_and_integrated_no_background_panel():
    im = render_frame(traditional(), 240, "OK", "DejaVuSans.ttf",
                      design=choose_caption_design([traditional()]))
    assert im.getpixel((0, 0))[3] == 0
    assert im.getpixel((239, 239))[3] == 0
    # The title is above the old rigid 0.88 height and enters the figure.
    assert any(im.getpixel((x, 190))[3] > 0 for x in range(65, 176))


def test_baked_caption_has_one_style_for_all_frames_and_retains_duration(tmp_path):
    src = tmp_path / "original.gif"
    frames = []
    for i in range(12):
        frame = pastel()
        ImageDraw.Draw(frame).line((115, 140, 128 + i * 2, 175),
                                   fill="#C34885", width=7)
        frames.append(frame)
    frames[0].save(src, save_all=True, append_images=frames[1:],
                   duration=120, loop=0, disposal=2)
    dest = tmp_path / "compressed.gif"
    result = export_one(src, dest, 500000, text="OK", font="DejaVuSans.ttf")
    assert result["caption_style"] == "cute"
    assert result["caption_placement"] == "integrated"
    assert result["bytes"] <= 500000
    with Image.open(dest) as gif:
        assert gif.info["loop"] == 0
        assert sum(f.info["duration"] for f in ImageSequence.Iterator(gif)) == 12 * 120


def test_pack_style_locked_once_across_all_batches(tmp_path):
    image_path = tmp_path / "private.png"
    traditional().save(image_path)
    root = tmp_path / "project"
    project = {"version": "3.1", "character": {"reference": str(image_path)}}
    one = _locked_caption_style(project, root, [], "auto", "auto")
    assert one == "heritage"
    saved = root / "build" / "caption-style.json"
    assert saved.is_file()
    assert json.loads(saved.read_text())["evidence"] == "character reference"
    image_path.unlink()
    assert _locked_caption_style(project, root, [], "auto", "auto") == one
    with pytest.raises(ValueError, match="locked"):
        _locked_caption_style(project, root, [], "cute", "auto")
