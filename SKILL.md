---
name: gif-sticker-studio
description: For Codex tasks making animated GIF/WeChat stickers from a character photo, drawing, video, GIF or sprite sheet; plan coordinated frame-by-frame acting, use the actually available image/video tools, review motion and character consistency, style Chinese captions, and export square looping GIFs up to 500000 bytes. Does not bundle a generation model.
---

# GIF Sticker Studio｜Codex 执行 Skill（V4.1）

## 任务目标与责任边界

不要假定任何使用者有固定角色、职业或审美偏好；只使用本次已提供的需求与素材。把用户本次提供或合法授权的角色/宠物/图片做成 **真正有表情和肢体运动的动态 GIF 表情包**。优先完成用户任务，而不是只写分镜、安装说明或静态动图。**工具可用性、原始动作素材、真实生成结果必须先被证实；不许虚构生成过程、模型权限、下载链接或验收通过。**

默认：正方形、循环 GIF、每个≤500000字节；一套16个独立表情（可自定义1–32）、每张规划16个独立姿势、每批4个，最终压缩不得少于12帧。用户明确指定的文案、数量、风格和动作优先。轻动态只有用户明确要求时才可采用，不能用一张图的缩放/晃动冒充角色表演。

## 先执行的决策，不要依赖猜测

1. 识别用户**本轮**素材：角色图片、GIF/视频、连续帧目录、图集或是否需要原创角色。不要使用前任用户的个人角色/偏好。若角色参考必不可少且未提供，才请用户提供。
2. **发现并检查当前 Codex 实际可调用的媒体工具**（不靠项目名称推断）：可生成真实视频则优先视频表演；仅有图像生成则生成至少4个锚点姿势、再补16张连续关键帧；已有动态视频/GIF/帧则直接导入。不内置视频模型、无需API密钥作为本项目配置。
3. 若只有文本代码执行、没有媒体生成工具且用户也没有动作素材：可以提供真实、可执行的制作计划和所缺的资源，**不得声称已经制作表情包**，不得偷偷回退静态轻动态。外部付费、发送私有图像、连接账号须尊重当前授权。
4. 用 `python scripts/studio_v4.py doctor --stage plan` 确认本地依赖；视频路线 `doctor --stage import --route video` 检查 FFmpeg。Pillow必需，FFmpeg仅视频导入必需。
5. 本地运行时从**本 Skill 根目录**执行 `scripts/...`。当前是克隆的 GitHub 仓库时可按仓库根目录运行；如仅安装了缺少 scripts 的单一说明文件，先正确安装完整仓库而不是编造可执行程序。

## 严格的“制作 → 审核 → 交付”流程

### 计划
```bash
python scripts/studio_v4.py plan --character "本次角色名" --reference "assets/character.png" --output workspaces/session
```
若用户给定动作文字则添加 `--actions "收到,哈哈,抱抱,再见"`；只要求数量则 `--count N`。产生 `production.json`、独立动作分镜与 `generation/<slug>-video.txt`。这些是**计划**，不是生成结果。

### 产生真实动作素材
- 视频：有实际权限的生成工具基于参考图生成固定镜头、单角色、明显头/脸/肩/手/身体变化的真实视频文件；优先原生 alpha 或纯绿/紫幕（角色不得与色键同色），无文字/其他人物/镜头推拉。调用外部服务前遵守用户授权与付费条件。
- 图像：生成真正不同的16张角色姿势 PNG（先审核 000/005/008/015），眼神、五官和身体相互配合，16张不能是重复图、全图平移或放大。
- 已有：使用用户的动画 GIF、MP4 或连续 PNG，不必调用模型。
- 有数据后才可执行：
```bash
python scripts/studio_v4.py import workspaces/session/production.json okay action.mp4 --background auto --mode cycle
python scripts/studio_v4.py review workspaces/session/production.json okay
```
`import` 选择真实动作帧并报告 QA；`review` 生成完全离线 HTML、联系表、JSON。逐帧检查角色身份、眼睛、嘴、手、服装、动作高潮及循环；对异常帧重新生成/替换，再复查。**程序化筛查无法自动修复坏脸/手。** 字幕不能让图像模型逐帧手写，应由后期程序固定叠加。

### 制作第一批并验证
```bash
python scripts/studio_v4.py doctor --stage build --project workspaces/session/production.json --font "/path/to/licensed-CJK.ttf"
python scripts/studio_v4.py build workspaces/session/production.json --font "/path/to/licensed-CJK.ttf"
python scripts/studio_v4.py verify workspaces/session/production.json --batch 1
```
`build` 已集成**前置检查 + 成品交付校验**：源帧、字幕字体是否可用、动作 QA、正方形、时长、循环、≥12帧、≤500000字节、每个 GIF 与 ZIP 清单/内容一一匹配。失败则**停止并说明原因，不宣称完成**。输出仍须人工查看字幕错别字、五官、画面美感和动态自然度。

先审第一批4个，得到实际反馈再继续下一批；用 `python scripts/studio_v4.py status workspaces/session/production.json` 查进度。完成全部批次后：
```bash
python scripts/studio_v4.py verify workspaces/session/production.json --all
```
不要把“自动测试通过”描述为“平台审核通过”。交付时说明完成张数、GIF/ZIP准确路径、是否通过技术校验、哪些仍需视觉审查；无法完成时列明阻断原因和已有的真实成果。

## 字幕与画风

每张表情独立设计动作，整套角色保持统一外观和字体体系。自动适配可用 `classic`、`cute`、`heritage`、`brush`，支持合法授权字体及 `--brush-font` 书法字体；不规定任何特定 IP、宗教、职业或国别美学。不得添加字幕底板/色条；缩略图中需清楚、字形正确、不遮住重要表情。字体是否缺字以及实际视觉适配**必须人为检查**，不是 Pillow 成功载入就算通过。

## 必看参考

- `references/codex-execution.md`：工具选择、失败恢复、质量验收与交付合同。
- `references/v4.md`：媒体导入细节和背景类型要求。
- `references/caption-v32.md`：字幕配色与视觉审查。
- `scripts/codex_doctor.py`、`scripts/validate_delivery.py`：可独立运行的机器检查。
- `README.md`：完整安装说明和兼容性边界。

**安全底线**：不要将用户图片、生成帧、字体和报告提交到公共仓库；不要静默调用可能收费的外部模型；不要在没真正产出 GIF 时宣称已完成。
