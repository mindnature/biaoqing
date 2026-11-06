"""Default Chinese sticker pack and deterministic four-at-a-time production layout.

The pack is a plan, not artwork; generating individual moving character poses
requires an image-capable agent or animator.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CAPTIONS = (
    "好的", "收到", "谢谢", "点赞",
    "哈哈哈", "爱你哟", "委屈", "大哭",
    "生气", "无语", "疑惑", "震惊",
    "么么哒", "加油", "拜拜", "晚安",
)
EXTRA_CAPTIONS = (
    "早安", "抱抱", "嗯？", "送你小心心",
    "忧愁", "666", "哇", "摸摸头",
    "辛苦了", "在吗", "开工啦", "吃饭啦",
    "困了", "冲鸭", "期待", "安排了",
)
ALL_CAPTIONS = DEFAULT_CAPTIONS + EXTRA_CAPTIONS
RECOMMENDED_COUNTS = (1, 4, 8, 16, 24, 32)
DEFAULT_BATCH_SIZE = 4
MAX_CAPTIONS = 32
FRAMES_PER_STICKER = 16

# Name, slug and expressive action description. An action has to involve more
# than a whole-sprite transform: coordinated expression, arms and torso.
ACTION_PRESETS = {
    "好的": ("okay", "微笑点头，右手抬起比出明确OK手势，眼神回应后自然收手"),
    "收到": ("received", "听到消息后站直，眼神聚焦，右手抬起认真敬礼，轻轻点头再复位"),
    "谢谢": ("thanks", "双手逐渐合十，眼睛笑弯，身体略向前躬，诚恳致谢后回正"),
    "点赞": ("thumbs-up", "眼睛一亮露齿微笑，手臂抬起并竖起大拇指，身体随之向前"),
    "哈哈哈": ("big-laugh", "从憋笑到仰头爆笑，眼睛弯起、张嘴大笑，肩膀和身体随笑起伏"),
    "爱你哟": ("love-you", "眼睛发亮，双手在胸前由两侧合成爱心，脸颊羞红，向前送心再收回"),
    "委屈": ("hurt", "眉眼低垂、嘴巴撅起，肩膀下沉，泪眼汪汪，抬手擦泪后恢复"),
    "大哭": ("cry", "嘴角开始颤抖，突然张大嘴放声大哭，泪珠喷涌、身体抽泣，再缓缓收势"),
    "生气": ("angry", "眉毛下压、鼓起双颊，双臂逐步叉腰，身体重心前移，哼了一声回头"),
    "无语": ("speechless", "半月眼缓缓侧目、嘴角下垂，双手无奈摊开，停顿后叹气"),
    "疑惑": ("confused", "先听清，再歪头、挑眉、微张嘴，头顶问号冒出，缓慢缩回"),
    "震惊": ("shocked", "眼睛逐帧睁大，嘴巴张成圆形，双手骤然抬起到脸颊旁，身体后仰"),
    "么么哒": ("kiss", "闭眼嘟嘴，一只手从嘴边向外送出飞吻，爱心飞出，害羞回位"),
    "加油": ("cheer", "双拳收在胸口蓄力，眼睛坚定，握拳向前打气，身体前倾后回正"),
    "拜拜": ("bye", "笑着抬手，手掌从肩旁有节奏来回挥动，头与身体配合，挥手告别"),
    "晚安": ("good-night", "抱着枕头，缓缓揉眼打哈欠，头靠枕头闭眼，安稳入睡"),
    "早安": ("good-morning", "从睡眼惺忪到伸懒腰、睁大眼微笑，抬手挥动说早安"),
    "抱抱": ("hug", "微笑张开双臂、向前迈近，身体前倾作拥抱状，慢慢松开"),
    "嗯？": ("huh", "眨眼后歪头，眼神朝上聚焦，眉毛上扬，身体微微前探"),
    "送你小心心": ("heart", "双手从胸前抬起形成爱心，身体前倾轻送爱心后回到原位"),
    "忧愁": ("sad", "轻轻叹气、肩膀下垂，抬手撑脸，眼神低落后缓缓抬头"),
    "666": ("awesome", "露出赞许的笑容，向前竖起大拇指，用力点头并收回"),
    "哇": ("wow", "眼神瞬间明亮、嘴张大，双手抬到脸边，身体后倾再回弹"),
    "摸摸头": ("pat", "抬手温柔地摸摸头，眼睛弯起，动作轻柔，逐渐收手"),
    "辛苦了": ("well-done", "双手送上暖茶，眼睛笑弯，身体微微前倾表达关心"),
    "在吗": ("anyone-there", "从边缘探头张望，眼睛左右转动，举手轻轻示意"),
    "开工啦": ("start-work", "整理袖口、握拳振作，身体坐直，精神饱满地开始工作"),
    "吃饭啦": ("dinner", "眼睛发亮、双手合拢，端起小饭碗开心招呼"),
    "困了": ("sleepy", "眯眼打哈欠、揉眼，肩膀渐渐放松，脑袋慢慢下垂"),
    "冲鸭": ("lets-go", "收紧双拳向下蓄力，双脚微屈，向前大步冲刺再收势"),
    "期待": ("excited", "双手在胸前交叠、眼神闪亮，轻轻踮脚张望，雀跃等待"),
    "安排了": ("on-it", "认真点头、挽起袖子，伸手比出确定手势，干练转身"),
}


def choose_captions(actions: list[str] | None = None, count: int | None = None) -> list[str]:
    """Default to 16; explicit captions or count override the preset."""
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_CAPTIONS):
        raise ValueError(f"Count must be between 1 and {MAX_CAPTIONS}")
    if actions is None:
        captions = list(ALL_CAPTIONS[: (count if count is not None else 16)])
    else:
        captions = [str(x).strip() for x in actions]
        if not captions or any(not x for x in captions):
            raise ValueError("Custom captions must not be empty")
        if count is not None and count != len(captions):
            raise ValueError("--count must match the number of explicit --actions")
    if len(captions) > MAX_CAPTIONS or len(set(captions)) != len(captions):
        raise ValueError("1..32 unique captions required")
    return captions


def group_actions(actions: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict]:
    if not 1 <= batch_size <= 8:
        raise ValueError("Batch size must be between 1 and 8")
    batches = []
    for index, start in enumerate(range(0, len(actions), batch_size), 1):
        subset = actions[start:start + batch_size]
        batches.append({
            "index": index,
            "name": f"batch-{index:02d}",
            "count": len(subset),
            "captions": [a["caption"] for a in subset],
            "slugs": [a["slug"] for a in subset],
            "planned_frames": len(subset) * FRAMES_PER_STICKER,
            "status": "planned",
        })
    return batches


def write_batch_guides(project: dict, root: Path):
    folder = root / "batches"
    folder.mkdir(parents=True, exist_ok=True)
    for batch in project["batches"]:
        subset = [a for a in project["actions"] if a["slug"] in batch["slugs"]]
        (folder / f'{batch["name"]}.json').write_text(
            json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        lines = [
            f'# {project["character"]["name"]} · 第 {batch["index"]}/{len(project["batches"])} 批',
            f'本批 {batch["count"]} 个独立 GIF，每个 16 张真实动作帧，共 {batch["planned_frames"]} 张。',
            '同一角色与画风，先审核第 0、5、8、15 帧，再补齐连续 16 帧。',
            '不可通过整体平移/摇晃/缩放模拟逐帧演出；字幕必须最后统一叠加。',
            '',
        ]
        for action in subset:
            lines += [f'## {action["caption"]} → {action["slug"]}',
                      f'动作：{action["gesture"]}',
                      f'分镜：prompts/{action["slug"]}.txt',
                      f'素材目录：{action["frames_dir"]}/000.png ... 015.png', '']
        (folder / f'{batch["name"]}.md').write_text("\n".join(lines) + "\n", encoding="utf-8")
