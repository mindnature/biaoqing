# Repository instructions for Codex

This repository contains the public GIF Sticker Studio skill and its supporting CLI. For actual user sticker production, activate `gif-sticker-studio` (repository-scoped entry at `.agents/skills/gif-sticker-studio/SKILL.md` or the full root skill). Read `SKILL.md` and `references/codex-execution.md` before claiming completion.

Do not fabricate media model access, inputs, generated frames, results, GIFs, passed tests, font licenses, downloadable paths, or WeChat approval. Follow user-provided constraints and keep local user images, fonts and outputs uncommitted.

When editing code, run the unit tests; when producing stickers, run `scripts/studio_v4.py doctor`, the relevant import and review, build, and final `verify`. GIF files must be square, looping, <=500000 bytes, with real character acting and captions visually checked.
