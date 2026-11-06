from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wechat_export import choose_frames, export_one, read_gif, verify


def make_gif(path: Path, n=12):
    frames = []
    for i in range(n):
        im = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
        pen = ImageDraw.Draw(im)
        pen.ellipse((45 + i * 2, 45, 125 + i * 2, 135), fill=(255, 80, 120, 255))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=2)


def test_export_under_500kb_and_loop(tmp_path):
    src = tmp_path / "source.gif"
    dest = tmp_path / "result.gif"
    make_gif(src)
    original, durations = read_gif(src)
    result = export_one(src, dest, 500000)
    assert result["bytes"] < 500000
    assert result["frames"] >= 4
    assert result["duration_ms"] == sum(durations)
    assert result["canvas"] in (240, 220, 200, 180, 160, 144, 128)
    assert verify(dest, 500000, sum(durations))["loop"] == 0
    with Image.open(dest) as gif:
        assert any(f.convert("RGBA").getpixel((0, 0))[3] == 0
                   for f in ImageSequence.Iterator(gif))


def test_frame_skip_preserves_total_duration(tmp_path):
    src = tmp_path / "a.gif"
    make_gif(src, 12)
    frames, durations = read_gif(src)
    for stride in (1, 2, 3, 4):
        selected, times = choose_frames(frames, durations, stride)
        assert len(selected) == (len(frames) + stride - 1) // stride
        assert sum(times) == sum(durations)


def test_requires_font_for_caption(tmp_path):
    src = tmp_path / "a.gif"
    make_gif(src)
    try:
        export_one(src, tmp_path / "b.gif", 500000, text="收到")
    except ValueError as exc:
        assert "--font" in str(exc)
    else:
        raise AssertionError("Missing font should fail explicitly")


def test_rejects_static_input(tmp_path):
    src = tmp_path / "a.gif"
    Image.new("RGB", (32, 32), "white").save(src)
    try:
        export_one(src, tmp_path / "b.gif", 500000)
    except ValueError as exc:
        assert "static" in str(exc)
    else:
        raise AssertionError("Static GIF should not masquerade as animation")
