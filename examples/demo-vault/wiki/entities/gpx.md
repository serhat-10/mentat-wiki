---
type: entity
summary: GPX is the open XML format for GPS tracks, routes and waypoints.
domain: engineering
created: 2026-11-11
updated: 2026-11-17
sources: [gpx-parsing-walkthrough]
tags: [gpx, formats]
status: stable
---

# GPX

## What it is

GPX is an open XML format for GPS data: tracks, routes and waypoints. A track is nested segments of
trackpoints with latitude and longitude, plus optional elevation and time.

## Why it matters here

It is the only input format trailmap accepts. A profile is just the elevation of each trackpoint in
order, so the format's shallow structure is most of the parsing problem.

## Notes

- Versions 1.0 and 1.1 are both common; the track structure is the same for our purposes.
- Elevation lives in `<ele>`, in metres, and is optional.
- Files come from phones, watches and route planners, so missing fields are normal.

## Related

- [[gpx-parsing-walkthrough]]
- [[trackpoint-parsing]]
- [[gpxkit]]
