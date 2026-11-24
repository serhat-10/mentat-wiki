# Capture policy

The policy lives in `core/capture-policy.md` in your vault, and the agent reads it at session
start. It holds a level per category and three frontmatter settings (`min_proposals`,
`min_acceptance`, `expiry_hours`). It is plain Markdown; you edit it.

## Levels

The default policy table defines eight categories: `decision`, `idea`, `thought`, `concept`,
`output`, `wrap`, `debugging` (all `ask` by default), and `chatter` (`never` by default). Proposal
commands (`propose`, `feedback`) accept `decision`, `idea`, `thought`, `concept`, and `output`.

Each category has one level:

- **`ask`** — the agent registers a proposal with `mentat-wiki propose --type <type> --title "<title>"`,
  the status line shows the pending count, and the agent asks one line:
  `Keep as <type> "<title>"?`. Default for all categories except `chatter`.
- **`auto`** — the agent captures without asking (using `mentat-wiki keep --auto` or
  `decide --auto`, the commands that log
  `auto: true`). Use this only for categories where you nearly always say yes.
- **`never`** — the agent does not propose or capture that category. You can still file items
  yourself with `mentat-wiki keep`.

A proposal is one question, not a conversation. If you say no, the agent records `rejected` and
clears the proposal.

## Proposal identity and ledger outcomes

Each proposal created by `mentat-wiki propose` receives a 12-character hex `id` in
`<vault>/.mentat/pending.json` and records at most one outcome under `proposal: "<id>"` in
`<vault>/.mentat/feedback.jsonl`.

`feedback.jsonl` is append-only. Each line stores `ts`, `date`, `type`, `title`, `outcome`, and
where relevant `via`, `proposal`, `auto`, `domain`, `project`, `result`, and `awaiting_capture`.

- **`kept`** — accepted and filed. `via: "proposal"` means it answered a pending proposal;
  `via: "explicit"` means you ran `keep` or `decide` directly (`keep --auto` also writes
  `outcome: "kept"` with `auto: true`, which `mentat-wiki policy` counts under `auto`).
- **`edited`** — you changed the proposal before keeping it (via `keep --edited`, `decide --edited`,
  or `feedback --outcome edited` followed by `keep`/`decide`). Even in the two-step flow, the
  proposal id ensures it is counted once.
- **`rejected`** — you said no (`mentat-wiki feedback --type <type> --title "<title>" --outcome rejected`).
  If no pending proposal matches, it is logged as `via: "explicit"` and counted toward `auto`
  demotion rather than proposal acceptance.
- **`ignored`** — the proposal went unanswered past `expiry_hours` (default 24 h).

The ledger also records `inbox`, `note`, and `wrap` events. `wrap` counts under `explicit` in the
`wrap` row; `inbox` and `note` are outside the policy table. None of them affect any proposal
acceptance rate.

## How acceptance is computed

Only proposals count:

```text
acceptance = (kept + edited) / proposed
```

- **Numerator:** proposals whose outcome is `kept` or `edited`.
- **Denominator:** all proposals with an outcome (`kept`, `edited`, `rejected`, or `ignored`),
  including unswept expired items currently sitting in `pending.json`.

Explicit captures and `auto` captures are excluded from both sides: filing a page yourself is not
evidence that you want the agent to ask, and an `auto` capture was never a proposal. Ignored
proposals count as proposed and not accepted: silence is not consent.

## Expiry

`propose` writes open proposals to `<vault>/.mentat/pending.json`. Once a proposal is older than
`expiry_hours` (default 24 h):

- It disappears from `pending()` and the status line immediately.
- `mentat-wiki policy` counts it in memory as `ignored` without writing any file.
- The next write (`propose`, `feedback`, `keep`, `decide`) or session start (`mentat-wiki context`)
  sweeps it out of `pending.json` and appends one `ignored` event to `feedback.jsonl`.

## Thresholds and suggestions

Three frontmatter keys in `core/capture-policy.md` control suggestions and expiry:

```yaml
min_proposals: 20
min_acceptance: 0.9
expiry_hours: 24
```

- **Promotion (`ask` -> `auto`):** suggested when an `ask` category has at least `min_proposals`
  proposals and acceptance at or above `min_acceptance`.
- **Demotion (`auto` -> `ask`):** suggested when an `auto` category accumulates at least 3
  rejections or ignores (`bad = rejected + ignored + explicit rejections`) and
  `bad > (1 - min_acceptance) * (bad + kept + edited + auto)`. Non-rejected explicit captures are
  excluded.

`mentat-wiki policy` (and `mentat-wiki policy --json`) is strictly read-only. It prints suggestions as text
and never modifies `core/capture-policy.md`.

## Example report

Fictional counts after a few months of use; real output format:

```text
category   level  proposed  kept  edited  rejected  ignored  explicit  auto  accepted
decision   ask          18    18       0         0        0         2     0      100%
idea       ask          24    20       2         1        1         3     0     91.6%
thought    ask           9     5       0         4        0         0     0     55.5%
...

Auto needs 20+ proposals with 90% or more accepted (kept or edited), and your approval. Unanswered proposals count as ignored after 24 h. Explicit and auto captures are not in the rate.

Suggestions:
- change `| idea | ask |` to `| idea | auto |` in core/capture-policy.md, with your approval
```

Here `idea` has passed both thresholds; `decision` has a perfect rate but only 18 proposals.

## Where proposals come from

- **Mid-session.** The capture protocol, loaded at session start, tells the agent to propose a
  durable item before offering it in prose.
- **At `/wrap`.** The skill offers at most three unfiled items from the session as proposals and
  asks nothing when none qualifies. Decisions the human made or approved are logged directly with
  `decide`; only decisions the agent would log on its own are proposed.
- **Hint.** In a registered folder or the vault folder, a prompt of 25 or more characters that
  sounds like "save this" makes the prompt hook remind the agent of the protocol. The built-in
  phrases are English; add your own in `~/.mentat/config.json`:
  `"hook": {"keep_cues": ["guárdalo así"], "stop_words": []}`.

Captures the human asks for (`/keep`, `/idea`, `decide` on request) are explicit and do not count
toward acceptance, unless their title matches an open proposal; then they answer it. `auto`
captures never answer a proposal.

## Promote or demote

1. Run `mentat-wiki policy` and review the table.
2. Open `core/capture-policy.md`.
3. Change that category's level in the table (for example, `ask` to `auto`, or back to `ask`).
4. Save. The next session reads the updated file.

To stop a category entirely, set its level to `never`. Existing pages and ledger entries stay
untouched.
