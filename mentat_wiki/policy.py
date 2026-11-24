"""Capture policy: read core/capture-policy.md and report how proposals fared per category.
Read-only: never writes any file. Promotion to `auto` is only ever suggested, never applied."""
import json
import math
import re
import time

from . import config
from .vault import Vault, VaultError

FILE = "core/capture-policy.md"
LEVELS = ("ask", "auto", "never")
OUTCOMES = ("kept", "edited", "rejected", "ignored")
DEFAULT_LEVELS = {"decision": "ask", "idea": "ask", "thought": "ask", "concept": "ask", "output": "ask",
                  "wrap": "ask", "debugging": "ask", "chatter": "never"}
DEFAULTS = {"min_proposals": 20, "min_acceptance": 0.9, "expiry_hours": 24}
DEMOTE_MIN = 3  # an auto category needs at least this many rejections or ignores before demotion
RATE_EPSILON = 1e-12


def _number(value, default, lo, hi):
    """Frontmatter values arrive as strings; return a finite number in [lo, hi] or the default."""
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if not math.isfinite(n) or not lo <= n <= hi:
        return default
    return int(n) if n.is_integer() else n


def _levels(body: str) -> dict:
    """Levels from the `| Category | Policy | Notes |` table; anything else keeps the defaults."""
    levels = dict(DEFAULT_LEVELS)
    previous = []
    active = False
    for line in body.splitlines():
        cells = [c.strip().strip("`").strip().casefold() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            active = False
        elif all(re.fullmatch(r":?-+:?", c) for c in cells):
            active = previous[:2] == ["category", "policy"] and len(previous) in (2, 3)
        elif active and cells[1] in LEVELS and re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", cells[0]):
            levels[cells[0]] = cells[1]
        previous = cells
    return levels


def load(vault) -> dict:
    """Thresholds and levels from core/capture-policy.md, with defaults for anything missing."""
    from .util import parse_frontmatter
    out = dict(DEFAULTS, levels=dict(DEFAULT_LEVELS))
    try:
        text = (vault.root / FILE).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return out
    meta, body = parse_frontmatter(text)
    if "min_proposals" in meta:
        try:
            minimum = int(meta["min_proposals"])
            if not 1 <= minimum <= 10 ** 6:
                raise ValueError
            out["min_proposals"] = minimum
        except (ValueError, TypeError):
            out["warning"] = "Invalid min_proposals. Using the default of 20."
    out["min_acceptance"] = float(_number(meta.get("min_acceptance"), 0.9, 0, 1))
    out["expiry_hours"] = _number(meta.get("expiry_hours"), 24, 0.01, 24 * 366)
    out["levels"] = _levels(body)
    return out


def pct(x) -> str:
    """0.895 -> '89.5%', 0.9 -> '90%'. Rounds down so a rate never looks higher than it is."""
    if x is None:
        return "-"
    s = f"{math.floor(x * 1000 + 1e-9) / 10:.1f}"
    return s.rstrip("0").rstrip(".") + "%"


def report(vault, now=None) -> list:
    """One dict per category: counts, acceptance, level, eligibility and a suggested table change."""
    pol = load(vault)
    now = time.time() if now is None else now
    rows = {c: {"category": c, "level": lvl, "proposed": 0, "kept": 0, "edited": 0, "rejected": 0,
                "ignored": 0, "explicit": 0, "auto": 0} for c, lvl in pol["levels"].items()}
    said_no = dict.fromkeys(rows, 0)  # explicit rejections, used only for demotion
    pending = vault.pending(None)
    seen = set()
    for e in vault.events():
        t, outcome = e.get("type"), e.get("outcome")
        if not isinstance(t, str) or t not in rows or outcome not in OUTCOMES:
            continue
        proposal = e.get("proposal")
        if isinstance(proposal, str) and proposal:
            if proposal in seen:
                continue
            seen.add(proposal)
        r = rows[t]
        if e.get("auto") is True:
            r["auto"] += 1
        elif e.get("via") == "proposal":
            r["proposed"] += 1
            r[outcome] += 1
        else:
            r["explicit"] += 1
            said_no[t] += outcome == "rejected"
    for p in pending:
        t = p.get("type")
        if isinstance(t, str) and t in rows and vault._age(p, now) >= pol["expiry_hours"] * 3600:
            proposal = p.get("id")
            if isinstance(proposal, str) and proposal:
                if proposal in seen:
                    continue
                seen.add(proposal)
            rows[t]["proposed"] += 1
            rows[t]["ignored"] += 1
    for c, r in rows.items():
        _finish(r, said_no[c], pol)
    return list(rows.values())


def _finish(r: dict, said_no: int, pol: dict) -> None:
    good = r["kept"] + r["edited"]
    r["acceptance"] = good / r["proposed"] if r["proposed"] else None
    r["eligible"] = (r["level"] == "ask" and r["proposed"] >= pol["min_proposals"]
                     and r["acceptance"] + RATE_EPSILON >= pol["min_acceptance"])
    bad = r["rejected"] + r["ignored"] + said_no
    c = r["category"]
    r["suggestion"] = None
    if r["eligible"]:
        r["suggestion"] = (f"change `| {c} | ask |` to `| {c} | auto |` in {FILE}, with your approval")
    elif (r["level"] == "auto" and bad >= DEMOTE_MIN
          and bad / (bad + good + r["auto"]) > 1 - pol["min_acceptance"] + RATE_EPSILON):
        r["suggestion"] = (f"change `| {c} | auto |` to `| {c} | ask |` in {FILE} "
                           f"({bad} rejected or ignored)")


def render(rows: list, pol: dict) -> str:
    cols = ["proposed", "kept", "edited", "rejected", "ignored", "explicit", "auto"]
    width = max([len(r["category"]) for r in rows] + [8])
    head = f"{'category':<{width}}  {'level':<5}  " + "  ".join(cols) + "  accepted"
    lines = [head]
    for r in rows:
        nums = "  ".join(f"{r[k]:>{len(k)}}" for k in cols)
        lines.append(f"{r['category']:<{width}}  {r['level']:<5}  {nums}  {pct(r['acceptance']):>8}")
    lines += ["", f"Auto needs {pol['min_proposals']}+ proposals with {pct(pol['min_acceptance'])} or more "
                  f"accepted (kept or edited), and your approval. Unanswered proposals count as ignored "
                  f"after {pol['expiry_hours']} h. Explicit and auto captures are not in the rate."]
    tips = [r["suggestion"] for r in rows if r["suggestion"]]
    lines += ["", "Suggestions:"] + [f"- {t}" for t in tips] if tips else ["", "No change suggested."]
    if "warning" in pol:
        lines.append(pol["warning"])
    return "\n".join(lines)


def _vault() -> Vault:
    root = config.vault_root()
    if root is None:
        raise VaultError("no vault configured. Run `mentat-wiki config --vault <path>`.")
    v = Vault(root)
    v.check()
    return v


def cmd_policy(a):
    v = _vault()
    pol, rows = load(v), report(v)
    if a.json:
        thresholds = {k: pol[k] for k in DEFAULTS}
        print(json.dumps({"thresholds": thresholds, "categories": rows}, indent=2))
    else:
        print(render(rows, pol))


def add_parser(subparsers) -> None:
    s = subparsers.add_parser("policy", help="capture acceptance per category and auto suggestions (read-only)")
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s.set_defaults(fn=cmd_policy)
