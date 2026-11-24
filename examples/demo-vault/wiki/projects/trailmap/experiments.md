---
type: project-status
domain: projects
summary: Experiment log for trailmap
updated: 2026-11-21
---

# trailmap: experiments

One line per attempt, newest last: what was tried (command, parameters, output path) and what happened. Failures count.

- 2026-11-19 09:15 [worked] streaming parse of the 42 km test track -> 9,840 points in 0.2 s at 18 MB peak memory
- 2026-11-20 16:40 [failed] five-point window without edge padding -> first and last elevations dropped 14 m
- 2026-11-21 11:05 [worked] 3 m climb threshold -> 640 m gain, within 20 m of the sum from the route map
