---
type: output
domain: engineering
created: 2026-11-13
updated: 2026-11-13
summary: GPS altitude jitter and sparse fixes create spikes; smoothing plus a climb threshold removes most.
project: trailmap
origin: session:2026-11-13-1826
auto: false
status: draft
---
# What causes spikes in GPX elevation profiles?

## Question

Why does the same hike export 610 m of gain in one app and 780 m in another?

## Answer

Consumer GPS altitude drifts between fixes, and summing raw differences counts that drift as
climbing. The two sources behind this answer agree on the cause. They differ on the cure: one
smoothing pass or three, and a threshold anywhere from 1 m to 5 m.

trailmap settles on one five-point pass over elevation only, then ignores climbs below 3 m. On the
coastal test track that gives 640 m. The window and the threshold belong in the output so the number
can be compared.

## Sources

- [[gpx-parsing-walkthrough]]
- [[elevation-smoothing-note]]

## Related

- [[elevation-smoothing]]
