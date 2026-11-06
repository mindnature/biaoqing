# GIF Sticker Studio｜通用动态表情包制作 Skill

基于**用户自己的或获得授权的参考素材**，协助制作适用于即时通讯的 GIF 动态表情包。支持人物、宠物、卡通、像素、插画、照片、潮玩和其他原创角色，不预设姓名、身份、性别、地域或美术风格。适用于 Codex 及能运行 Python、使用图像工具的智能体。

> **能力边界**：本仓库支持动作分镜、视频/GIF/PNG 动作素材导入、抽帧、轻量抠像、逐帧审核、字幕、压缩和打包，不内置图像或视频生成模型；真实角色表演需要用户的现成动画素材或外部生成工具；单张静态图摇摆或缩放不等于逐帧动画。

## Codex 安装后，如何尽量减少出错？

项目现在包含面向 Codex 的完整执行规范和两项可执行质量门禁：

- **[Codex 执行规范](references/codex-execution.md)**：智能体自动判断是否拥有视频生成、图像生成或现成素材，选择最合适路线；不得把静态图摇摆当作真实角色表演。
- **制作前检查** `scripts/codex_doctor.py`：检查本地环境、FFmpeg（仅视频需要）、中文字体和下一批真实动作帧是否齐备。它不会伪称 Codex 已拥有某个付费生成服务。
- **交付前验收** `scripts/validate_delivery.py`：逐个核验压缩后 GIF 的正方形、循环、大小、帧数、时长、动作信号；核对 ZIP 的文案清单及每个 GIF 的实际字节，避免旧包、缺包或错包。
- **`studio_v4.py build` 已串联前检与验收**，出错直接报告、不能伪称完成；美术质量与文字错字仍必须人工预览。

首次使用可以先运行：

```bash
python scripts/studio_v4.py doctor --stage plan
# 视频来源才需要 ffmpeg，运行：
python scripts/studio_v4.py doctor --stage import --route video
```

Codex 通过完整仓库根目录安装此 Skill，保留 `SKILL.md`、`scripts/`、`references/`；如果是直接克隆并在仓库中启动 Codex，`.agents/skills/gif-sticker-studio/SKILL.md` 提供项目级发现入口。**不能只下载这个入口而不安装脚本。** 当前 Codex 对 Skill 目录的自动发现规则以官方文档为准。

## V4.0｜真正的动画素材接入：图像 / 视频 / 已有素材三条路线

从 V4.0 起，**不必先手工准备好全部 16 张 PNG**。用户有权使用的动画视频（MP4/MOV/WebM）或现有动态 GIF、连续 PNG 可以直接导入：视频抽帧（需要 FFmpeg）→ 检测绿幕/紫幕或已有透明通道 → 色键透明化 → 统一坐标与方形画布 → 16 张真实姿势 → 动作 QA → 本地逐帧可视化预览 → 继续使用现有字幕、500KB GIF 导出与 4 张/批 ZIP。

### 最简单的两条使用方法

**方式一：通过 Codex 等智能体生成动画视频，再导入**

```sh
# 创建默认一套16个表情，4张一批；同时为每个表情写好图生视频提示词
python scripts/studio_v4.py plan \
  --character "示例角色" --reference "assets/character.png" \
  --output workspaces/sample

# 找到 generation/okay-video.txt，用已连接且获授权的视频工具生成对应动作 MP4；
# 本仓库不会自动调用外部模型或消耗 API 额度。
# 建议生成固定镜头、真实肢体动作、纯绿幕/紫幕背景的视频。
python scripts/studio_v4.py import \
  workspaces/sample/production.json okay /path/to/action.mp4 \
  --background auto --mode cycle

# 浏览器打开生成的离线 HTML，对16帧的脸、手、衣服及循环逐格审核
python scripts/studio_v4.py review workspaces/sample/production.json okay

# 第一批4个真实动作均导入并通过质量检查后，使用已有生产管线导出
python scripts/studio_v4.py build workspaces/sample/production.json \
  --font "/path/to/licensed-CJK-font.ttf"
```

**方式二：不用视频模型，直接导入现有 GIF 或 PNG 帧**

```sh
python scripts/studio_v4.py import workspaces/sample/production.json \
  okay /path/to/animated.gif
# 或 source 换成包含连续 PNG/JPG/WebP 的目录
```

**方式三：图像生成关键姿势**。打开 `prompts/<action>.txt`，由具备图像生成能力的智能体按固定角色参考图创作真实连续的 16 张动作 PNG（也可先生成动作图集并拆分）；然后走同样的 review/build。与视频路线相比，这条路线可能更易维持画面细节，但人物动作的连续性需要重点检查。

**具体边界**：工具不内置 GPT/Grok 或任何图生视频模型，也不自动代替用户登录、付费或授权服务。直接读取 MP4 需要安装 FFmpeg；透明背景只支持真实 alpha 或色键绿幕/紫幕的确定性处理，复杂实拍背景仍需外部抠像工具。自动循环选择和质量报告是启发式筛查，**不能保证人物真实、动作自然或所有平台审核通过**。

详细步骤、失败处理和生成服务责任边界见 [V4.0 生产指南](references/v4.md)。

## 默认规则与可配置项

