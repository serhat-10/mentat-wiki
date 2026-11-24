"""One-line status for Claude Code's statusLine. Reads local files only; no model calls."""
import json
import sys

from . import config, util
from .vault import Vault

DIM, YELLOW, RESET = "\x1b[2m", "\x1b[33m", "\x1b[0m"


def _data(stdin_text) -> dict:
    try:
        data = json.loads(stdin_text if isinstance(stdin_text, str) else "")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cwd(stdin_text: str):
    data = _data(stdin_text)
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        ws = data.get("workspace")
        cwd = ws.get("current_dir") if isinstance(ws, dict) else None
    return cwd if isinstance(cwd, str) and cwd else None


def _session(stdin_text: str) -> str:
    """Segment showing this session's id8 (what a capture's origin should say).
    Warns when the folder's recorded slot belongs to another session (two sessions, one folder)."""
    data = _data(stdin_text)
    sid = util._clean_sid(data.get("session_id"))
    if not sid:
        return "🔑 –"
    cwd = _cwd(stdin_text)
    slot = util.recorded_session(cwd) if cwd else ""
    if slot and slot != sid:
        return f"🔑 {sid} {YELLOW}⚠ origin slot {slot}{RESET}"
    return f"🔑 {sid}"


def render(stdin_text: str = "") -> str:
    root = config.vault_root()
    if root is None or not (root / "wiki" / "index.md").exists():
        return f"{DIM}🧠 – · {_session(stdin_text)}{RESET}"
    v = Vault(root)
    project = config.project_for(_cwd(stdin_text))
    today = util.today()
    ev = [e for e in v.events() if e.get("date") == today and e.get("outcome") == "kept"]
    kept = len(ev)
    ideas = sum(1 for e in ev if e.get("type") == "idea")
    pending = len(v.pending())
    inbox = root / "inbox" / "inbox.md"
    waiting = inbox.read_text(encoding="utf-8", errors="replace").count("- [ ]") if inbox.exists() else 0

    if project is None:
        parts = [f"🧠 –"]
    else:
        parts = [f"🧠 {project}"]
    parts.append(f"kept {kept} today" if kept else f"{YELLOW}kept 0 today{RESET}")
    if ideas:
        parts.append(f"💡{ideas}")
    if pending:
        parts.append(f"{YELLOW}❓{pending} to confirm{RESET}")
    if waiting:
        parts.append(f"inbox {waiting}")
    parts.append(_session(stdin_text))
    line = " · ".join(parts)
    return f"{DIM}{line}{RESET}" if project is None else line


def main() -> None:
    try:
        util.utf8_stdio()
        text = "" if sys.stdin.isatty() else sys.stdin.read()
        print(render(text))
    except Exception:  # a status line must never break the UI
        print("🧠")
