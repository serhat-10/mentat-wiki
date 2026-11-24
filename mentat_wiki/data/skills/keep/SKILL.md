---
name: keep
description: File what was just discussed into the Mentat vault as an idea, thought, concept or output. Use when the user says /keep, "save this", or accepts a "Keep as ...?" proposal.
---
<!-- managed-by: mentat-wiki -->

# /keep

File durable value from this session into the vault. Distill; never paste raw chat.

1. Pick the type: `idea` (worth a day someday), `thought` (half-formed), `concept` (reusable knowledge), `output` (analysis worth keeping). Unclear: `mentat-wiki inbox "<one line>"` and stop.
2. Check for an existing page: `mentat-wiki find "<2-4 keywords>" --limit 3`. If one covers it, tell the user and update that page instead of creating a duplicate.
3. Write a clear title, a ONE-line summary, and a short body: what it is, why it matters, first step if relevant. No secrets, no personal data about other people, no home-directory paths.
4. If the user edited the proposal, add `--edited` to the command. Supply the body on stdin.

```
mentat-wiki keep --type <type> --title "<title>" --summary "<one line>" --domain <domain> --body -
```

   Domains: the list in the session context (`Domains: ...`), from `## Domains` in the vault's CLAUDE.md. For ideas add `--value 1-5 --effort 1-5` (effort 1 = under an hour, 5 = multi-day). Add `--auto` only if captured without asking. Origin (`session:<id8>`) is filled in automatically; if you know this session's id, add `--origin session:<first 8 chars>`.
   Concepts and thoughts go through this command too (`--type concept` writes to wiki/concepts/, `--type thought` to wiki/thoughts/); never hand-write them, or the feedback log misses them.
5. If the command refuses for sensitive content, redact and retry once, then tell the user what was removed.
6. Reply with one line: the type and the path.

$ARGUMENTS
