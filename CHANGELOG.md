# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0 - Unreleased

First public release.

### Added

- One command, `mentat-wiki` (also `python -m mentat_wiki`). The name avoids an unrelated PyPI
  package that installs `mentat`.
- `mentat-wiki init` creates a vault: `CLAUDE.md` schema (including `## Domains`), `AGENTS.md`, `core/`
  (`SOUL.md`, `USER.md`, `MEMORY.md`, `capture-policy.md`), `raw/`, `wiki/` with `index.md` and
  `log.md`, `inbox/`, and `_templates/`.
- Capture commands: `keep` for ideas, thoughts, concepts, and outputs (`--auto`, `--edited`);
  `inbox` for unclear one-liners; `decide` for project decisions (`--title`, `--edited`); `note`
  for instant experiment attempts; `wrap` for end-of-session status and open threads.
- Proposal tracking: `propose` assigns each pending proposal an id in `pending.json` and records at
  most one outcome (`kept`, `edited`, `rejected`, or `ignored` after `expiry_hours`, default 24 h)
  in `feedback.jsonl`.
- `mentat-wiki policy` (and `--json`): read-only acceptance report per category using thresholds from
  `core/capture-policy.md` frontmatter (`min_proposals`, `min_acceptance`, `expiry_hours`);
  suggests `auto` promotions and `ask` demotions without editing the policy file.
- Project continuity: `project register` (defaults name to folder, refuses the vault folder, and
  refuses a folder-derived name that already belongs to another folder on this machine) creates
  `status.md`,
  `decisions.md`, and `open-threads.md`; `context` injects protocol, `core/`, project state (or
  vault-folder guidance when run inside the vault); `handover` prints a paste-ready continuation
  prompt.
- `/wrap` offers at most three unfiled items from the session as proposals, so the acceptance
  ledger fills during normal use; decisions the human made are logged directly.
- Session checkpoints: the `UserPromptSubmit` hook records per-folder checkpoints (no prompt text)
  and adds page hints only in registered project folders and the vault folder (cue phrases and stop
  words are English and can be extended under `hook` in `config.json`); `mentat-wiki resume` reports the last session, whether it was wrapped, and git changed-file count.
- Search: local SQLite FTS5 index (returns titles and summaries) via `mentat-wiki find "query"` and
  `mentat-wiki find --ideas`.
- `mentat-wiki digest`: read-only report of recent ideas, top parked ideas, and capture-policy summary.
- `mentat-wiki doctor`: checks frontmatter, types, domains, wiki links, index entries, page sizes,
  `core/` budget, sensitive content, inbox count, and Claude Code integration status.
- Claude Code integration: `mentat-wiki install claude` previews a diff, backs up any existing
  `settings.json`, wires hooks, status line, and `/idea`, `/keep`, `/wrap` skills, and selects
  `mentat-wiki` when on `PATH` for this interpreter or `<python> -m mentat_wiki` otherwise. Supports
  `--dry-run`, `--yes`, `--claude-dir`, `--command`, and `--force-statusline`. `mentat-wiki uninstall
  claude` reverts only what it added.
- Privacy scan on captured text: refuses API keys, tokens, private keys, secret assignments,
  home-folder paths, and real email addresses; allows version strings (`react@18.2.0`),
  `example.com` placeholders, and `git@` SSH remotes. Captured pages record `origin` and `auto`.
- `mentat-wiki config --vault` and `mentat-wiki config --command`; `mentat-wiki --version`.
- Per-machine state in `~/.mentat` (`config.json`, `sessions.json`, `checkpoints.json`,
  `install-claude.json`); vault state in `<vault>/.mentat` (`feedback.jsonl`, `pending.json`,
  `index.db`).

### Safety

- Hooks never fail loudly: `mentat-wiki context` as a SessionStart hook prints nothing and exits 0 on
  any unexpected error, and optional files or housekeeping steps cannot cost a session its context.
- The privacy scan also recognises GitHub fine-grained tokens, Slack tokens, Stripe live keys,
  Google API keys and JSON Web Tokens.
- `mentat-wiki uninstall claude` changes nothing without an install manifest unless `--legacy` is
  passed, and removes a `settings.json` that the install itself created.
- A config file or proposal queue that does not parse is never overwritten: the config write is
  refused, the queue is moved aside with a timestamp.
- The `python -m mentat_wiki` fallback uses forward slashes on Windows so bash-run hooks work.
- Slugs never produce Windows device names (`CON`, `NUL`, `COM1`, ...).
