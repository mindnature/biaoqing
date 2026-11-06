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
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageChops, ImageStat
from caption_design import choose_caption_design

from studio_v2 import ACTION_LIBRARY, FRAME_COUNT, _project, _save_json, analyze, build as v2_build, plan as v2_plan, read_frames
from sticker_pack_v31 import ACTION_PRESETS, DEFAULT_BATCH_SIZE, choose_captions, group_actions, write_batch_guides

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


def acting_report(frames: list[Image.Image], *, compressed: bool = False):
    """Reject fake actions produced by only translating/scaling one sprite."""
    # Check real canvas edges on the COMPLETE final frame. Cropping a frame
    # through the integrated caption creates an artificial "clipped" boundary.
    base = analyze(frames)
    # For motion characterization exclude the fixed caption region. The
    # new integrated typography starts higher than the V3.1 bottom label.
    motion_frames = ([im.crop((0, 0, im.width, max(2, round(im.height * 0.66))))
                      for im in frames] if compressed else frames)
    normalized = [normalize_pose(x) for x in motion_frames]
    poses = [0]
    pose_threshold = .010 if compressed else .016
    for i in range(1, len(normalized)):
        if all(difference(normalized[i], normalized[j]) >= pose_threshold for j in poses):
            poses.append(i)
    max_pose = max((difference(a, b) for a in normalized for b in normalized), default=0.0)
    upper = max((difference(normalized[0], x, (0.06, 0.46)) for x in normalized[1:]), default=0.0)
    torso = max((difference(normalized[0], x, (0.46, 0.94)) for x in normalized[1:]), default=0.0)
    issues = list(base['issues'])
    if len(frames) < MIN_OUTPUT_FRAMES:
        issues.append({'severity': 'block', 'code': 'too_few_keyframes',
                       'reason': 'Full performance requires at least 12 actual frames'})
    if len(poses) < (2 if compressed else 4) or max_pose < (.010 if compressed else .038):
        issues.append({'severity': 'block', 'code': 'whole_sprite_only',
                       'reason': 'Pose-normalized frames are nearly identical: no credible character acting'})
    if upper < (.006 if compressed else .018) or torso < (.008 if compressed else .018):
        issues.append({'severity': 'block', 'code': 'not_coordinated_acting',
                       'reason': 'Insufficient changes across face/head and torso/arms'})
    status = ('blocked' if any(i['severity'] == 'block' for i in issues)
              else 'review_required' if issues else 'technical_pass')
    return {'status': status, 'frame_count': len(frames), 'post_export_profile': compressed,
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


def plan_v3(character: str, reference: str, actions: list[str] | None, output: Path,
            appearance='illustration', frame_duration=140, count: int | None = None,
            batch_size: int = DEFAULT_BATCH_SIZE):
    """V3.1: default to 16 stickers, each with 16 real key poses; batches of four."""
    if frame_duration < 40 or frame_duration > 250 or frame_duration % 20:
        raise ValueError('Duration must be 40..250ms in multiples of 20ms')
    captions = choose_captions(actions, count)
    # The curated 16 have their own poses/gestures rather than 16 generic prompts.
    ACTION_LIBRARY.update(ACTION_PRESETS)
    project = v2_plan(character, reference, captions, output, appearance)
    project['motion_mode'] = 'full_character_performance'
    project['version'] = '3.1'
    project['frame_duration_ms'] = frame_duration
    project['pack'] = {
        'preset': 'default-16' if actions is None and count is None else
                  'preset-count' if actions is None else 'user-captions',
        'count': len(captions),
        'frames_per_sticker': FRAME_COUNT,
        'total_planned_frames': len(captions) * FRAME_COUNT,
        'batch_size': batch_size,
    }
    for action in project['actions']:
        action['motion_mode'] = 'full_character_performance'
        for keyframe in action['keyframes']:
            keyframe['duration_ms'] = frame_duration
        prompt = output / 'prompts' / f"{action['slug']}.txt"
        prompt.write_text(prompt.read_text(encoding='utf-8') + """
V3.1 强制验收：角色必须真的表演动作，而非整体弹跳、平移、缩放。眼神、眉毛、嘴部、头部方向、肩膀、双臂或双手和身体重心必须按动作含义协调变化。先生成关键锚点000/005/008/015并单独验收，再补齐16张连续姿态。保留原角色五官、画风、标志发饰、服装和姿态连续性。每帧禁止文字；画面透明，固定机位和统一坐标。
禁止仅轻动态、呼吸/晃动、冻结脸或身体、仅转动独立手臂、让画面位置变化冒充真实表演。
""", encoding='utf-8')
    project['batches'] = group_actions(project['actions'], batch_size)
    for batch in project['batches']:
        for action in project['actions']:
            if action['slug'] in batch['slugs']:
                action['batch'] = batch['index']
    _save_json(output / 'production.json', project)
    write_batch_guides(project, output)
    return project


def pack_progress(production: Path):
    """File-backed production status; technical exports are not user acceptance."""
    project = _project(production)
    if project.get('version') != '3.1':
        raise ValueError('Batch status requires a V3.1 production plan')
    root = production.parent
    batches = []
    next_batch = None
    for b in project['batches']:
        directory = root / 'build' / b['name']
        summary_file = directory / 'v3-summary.json'
        valid = False
        if summary_file.is_file() and (directory / 'wechat-pack.zip').is_file():
            try:
                summary = json.loads(summary_file.read_text(encoding='utf-8'))
                exported = {entry['slug'] for entry in summary['actions']}
                valid = (summary.get('v3_full_performance') is True and
                         exported == set(b['slugs']) and
                         all((directory / 'wechat' / f"{slug}.gif").is_file()
                             for slug in b['slugs']))
            except (ValueError, TypeError, KeyError):
                valid = False
        if not valid and next_batch is None:
            next_batch = b['index']
        batches.append({'index': b['index'], 'name': b['name'],
                        'count': b['count'],
                        'status': 'technical_built' if valid else 'planned',
                        'captions': b['captions']})
    return {'version': '3.1', 'total_stickers': len(project['actions']),
            'total_planned_frames': len(project['actions']) * FRAME_COUNT,
            'batch_size': project['pack']['batch_size'],
            'batches': batches, 'next_batch': next_batch,
            'all_batches_built': next_batch is None,
            'user_acceptance': 'pending'}


def assemble_v31(production: Path, *, max_bytes: int = 500000):
    """Make one ZIP only after all four-sticker batches were technically built."""
    from wechat_export import read_gif, verify
    project = _project(production)
    progress = pack_progress(production)
    if not progress['all_batches_built']:
        raise ValueError(f"Unfinished batch {progress['next_batch']}; build all batches before assembling")
    root = production.parent
    items = []
    for action in project['actions']:
        batch_name = f"batch-{action['batch']:02d}"
        gif = root / 'build' / batch_name / 'wechat' / f"{action['slug']}.gif"
        frames, durations = read_gif(gif)
        if len(frames) < MIN_OUTPUT_FRAMES:
            raise ValueError(f"{action['slug']}: fewer than {MIN_OUTPUT_FRAMES} final animation frames")
        expected_duration = sum(k['duration_ms'] for k in action['keyframes'])
        metrics = verify(gif, max_bytes, expected_duration)
        review = acting_report(frames, compressed=True)
        if review['status'] == 'blocked':
            raise ValueError(f"Final performance gate rejected {action['slug']}")
        items.append({'caption': action['caption'], 'slug': action['slug'],
                      'batch': action['batch'], 'file': str(gif),
                      'zip_name': f"{len(items)+1:02d}-{action['slug']}.gif",
                      'bytes': metrics['bytes'], 'frames': metrics['frames']})
    destination = root / 'build' / 'complete-pack.zip'
    manifest = {'version': '3.1', 'character': project['character']['name'],
                'count': len(items), 'frames_per_sticker_planned': FRAME_COUNT,
                'batch_size': project['pack']['batch_size'],
                'items': [{k: v for k, v in item.items() if k != 'file'} for item in items],
                'user_acceptance': 'pending',
                'platform_acceptance': 'not_checked'}
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for entry in items:
            archive.write(entry['file'], arcname=entry['zip_name'])
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(destination) as archive:
        if archive.testzip() is not None:
            destination.unlink(missing_ok=True)
            raise ValueError('Final pack ZIP integrity failure')
        if len([n for n in archive.namelist() if n.endswith('.gif')]) != len(items):
            destination.unlink(missing_ok=True)
            raise ValueError('Final pack is missing animated stickers')
    _save_json(root / 'build' / 'complete-manifest.json', manifest)
    return {'zip': str(destination), 'count': len(items),
            'batches': len(project['batches']), 'user_acceptance': 'pending'}


def _locked_caption_style(project: dict, root: Path, actions: list[dict],
                          choice: str = "auto", appearance: str = "auto") -> str:
    """Choose once for the character, persist for all future four-sticker batches."""
    if project.get("version") != "3.1":
        return choice
    config_path = root / "build" / "caption-style.json"
    if config_path.is_file():
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        locked = saved["style"]
        if choice not in ("auto", locked):
            raise ValueError(f"Caption style is locked to {locked}; rebuild the pack in a new workspace to change it")
        return locked
    reference = Path(project["character"].get("reference", ""))
    if not reference.is_file():
        reference = root / reference
    if reference.is_file():
        with Image.open(reference) as im:
            frames = [im.convert("RGBA").copy()]
        evidence = "character reference"
    else:
        # Workspaces sometimes reference a private image managed by the agent,
        # not stored at that path; use the first built action as the fallback.
        frames = read_frames(root / actions[0]["frames_dir"], FRAME_COUNT)
        evidence = "first action poses (reference file unavailable)"
    effective_appearance = project["character"].get("appearance", "auto") if appearance == "auto" else appearance
    design = choose_caption_design(frames, style=choice, appearance=effective_appearance)
    _save_json(config_path, {
        "version": "3.3", "style": design.name, "placement": design.placement,
        "reason": design.reason, "evidence": evidence, "appearance": appearance,
        "user_override": choice != "auto",
        "note": "Heuristic decision; review first batch typography visually before extending pack."
    })
    return design.name


def build_v3(production: Path, font: str, *, max_bytes=500000, heart=False,
             batch: int | None = None, caption_style: str = "auto",
             appearance: str = "auto", brush_font: str | None = None):
    project = _project(production)
    if project.get('motion_mode') != 'full_character_performance' or project.get('version') not in ('3.0', '3.1'):
        raise ValueError('Requires a full_character_performance production.json')
    root = production.parent
    if project.get('version') == '3.1':
        progress = pack_progress(production)
        index = batch if batch is not None else progress['next_batch']
        if index is None:
            raise ValueError('All batches already built; use assemble to create the full pack')
        if not isinstance(index, int) or not 1 <= index <= len(project['batches']):
            raise ValueError(f"Batch must be 1..{len(project['batches'])}")
        if any(x['status'] != 'technical_built' for x in progress['batches'][:index-1]):
            raise ValueError('Complete earlier batches first; production runs in batches of four')
        current = project['batches'][index-1]
        selected = set(current['slugs'])
        destination = root / 'build' / current['name']
        actions = [action for action in project['actions'] if action['slug'] in selected]
    else:
        if batch is not None:
            raise ValueError('--batch requires a V3.1 project')
        selected = None
        destination = root / 'build'
        actions = project['actions']
        index = None
    reports = []
    for action in actions:
        if action.get('motion_mode') != 'full_character_performance':
            raise ValueError(f"{action['slug']}: action mode mismatch")
        frames = read_frames(root / action['frames_dir'], FRAME_COUNT)
        report = acting_report(frames)
        report['action'] = action['slug']
        reports.append(report)
        _save_json(destination / 'v3-quality' / f"{action['slug']}.json", report)
    failures = [r['action'] for r in reports if r['status'] == 'blocked']
    if failures:
        raise ValueError('V3 full-performance gate blocked: ' + ', '.join(failures) +
                         '; inspect v3-quality; no fallback to light-motion')
    chosen_style = _locked_caption_style(project, root, actions, caption_style, appearance)
    if chosen_style == "brush" and not brush_font:
        raise ValueError("Ink-brush style requires --brush-font with a licensed Chinese calligraphy font. Do not replace it with generic bold typography.")
    result = v2_build(production, font, max_bytes=max_bytes, heart=heart,
                      min_output_frames=MIN_OUTPUT_FRAMES, selected_slugs=selected,
                      build_dir=destination, caption_style=chosen_style,
                      appearance=appearance, brush_font=brush_font)
    from wechat_export import read_gif
    for item in result['actions']:
        final_frames, _ = read_gif(Path(item['gif']))
        if len(final_frames) < MIN_OUTPUT_FRAMES:
            Path(result['zip']).unlink(missing_ok=True)
            raise ValueError(f"Final GIF {item['slug']} lost too many action poses")
        report = acting_report(final_frames, compressed=True)
        _save_json(destination / 'v3-quality' / f"{item['slug']}-export.json", report)
        if report['status'] == 'blocked':
            Path(result['zip']).unlink(missing_ok=True)
            codes = [issue['code'] for issue in report['issues'] if issue['severity'] == 'block']
            raise ValueError(f"Compressed GIF {item['slug']} no longer passes full-performance check: {codes}; "
                             f"poses={report['distinct_normalized_poses']}; "
                             f"changes={report['max_normalized_change']}, "
                             f"head={report['head_region_change']}, torso={report['torso_region_change']}")
    result['v3_full_performance'] = True
    result['caption_style'] = chosen_style
    result['version'] = project['version']
    result['batch'] = index
    result['visual_acceptance'] = 'pending'
    _save_json(destination / 'v3-summary.json', result)
    if project.get('version') == '3.1' and pack_progress(production)['all_batches_built']:
        result['complete_pack'] = assemble_v31(production, max_bytes=max_bytes)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('plan', help='Default 16 GIFs × 16 acting frames; four GIFs per batch')
    q.add_argument('--character', required=True)
    q.add_argument('--reference', required=True)
    q.add_argument('--actions', help='Optional comma-separated custom captions; overrides default 16')
    q.add_argument('--count', type=int, help='Optional 1..32 preset count; default 16')
    q.add_argument('--output', type=Path, required=True)
    q.add_argument('--appearance', choices=['illustration','pixel','photographic'], default='illustration')
    q.add_argument('--duration', type=int, default=140)
    q = sub.add_parser('import-atlas')
    q.add_argument('atlas', type=Path)
    q.add_argument('output', type=Path)
    q = sub.add_parser('inspect')
    q.add_argument('frames', type=Path)
    q.add_argument('--report', type=Path)
    q = sub.add_parser('build', help='Build next four GIFs, or one selected batch, or --all')
    q.add_argument('production', type=Path)
    q.add_argument('--font', required=True)
    group = q.add_mutually_exclusive_group()
    group.add_argument('--batch', type=int)
    group.add_argument('--all', action='store_true')
    q.add_argument('--heart', action='store_true')
    q.add_argument('--caption-style', choices=['auto', 'classic', 'cute', 'heritage', 'brush'], default='auto')
    q.add_argument('--brush-font', help='Licensed Chinese brush/calligraphy font for ink-paper illustrations')
    q.add_argument('--appearance', choices=['auto', 'photographic', 'illustration', 'pixel'], default='auto')
    q.add_argument('--max-bytes', type=int, default=500000)
    q = sub.add_parser('status', help='Show built/pending groups')
    q.add_argument('production', type=Path)
    q = sub.add_parser('assemble', help='Create final 16-GIF ZIP after all batches are ready')
    q.add_argument('production', type=Path)
    q.add_argument('--max-bytes', type=int, default=500000)
    a = p.parse_args(argv)
    if a.command == 'plan':
        actions = [x.strip() for x in a.actions.split(',')] if a.actions is not None else None
        res = plan_v3(a.character, a.reference, actions, a.output, a.appearance, a.duration, count=a.count)
        summary = {'version':res['version'], 'count':len(res['actions']),
                   'frames_per_sticker':FRAME_COUNT,
                   'total_planned_frames':len(res['actions']) * FRAME_COUNT,
                   'batch_size':res['pack']['batch_size'],
                   'batches':[{'index':b['index'], 'count':b['count'],
                               'captions':b['captions']} for b in res['batches']]}
    elif a.command == 'import-atlas':
        summary = import_atlas(a.atlas, a.output)
    elif a.command == 'inspect':
        summary = acting_report(read_frames(a.frames))
        if a.report:
            _save_json(a.report, summary)
    elif a.command == 'status':
        summary = pack_progress(a.production)
    elif a.command == 'assemble':
        summary = assemble_v31(a.production, max_bytes=a.max_bytes)
    elif a.all:
        project = _project(a.production)
        if project.get('version') != '3.1':
            raise ValueError('--all requires a V3.1 project')
        completed = []
        while pack_progress(a.production)['next_batch'] is not None:
            result = build_v3(a.production, a.font, max_bytes=a.max_bytes, heart=a.heart,
                              caption_style=a.caption_style, appearance=a.appearance, brush_font=a.brush_font)
            completed.append(result['batch'])
        summary = {'version':'3.1', 'completed_batches':completed,
                   'complete_pack':assemble_v31(a.production, max_bytes=a.max_bytes)}
    else:
        res = build_v3(a.production, a.font, max_bytes=a.max_bytes, heart=a.heart,
                       batch=a.batch, caption_style=a.caption_style, appearance=a.appearance, brush_font=a.brush_font)
        summary = {'version':res['version'], 'batch':res['batch'],
                   'produced':len(res['actions']), 'zip':res['zip'],
                   'complete_pack':res.get('complete_pack'),
                   'visual_acceptance':'pending'}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print('ERROR:', error, file=sys.stderr)
        raise SystemExit(2)
