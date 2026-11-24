"""Per-folder session checkpoints, so a session that ended without /wrap (power loss, closed window)
can be found again. Stored in ~/.mentat/checkpoints.json next to sessions.json: per-machine, outside the
vault. Holds ids, a transcript path, timestamps and a count only, never prompt text.
Whether a session was wrapped is decided by comparing its last activity with the project's last `wrap`
event in the vault feedback log (no flag to keep in sync)."""
import json
import os
import re
import time
from pathlib import Path

from . import util

TTL = 7 * 24 * 3600
KEEP = 5


def _path() -> Path:
    return util._sessions_path().with_name("checkpoints.json")


def clean_sid(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", value if isinstance(value, str) else "")[:64]


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(data, now=None) -> None:
    """Called by the per-prompt hook with its stdin JSON. Never raises."""
    try:
        if not isinstance(data, dict):
            return
        sid = clean_sid(data.get("session_id"))
        if not sid:
            return
        now = time.time() if now is None else now
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else os.getcwd()
        folder = util._cwd_key(cwd)
        clean = {}
        for f, sessions in _load().items():
            if not isinstance(sessions, dict):
                continue
            kept = {k: v for k, v in sessions.items()
                    if isinstance(v, dict) and isinstance(v.get("ts"), (int, float)) and 0 <= now - v["ts"] <= TTL}
            if kept:
                clean[f] = kept
        sessions = clean.setdefault(folder, {})
        prev = sessions.get(sid, {})
        n = prev.get("n", 0)
        entry = {"id": sid[:8], "ts": now, "n": (n if isinstance(n, int) else 0) + 1}
        tp = data.get("transcript_path")
        if isinstance(tp, str) and tp:
            entry["tp"] = tp[:400]
        elif prev.get("tp"):
            entry["tp"] = prev["tp"]
        sessions[sid] = entry
        if len(sessions) > KEEP:
            for k in sorted(sessions, key=lambda k: sessions[k]["ts"])[:len(sessions) - KEEP]:
                del sessions[k]
        util.write_atomic(_path(), json.dumps(clean))
    except Exception:
        pass


def latest(cwd=None, exclude=None, now=None):
    """Most recent checkpoint for cwd (or its nearest checkpointed parent folder) within 7 days, skipping
    the session id `exclude`. Returns {"sid", "id", "ts", "n", "tp"} or None."""
    try:
        now = time.time() if now is None else now
        here = util._cwd_key(cwd or os.getcwd())
        best = None
        for folder, sessions in _load().items():
            if not (here == folder or here.startswith(folder.rstrip(os.sep) + os.sep)):
                continue
            if not isinstance(sessions, dict):
                continue
            for sid, e in sessions.items():
                if not isinstance(e, dict) or not isinstance(e.get("ts"), (int, float)):
                    continue
                if not 0 <= now - e["ts"] <= TTL or (exclude and sid == exclude):
                    continue
                key = (len(folder), e["ts"])
                if best is None or key > best[0]:
                    best = (key, {"sid": sid, "id": e.get("id", sid[:8]), "ts": e["ts"],
                                  "n": e.get("n", 0), "tp": e.get("tp", "")})
        return best[1] if best else None
    except Exception:
        return None


def last_wrap_ts(vault, project) -> float:
    """Timestamp of the project's last wrap event, 0 when never wrapped."""
    try:
        return max([e["ts"] for e in vault.events()
                    if e.get("type") == "wrap" and (not project or e.get("project") == project)
                    and isinstance(e.get("ts"), (int, float))] or [0])
    except Exception:
        return 0


def stamp(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
