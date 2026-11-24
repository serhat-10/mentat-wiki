# Architecture

Mentat is a CLI plus two Claude Code hooks and a status line. There is no server and no background
process. Each command opens the vault, does its work, and exits.

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing and subcommand entry points (delegates `install`/`uninstall` to `installer.py` and `policy` to `policy.py`). |
| `vault.py` | Vault layout, capture, proposals, ledger, projects, decisions, wrap, notes, handover. The only writer of wiki pages. |
| `search.py` | Local SQLite FTS5 index (indexes title, summary, and body; returns titles and summaries); `--ideas` ranks parked ideas by value minus effort. |
| `policy.py` | Reads `core/capture-policy.md`, aggregates the ledger, prints `mentat-wiki policy`; read-only, suggests only. |
| `installer.py` | `install claude`, `--dry-run`, `uninstall claude`, and install checks for `doctor`; previews a diff and reverts only its own entries. |
| `templates.py` | Installs packaged vault templates from `data/templates/` via `importlib.resources` without overwriting existing files. |
| `hook.py` | `UserPromptSubmit`: records a checkpoint and prints a short hint (titles and paths only) or nothing. |
| `statusline.py` | One line: project, kept today, ideas, proposals, inbox, and session id (from local files only). |
| `checkpoint.py` | Per-folder session checkpoints and `mentat-wiki resume`. |
| `digest.py` | Read-only ideas and capture-policy digest. |
| `doctor.py` | Vault and install checks: frontmatter, types, domains, links, index, size, `core/` budget, privacy, inbox count, Claude Code setup. |
| `util.py` | Slugs, flat frontmatter, atomic writes, the vault lock, privacy scan, session ids. |
| `config.py` | `~/.mentat/config.json`: vault path, agent command string, folder-to-project map. |

## Data flow

1. **Session start.** `mentat-wiki context` saves the session id, syncs `index.db`, sweeps expired
   proposals into `ignored`, and prints the capture protocol, `core/*.md`, and (for a registered
   project) `status.md`, `open-threads.md`, and recent experiment notes, capped at 6,000
   characters. Sessions started inside the vault folder itself also receive the capture protocol,
   `core/*.md`, and a reminder to pass `--project <name>`. Any unwrapped-session notice or eligible
   capture-policy notice is appended after truncation. Other unregistered folders receive no
   context unless `--always` is passed.
2. **Each prompt.** `mentat-wiki hook` records a checkpoint (session id, timestamp, prompt count, and
   transcript path; no prompt text). In a registered project folder or the vault folder, when a
   prompt looks keep-worthy or matches existing pages, it also prints a hint with page names and
   paths only. Other folders get no hint, matching `context`.
3. **Each turn.** `mentat-wiki status-line` reads the hook JSON on stdin and prints one line from local
   files only.
4. **Capture.** `propose` sweeps expired proposals and writes `pending.json` (each proposal gets a
   12-hex-character id). `keep` writes a page, updates `wiki/index.md`, answers a matching
   open proposal (an `auto` capture leaves it pending), and appends one ledger event. `decide` appends to the project's `decisions.md`, clears
   any matching proposal, and appends to the ledger. `feedback --outcome rejected` writes `rejected`
   and removes the proposal; `feedback --outcome edited` records `edited` (`awaiting_capture: true`)
   and marks the pending entry `edited` so the following `keep` or `decide` consumes it without
   double-counting.

## Files written, and when

- `init`: the vault folders, missing template files, `wiki/index.md`, `wiki/log.md`, and `vault` in
  `~/.mentat/config.json` (if unset).
- `project register`: `wiki/projects/<slug>/{status,decisions,open-threads}.md`, a `wiki/index.md`
  entry, and the folder mapping in `~/.mentat/config.json`. Refuses the vault folder itself, and
  refuses a name derived from the folder when that name already belongs to another folder on this
  machine (an
  explicit name shares the project on purpose).
- `keep`: `wiki/<type>s/<slug>.md` (`ideas`, `thoughts`, `concepts`, or `outputs`),
  `wiki/index.md`, `feedback.jsonl`, and `pending.json`.
- `decide`: `wiki/projects/<slug>/decisions.md`, `feedback.jsonl`, and `pending.json`.
- `wrap`: `wiki/projects/<slug>/status.md`, optionally `open-threads.md`, `wiki/log.md`, and
  `feedback.jsonl`.
- `note`: `wiki/projects/<slug>/experiments.md` and `feedback.jsonl`.
- `inbox`: `inbox/inbox.md` and `feedback.jsonl`.
- `propose`, `feedback`: `pending.json` and `feedback.jsonl`.
- `config`: `~/.mentat/config.json`.
- `install claude`, `uninstall claude`: `~/.claude/settings.json` (with a backup of any existing
  file), `~/.claude/skills/{idea,keep,wrap}/SKILL.md`, `~/.mentat/install-claude.json`, and
  `~/.mentat/config.json` when the stored command changes.
- `hook`: `~/.mentat/checkpoints.json`.
- `find`: `index.db`.
- `context`: `sessions.json` (and `CLAUDE_ENV_FILE` when set), `index.db`, and (when pending
  proposals expire or need reconciliation) `feedback.jsonl` and `pending.json`.
- `policy`, `digest`, `status-line`, `resume`, `handover`, `project list`, and `doctor` are
  read-only.

## Locking and atomic writes

Captures, proposals, wraps, sweeps and the pages written by `project register` run inside
`util.lock(<vault>/.mentat/lock)`, an exclusive lock file. `init` writes template files directly, and
SQLite manages `index.db` itself. A
second process waits up to 10 seconds, then exits with code 2. A lock older than 120 seconds is
treated as crashed and removed, but only if its mtime did not change between checks. The Claude
Code installer uses the same lock mechanism in the config folder during install and uninstall.

Pages, state JSON files (`pending.json`, `config.json`, `sessions.json`, `checkpoints.json`), and
installer writes use `util.write_atomic`: a temporary file in the target folder followed by
`os.replace`, with short retries on Windows when another process holds the target open. Readers
never see a half-written file.

## State locations

Per machine, in `~/.mentat` (or the parent directory of `MENTAT_CONFIG` when set):
`config.json` (vault path, command string, project map), `sessions.json` (session id per folder,
24-hour TTL), `checkpoints.json` (7-day TTL, five most recent sessions per folder),
`install-claude.json` (installer manifest), and `lock` during install or uninstall.

In the vault, `<vault>/.mentat`: `feedback.jsonl` (append-only ledger), `pending.json` (active
proposals, default 24-hour expiry), `index.db` (SQLite FTS5 index), and `lock` during a write.

The ledger is the source of truth for capture history. Whether a session was wrapped is derived by
comparing its last checkpoint timestamp with the project's last `wrap` event, so no separate flag
needs syncing.
