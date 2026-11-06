# Contributing to GIF Sticker Studio

This is a **general-purpose, public** animated sticker workflow. Changes should work for independent creators, educators, businesses and hobbyists using people, pets, illustrated characters, photographs, toys or other authorized imagery.

- Do not put any developer's or user's private identity, personal brand, specific IP character, biography, artistic taste, account information or user-uploaded photo into default prompts, examples, tests or source files.
- Example names must be generic (e.g. `示例角色`, `character.png`, `workspaces/sample`). Keep original user assets out of commits. `assets/`, `uploads/` and `workspaces/` are gitignored for this reason.
- Keep **square GIF**, **≤500000-byte default target**, **looping**, and the production defaults of 16 GIFs × 16 planned poses × batches of 4, while honoring explicit user customization.
- Prefer style-adaptive behavior, not hardcoded cultural, gender, age or character preferences. Optional `classic`, `cute`, `heritage` and `brush` styles are choices, never forced on all users.
- Preserve real articulated character acting. A static image translated, scaled or shaken is not a full frame-by-frame animation.
- Whenever an optional font, model or backend is unavailable, provide a clear error or a plainly disclosed generic fallback. Never claim a font, generated pose or platform review exists when it does not.
- Use only licensed/authorized images, fonts and media. **Keep required third-party MIT notices and attribution** in `LICENSE` and `NOTICE.md` even when changing the README or project branding.
- Write tests for new behavior and run `python -m pytest -q` before requesting a merge.
