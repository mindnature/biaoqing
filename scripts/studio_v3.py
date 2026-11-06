#!/usr/bin/env python3
"""Full-character acting gate and workflow for Siran GIF Studio V3.

No generative model is bundled. A capable image model or artist must create
16 identity-consistent, genuinely different character poses.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageStat

from studio_v2 import FRAME_COUNT, _project, _save_json, analyze, build as v2_build, plan as v2_plan, read_frames

MIN_OUTPUT_FRAMES = 12
NORMAL_SIZE = 128


def normalize_pose(image: Image.Image) -> Image.Image:
    """Remove whole-sprite translation/scale before measuring articulation."""
    im = image.convert('RGBA')
    alpha = im.getchannel('A').point(lambda a: 255 if a >= 128 else 0)
    bounds = alpha.getbbox()
    if not bounds:
        return Image.new('RGB', (NORMAL_SIZE, NORMAL_SIZE), 'white')
    cut = im.crop(bounds)
    cut.thumbnail((NORMAL_SIZE - 12, NORMAL_SIZE - 12), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (NORMAL_SIZE, NORMAL_SIZE), (255, 255, 255, 255))
    canvas.alpha_composite(cut, ((NORMAL_SIZE - cut.width) // 2, (NORMAL_SIZE - cut.height) // 2))
    return canvas.convert('RGB')


def difference(a: Image.Image, b: Image.Image, region: tuple[float, float] = (0, 1)) -> float:
    """Mean RGB change in a vertical region, normalized 0..1."""
    y1 = max(0, int(a.height * region[0]))
    y2 = min(a.height, int(a.height * region[1]))
    if y1 >= y2:
        raise ValueError('Invalid comparison region')
    changed = ImageChops.difference(a.crop((0, y1, a.width, y2)), b.crop((0, y1, b.width, y2)))
    return sum(ImageStat.Stat(changed).mean) / (3 * 255)


def acting_report(frames: list[Image.Image]):
    """Reject fake actions produced by only translating/scaling one sprite."""
    base = analyze(frames)
    normalized = [normalize_pose(x) for x in frames]
    poses = [0]
    for i in range(1, len(normalized)):
        if all(difference(normalized[i], normalized[j]) >= .016 for j in poses):
            poses.append(i)
    max_pose = max((difference(a, b) for a in normalized for b in normalized), default=0.0)
    upper = max((difference(normalized[0], x, (0.06, 0.46)) for x in normalized[1:]), default=0.0)
    torso = max((difference(normalized[0], x, (0.46, 0.94)) for x in normalized[1:]), default=0.0)
    issues = list(base['issues'])
    if len(frames) < MIN_OUTPUT_FRAMES:
        issues.append({'severity': 'block', 'code': 'too_few_keyframes',
                       'reason': 'Full performance requires at least 12 actual frames'})
    if len(poses) < 4 or max_pose < .038:
        issues.append({'severity': 'block', 'code': 'whole_sprite_only',
                       'reason': 'Pose-normalized frames are nearly identical: no credible character acting'})
    if upper < .018 or torso < .018:
        issues.append({'severity': 'block', 'code': 'not_coordinated_acting',
                       'reason': 'Insufficient changes across face/head and torso/arms'})
    status = ('blocked' if any(i['severity'] == 'block' for i in issues)
              else 'review_required' if issues else 'technical_pass')
    return {'status': status, 'frame_count': len(frames),
            'distinct_normalized_poses': len(poses), 'pose_indices': poses,
            'max_normalized_change': round(max_pose, 5),
            'head_region_change': round(upper, 5),
            'torso_region_change': round(torso, 5), 'issues': issues,
            'automated_visual_acceptance': False, 'user_acceptance': 'pending',
            'note': 'Heuristic gate cannot identify anatomy errors, artistic quality or emotional expression.'}


def import_atlas(source: Path, target: Path, *, grid: int = 4):
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError('Refusing to overwrite an existing frame directory')
    with Image.open(source) as im:
        sprite = im.convert('RGBA')
    w, h = sprite.size
    if w % grid or h % grid:
        raise ValueError('Atlas dimensions must be divisible by grid size')
    cw, ch = w // grid, h // grid
    target.mkdir(parents=True, exist_ok=True)
    for i in range(grid * grid):
        x, y = (i % grid) * cw, (i // grid) * ch
        sprite.crop((x, y, x + cw, y + ch)).save(target / f'{i:03d}.png')
    report = acting_report(read_frames(target, grid * grid))
    _save_json(target / 'v3-import-review.json', report)
    return report


def plan_v3(character: str, reference: str, actions: list[str], output: Path,
            appearance='illustration', frame_duration=140):
    if frame_duration < 40 or frame_duration > 250 or frame_duration % 20:
        raise ValueError('Duration must be 40..250ms in multiples of 20ms')
    project = v2_plan(character, reference, actions, output, appearance)
    project['motion_mode'] = 'full_character_performance'
    project['version'] = '3.0'
    project['frame_duration_ms'] = frame_duration
    for action in project['actions']:
        action['motion_mode'] = 'full_character_performance'
        for k in action['keyframes']:
            k['duration_ms'] = frame_duration
        prompt = output / 'prompts' / f"{action['slug']}.txt"
        prompt.write_text(prompt.read_text(encoding='utf-8') + """
