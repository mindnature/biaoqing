# V3.2：角色自适应艺术字幕系统

## 设计目标

用户反馈：同一项目中「好的」人物 GIF 的粉红字太细、太小、位置偏低，明显与主体分离；另一张猫咪「无语…」使用暖白色粗字、深棕厚描边，整体更协调、有力量。**不要把任何单一配色强制加到所有角色**；让 Skill 根据角色画风自动选择最匹配的文字设计。

## 何为自动

本项目的 **自动选择是 Pillow 图像分析和确定性排版**，非对画风语义的深度视觉理解。读取原始角色图（优先）或原始动作帧（回退），分析透明覆盖度、亮暗、颜色饱和度和暖色比例，一次性选择：

| style | 填充 | 描边与轮廓 | 适用 |
| --- | --- | --- | --- |
| classic | 暖白 \`#FFF9F0\` | 深棕 \`#3A241E\` + 深外轮廓 | 写实猫咪、摄影场景、需要强对比的角色 |
| cute | 粉红 \`#FF79A9\` | 白色内描边 + 深莓色外轮廓 | 明亮/柔和/彩度高的卡通角色 |
| heritage | 浅米金 \`#FBE7BA\` | 墨棕 \`#47352D\` + 深外轮廓 | 暖调、深色服装、国风手绘人物 |

相同一套角色所有 GIF 使用同样的 style，第一次构建时锁定到 \`build/caption-style.json\`。每张 GIF 内的样式在所有帧也保持固定。识别不满意时，用户可指定 \`--caption-style classic|cute|heritage\`。更换一整套角色风格，应当使用新的工作区重新生成避免混搭。

## 排版要求

- 使用大字重、饱满的中文粗圆或黑体字形，防止「瘦字」「空心字」或「通用淡粉字」观感；**字体文件必须由用户提供合法授权的本地字体**。
- 采用可读的多层次描边，而不是只画 2–3px 细白边：背后阴影 → 深色外轮廓 → 内层描边 → 清晰的文字填充。
- 图片覆盖接近全画面时，以画面较低处的角色表情区附近进行覆盖式排版；透明角色图则将文字与人物下半部协调融合，避免角色与字幕上下分家。
- 按文案实际长度自动缩放文字以适配小画布，避免超出左右边缘或压住眼睛。
- **禁用底色条、字幕底板、半透明框**；爱心装饰仅在需要时启用。
- 字幕在一个 GIF 内固定，绝不逐帧重选画风、位置和颜色；但角色仍需做 16 帧真正的身体表演，不得只有整张图上下浮动。

## 命令

独立 GIF：
\`\`\`sh
python scripts/wechat_export.py raw.gif done.gif --text "无语…" --font "/path/to/authorized-bold-CJK.ttf"
python scripts/wechat_export.py raw.gif done.gif --text "好的" --font "/path/to/authorized-bold-CJK.ttf" --caption-style heritage
\`\`\`

批量微信 GIF：
\`\`\`sh
python scripts/wechat_export.py raw_folder done_folder --captions captions.json --font "/path/to/authorized-bold-CJK.ttf" --zip pack.zip
\`\`\`

完整 V3.1 分组工作流（V3.2 字幕风格锁定）：
\`\`\`sh
python scripts/studio_v3.py plan --character "小玄游" --reference "private/role.png" --output workspaces/xuanyou
# 完成该批每张16帧真实连续PNG
python scripts/studio_v3.py build workspaces/xuanyou/production.json --font "/path/to/authorized-bold-CJK.ttf"
python scripts/studio_v3.py status workspaces/xuanyou/production.json
\`\`\`

可提供 \`--appearance photographic|illustration|pixel\` 显式提示照片、插画或像素画风。若已经开始导出一批，建议固定使用相同外观参数；全部批次共用首次锁定样式。

## 人工验收不可跳过

自动分类可能误判，尤其是混合媒材、浅色背景的照片、暖色卡通和新奇画风。必须检查：
1. 缩略图下文字是否足够粗、边界足够深、可快速辨识；
2. 文案和文字位置是否与动作呼应、人物眼睛/嘴巴是否被遮挡；
3. 字体是否真正包含所有汉字，是否有缺字、错字、假字；
4. 是否出现文字重复叠加、字幕条、移动字幕；
5. 降采样到微信 GIF 后，描边是否发虚、整体是否还能清晰辨认。

这个模块**不是新的图像生成模型，不会自动替换字体文件或自行修复复杂造型**。遇到需要艺术修正时先手动覆盖样式或更换有授权的字体、排版，再重新导出。
