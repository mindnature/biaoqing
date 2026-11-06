---
name: siran-gif-studio
description: 使用自有或已授权的角色参考图制作可审查的逐帧角色动作、高清或像素轻动态 GIF，并导出固定中文字幕的微信表情包。必须保留角色一致性、逐帧视觉验收、微信文件大小验证。
---

# 思然 GIF Studio · 角色动态表情包 Skill

## V2.0 执行入口（优先执行）

**先阅读 [V2.0 工作流](references/v2.md)。** 对新的完整逐帧动作请求，优先使用 V2.0，而不是直接拿一个静止立绘交给轻动态导出器：

1. 按用户最新确认的角色形象、画风与台词运行 \`python scripts/studio_v2.py plan --character "角色" --reference "角色图片路径" --actions "收到,哈哈,委屈,哼" --output workspaces/角色\`，产出每项动作独立的 16 帧分镜和 prompt；不要生成未经用户授权的角色形象。
2. **利用智能体自身合法可用的图像生成/绘画能力**，按四个关键姿势的身份锚点初审，再补足连续动作的 16 张无文字、透明的单帧 PNG：\`frames/<slug>/000.png ... 015.png\`。没有图像工具就如实说明，不能把静态图复制/整图移动来冒充完整表演。
3. \`python scripts/studio_v2.py inspect ...\` 抓技术风险；按报告重新画问题帧，或用 \`repair\` 实施显式、可审查的位置修正或帧替换。**不得把量化指标当做人脸/手指视觉识别**。
4. \`python scripts/studio_v2.py build workspaces/角色/production.json --font <CJK_FONT> --heart\` 将有真实连续姿势的 16 帧合成为 GIF，通过微信体积导出后批量打包。默认重要问题阻止制作、可疑问题标注待审核；\`--strict\` 把可疑问题也作为阻断。
5. 再打开 \`build/reports/*-contact.png\`、原始和压缩 GIF，检查角色、字幕、首尾、抽帧、动作表达；记录用户是否认可，**不可自动声称微信审核/用户验收通过**。

V1 的 \`export_pack.py\`、\`export_keyframes.py\` 与 \`wechat_export.py\` 仍保留用于单独的轻动态、关键帧及导出需求。V2 不具备内建生成模型或模型级的自动动作修复。


## 任务分界
这是**角色动画制作工作流**，并非模型权重或静态图自动变成完整动作的算法。
你（执行本 Skill 的智能体）负责审美判断、动作规划、用可用图像工具产生角色素材、运行动画脚本、检查成品。
Python 脚本只负责将已存在的关键姿势/动作图集合成为动画，以及导出/验证。不得声称没有姿势素材也能自动完成。
如果没有图片生成工具，先说明限制，仍可帮助把已提供的 PNG 帧合成为 GIF。

## 输入与权利
- 只处理用户提供/获授权的图片、模型、字体；示例图库中的第三方 IP 不应视为可商用资产。
- 优先使用用户**最近确认的同一角色参考图**，锁定头身比、轮廓、配色、耳朵/头发、五官、装饰物、服装、笔触和材质；不同表情可以变，但角色不能换脸。
- 用户已指定的角色、文案、数量、画风、动作方式和平台规格必须沿用；不要反复提问。
- 默认优先高清可爱插画（HD），**不要仅因为项目源名带 pixel 就转像素风**。
- 外观与运动分开选择：pixel/illustration/photographic × light/consecutive。

## 单张 GIF：先动作设计，再画关键帧
1. 为每一条文案设计**独立可读的动作**，避免同一站姿换文字。先给明确的表演分镜：起势 → 蓄力 → 主动作 → 回弹 → 收势与循环。
2. 对新角色先制作 3–4 个关键姿势（含中性、预备、峰值和回稳），检查身份特征；只有通过后再扩充至约 12–16 张连续关键姿势。
3. 关键姿势最好构成**透明 PNG atlas**，通常 4×4 网格；一格一帧，位置、缩放、光照、角色体积和所有五官必须一致。给足透明边距，不得跨格。
4. 动作必须包含头、表情、躯干及有关肢体的协调变化。**整图跳动 / 脸不动只旋转胳膊 / 无缝融化形变**不能冒充逐帧表演。
5. 图集中**不要让生成模型直接写中文字**；每张只画角色，字在合成/导出时独立固定叠加。

## 合成选择
- 轻动态：`python scripts/export_pack.py <manifest.json> <empty-output> --font <CJK_FONT>`。适合已设计不同姿势的大套 GIF，但这是 whole-sprite motion preset，不能称为完整肢体表演。
- 高清插画/真人连续动作：`python scripts/export_keyframes.py <action-manifest.json> <empty-output> --font <CJK_FONT>`。清单说明：`references/keyframes.md`。
- 像素连续动作：`python scripts/export_pixel_actions.py <pixel-manifest.json> <output> --font <CJK_FONT>`。清单说明：`references/pixel-actions.md`。
- 技术审查：`python scripts/review_gif.py extract <gif> <review-dir>`；检查逐帧五官、手、服装、相邻帧位移、首尾循环，必要时修复后重新合成。`references/stability.md` 与 `references/character-consistency.md` 提供规范。

## 微信导出（本仓库新增）
- 首选透明方形 GIF；默认**500000 字节**上限是保守的导出目标，而不是对微信所有场景的官方规格声明。
- **若上游 GIF 已含文字，不能再次使用 --text 叠加**。如果上游没有字幕，使用：
`python scripts/wechat_export.py input.gif output.gif --text 收到 --font <CJK_FONT> --heart`。
- 字幕由程序逐帧在**同一固定坐标**绘制：粉红粗字、白描边、可选小爱心；禁止任何底色条、矩形字幕框；避免文字压在角色脸上。
- 批量：`python scripts/wechat_export.py input-folder output-folder --captions captions.json --font <CJK_FONT> --zip output.zip`。语义不同的 GIF 必须匹配实际文件名，不能靠图集格序猜。
- 对于字形缺失、字体路径错误或小于帧数/大小要求的情况，停止/说明。压缩不成功时不要直接提交超限文件，更不要宣传「微信已验收」。
- 微信使用规格、保真与视觉检查：`references/wechat.md`。

## 质量门槛
先从实际 GIF 解码检查尺寸、透明通道、持续时间、循环和文件体积；其次以原大小逐帧检查角色身份、手指/耳朵、衣服、不合理的合并/分离、瞬间闪烁和循环断点；最后用真人视觉审核字幕的字形和位置。
技术检查通过 **≠** 用户认可，也 **≠** 微信平台审核通过。
任何重新导出的文件均重新检查。**不要把旧版失败小样当作「已成功模板」**。
先完成一张高质量小样通过用户确认，再扩大批量；用户已经批准的小样应当沿用参数。

## 交付
每条文案独立 GIF；按类别文件夹；可选 ZIP、动态预览/MP4；汇报真实通过与待复核项目。永不伪称已完成没有实际生成的素材。
