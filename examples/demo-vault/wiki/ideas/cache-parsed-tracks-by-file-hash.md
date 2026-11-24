---
type: idea
domain: engineering
created: 2026-11-18
updated: 2026-11-18
summary: Hash the GPX file and reuse the parsed track so repeated profiles are instant.
value: 4
effort: 2
est_days: 1
idea_status: parked
project: trailmap
origin: session:2026-11-18-2107
auto: false
status: draft
---
# Cache parsed tracks by file hash

## Why

The same file is opened again and again while tuning the profile. Parsing 10,000 points is fast,
but not free.

## First step

Hash the file with `hashlib.sha1`, keep a small cache next to the index, and reuse the parsed points
when the hash matches.

## Open questions

- Where should the cache live when the vault is the only writable folder?
- Does [[trackpoint-parsing]] change often enough to invalidate old entries?
