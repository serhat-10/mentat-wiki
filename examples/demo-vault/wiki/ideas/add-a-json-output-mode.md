---
type: idea
domain: engineering
created: 2026-11-18
updated: 2026-11-19
summary: Emit the profile as JSON so another tool can plot it without parsing text.
value: 3
effort: 2
est_days: 1
idea_status: parked
project: trailmap
origin: session:2026-11-18-2131
auto: false
status: draft
---
# Add a --json output mode

## Why

A JSON mode lets another tool plot the profile without scraping text columns, and it costs one
serialiser.

## First step

Add `--json` and emit distance, elevation, gain and the smoothing window.

## Open questions

- Should the window be part of the JSON so consumers can reproduce the smoothing? See
  [[elevation-smoothing]].
