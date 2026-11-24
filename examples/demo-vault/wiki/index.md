---
type: index
updated: 2026-11-23
---

# Index

Catalog of every wiki page. Format: `- [[page]]: one-line summary (domain)`.

## Sources

- [[gpx-parsing-walkthrough]]: How a walkthrough parses GPX: tracks, segments, points, optional elevation. (engineering)
- [[elevation-smoothing-note]]: Why raw GPS altitude inflates gain, and how a window plus a threshold fixes it. (engineering)

## Concepts

- [[trackpoint-parsing]]: A GPX track is nested segments of trackpoints; elevation is optional on every point. (engineering)
- [[elevation-smoothing]]: A moving average over a short window removes altitude jitter before gain is summed. (engineering)

## Entities

- [[gpx]]: GPX is the open XML format for GPS tracks, routes and waypoints. (engineering)
- [[gpxkit]]: gpxkit is a fictional, small GPX reader: it streams points and smooths nothing. (engineering)

## Ideas

- [[cache-parsed-tracks-by-file-hash]]: Hash the GPX file and reuse the parsed track so repeated profiles are instant. (engineering)
- [[add-a-json-output-mode]]: Emit the profile as JSON so another tool can plot it without parsing text. (engineering)
- [[compare-two-routes-side-by-side]]: Show gain, distance and steepest kilometre for two GPX files in one table. (engineering)

## Thoughts

- [[elevation-noise-is-a-product-decision]]: How much to smooth is a choice about the number shown, not a parsing detail. (engineering)
- [[profiles-need-a-stated-window]]: A profile should print its smoothing window, or two tools will never agree on gain. (engineering)

## Projects

- [[projects/trailmap/status]]: Status of trailmap (projects)

## Outputs

- [[what-causes-spikes-in-gpx-elevation-profiles]]: GPS altitude jitter and sparse fixes create spikes; smoothing plus a climb threshold removes most. (engineering)
