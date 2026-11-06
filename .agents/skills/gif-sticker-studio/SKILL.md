---
name: gif-sticker-studio
description: Repository-scoped Codex skill to create and validate square animated GIF stickers from user-provided reference images, videos or frame sequences, using actual available media-generation tools and strict delivery QA.
---

# GIF Sticker Studio｜仓库内 Codex 入口

本文件专供 **在本 GitHub 仓库工作目录中启动 Codex** 时自动发现 Skill。完整执行说明在仓库根目录：

- 先读取 \`../../../SKILL.md\`，按其中流程完成任务。
- 从仓库根目录执行 \`python scripts/studio_v4.py doctor\`、\`plan\`、\`import\`、\`review\`、\`build\`、\`verify\`。
- 相对于本文件，完整代码位于 \`../../../scripts/studio_v4.py\`，检查说明位于 \`../../../references/codex-execution.md\`。
- **不要仅安装本子目录作为独立 Skill**，它没有内置脚本。普通用户应通过 \`$skill-installer\` 从本仓库根目录 \`.\` 安装整个 Skill（而不是只下载这个入口）。
- 用户提供的私有素材、字体、项目输出不可提交公共仓库。没有可用媒体模型时不要冒充已生成真实动画。
