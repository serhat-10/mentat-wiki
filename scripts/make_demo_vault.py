"""Build the fictional demo vault in examples/demo-vault.

Regenerate from the repo root with: python scripts/make_demo_vault.py
"""
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "examples" / "demo-vault"
sys.path.insert(0, str(ROOT))  # so the script can reuse util from the repo
from mentat_wiki import util  # noqa: E402

DATE = datetime.date.today


def ago(days: int) -> str:
    return (DATE() - datetime.timedelta(days=days)).isoformat()


# -- CLI plumbing ---------------------------------------------------------
def demo_env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("MENTAT_VAULT", "MENTAT_CMD", "MENTAT_SESSION", "CLAUDE_SESSION_ID")}
    env["MENTAT_CONFIG"] = str(tmp / "config.json")
    env["CLAUDE_CONFIG_DIR"] = str(tmp / "claude")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(env: dict, *args: str, stdin: str = "") -> str:
    print("+ python -m mentat_wiki " + " ".join(args))
    r = subprocess.run([sys.executable, "-m", "mentat_wiki", *args], cwd=str(ROOT), env=env,
                       input=stdin, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    output = (r.stdout or "") + (r.stderr or "")
    if output.strip():
        print(output.rstrip())
    if r.returncode != 0:
        raise SystemExit(f"demo: command failed ({r.returncode}): {' '.join(args)}\n{output}")
    return r.stdout or ""


# -- page writing ---------------------------------------------------------
def guard(text: str) -> None:
    hits = util.privacy_scan(text)
    if hits:
        raise SystemExit(f"demo: refused content with possible sensitive data ({', '.join(hits)})")


def page(path: Path, meta: dict, body: str) -> None:
    text = "\n".join(["---", *(f"{k}: {v}" for k, v in meta.items()), "---", "", body.strip(), ""])
    guard(text)
    util.write_atomic(path, text)


def add_index(section: str, link: str, summary: str, domain: str) -> None:
    path = VAULT / "wiki" / "index.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    head = lines.index(f"## {section}")
    end = next((i for i in range(head + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = [l for l in lines[head + 1:end]
            if l.strip() and l.strip() != "_(none yet)_"]
    body.append(f"- [[{link}]]: {summary} ({domain})")
    lines[head + 1:end] = [""] + body + [""]
    util.write_atomic(path, "\n".join(lines))


def meta(type_, summary, domain, created, updated, sources="[]", tags="[]", quality=None,
         status="stable"):
    out = {"type": type_, "summary": summary, "domain": domain, "created": created,
           "updated": updated, "sources": sources, "tags": tags}
    if quality:
        out["quality"] = quality
    out["status"] = status
    return out


# -- captures -------------------------------------------------------------
def keep(env, type_, title, summary, body, domain, value=None, effort=None, est_days=None):
    args = ["keep", "--type", type_, "--title", title, "--summary", summary,
            "--domain", domain, "--project", "trailmap", "--body", "-"]
    if value is not None:
        args += ["--value", str(value), "--effort", str(effort)]
    if est_days is not None:
        args += ["--est-days", str(est_days)]
    run(env, *args, stdin=body)


def decide(env, decision, why, rejected):
    run(env, "decide", "--project", "trailmap", "--decision", decision, "--why", why,
        "--rejected", rejected)


def note(env, result, text):
    run(env, "note", "--project", "trailmap", "--result", result, text)


# -- hand-written pages (sources, entities) --------------------------------
RAW_GPX = """\
<!-- Fictional source. Written for the mentat-wiki demo vault. Not a real article. -->

# Reading a GPX track without a map library

A note from a fictional hiking club's tooling evening.

GPX is XML. The root element holds one or more tracks, each track holds segments, and each segment
holds trackpoints in order. A trackpoint carries latitude and longitude as attributes. Elevation and
time are child elements, and both are optional.

The walkthrough starts with the smallest possible reader: walk the document, remember the current
track and segment, and append a point when a trackpoint closes. That is enough for a profile. No map
tiles, no projection, no geometry library.

Two details matter more than they look.

First, elevation is optional. Route exports often drop it, and consumer apps write an empty element
instead of a number. Treat both as missing. Do not substitute zero, or the profile gains a cliff at
sea level.

Second, keep memory flat. A long ride can hold tens of thousands of points, and a parser that keeps
the whole XML tree costs more than the numbers are worth. A streaming reader returns points one at a
time, so the profile code can sum as it goes.

The note also suggests a small test folder: one clean file, one file with no elevation, one file
with a single-point segment. Those three cover most breakage seen in practice.

Fictional. No real article, person or organisation is described.
"""

RAW_SMOOTHING = """\
<!-- Fictional source. Written for the mentat-wiki demo vault. Not a real article. -->

# Smoothing noisy elevation profiles

A fieldwork note from a fictional route-planning group.

GPS altitude is the least trustworthy number in a track. Between fixes it drifts by several metres,
and the drift is not random enough to cancel when summed. A flat walk can report 200 m of climbing
from noise alone.

The note compares raw cumulative gain with gain after a moving average over elevation. Smoothing
distance or time is a mistake: the x axis is exact enough, and changing it moves every gradient.

The window is a trade. Five points at a one-second interval remove most spikes and keep short climbs.
Fifteen points hide real steps on a staircase. Three passes over the same data flatten the profile
until it looks like a smoothing demo and not a hill.

Edges need padding. A moving average that starts at the second point loses the first and last
elevations, and on an out-and-back route the start and finish should match. Repeat the first and last
values before smoothing.

The second half of the note is about thresholds. Even a smooth profile wobbles by a metre or two, so
every wobble adds a little gain. Count a climb only after it passes a threshold. Three metres is a
reasonable start for day hikes; one metre keeps noise, five metres hides small rises.

Fictional. The numbers are illustrative, not measurements.
"""


def write_sources() -> None:
    raw = VAULT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    guard(RAW_GPX)
    util.write_atomic(raw / "gpx-parsing-notes.md", RAW_GPX)
    guard(RAW_SMOOTHING)
    util.write_atomic(raw / "elevation-smoothing-notes.md", RAW_SMOOTHING)

    page(VAULT / "wiki" / "sources" / "gpx-parsing-walkthrough.md",
         meta("source", "How a walkthrough parses GPX: tracks, segments, points, optional elevation.",
              "engineering", ago(21), ago(20), tags="[gpx, parsing]", quality="secondary"),
         """\
# GPX parsing walkthrough

Raw file: `raw/gpx-parsing-notes.md` (fictional, written for this demo).

## Key takeaways

- A GPX track is a track, then segments, then trackpoints; the structure is shallow.
- A streaming reader keeps memory flat on long tracks.
- Elevation and time are optional and must be treated as missing, not as zero.

## Details

The note walks through a fictional club's export folder: one file per hike, mixed GPX versions, and
a few files with no elevation at all. It recommends reading attributes first, then the child tags in
document order, and testing with one clean file, one file without elevation and one single-point
segment.

## Contradictions

_(none yet)_

## Agent notes (not from source, unverified)

trailmap reads small files in one pass with the standard library and switches to a streaming reader
above 5 MB. The switch is untested on a real large file.

## Related

- [[trackpoint-parsing]]
- [[gpx]]
- [[gpxkit]]
- [[elevation-smoothing]]
""")

    page(VAULT / "wiki" / "sources" / "elevation-smoothing-note.md",
         meta("source", "Why raw GPS altitude inflates gain, and how a window plus a threshold fixes it.",
              "engineering", ago(17), ago(16), tags="[gpx, elevation, smoothing]", quality="tertiary"),
         """\
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
""")


def write_entities() -> None:
    page(VAULT / "wiki" / "entities" / "gpx.md",
         meta("entity", "GPX is the open XML format for GPS tracks, routes and waypoints.",
              "engineering", ago(12), ago(6), sources="[gpx-parsing-walkthrough]",
              tags="[gpx, formats]"),
         """\
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
""")

    page(VAULT / "wiki" / "entities" / "gpxkit.md",
         meta("entity", "gpxkit is a fictional, small GPX reader: it streams points and smooths nothing.",
              "engineering", ago(12), ago(5), sources="[gpx-parsing-walkthrough]",
              tags="[gpx, libraries]", status="draft"),
         """\
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
""")


def write_core() -> None:
    """Fill the two core placeholders a used vault would have filled."""
    text = """\
---
type: core
summary: Who the human is (filled in by the human, kept short)
---

# User

- Role: solo developer, evenings and weekends
- Focus now: trailmap, an offline hiking-route planner
- Preferences: short answers, concrete examples, no filler
- Allowed names: none
"""
    guard(text)
    util.write_atomic(VAULT / "core" / "USER.md", text)

    text = """\
---
type: core
summary: Durable facts every session needs (a few lines, curated)
---

# Memory

- trailmap lives in a separate folder and is registered as project trailmap.
- `raw/` is read-only; wiki pages are written through the `mentat-wiki` CLI.
- Gain figures here come from local test tracks, not from a survey.
"""
    guard(text)
    util.write_atomic(VAULT / "core" / "MEMORY.md", text)


# -- dates, log and verification ------------------------------------------
# stem -> (created days ago, updated days ago); the demo shows a few weeks of use.
DATES = {
    "gpx-parsing-walkthrough": (21, 20),
    "elevation-smoothing-note": (17, 16),
    "trackpoint-parsing": (20, 19),
    "elevation-smoothing": (16, 15),
    "what-causes-spikes-in-gpx-elevation-profiles": (10, 10),
    "gpx": (12, 6),
    "gpxkit": (12, 5),
    "cache-parsed-tracks-by-file-hash": (5, 5),
    "add-a-json-output-mode": (5, 4),
    "compare-two-routes-side-by-side": (1, 1),
    "elevation-noise-is-a-product-decision": (2, 2),
    "profiles-need-a-stated-window": (1, 1),
}
# stem -> (days ago, clock) for the session id in `origin`, so it matches `created`.
ORIGINS = {
    "trackpoint-parsing": (20, "1942"),
    "elevation-smoothing": (16, "1018"),
    "what-causes-spikes-in-gpx-elevation-profiles": (10, "1826"),
    "cache-parsed-tracks-by-file-hash": (5, "2107"),
    "add-a-json-output-mode": (5, "2131"),
    "compare-two-routes-side-by-side": (1, "2012"),
    "elevation-noise-is-a-product-decision": (2, "2205"),
    "profiles-need-a-stated-window": (1, "2044"),
}


def set_dates(path: Path, created=None, updated=None) -> None:
    text = path.read_text(encoding="utf-8")
    if created:
        text = re.sub(r"(?m)^created: .*$", f"created: {created}", text, count=1)
    if updated:
        text = re.sub(r"(?m)^updated: .*$", f"updated: {updated}", text, count=1)
    util.write_atomic(path, text)


def backdate() -> None:
    for path in (VAULT / "wiki").rglob("*.md"):
        if path.name in ("index.md", "log.md") and path.parent.name == "wiki":
            continue
        if path.stem in DATES:
            created, updated = DATES[path.stem]
            set_dates(path, ago(created), ago(updated))
        if path.stem in ORIGINS:
            days_ago, clock = ORIGINS[path.stem]
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"(?m)^origin: .*$", f"origin: session:{ago(days_ago)}-{clock}",
                          text, count=1)
            util.write_atomic(path, text)

    # Decision rows and experiment stamps were written by the CLI with today's date.
    decisions = VAULT / "wiki" / "projects" / "trailmap" / "decisions.md"
    days, clocks = [13, 12, 8, 7, 3], ["1005", "1022", "1640", "1702", "0948"]
    lines, i = decisions.read_text(encoding="utf-8").split("\n"), 0
    for n, line in enumerate(lines):
        if line.startswith("| 20") and i < len(days):
            line = re.sub(r"session:\d{4}-\d{2}-\d{2}-\d{4}",
                          f"session:{ago(days[i])}-{clocks[i]}", line)
            head, sep, rest = line.partition(" | ")
            lines[n] = f"| {ago(days[i])}{sep}{rest}"
            i += 1
    util.write_atomic(decisions, "\n".join(lines))
    set_dates(decisions, updated=ago(3))

    experiments = VAULT / "wiki" / "projects" / "trailmap" / "experiments.md"
    stamps = [(4, "09:15"), (3, "16:40"), (2, "11:05")]

    def stamp(_m):
        days_ago, clock = stamps.pop(0) if stamps else (0, "12:00")
        return f"- {ago(days_ago)} {clock} ["

    text = re.sub(r"(?m)^- \d{4}-\d{2}-\d{2} \d{2}:\d{2} \[", stamp,
                  experiments.read_text(encoding="utf-8"))
    util.write_atomic(experiments, text)
    set_dates(experiments, updated=ago(2))

    inbox = VAULT / "inbox" / "inbox.md"
    text = re.sub(r"(?m)^- \[ \] \d{4}-\d{2}-\d{2} ", f"- [ ] {ago(1)} ",
                  inbox.read_text(encoding="utf-8"))
    util.write_atomic(inbox, text)


def write_log() -> None:
    entries = [
        (ago(21), "ingest", "gpx parsing walkthrough", "raw/gpx-parsing-notes.md"),
        (ago(17), "ingest", "elevation smoothing note", "raw/elevation-smoothing-notes.md"),
        (ago(10), "query", "what causes spikes in gpx elevation profiles",
         "Answered from [[gpx-parsing-walkthrough]] and [[elevation-smoothing-note]]."),
        (ago(6), "lint", "trailmap: links and frontmatter", "Checked index entries and orphans."),
        (ago(0), "session", "trailmap: wrap",
         "Parser and text profile work end to end; smoothing is in place."),
    ]
    text = ("# Log\n\nAppend-only. Format: "
            "`## [YYYY-MM-DD] <ingest|query|lint|session> | <title>`\n")
    for date, kind, title, note in entries:
        text += f"\n## [{date}] {kind} | {title}\n{note}\n"
    guard(text)
    util.write_atomic(VAULT / "wiki" / "log.md", text)


def verify(env: dict) -> None:
    out = run(env, "doctor")
    bad = [line for line in out.splitlines() if line.startswith(("ERROR", "WARN"))]
    if bad:
        raise SystemExit("demo: doctor reported issues:\n" + "\n".join(bad))
    run(env, "find", "gpx")


def main() -> None:
    print(f"demo: building {VAULT.relative_to(ROOT).as_posix()}")
    if VAULT.exists():
        shutil.rmtree(VAULT)

    with tempfile.TemporaryDirectory(prefix="mentat-demo-") as tmp:
        tmp = Path(tmp)
        env = demo_env(tmp)
        work = tmp / "trailmap"
        work.mkdir()

        run(env, "init", str(VAULT))
        run(env, "project", "register", "trailmap", "--path", str(work))

        keep(env, "concept", "Trackpoint parsing",
             "A GPX track is nested segments of trackpoints; elevation is optional on every point.",
             """\
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
""", "engineering")

        keep(env, "concept", "Elevation smoothing",
             "A moving average over a short window removes altitude jitter before gain is summed.",
             """\
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
""", "engineering")

        keep(env, "idea", "Cache parsed tracks by file hash",
             "Hash the GPX file and reuse the parsed track so repeated profiles are instant.",
             """\
## Why

The same file is opened again and again while tuning the profile. Parsing 10,000 points is fast,
but not free.

## First step

Hash the file with `hashlib.sha1`, keep a small cache next to the index, and reuse the parsed points
when the hash matches.

## Open questions

- Where should the cache live when the vault is the only writable folder?
- Does [[trackpoint-parsing]] change often enough to invalidate old entries?
""", "engineering", value=4, effort=2, est_days=1)

        keep(env, "idea", "Add a --json output mode",
             "Emit the profile as JSON so another tool can plot it without parsing text.",
             """\
## Why

A JSON mode lets another tool plot the profile without scraping text columns, and it costs one
serialiser.

## First step

Add `--json` and emit distance, elevation, gain and the smoothing window.

## Open questions

- Should the window be part of the JSON so consumers can reproduce the smoothing? See
  [[elevation-smoothing]].
""", "engineering", value=3, effort=2, est_days=1)

        keep(env, "idea", "Compare two routes side by side",
             "Show gain, distance and steepest kilometre for two GPX files in one table.",
             """\
## Why

Comparing two hikes is the most common question once a single profile works.

## First step

Accept two files and print one table with distance, gain and the steepest kilometre.

## Open questions

- How do we align two tracks that start at different points?
""", "engineering", value=3, effort=4, est_days=3)

        keep(env, "thought", "Elevation noise is a product decision",
             "How much to smooth is a choice about the number shown, not a parsing detail.",
             """\
The parser can hand back exact numbers, but a profile is a summary. Choosing a window and a
threshold is choosing what the gain figure means, so it belongs in the display layer. See
[[elevation-smoothing]].
""", "engineering")

        keep(env, "thought", "Profiles need a stated window",
             "A profile should print its smoothing window, or two tools will never agree on gain.",
             """\
If trailmap prints its smoothing window, two tools can disagree and both be right. Without it,
every gain figure looks like a bug. See [[elevation-smoothing]].
""", "engineering")

        keep(env, "output", "What causes spikes in GPX elevation profiles?",
             "GPS altitude jitter and sparse fixes create spikes; smoothing plus a "
             "climb threshold removes most.",
             """\
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
""", "engineering")

        decide(env, "Parse GPX with a streaming reader",
               "Long tracks should not sit in memory, and expat ships with Python.",
               "Loading the whole XML tree and a third-party GPX package.")
        decide(env, "Keep elevation smoothing in trailmap, not in gpxkit",
               "The reader stays thin and the display choice stays ours.",
               "Smoothing inside gpxkit and a plugin hook for filters.")
        decide(env, "Use a five-point moving average for elevation",
               "Plain to explain and good enough for day hikes.",
               "A Savitzky-Golay filter, a Kalman filter, raw altitude.")
        decide(env, "Ignore climbs below 3 m",
               "GPS altitude jitter inflated gain by 12-18% on the test tracks.",
               "Raw cumulative gain, a 1 m threshold, a 5 m threshold.")
        decide(env, "Ship the text profile before any plot",
               "It works over ssh and in every terminal, with no GUI dependency.",
               "A Tkinter window in the first release and an SVG chart.")

        note(env, "worked",
             "streaming parse of the 42 km test track -> 9,840 points in 0.2 s at 18 MB peak memory")
        note(env, "failed",
             "five-point window without edge padding -> first and last elevations dropped 14 m")
        note(env, "worked",
             "3 m climb threshold -> 640 m gain, within 20 m of the sum from the route map")

        run(env, "wrap", "--project", "trailmap",
            "--where", "Parser and text profile work end to end. Five-point smoothing runs with a "
                       "3 m climb threshold; the coastal test track reports 640 m of gain.",
            "--next", "Add --json output for plotting.",
            "--thread", "Write a regression test that pins the coastal track at 640 m of gain.",
            "--thread", "Try a nine-point window on the coastal track and compare total gain.")

        run(env, "inbox", "Check whether hikers read D+ or total ascent in the profile footer")

        write_sources()
        write_entities()
        write_core()
        add_index("Sources", "gpx-parsing-walkthrough",
                  "How a walkthrough parses GPX: tracks, segments, points, optional elevation.",
                  "engineering")
        add_index("Sources", "elevation-smoothing-note",
                  "Why raw GPS altitude inflates gain, and how a window plus a threshold fixes it.",
                  "engineering")
        add_index("Entities", "gpx",
                  "GPX is the open XML format for GPS tracks, routes and waypoints.", "engineering")
        add_index("Entities", "gpxkit",
                  "gpxkit is a fictional, small GPX reader: it streams points and smooths nothing.",
                  "engineering")

        backdate()
        write_log()
        verify(env)

    shutil.rmtree(VAULT / ".mentat", ignore_errors=True)
    print(f"demo: ready at {VAULT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