| 项目 | 默认行为 |
| --- | --- |
| 表情包数量 | 一套 **16 个独立 GIF**，支持 1–32 个或用户自定文案 |
| 生产节奏 | **每批 4 个**，便于预览、修正后再批量制作 |
| 角色表演 | 每个 GIF **规划 16 帧**，逐帧变化（默认 140ms/帧） |
| 画布格式 | **正方形 GIF**，循环播放 |
| 文件体积 | 单个 GIF **≤500,000 字节**（项目默认导出目标） |
| 画面与文字 | 优先透明背景；文字与动画分层，字幕逐帧固定 |
| 视觉风格 | **auto**：根据素材分析后适配，不默认某个 IP 或固定配色 |
| 发布审核 | 技术检查不等于平台审核、角色外观或动作质量的人工验收 |

这是一套适合微信使用的默认导出参数，**不是所有聊天平台统一的官方规格**。实际上传前应核对目标平台的最新规则。要求 16 个 GIF、每个规划 16 帧，与最终 GIF 因压缩最低保留 12 帧是两个不同概念。

## 安装

打开 Codex 或兼容 Agent Skill 的智能体，提供本仓库地址：`https://github.com/mindnature/biaoqing`。安装后按照 `SKILL.md` 执行。

本地使用：Python 3.10+，执行 `python -m pip install -r requirements.txt`。导入 MP4/MOV/WebM 视频必须安装 FFmpeg；GIF 和 PNG 目录导入不需要。字体由使用者提供有合法使用权的本地 CJK 字体，本项目不分发字体。

## 从参考图到动态 GIF

```sh
# 1. 创建默认16个表情的制作计划：4批，每批4个
python scripts/studio_v3.py plan \
  --character "示例角色" \
  --reference "assets/character.png" \
  --output workspaces/sample

# 也可以指定具体词语；此时按输入数量而不是强制补足16个
python scripts/studio_v3.py plan \
  --character "示例角色" \
  --reference "assets/character.png" \
  --actions "好的,谢谢,哈哈,晚安" \
  --output workspaces/custom

# 2. 通过图像生成工具或手绘：每条表情准备16张不同姿势的透明 PNG，
#    保存在 frames/<动作名>/000.png ... 015.png
#    先审第0、5、8、15帧，确认角色一致，再补齐完整动作

# 3. 检查每个动作，避免整图轻微晃动冒充真正表演
python scripts/studio_v3.py inspect workspaces/sample/frames/okay

# 4. 一次构建下一批4个 GIF；完成一批后再处理下一批
python scripts/studio_v3.py build workspaces/sample/production.json \
  --font "/path/to/licensed-CJK-font.ttf"

# 5. 查询进度；所有批次完成后自动产生 build/complete-pack.zip
python scripts/studio_v3.py status workspaces/sample/production.json
```

也支持 `--count 1`、`--count 4`、`--count 8`、`--count 24`、`--count 32` 等指定数量。对于需要书法题字的素材，可另加 `--brush-font "/path/to/licensed-calligraphy.ttf"`；字体不具备时应使用合法可用的替代样式，并向用户说明视觉差异。

## 逐帧动作与导出

每个表情有独立动作分镜，且应有真实的眼神、脸部、头部、手臂和身体变化。原始动作帧必须同尺寸、同身份、尽量固定镜头，不应由一张静图直接复制 16 份。可用 `scripts/studio_v3.py import-atlas` 拆分规范的 4×4 图集，再通过 `inspect` 检查。

项目包含 `scripts/export_keyframes.py`、`scripts/export_pixel_actions.py` 等动作合成器，以及 `scripts/wechat_export.py` 正方形 GIF 导出器。轻动态制作仅在用户明确提出时使用，不能默认为“完整角色表演”。

## 通用字幕设计

`auto` 使用画面颜色、透明度与亮度启发式选择协调的字幕。支持 `classic`（高对比）、`cute`（萌系）、`heritage`（暖色插画）、`brush`（水墨题字）等可选风格，不将任何风格与某个具体角色绑定。文字不使用底色条或字幕板，并固定于整张 GIF 的一致位置。

```sh
python scripts/wechat_export.py input.gif output.gif \
  --text "收到" --font "/path/to/licensed-CJK-font.ttf" \
  --caption-style auto

# 手动选样式，或在需要书法字体时传入 --brush-font
python scripts/wechat_export.py input.gif output.gif \
  --text "加油" --font "/path/to/licensed-CJK-font.ttf" \
  --caption-style classic
```

该配色判断不是大模型审美判断：应在小尺寸聊天场景预览字体、颜色对比、描边、遮挡、文字正确性与循环动作。整套表情采用一致视觉系统，但每个表情的动作必须独立。

## 质量与测试

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

自动检查包括空白、裁切、跳帧风险、重复姿势、压缩后动作信号、时长、循环、正方形和文件大小等。**不会自动发现所有五官/手部错误，也不能保证平台审核通过。** 制作或分享他人形象、字体、商标与作品时应确认相应使用权。

## 资料与许可

使用规则见 [SKILL.md](SKILL.md)，动画工作流见 [references/v3.md](references/v3.md)，字幕风格见 [references/caption-v32.md](references/caption-v32.md) 与 [references/typography-v33.md](references/typography-v33.md)。历史兼容接口见 `references/v2.md` 和 `references/v31.md`。

项目按 [MIT License](LICENSE) 发布。仓库保留其所包含第三方开源代码/文档依法要求的版权及许可声明，见 [NOTICE.md](NOTICE.md)；第三方字体、图像和角色素材的权利单独确认。
