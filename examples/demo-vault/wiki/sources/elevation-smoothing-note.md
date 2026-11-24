---
type: source
summary: Why raw GPS altitude inflates gain, and how a window plus a threshold fixes it.
domain: engineering
created: 2026-11-06
updated: 2026-11-07
sources: []
tags: [gpx, elevation, smoothing]
quality: tertiary
status: stable
---

# Elevation smoothing note

Raw file: `raw/elevation-smoothing-notes.md` (fictional, written for this demo).

## Key takeaways

- Consumer GPS altitude is noisy enough to inflate cumulative gain.
- Smooth elevation only; leave distance and time untouched.
- A climb threshold matters as much as the smoothing window.

## Details

The note compares raw gain with gain after a five-point moving average on three fictional walking
routes. The gap was 12-18% on two routes and under 4% on the third, which had open sky all day.
Three passes over-smooth short climbs, and an unpadded moving average loses the first and last
elevations.

## Contradictions

The note reports a three-pass window as best for noisy days; one pass is enough on the test tracks
used here. Both are noted, not averaged.

## Agent notes (not from source, unverified)

trailmap uses one pass and a 3 m threshold. The gain figures in this vault come from local test
tracks, not from the note.

## Related

- [[elevation-smoothing]]
- [[trackpoint-parsing]]
- [[what-causes-spikes-in-gpx-elevation-profiles]]
