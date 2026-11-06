# 思然 GIF Studio · 原创 IP 动态表情包工作室

让 Codex / 支持自定义 Skill 的智能体根据**你有权使用的角色参考图**规划表情，制作轻动态或完整逐帧表演，审核后输出可独立发送的透明 GIF。此仓库基于 [WoYun520/pixel-gif-sticker-pack](https://github.com/WoYun520/pixel-gif-sticker-pack) 的 MIT 开源代码升级；本仓库不重新分发原项目的大量示例 GIF 和可能涉及第三方 IP 的素材。

> 项目状态：**可运行的 Skill 与 Python 导出工具**，不是无需模型的「一张图自动变成完整动画」服务。复杂动作需要具备图像生成能力的智能体先制作连续关键帧；Python 脚本承担合成、压缩与验证。视觉效果需要人工审核。

## V3.1｜默认 16 张微信表情包，每张 16 帧，分 4 批制作

**不用再指定每套多少张。** 上传你有权使用的原创 IP 角色参考图，说「做一套表情包」，现在默认自动创建 **16 个独立 GIF × 每个 GIF 16 张真正不同的角色动作帧 = 256 张动作帧**；按 **每批 4 个 GIF** 分批生成与审核，每批需 64 张动作帧。**动作帧必须由具备绘图/图像生成能力的智能体或创作者实际制作，Python 工具不能凭空画出动作。**

固定默认文案（按批次）：

| 批次 | 4 个表情 | 独立 GIF | 计划动作帧 |
| --- | --- | ---: | ---: |
| 第 1 批 | 好的、收到、谢谢、点赞 | 4 | 64 |
| 第 2 批 | 哈哈哈、爱你哟、委屈、大哭 | 4 | 64 |
| 第 3 批 | 生气、无语、疑惑、震惊 | 4 | 64 |
| 第 4 批 | 么么哒、加油、拜拜、晚安 | 4 | 64 |
| **总计** | **16 种不同的动作表演** | **16** | **256** |

快速开始：

~~~sh
# 默认的16张表情，每张16帧，自动分成4个批次。角色参考图保留在本地工作区。
python scripts/studio_v3.py plan --character "一然" --reference "private/role.png" --output workspaces/yiran

# 请有图像生成能力的 Codex / 智能体按照 prompts/ 和 batches/ 的分镜，
# 为第1批4个动作各制作000.png到015.png的16张独立透明角色姿势图
# 检查后只输出第1批四张 GIF / 对应质量报告 / ZIP，无需预先完成第2—4批
python scripts/studio_v3.py build workspaces/yiran/production.json --font "/path/to/CJK-Font.ttf" --heart

# 查看已完成批次与下一批；依次补全其他批次关键帧，并再次执行上一条 build
python scripts/studio_v3.py status workspaces/yiran/production.json

# 全部批次制作且技术检查通过后，程序自动导出 build/complete-pack.zip
# 已经具备全部关键帧时，也可以显式逐批构建：
python scripts/studio_v3.py build workspaces/yiran/production.json --font "/path/to/CJK-Font.ttf" --all

# 手动重组最终 ZIP（必须先完成全部批次）
python scripts/studio_v3.py assemble workspaces/yiran/production.json
~~~

也可指定预设数量：\`--count 1\`、\`--count 4\`、\`--count 8\`、\`--count 16\`、\`--count 24\` 或 \`--count 32\`；程序也支持 1–32 范围内其他明确数量。自定义文案优先于默认清单，例如 \`--actions "哇,收到,哼,晚安"\`；指定 \`--count\` 和 \`--actions\` 时数量须一致。不足 4 张的尾批次会按实际张数生成。

保留 V3 完整逐帧表演门禁、固定字幕和微信体积验证，不允许自动降级到一张图摇摆的轻动态。**自动测试通过不等于表演已由用户验收或微信官方审核通过。**

阅读 [V3.1 批量生产指南](references/v31.md) 和 [V3 动作表演质量规范](references/v3.md)。

## V3.0｜完整动作技术规范（兼容旧项目）

**已从「合成和压缩 GIF」升级为具备表演动作门禁的工作流**。V3 不能凭空生成关键姿势：需要有图像生成能力的 Codex/智能体或画师，先制作角色 16 张连续动作 PNG。针对你反馈的「人物没动作、只有轻动态」，现在会对裁剪对齐后的姿势进行比较，只有整图平移、缩放或少量重复画面会被拦截，**不会自动偷偷退回轻动态模式**。

```sh
# 角色动作分镜：为每条表情生成16帧方案，默认140ms/帧
python scripts/studio_v3.py plan --character "一然" --reference "private/role.png" --actions "哈哈,委屈,收到,哼" --output workspaces/yiran

# 使用智能体图像工具生成、核对16张真正独立的动作帧，放入 frames/<slug>/000.png 到 015.png
# 或把4x4透明姿势图集准确拆解（每一格必须真实变化，不能只是整图移动）
python scripts/studio_v3.py import-atlas atlas.png workspaces/yiran/frames/hmph

# 检测是否仅轻动态、帧数不足、无真实脸部与身体局部变化
python scripts/studio_v3.py inspect workspaces/yiran/frames/hmph --report workspaces/yiran/hmph.json

# 全部动作帧就绪后，统一合成透明GIF，字幕后期添加，微信压缩且保留不少于12帧
python scripts/studio_v3.py build workspaces/yiran/production.json --font "/path/to/authorized-CJK-font.ttf" --heart
```

V3 对原始动作帧和最终压缩 GIF 都执行检查，并保存质量报告。**数值通过不代表动作自然或微信审核通过**，仍需实际播放与逐帧目视确认。模型没有能力生成连续关键帧时会明确失败，不会伪称完整表演。更多细节：[V3.0 逐帧表演说明](references/v3.md)。

## V2.0 新能力：真实动作制作工作流

**一张角色图不会自动被本脚本变成高质量逐帧动画。** V2 提供可执行的动作分镜、量化异常检测、显式单帧修复和批量合成；必须先由支持图像生成的智能体或绘图人员制作 16 张真实、连续、有透明背景的动作关键帧。

~~~sh
# 1. 为一然生成9种表情动作分镜与独立的制作提示词
python scripts/studio_v2.py plan --character "一然" --reference "private/yiran.png" --actions "哈哈,委屈,收到,哼,嗯？,晚安,早安,加油,拜拜" --output workspaces/yiran

# 2. 用智能体按照 prompts/*.txt 生成、审核并保存每张16帧动作PNG：000.png~015.png
# 3. 合成之前检测帧级问题
python scripts/studio_v2.py inspect workspaces/yiran/frames/received --report workspaces/yiran/received-review.json

# 4. 把所有动作的16张PNG准备好后，单命令生成 GIF / ZIP / 检查报告
python scripts/studio_v2.py build workspaces/yiran/production.json --font "/path/to/CJK-Font.ttf" --heart
~~~

\`scripts/studio_v2.py repair\` 支持按照人工指定的替换图和位置偏移修复帧，并保留修复记录，不会错误地声称程序可自动重绘变形的手或脸。

详细功能、目录示意、问题处理与边界：**[V2.0 操作说明](references/v2.md)**。

## 从零开始（推荐）

1. 在 Codex 发送：`请从 https://github.com/mindnature/biaoqing 安装并使用这个 Skill。`
2. 上传自己的角色图，并说明要做的动作（建议先试「收到」「哈哈」「委屈」「哼」）。角色必须保持固定头身比、发型/配饰、色彩及表情特征。
3. 首先生成 **3–4 张动作关键姿势** 检查角色一致性，再制作约 12–16 张连续姿势的透明图集，保留无文字画面。
4. 根据 `SKILL.md` 选择原项目提供的 **完整动作** 合成器或轻动态合成器，逐帧检查并修复问题。
5. 用本仓库新增的 `scripts/wechat_export.py` 统一叠字、压缩并验证每张 GIF。实际尺寸/体积请以当前微信表情开放平台要求为准。

## 本仓库的关键升级

| 功能 | 对应文件 |
| --- | --- |
| Codex Skill 使用规范、角色动作与视觉验收 | `SKILL.md` |
| 原项目高清关键帧 GIF 合成 | `scripts/export_keyframes.py` |
| 原项目像素全身动作合成 | `scripts/export_pixel_actions.py` |
| 原项目轻动态合成 | `scripts/export_pack.py` |
| 原项目逐帧检查、循环接缝审核 | `scripts/review_gif.py` |
| **新增：微信小体积透明 GIF、固定中文字幕、批量 ZIP、输出验证** | `scripts/wechat_export.py` |
| **新增：微信规范、角色锁定、使用清单** | `references/wechat.md`、`references/character-consistency.md` |
| **新增：自动测试** | `tests/`、`.github/workflows/ci.yml` |

## 环境

Python 3.10+；先安装 `python -m pip install -r requirements.txt`。预览 MP4 还需要 FFmpeg（含 libx264）。字幕必须提供本机已授权的、覆盖中文的字体文件路径；项目**不附带字体文件**。

## 微信 GIF 导出（新增功能）

已有不带字幕的动画 GIF，添加静止中文字幕（粉红粗字+白描边，爱心可选），再严格按**500,000 字节**上限导出：

```sh
python scripts/wechat_export.py input.gif output.gif --text 收到 --font "/path/to/ChineseFont.ttf" --heart
```

批量导出（`captions.json` 将原文件名，不含扩展名，映射到字幕）：

```sh
python scripts/wechat_export.py build/gifs build/wechat --captions captions.json --font "/path/to/ChineseFont.ttf" --zip build/wechat.zip
```

`captions.json` 示例：

```json
{"001": "哈哈", "002": "委屈", "003": "收到", "004": "哼"}
```

如源 GIF 本身已带文字，**不要再次添加字幕**，否则文字会重复。此导出器把整个源动画按原始比例缩入方形画布，在下方给新字幕留空间；生成 GIF 是有损压缩，体积过大时将降低调色板、分辨率或帧数；若压缩后仍超过指定大小就直接失败，不会伪称通过。保持总时长，但降帧有可能损失动作流畅度，须再次人工审核。

**要让微信字幕只叠加一次：**高清关键帧动作清单必须保留非空 `text`（用于命名），同时在 entry 中设置 `"render_caption": false`；这样上游只合成无字幕的角色动作。然后用 `wechat_export.py --text 收到 --font ...` 添加唯一的固定字幕。可参考 `examples/action-manifest.example.json`（须自行提供 4×4 透明关键帧图集 `poses.png`）。

原项目各合成器的指令示例：

```sh
python scripts/export_pack.py manifest.json build/light --font "/path/to/ChineseFont.ttf"
python scripts/export_keyframes.py action-manifest.json build/actions --font "/path/to/ChineseFont.ttf"
python scripts/export_pixel_actions.py pixel-manifest.json build/pixel --font "/path/to/ChineseFont.ttf"
python scripts/review_gif.py extract build/wechat/003.gif build/review/003
```

轻动态与逐帧关键帧所需 JSON 结构见 `references/manifest.md`、`references/keyframes.md` 和 `references/pixel-actions.md`。脚本**不会自动生成角色姿势**，仍需先生成素材。

## 验证

```sh
python -m pytest -q
```

自动检测文件解码、方形画布、循环、时长、透明像素、大小及部分非法输入。**自动测试通过不等于**微信平台审核通过，也不等于角色动作自然；尤其要检查首尾循环、字形、脸部一致性、手部变形及字幕遮挡。

## 版权与许可

本项目基于原作者 WoYun520 以 **MIT License** 发布的代码与文档进行二次开发，并保留原版版权声明，详见 `LICENSE`、`NOTICE.md`。新增代码同样以 MIT 发布。角色肖像、示例图片、商标、字体等第三方权利需分别获得授权；不能因为工具开源就假定角色素材可自由商用。
