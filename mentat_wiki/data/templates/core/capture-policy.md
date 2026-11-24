---
type: policy
summary: What the agent captures (ask, auto, never) and when a category may move to auto
min_proposals: 20
min_acceptance: 0.9
expiry_hours: 24
---

# Capture policy

Levels: `auto` = keep and report in one line; `ask` = propose in one line, wait; `never` = do not capture.

| Category | Policy | Notes |
|---|---|---|
| decision | ask | project decisions in a registered project |
| idea | ask | worth a day someday |
| thought | ask | half-formed thought or observation |
| concept | ask | reusable knowledge from a chat |
| output | ask | analysis worth keeping |
| wrap | ask | project status at session end |
| debugging | ask | unresolved debugging at session end, as an open thread |
| chatter | never | casual chat, trivial one-off fixes, anything with secrets or personal data |

Promotion: a category moves to `auto` only after `min_proposals` proposals with at least
`min_acceptance` accepted, and only with the human's approval. `mentat-wiki policy` reports this; it never
edits this file. Demotion: if the human deletes auto-captured items, move the category back to `ask`.
