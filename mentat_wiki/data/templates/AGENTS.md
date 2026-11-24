# Agent instructions

This vault is maintained by LLM agents. Any agent that can run shell commands follows the same rules.

1. Read `CLAUDE.md` in this folder. It is the schema: layers, domains, layout, operations, privacy.
2. At session start, run `mentat-wiki context --always` and read its output before anything else.
3. Write only through the `mentat-wiki` CLI (`keep`, `inbox`, `decide`, `note`, `wrap`, `propose`,
   `feedback`). Hand-edit `wiki/` pages only for ingest and approved lint fixes.
4. Never edit `raw/`. Ask before changing `core/` or `CLAUDE.md`.
5. Never write secrets, third-party personal data or raw chat text.