V3 强制验收：角色必须真的表演动作，而非整体弹跳、平移、缩放。眼神、眉毛、嘴部、头部方向、肩膀、双臂或双手和身体重心必须按动作含义协调变化。先生成关键锚点000/005/008/015并单独验收，再补齐16张连续姿态。保留原角色五官、画风、标志发饰、服装和姿态连续性。每帧禁止文字；画面透明，固定机位和统一坐标。
禁止仅轻动态、呼吸/晃动、冻结脸或身体、仅转动独立手臂、让画面位置变化冒充真实表演。
""", encoding='utf-8')
    _save_json(output / 'production.json', project)
    return project


def build_v3(production: Path, font: str, *, max_bytes=500000, heart=False):
    project = _project(production)
    if project.get('motion_mode') != 'full_character_performance' or project.get('version') != '3.0':
        raise ValueError('V3 requires full_character_performance production.json; use studio_v3.py plan')
    root = production.parent
    reports = []
    for action in project['actions']:
        if action.get('motion_mode') != 'full_character_performance':
            raise ValueError(f"{action['slug']}: action mode mismatch")
        frames = read_frames(root / action['frames_dir'], FRAME_COUNT)
        report = acting_report(frames)
        report['action'] = action['slug']
        reports.append(report)
        _save_json(root / 'build' / 'v3-quality' / f"{action['slug']}.json", report)
    failures = [r['action'] for r in reports if r['status'] == 'blocked']
    if failures:
        raise ValueError('V3 full-performance gate blocked: ' + ', '.join(failures) +
                         '; inspect build/v3-quality; no fallback to light-motion')
    result = v2_build(production, font, max_bytes=max_bytes, heart=heart,
                      min_output_frames=MIN_OUTPUT_FRAMES)
    from wechat_export import read_gif
    for item in result['actions']:
        final_frames, _ = read_gif(Path(item['gif']))
        if len(final_frames) < MIN_OUTPUT_FRAMES:
            raise ValueError(f"Final GIF {item['slug']} lost too many action poses")
        report = acting_report(final_frames)
        _save_json(root / 'build' / 'v3-quality' / f"{item['slug']}-export.json", report)
        if report['status'] == 'blocked':
            raise ValueError(f"Compressed GIF {item['slug']} no longer passes full-performance check")
    result['v3_full_performance'] = True
    result['visual_acceptance'] = 'pending'
    _save_json(root / 'build' / 'v3-summary.json', result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('plan')
    q.add_argument('--character', required=True)
    q.add_argument('--reference', required=True)
    q.add_argument('--actions', required=True)
    q.add_argument('--output', type=Path, required=True)
    q.add_argument('--appearance', choices=['illustration','pixel','photographic'], default='illustration')
    q.add_argument('--duration', type=int, default=140)
    q = sub.add_parser('import-atlas')
    q.add_argument('atlas', type=Path)
    q.add_argument('output', type=Path)
    q = sub.add_parser('inspect')
    q.add_argument('frames', type=Path)
    q.add_argument('--report', type=Path)
    q = sub.add_parser('build')
    q.add_argument('production', type=Path)
    q.add_argument('--font', required=True)
    q.add_argument('--heart', action='store_true')
    q.add_argument('--max-bytes', type=int, default=500000)
    a = p.parse_args(argv)
    if a.command == 'plan':
        res = plan_v3(a.character, a.reference, [x.strip() for x in a.actions.split(',')],
                      a.output, a.appearance, a.duration)
        summary = {'version':res['version'], 'actions': [x['slug'] for x in res['actions']]}
    elif a.command == 'import-atlas':
        summary = import_atlas(a.atlas, a.output)
    elif a.command == 'inspect':
        summary = acting_report(read_frames(a.frames))
        if a.report:
            _save_json(a.report, summary)
    else:
        res = build_v3(a.production, a.font, max_bytes=a.max_bytes, heart=a.heart)
        summary = {'version':'3.0', 'zip':res['zip'], 'v3_full_performance':True}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print('ERROR:', error, file=sys.stderr)
        raise SystemExit(2)
