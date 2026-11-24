# Vault schema

This vault is a personal knowledge base maintained by an LLM agent, following the "LLM Wiki"
pattern. The human curates sources and asks questions. The agent writes and maintains the wiki.
Everything is plain Markdown and works in any editor or Obsidian.

The `mentat-wiki` CLI does the filing: it picks the folder, writes frontmatter, updates the index, appends a
log line on wrap, and refuses text that looks sensitive. Write through it whenever a command exists. Edit pages by
hand only for ingest, lint fixes and page updates.

## Layers

| Layer | Path | Owner | Rule |
|---|---|---|---|
| Raw sources | `raw/` (images in `raw/assets/`) | human | Immutable. Read, never edit. |
| Wiki | `wiki/` | agent | Agent creates, updates, links. Human reads. |
| Core | `core/` | shared | Small, loaded every session. Keep each file short. |
| Schema | `CLAUDE.md`, `AGENTS.md` | shared | This file. Ask before changing it. |

## Domains

Every wiki page carries one domain in frontmatter. `mentat-wiki keep --domain` accepts only the names
below (plus `projects` and `other`, which are always accepted). To add a
domain, add a bullet here first, in the same form.

- `engineering`: software and systems notes
- `ai-tools`: AI products, models and tooling
- `research`: papers, science, theory
- `academic`: course material and study notes
- `reading`: general articles and books
- `projects`: personal or work projects
- `hobbies`: hobbies and side interests
- `other`: anything that fits nowhere else

## Wiki layout

- `wiki/index.md`: catalog of every page, one line each: `- [[page]]: summary (domain)`. Updated on
  every write.
- `wiki/log.md`: append-only timeline: `## [YYYY-MM-DD] <ingest|query|lint|session> | <title>`.
- `wiki/sources/`: one summary page per raw source.
- `wiki/concepts/`: topics, patterns, troubleshooting.
- `wiki/entities/`: tools, libraries, organizations, repos, public figures.
- `wiki/projects/<name>/`: `status.md`, `decisions.md`, `open-threads.md`, `experiments.md`.
- `wiki/outputs/`: answers worth keeping.
- `wiki/ideas/`: "worth a day someday", with value, effort and idea_status.
- `wiki/thoughts/`: half-formed and short.
- `inbox/`: one-line items of unclear type, triaged weekly.

Page templates live in `_templates/`. Use `[[wikilinks]]`. Filenames are lowercase-kebab-case and
unique across the wiki. Every page has a one-line `summary` in frontmatter.

## Operations

**Ingest** (one source at a time, human in the loop):
1. Check the source is not thin (150+ words of real prose). If it is, offer to fetch the URL or ask
   for the full text.
2. Read it and discuss the key takeaways with the human first.
3. Write `wiki/sources/<slug>.md` from `_templates/source.md`. Set `quality`.
4. Create or update concept and entity pages (10-15 touched pages is normal). Run `mentat-wiki find`
   first and update instead of duplicating. Entity pages only for things likely to recur.
5. On a contradiction, record both sides under `## Contradictions` (source vs source, or source vs
   wiki). Your own knowledge goes under `## Agent notes (not from source, unverified)`.
6. Add every new page to `wiki/index.md` and append a log entry.

**Query**: run `mentat-wiki find` or read the index first, then drill into pages. Cite `[[wikilinks]]`.
Answer in the form that fits. Offer to file a reusable answer with `mentat-wiki keep --type output`.

**Lint** (on request, or about every 10 ingests): run `mentat-wiki doctor`, then look for contradictions,
stale claims, orphans, concepts named in 3+ pages without their own page, and missing links. Report
first. Fix only after the human approves.

## Project continuity

- Session start in a project: `mentat-wiki context` prints core/, status and open threads. Say in one
  line where we left off. `mentat-wiki resume` shows how the last session in this folder ended.
- Decisions: when the human makes or approves a decision, record it with
  `mentat-wiki decide --decision ... --why ... --rejected ...`. A decision you would record on your
  own is a capture: propose it first (see Capture).
- Experiments: `mentat-wiki note "<what was tried> -> <result>" --result worked|failed|info`, right away.
- Session end: `mentat-wiki wrap --where ... --next ... --thread ...` rewrites status and open threads
  and adds a log line.
- Moving to another tool: `mentat-wiki handover` prints a paste-ready prompt.

## Capture

Value is captured while the session is live. Follow `core/capture-policy.md`: `auto` = keep and
report in one line; `ask` = propose in one line and wait; `never` = do not capture.

- Type decides the folder: `mentat-wiki keep --type idea|thought|concept|output`, `mentat-wiki decide` for
  project decisions, `mentat-wiki inbox "<line>"` when unsure.
- To ask: run `mentat-wiki propose --type <type> --title "<title>"`, then ask in one line, e.g.
  Keep as idea "<title>" (value 4, effort 2)? y/n. Do not ask twice.
- Record every outcome: `mentat-wiki keep` or `mentat-wiki decide` records a yes (add `--edited` if the
  human changed it); `mentat-wiki feedback --type <type> --title "<title>" --outcome rejected` records a
  no. Unanswered proposals expire after 24 hours and count as ignored.
- `mentat-wiki policy` reports which categories have earned `auto`. Only the human changes the policy.
- `mentat-wiki digest` lists recent and top open ideas.
- Check `mentat-wiki find` first; update an existing page instead of duplicating.
- Never capture secrets, third-party personal data or raw chat text.

## Token budget

- `core/` together under 2,200 characters. `status.md` under ~500 tokens.
- Read the index or `mentat-wiki find` first. Never load the whole wiki.
- Split pages over ~1,500 words.

## Privacy rules (hard)

- Never write secrets: keys, tokens, passwords, connection strings.
- No third-party personal data. No employer or customer names unless `core/USER.md` allows them.
- Never store raw chat transcripts. Summarize instead.
- Mark a fix `verified: true` only if the human confirmed it.
- If unsure, ask.

## Style

Write in the language and style named in `core/USER.md` and `core/SOUL.md`. Every claim traces to a
source page or a project decision, or is marked unverified. Edit `wiki/` freely. Never edit `raw/`. Ask before
changing `core/` or this schema.

## Frontmatter

```yaml
type: source | concept | entity | project-status | output | idea | thought
summary: one line, required
domain: one of the domains above
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
tags: []          # optional, 2-4
quality: primary | secondary | tertiary   # source pages only
status: draft | stable | stale
```

Captured pages also carry `origin: session:<id8>` and `auto: true|false`. Ideas add `value` (1-5),
`effort` (1-5), `est_days` and `idea_status: parked | active | done | dropped`.
