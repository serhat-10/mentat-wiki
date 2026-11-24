---
name: idea
description: Park an idea in the Mentat vault with a value and effort estimate. Use when the user says /idea or describes something worth a day someday.
---
<!-- managed-by: mentat-wiki -->

# /idea

Park the idea fast. Do not ask questions unless the idea is unintelligible.

1. Take the idea from the arguments below, or from the last thing discussed.
2. Estimate `value` (1-5, how much it would help) and `effort` (1 = under an hour, 5 = multi-day). Be honest; the user may override.
3. Check for a duplicate: `mentat-wiki find "<keywords>" --limit 3`.
4. Supply why the idea matters and its first step on stdin.

```
mentat-wiki keep --type idea --title "<title>" --summary "<one line>" --domain <domain> --value <1-5> --effort <1-5> --body -
```

The origin (`session:<id8>`) is filled in automatically. If you know this session's id, add `--origin session:<first 8 chars>`.

5. Reply in one line: title, value, effort, path. No secrets or personal data in the text.

To review parked ideas later: `mentat-wiki find --ideas`.

$ARGUMENTS
