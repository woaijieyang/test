# AGENTS.md

Codex must follow this file when working in `zx-experiment`.

Do not create or use `agent.md`. Codex discovers `AGENTS.md`.

## Paths

- Project root: `/mnt/data/Project/vln/zx-experiment`
- Same directory in the file manager: `/home/zy/DataDrive/Project/vln/zx-experiment`
- Codex system root: `/mnt/data/Project/vln/zx-experiment/.codex`

## Hard Rules

1. MUST treat `/mnt/data/Project/vln/zx-experiment` as the only writable root.
2. MAY read outside the project root when needed for context.
3. MUST NOT write, edit, delete, move, rename, patch, format, download, cache,
   or generate files outside `/mnt/data/Project/vln/zx-experiment`.
4. MUST keep all Codex logs, records, scratch files, temporary outputs, and
   generated work data under `/mnt/data/Project/vln/zx-experiment`.
5. MUST use `/mnt/data/Project/vln/zx-experiment/.codex/tmp` for temporary or
   cache data when a command needs a writable temp location.
6. MUST stop and ask the user if a task requires writing outside the project
   root.

## Protected External Paths

These are read-only unless the user explicitly changes the write boundary:

- `/mnt/data/Project/vln`
- `/mnt/data/Project/vln/data`
- `/mnt/data/Project/vln/mp3d`
- `/mnt/data/Project/vln/logs`
- `/mnt/data/Project/vln/external`
- `/mnt/data/Project/vln/StreamVLN`
- `/mnt/data/Project/vln/.git`
- `/home/zy`
- `/tmp`

## Records

For meaningful work, write a short record under:

`/mnt/data/Project/vln/zx-experiment/.codex/records/sessions`

Use absolute paths in records and final answers.
