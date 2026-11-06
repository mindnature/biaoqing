# Codex 制作可靠性指南｜GIF Sticker Studio V4.1

这是面向执行智能体的检查清单，不是生成模型，不会保证每次审美效果百分之百一致。

## 安装与发现

Codex 标准 Skill 需要 `SKILL.md` 中包含 `name`、`description` 的 YAML frontmatter。安装**本仓库根目录完整 Skill**，保留 `scripts/` 与 `references/`。根目录直接克隆、在项目中启动 Codex 时，`.agents/skills/gif-sticker-studio/SKILL.md` 是项目级发现入口，它会指向根目录真正的 Skill；若只安装该入口目录，会缺失脚本，因此不支持。

建议用户在 Codex 的对话中运行：

> 使用 $skill-installer，从 https://github.com/mindnature/biaoqing 的仓库根目录（path "."）安装完整 gif-sticker-studio Skill；安装后检查 SKILL.md、scripts/studio_v4.py、scripts/codex_doctor.py 与 scripts/validate_delivery.py 都存在。旧安装应先更新，不要同时保留多个同名 Skill 版本。

如果安装器没有支持直接从仓库根目录的下载操作，则克隆整个仓库，在 Codex 中打开该项目，使用仓库内自动发现的 Skill 入口。不要编造安装成功的日志。有关路径的细节以当前 Codex 的官方 Skill 说明为准。

## 任务路由：先实际发现能力

| 实际可用 | 采取行动 | 禁止 |
| --- | --- | --- |
| 可访问真正的图生视频工具 | 生成固定镜头、无字、绿幕/透明的短动作视频 → `studio_v4.py import` | 假称无需授权、额度或完全免费 |
| 只能生成图像或编辑图片 | 先生成第0/5/8/15锚点帧并校验，再补成16张相同角色连续姿势 | 拿同一张图整体位移代替肢体动作 |
| 已有 GIF、MP4、透明帧 | 直接导入现有动画，并做动作/透明检查 | 无条件重新生成用户提供的作品 |
| 无任何图像/视频生成能力或动画素材 | 明确缺少的执行能力，提供可执行的分镜及素材要求 | 谎称 GIF 已完成 |

先跑 `python scripts/studio_v4.py doctor --stage plan`。它只检查**本地**依赖；显示 `model_generation: unknown` 是正常的，必须由 Codex 自己检查当前工具可用性，不能把 “Pillow 已安装” 当作视频生成可用。

媒体导入路线：
- 视频：FFmpeg 必需，执行 `doctor --stage import --route video`。
- GIF/PNG：仅 Pillow，支持没有 FFmpeg 的用户。
- 原背景复杂：需要实际分割工具或重新让生成模型输出绿幕/透明，不能错误抠掉人物服装和毛发。
- 禁止把用户的原始人像、文字、字体上传到未授权第三方。

## 质量门禁与处理策略

**第一阶段｜角色身份/动作质量**
先核对原图，必要时写简短角色档案：比例、轮廓、颜色、五官、耳朵/发型、服饰和特征物。每个表情要与情绪相符的动作起势、发展、峰值、回收。不能仅头部整体晃动。模型输出不可控时，优先用单一源图持续生成的短视频；发现脸崩、肢体错位，应重新生成该段或替换异常帧。

**第二阶段｜代码检测**
必须检查动作目录中每张是无字、同尺寸的实际 PNG，`studio_v4.py review` 生成离线可预览 HTML。机器判定 `blocked` 不允许打包；`review_required` 需逐格视觉复核，不能假装自动修好了角色。若角色动作是一次性的，`--mode one-shot` 优于强制周期化。

**第三阶段｜字体与字幕**
一般文字由可用、合法的本地中文字体渲染。先核实文字和字体是否匹配，出样后实看是否错字、缺字、错位、太细、太小、遮住脸。自动样式分类只是启发式，没有真正的设计师语义理解。字体不存在或明确的书法字体不可用时提示；自动书法回退也必须说明，不隐瞒视觉差异。**不能通过软件成功加载字体证明汉字字形完全正确**。

**第四阶段｜导出与交付**
```bash
python scripts/studio_v4.py doctor --stage build --project workspaces/session/production.json --font "/path/to/font.ttf"
python scripts/studio_v4.py build workspaces/session/production.json --font "/path/to/font.ttf"
python scripts/studio_v4.py verify workspaces/session/production.json --batch 1
```
正常构建已经包含 preflight + delivery-validation，`verify` 可以复查过去的结果。它检查实际 GIF（方形、循环、<=500000字节、时长、至少12帧、动作质量）与 ZIP 中包含的每张 GIF 字节一一对应、manifest 中 slug/文案与 production.json 完全匹配。失败不能输出“已完成”，应定位问题并重新构建/修复。全部完成用 `verify --all`。

**第五阶段｜艺术和平台审查**
人工打开**压缩后的成品 GIF**，不是只看原帧：检查循环、字的大小、透明边缘、帧间闪动、GIF 降采样后的毛发与笔锋；检查每张是否表达对应文案。对微信等平台的当期官方上传要求单独核验。输出为「技术验收已通过，艺术及平台验收待确认」，不能报告已经被微信官方批准。

## 错误 → 处理

| 报错/失败 | 真实原因 | 解决办法 |
| --- | --- | --- |
| ffmpeg missing | 当前环境不能读取 MP4 | 安装 FFmpeg，或改导入现成的 GIF/PNG |
| 未提供图像/视频模型 | Skill 不含生成模型 | 使用 Codex 已连接的有效媒体工具，或提供现成动作 |
| no chroma/opaque background | 背景不是透明/绿幕/紫幕 | 请求专业抠像或重新生成色键素材 |
| whole_sprite_only | 动作基本只是全图移动 | 重做面部、头、手和身体联合运动 |
| duplicate/loop seam | 首尾或中间姿势不连续 | 替换异常帧，必要时选 one-shot |
| font unavailable/missing glyphs | 本地字体不可用或缺字 | 换有授权的合适中文字体，重新渲染并目视检查 |
| GIF too large | 压缩仍超 500000 字节或帧数不足 | 简化动画复杂度/色彩或重新制作，不能直接交付超限 |
| ZIP mismatch | 旧包、重复文件、错文案、数据不一致 | 重新构建并通过 `verify`，不要交付旧 ZIP |

## 交付的最小真实声明

明确写：实际完成 X/Y 张；具体 GIF 和 ZIP **真实存在的路径**；机器验证通过/失败（指出报告路径）；视觉审核状态；平台审核尚未进行；如未能生成真实动作，说明哪个环节缺少授权工具/素材。绝不把已生成的提示词、HTML 审核页或静态样例描述为已经交付的动图。
