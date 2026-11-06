"""V3 acceptance tests: no static bounce masquerading as frame-by-frame acting."""
from pathlib import Path
import sys

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from studio_v3 import acting_report, build_v3, import_atlas, plan_v3


def character(pose=0, *, dx=0, scale=1.0):
    canvas = Image.new('RGBA', (256, 256))
    art = Image.new('RGBA', (160, 210))
    d = ImageDraw.Draw(art)
    d.ellipse((42, 13, 119, 97), fill='#F5BA91', outline='#755E51', width=3)
    d.ellipse((64, 53, 70, 58), fill='#252627')
    d.ellipse((94, 53, 100, 58), fill='#252627')
    d.rounded_rectangle((57, 95, 105, 157), radius=7, fill='#41516C')
    d.line((70, 71, 84 + pose % 7, 75 + pose % 5), fill='#7B2D3E', width=3)
    d.line((62, 116, 34 - pose * 2, 137 - pose * 2), fill='#41516C', width=11)
    d.line((99, 117, 129 + pose * 2, 125 + pose), fill='#41516C', width=11)
    d.ellipse((25 - pose * 2, 130 - pose * 2, 40 - pose * 2, 145 - pose * 2), fill='#F5BA91')
    if scale != 1:
        art = art.resize((int(160*scale), int(210*scale)), Image.Resampling.NEAREST)
    canvas.alpha_composite(art, (int((256-art.width)/2 + dx), int((256-art.height)/2)))
    return canvas


def fake_bounce():
    return [character(0, dx=(i % 6)*2, scale=0.92 + (i%4)*0.02) for i in range(16)]


def performance():
    return [character(i) for i in range(16)]


def test_bounce_is_not_full_performance():
    r = acting_report(fake_bounce())
    assert r['status'] == 'blocked'
    assert any(e['code'] == 'whole_sprite_only' for e in r['issues'])


def test_real_articulated_frames_pass_numeric_screening():
    r = acting_report(performance())
    assert r['status'] != 'blocked', r
    assert r['distinct_normalized_poses'] >= 4
    assert r['automated_visual_acceptance'] is False


def test_repeated_static_frames_are_rejected():
    r = acting_report([character(0)]*16)
    assert r['status'] == 'blocked'


def test_insufficient_frame_count_is_rejected():
    r = acting_report(performance()[:8])
    assert any(e['code'] == 'too_few_keyframes' for e in r['issues'])


def test_plan_marks_full_acting_and_sample_timing(tmp_path):
    p = plan_v3('示例角色', 'user-reference.png', ['哼','收到'], tmp_path/'project')
    assert p['motion_mode'] == 'full_character_performance'
    assert p['version'] == '3.1'
    assert p['actions'][0]['keyframes'][0]['duration_ms'] == 140
    prompt = (tmp_path/'project'/'prompts'/'hmph.txt').read_text(encoding='utf8')
    assert '禁止仅轻动态' in prompt


def test_import_atlas_splits_16_independent_poses(tmp_path):
    sheet = Image.new('RGBA', (1024, 1024))
    for i, f in enumerate(performance()):
        sheet.alpha_composite(f, (i%4*256, i//4*256))
    path = tmp_path/'sheet.png'
    sheet.save(path)
    r = import_atlas(path, tmp_path/'frames')
    assert r['status'] != 'blocked', r
    assert (tmp_path/'frames'/'015.png').exists()
    assert (tmp_path/'frames'/'v3-import-review.json').exists()


def test_build_rejects_fake_bounce_before_generating_zip(tmp_path):
    root = tmp_path/'project'
    p = plan_v3('示例角色', 'user-reference.png', ['哼'], root)
    folder = root / p['actions'][0]['frames_dir']
    for i, f in enumerate(fake_bounce()):
        f.save(folder / f'{i:03d}.png')
    with pytest.raises(ValueError, match='full-performance gate blocked'):
        build_v3(root/'production.json', 'DejaVuSans.ttf')
    assert not (root/'build'/'batch-01'/'wechat-pack.zip').exists()

def test_end_to_end_acting_exports_gif_and_zip(tmp_path):
    from zipfile import ZipFile
    from PIL import Image, ImageSequence
    root = tmp_path / 'project'
    p = plan_v3('Test', 'reference.png', ['OK'], root)
    folder = root / p['actions'][0]['frames_dir']
    for i, frame in enumerate(performance()):
        frame.save(folder / f'{i:03d}.png')
    result = build_v3(root / 'production.json', 'DejaVuSans.ttf', max_bytes=500000)
    assert result['v3_full_performance'] is True
    assert result['visual_acceptance'] == 'pending'
    output = root / 'build' / 'batch-01' / 'wechat' / 'custom-01.gif'
    assert output.is_file() and output.stat().st_size <= 500000
    with Image.open(output) as im:
        assert im.n_frames >= 12
        assert im.info['loop'] == 0
        assert sum(f.info['duration'] for f in ImageSequence.Iterator(im)) == 16 * 140
    with ZipFile(root / 'build' / 'batch-01' / 'wechat-pack.zip') as bundle:
        assert bundle.testzip() is None
