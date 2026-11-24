---
type: concept
domain: engineering
created: 2026-11-03
updated: 2026-11-04
summary: A GPX track is nested segments of trackpoints; elevation is optional on every point.
project: trailmap
origin: session:2026-11-03-1942
auto: false
status: draft
---
# Trackpoint parsing

## Summary

A GPX file stores one or more tracks. Each track holds segments, and each segment is an ordered list
of trackpoints with latitude, longitude and an optional elevation.

## Details

- Parse with a streaming reader. Tracks can be large and the interesting tags are shallow.
- Treat `<ele>` as optional: some route exports carry only coordinates.
- Keep the raw point order. Smoothing is a later step, not part of reading.
- Drop points with no coordinates instead of guessing them.

## Examples

A 12 km day hike exported by a phone at a five-second interval holds about 3,000 trackpoints.

## Contradictions

None yet.

## Agent notes (not from source, unverified)

Consumer apps often write several segments for one walk when the signal drops.

## Related

- [[gpx]]
- [[gpxkit]]
- [[gpx-parsing-walkthrough]]
