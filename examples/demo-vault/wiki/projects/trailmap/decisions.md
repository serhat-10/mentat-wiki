---
type: project-status
domain: projects
summary: Decision log for trailmap
updated: 2026-11-20
---

# trailmap: decisions

Append only. One row per decision.

| Date | Decision | Why | Rejected alternatives | Origin |
|---|---|---|---|---|
| 2026-11-10 | Parse GPX with a streaming reader | Long tracks should not sit in memory, and expat ships with Python. | Loading the whole XML tree and a third-party GPX package. | session:2026-11-10-1005 |
| 2026-11-11 | Keep elevation smoothing in trailmap, not in gpxkit | The reader stays thin and the display choice stays ours. | Smoothing inside gpxkit and a plugin hook for filters. | session:2026-11-11-1022 |
| 2026-11-15 | Use a five-point moving average for elevation | Plain to explain and good enough for day hikes. | A Savitzky-Golay filter, a Kalman filter, raw altitude. | session:2026-11-15-1640 |
| 2026-11-16 | Ignore climbs below 3 m | GPS altitude jitter inflated gain by 12-18% on the test tracks. | Raw cumulative gain, a 1 m threshold, a 5 m threshold. | session:2026-11-16-1702 |
| 2026-11-20 | Ship the text profile before any plot | It works over ssh and in every terminal, with no GUI dependency. | A Tkinter window in the first release and an SVG chart. | session:2026-11-20-0948 |
