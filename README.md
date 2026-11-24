# mentat-wiki

**Coding agents forget where you left off when a session ends.** mentat-wiki keeps each
project's status, next step, decisions, open threads and experiment notes in a local Markdown wiki.
The next session starts with the status, open threads and recent notes loaded (decisions stay one
file away), and `/wrap` updates them before you stop.

Claude Code first; any shell-capable agent through `AGENTS.md`. Python 3.10+, standard library
only, no services, no network calls, no telemetry. MIT. Early release (alpha). Built on Andrej
Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## What a session looks like

A fictional project from the [demo vault](https://github.com/serhat-10/mentat-wiki/tree/main/examples/demo-vault);
real command output, shortened.

**Session start.** The SessionStart hook runs `mentat-wiki context`, and the agent sees:

```text
# trailmap: status
## Where we left off
Parser and text profile work end to end. Five-point smoothing runs with a 3 m climb threshold;
the coastal test track reports 640 m of gain.
## Next step
- Add --json output for plotting.

# trailmap: open threads
- [ ] Write a regression test that pins the coastal track at 640 m of gain.
- [ ] Try a nine-point window on the coastal track and compare total gain.

Recent experiment notes:
- 2026-11-20 16:40 [failed] five-point window without edge padding -> first and last elevations dropped 14 m
- 2026-11-21 11:05 [worked] 3 m climb threshold -> 640 m gain, within 20 m of the sum from the route map
```

**During the session.** The agent logs what you decide and every attempt, failures included:

```text
$ mentat-wiki decide --decision "Pad the edges before smoothing" --why "keeps the first and last points" --rejected "nine-point window"
decision recorded
$ mentat-wiki note --result worked "edge padding -> first and last elevations within 1 m"
noted in wiki/projects/trailmap/experiments.md
```

The Claude Code status line shows the project, what was kept today, proposals waiting for your
answer, and the short session id (`🔑`):

```text
🧠 trailmap · kept 3 today · ❓1 to confirm · 🔑 5f2c9a1e
```

**Session end.** You type `/wrap`. The agent rewrites the status and open threads, so the next
session starts from here:

```text
$ mentat-wiki wrap --where "Smoothing pads the edges now; the coastal track keeps 640 m of gain." --next "Add --json output for plotting." --thread "Pin the coastal track at 640 m in a regression test."
status updated
```

**Next session.** It starts from what you wrapped; the nine-point thread you dropped is gone:

```text
# trailmap: status
## Where we left off
Smoothing pads the edges now; the coastal track keeps 640 m of gain.
## Next step
- Add --json output for plotting.

# trailmap: open threads
- [ ] Pin the coastal track at 640 m in a regression test.

Recent experiment notes:
- 2026-11-24 18:57 [worked] edge padding -> first and last elevations within 1 m
```

## Quickstart

```bash
pipx install mentat-wiki          # or: pip install mentat-wiki
mentat-wiki init ~/vault          # creates the vault and remembers its path
mentat-wiki install claude        # shows a diff and asks first; --dry-run only previews
cd ~/code/my-app                  # any existing project folder
mentat-wiki project register      # name defaults to the folder: my-app
mentat-wiki doctor                # checks the vault and the Claude Code setup
```

If `mentat-wiki` is not found after a pip install, use `python -m mentat_wiki` in its place; the
installer does the same. Then start Claude Code in `~/code/my-app`. The first session says there is nothing recorded yet;
from the first `/wrap` on, every session starts where the last one stopped.

### What `install claude` changes

In `~/.claude/settings.json` (backed up first as `settings.json.bak-<time>`; your existing hooks,
permissions and status line stay; an older `mentat` entry is upgraded):

- a `SessionStart` hook, `mentat-wiki context`: loads your vault's `core/` rules plus this
  project's status, open threads and recent experiment notes;
- a `UserPromptSubmit` hook, `mentat-wiki hook`: writes a local session checkpoint (session id,
  time, prompt count and transcript path, never prompt text) and, only in registered folders and the vault, may add a short hint
  naming related pages;
- a status line, only if you have none (`--force-statusline` replaces yours);
- the permission `Bash(mentat-wiki *)`, so the agent can run the CLI without a prompt each time.

It also writes the `/idea`, `/keep` and `/wrap` skills to `~/.claude/skills/`, skipping any you
already have with that name. If `mentat-wiki` is not on `PATH` for this Python, every entry uses
`<python> -m mentat_wiki` instead; `mentat-wiki config --command` overrides the choice. A manifest in
`~/.mentat/install-claude.json` records each entry; `mentat-wiki uninstall claude` removes only
those.

Your repositories are never written to. `project register` maps the folder to a project in
`~/.mentat/config.json`; all pages live in the vault. The vault's own `CLAUDE.md` and `AGENTS.md`
are for sessions inside the vault, not for your repos.

## Daily use

You:

- `/wrap` before you stop.
- `/keep` or `/idea` to file something right now.
- `mentat-wiki resume`: how the last session in this folder ended, and how to reopen it.
- `mentat-wiki handover`: a paste-ready prompt to continue in another tool.
- `mentat-wiki find "smoothing"` and `mentat-wiki digest` to look things up.

The agent:

- reads status, open threads and recent notes at session start;
- logs the decisions you make or approve (`decide`) and each experiment attempt (`note`);
- checks for an existing page before writing a new one;
- asks once before saving anything else (next section).

## Ask-first capture (early)

When something worth keeping comes up mid-session (an idea, reusable knowledge, a decision the
agent would log on its own), the agent registers a proposal, the status line shows it, and it asks
one line:

```text
Keep as idea "Export the profile as SVG"? y
kept wiki/ideas/export-the-profile-as-svg.md
```

`/wrap` also offers up to three unfiled items this way. Each answer (kept, edited, rejected, or
ignored after 24 h) goes to a local ledger. `mentat-wiki policy` shows acceptance per category, and
after 20 or more proposals with at least 90% accepted it suggests letting that category save
without asking. It never changes anything itself: you edit `core/capture-policy.md`.

This part is new. Expect a few weeks of normal use before it has enough answers to suggest
anything. Details: [docs/capture-policy.md](https://github.com/serhat-10/mentat-wiki/blob/main/docs/capture-policy.md).

## Why not CLAUDE.md or built-in memory?

`CLAUDE.md` holds the instructions you write, and Claude Code's auto memory keeps facts the model
picks. Both help, and mentat-wiki runs next to them. It adds:

- a fixed project-state shape: where we left off, next step and open threads, which `/wrap`
  rewrites, plus decisions with the alternatives you rejected and experiment notes, appended as
  you go;
- one vault for all your projects, with idea, knowledge and source pages linked across them;
- plain files that any agent or editor can read, and `handover` to continue in another tool.

Other tools in this space:

- **claude-mem** handles automatic session-wide capture and compression for Claude Code. Use it for
  hands-off cross-session memory.
- **basic-memory** serves local Markdown notes over MCP. Use it for cross-client MCP access to a
  knowledge graph.
- **claude-obsidian** centers on an Obsidian vault driven by Claude Code. Use it if Obsidian is
  your workflow hub.

Choose mentat-wiki for explicit project continuity, a wiki you curate, and zero services: one
stdlib-only CLI, plain Markdown, and a local SQLite FTS5 index.

## Privacy and safety

- Capture commands scan the text they are about to write and refuse common secrets (OpenAI,
  Anthropic, Google, AWS and Stripe keys, GitHub and Slack tokens, JWTs, private keys,
  `password=...`), home-folder paths and real email addresses. Version strings, `example.com` and
  `git@host:path` pass. It is pattern matching, not a guarantee; review what you keep.
- mentat-wiki does not store chat transcripts: hooks record no prompt text, and capture commands
  write only the text they are given. Captured pages record `origin` and `auto: true|false`.
- Session-start context is bounded: the body is capped at 6,000 characters (`--max-chars`), and
  `doctor` warns when `core/` grows past 2,200 characters (about 550 tokens).
- `~/.mentat/config.json` stores local paths on purpose (vault path, folder-to-project map); it
  stays on your machine.
- The installer backs up `settings.json`, and uninstall reverts only the entries its manifest
  recorded. Without a manifest it changes nothing unless you pass `--legacy`.

See [SECURITY.md](https://github.com/serhat-10/mentat-wiki/blob/main/SECURITY.md).

## Other agents

Point any shell-capable agent at your vault's `AGENTS.md`, or tell it to run
`mentat-wiki context --always` at session start and write through the CLI. Only Claude Code gets hooks, the status line and the
`/idea`, `/keep`, `/wrap` skills today.

## Commands

<details>
<summary>All commands</summary>

| Command | Purpose |
|---|---|
| `mentat-wiki init ~/vault` | Create a vault with the schema and templates. |
| `mentat-wiki install claude` | Wire hooks, status line, permission and skills (`--dry-run` previews). |
| `mentat-wiki uninstall claude` | Revert installer changes (`--legacy` also removes hand-written mentat hooks). |
| `mentat-wiki project register my-app` | Register this folder (`project list` lists). |
| `mentat-wiki context` | Print the session-start context (`--always` in unregistered folders). |
| `mentat-wiki keep --type idea --title "Retry queue" --summary "Queue uploads" --value 4 --effort 2` | File an idea, thought, concept or output. |
| `mentat-wiki inbox "Check backups"` | Park a one-line item. |
| `mentat-wiki decide --decision "Use SQLite" --why "Zero deps" --rejected "External index"` | Append a project decision. |
| `mentat-wiki wrap --where "Cache done" --next "Add queue" --thread "Check timeouts"` | Rewrite status and open threads. |
| `mentat-wiki note --result worked "1k pages in 12 ms"` | Log an experiment attempt. |
| `mentat-wiki propose --type idea --title "Retry queue"` | Register a pending proposal. |
| `mentat-wiki feedback --type idea --title "Retry queue" --outcome rejected` | Record a rejected or edited proposal. |
| `mentat-wiki find "retry"` | Search pages (`--ideas` ranks parked ideas). |
| `mentat-wiki policy` | Acceptance per category (`--json` supported). |
| `mentat-wiki digest` | Recent ideas, top parked ideas, policy summary. |
| `mentat-wiki resume` | How the last session in this folder ended. |
| `mentat-wiki handover` | Paste-ready prompt for another tool. |
| `mentat-wiki doctor` | Check schema, links, index, size, privacy, install. |
| `mentat-wiki config --vault ~/vault` | Set the vault (`--command` sets the CLI string). |
| `mentat-wiki --version` | Print the version. |

</details>

## FAQ

**Do I need Obsidian?** No. Any editor works; Obsidian just renders the `[[links]]` nicely.

**Why `mentat-wiki` and not `mentat`?** An unrelated, older PyPI package already installs a
`mentat` command. A unique name avoids colliding with it.

**What if `mentat-wiki` is not on `PATH`?** `install claude` falls back to
`<python> -m mentat_wiki`. Override with `mentat-wiki config --command "python -m mentat_wiki"`.

**Two repos have the same folder name.** `project register` refuses a folder-derived name already
used by another folder on this machine; pass a name (`mentat-wiki project register api-billing`). Passing an existing name on purpose
shares it, for example across worktrees of one repo.

**Can I change domains or the schema?** Yes. Edit the vault's `CLAUDE.md` (`## Domains`;
`projects` and `other` are always valid).

**When does the agent save without asking?** Project log updates (`/wrap`, decisions you made or
approved, experiment notes) and any category you set to `auto` in `core/capture-policy.md`.
Everything else asks once (`chatter` is `never`).

## Uninstall

`mentat-wiki uninstall claude`, then `pipx uninstall mentat-wiki` or `pip uninstall mentat-wiki`.
Your vault stays plain Markdown.

## Documentation

[Demo vault](https://github.com/serhat-10/mentat-wiki/tree/main/examples/demo-vault) ·
[Architecture](https://github.com/serhat-10/mentat-wiki/blob/main/docs/architecture.md) ·
[Capture policy](https://github.com/serhat-10/mentat-wiki/blob/main/docs/capture-policy.md) ·
[Contributing](https://github.com/serhat-10/mentat-wiki/blob/main/CONTRIBUTING.md) ·
[Security](https://github.com/serhat-10/mentat-wiki/blob/main/SECURITY.md) ·
[Changelog](https://github.com/serhat-10/mentat-wiki/blob/main/CHANGELOG.md)

## License

MIT. See [LICENSE](https://github.com/serhat-10/mentat-wiki/blob/main/LICENSE).
