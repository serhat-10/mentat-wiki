---
type: entity
summary: gpxkit is a fictional, small GPX reader: it streams points and smooths nothing.
domain: engineering
created: 2026-11-11
updated: 2026-11-18
sources: [gpx-parsing-walkthrough]
tags: [gpx, libraries]
status: draft
---

# gpxkit

## What it is

gpxkit is a fictional, small GPX reader used as the parsing layer in trailmap. It streams trackpoints
and leaves smoothing to the caller. It is invented for this demo vault and is not a real package.

## Why it matters here

Keeping the reader thin makes the smoothing decision testable on its own. If gpxkit filtered
elevation, trailmap could not show a raw profile for comparison.

## Notes

- API shape: `iter_points(path)` yields latitude, longitude, elevation and time.
- Standard library only; no geometry or projection code.
- Missing elevation comes back as `None`, never as zero.

## Related

- [[trackpoint-parsing]]
- [[elevation-smoothing]]
- [[gpx]]
- [[gpx-parsing-walkthrough]]
