---
name: wrap
description: End-of-session wrap-up for the Mentat vault. Rewrites the project's status, records decisions and open threads. Use when the user says /wrap or is finishing work.
---
<!-- managed-by: mentat-wiki -->

# /wrap

Close the session so the next one starts where this one stopped. Keep it short.

1. The project comes from the working folder. If the folder is not registered (for example, the session runs in the vault itself), use the project this session worked on and add `--project <name>` to every `decide` and `wrap` command below. If the session names no single project, run the command once without `--project`: its error lists the known projects. Ask the user which one, and stop if they do not pick one. Never register the vault folder as a project.
2. Record each decision the user made or approved this session that is not yet logged:
   `mentat-wiki decide --decision "<what>" --why "<why>" --rejected "<alternatives>"`
   A decision you made on your own is not logged here; it goes to step 4 as a proposal.
3. Rewrite the status (replaces the old one; under ~150 words; facts, no filler):

```
mentat-wiki wrap --where "<where we left off>" --next "<next step>" --thread "<open thread>" --thread "<another>"
```

   Repeat `--thread` for every open question or todo; the list replaces the old open threads. If
   nothing is open, pass one empty `--thread ""` to clear the list.
4. Unfiled items: pick at most three items from this session that are not filed yet, that the
   user did not already ask to file, and whose category is `ask` in the capture policy
   (decisions you made on your own, ideas, thoughts, knowledge, outputs). For each, first run
   `mentat-wiki propose --type <type> --title "<title>"`, then ask one line:
   Keep as <type> "<title>"? On yes: decision -> `mentat-wiki decide --title "<title>" ...`,
   other types -> /keep with the same title. On no:
   `mentat-wiki feedback --type <type> --title "<title>" --outcome rejected`.
   If nothing qualifies, skip this step and ask nothing.
5. Reply with a three-line recap: decisions logged, status updated, items kept. If the user will continue in another tool or on another machine, offer `mentat-wiki handover` (prints a paste-ready prompt).

No secrets, no personal data, no raw chat text. The command refuses sensitive content.

$ARGUMENTS
