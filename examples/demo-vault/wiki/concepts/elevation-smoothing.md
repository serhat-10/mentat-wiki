---
type: concept
domain: engineering
created: 2026-11-07
updated: 2026-11-08
summary: A moving average over a short window removes altitude jitter before gain is summed.
project: trailmap
origin: session:2026-11-07-1018
auto: false
status: draft
---
# Elevation smoothing

## Summary

GPS altitude drifts between fixes. A short moving average over elevation, followed by a climb
threshold, gives a gain figure that matches the shape of the walk.

## Details

- Smooth elevation only; leave distance and time alone.
- A five-point window hides spikes without flattening real climbs.
- Pad the ends by repeating the first and last values, or the edges lose height.
- Count a climb only after it passes a threshold; 3 m works for day hikes.

## Examples

On the coastal test track, raw gain is 780 m, smoothed gain is 640 m, and both use the same points.

## Contradictions

The smoothing note recommends three passes for noisy days; one pass was enough here.

## Agent notes (not from source, unverified)

The window is a display choice, not a property of the file.

## Related

- [[elevation-smoothing-note]]
- [[gpxkit]]
- [[what-causes-spikes-in-gpx-elevation-profiles]]
