"""Weekly ideas digest. Read-only: scans wiki/ideas, writes nothing."""
import datetime

from . import policy, util
from .vault import Vault


def _date(s):
    try:
        return datetime.date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


def _int(s, default):
    try:
        return int(str(s).strip())
    except ValueError:
        return default


def load(v: Vault) -> list:
    out = []
    for p in sorted((v.wiki / "ideas").glob("*.md")):
        meta, body = util.parse_frontmatter(p.read_text(encoding="utf-8-sig", errors="replace"))
        if meta.get("type") != "idea":
            continue
        created = _date(meta.get("created", ""))
        updated = _date(meta.get("updated", "")) or created
        out.append({"slug": p.stem, "summary": meta.get("summary", ""),
                    "status": meta.get("idea_status", "parked"),
                    "value": _int(meta.get("value", ""), 0), "effort": _int(meta.get("effort", ""), 0),
                    "created": created, "updated": updated})
    return out


def _line(i):
    return f"- [[{i['slug']}]] (v{i['value']} e{i['effort']}): {i['summary']}"


def _policy_lines(v: Vault, since: datetime.date, days: int) -> list:
    proposed = accepted = 0
    for e in v.events():
        if not isinstance(e, dict) or e.get("auto") is True or e.get("via") != "proposal":
            continue
        outcome = e.get("outcome")
        if outcome not in policy.OUTCOMES:
            continue
        d = _date(e.get("date", ""))
        if "date" in e and d is None:
            continue
        if isinstance(e.get("ts"), (int, float)):
            try:
                timestamp_date = datetime.date.fromtimestamp(e["ts"])
            except (OverflowError, OSError, ValueError):
                continue
            d = d or timestamp_date
        if d and d >= since:
            proposed += 1
            if outcome in ("kept", "edited"):
                accepted += 1
    rate = policy.pct(accepted / proposed) if proposed else "-"
    out = [f"- Overall proposal acceptance (last {days} days): {accepted}/{proposed} ({rate})"]
    eligible = [r for r in policy.report(v) if r.get("eligible")]
    if eligible:
        for r in eligible:
            out.append(f"- Eligible for auto: {r['category']} "
                       f"({r['proposed']} proposals, {policy.pct(r['acceptance'])} accepted)")
    else:
        out.append("- Eligible for auto: _(none)_")
    return out


def build(v: Vault, days: int = 7, top: int = 3, today=None) -> str:
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=days)
    ideas = load(v)
    recent = [i for i in ideas if i["updated"] and i["updated"] >= since]
    recent.sort(key=lambda i: i["updated"], reverse=True)
    opened = [i for i in ideas if i["status"] == "parked"]
    opened.sort(key=lambda i: (i["value"] - i["effort"], i["value"]), reverse=True)
    lines = [f"# Ideas digest {today.isoformat()}", "", f"## New or updated (last {days} days)", ""]
    lines += [_line(i) for i in recent] or ["_(none)_"]
    lines += ["", f"## Top parked ideas (value minus effort)", ""]
    lines += [_line(i) for i in opened[:top]] or ["_(none)_"]
    lines += ["", "## Capture policy", ""] + _policy_lines(v, since, days)
    return "\n".join(lines)
