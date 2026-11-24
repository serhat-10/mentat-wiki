"""Small helpers: slugs, flat frontmatter, atomic writes, locking, privacy scan."""
import contextlib
import datetime
import hashlib
import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path

_TR = str.maketrans({"ı": "i", "İ": "I", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe",
                     "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})


def utf8_stdio() -> None:
    """Windows consoles default to a legacy codepage; emit UTF-8 when the stream allows it."""
    import sys
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def today() -> str:
    return datetime.date.today().isoformat()


SESSION_TTL = 24 * 3600


def _sessions_path() -> Path:
    # Same folder as the user config (~/.mentat, or MENTAT_CONFIG's folder): per-machine, not in the vault.
    return Path(os.environ.get("MENTAT_CONFIG") or Path.home() / ".mentat" / "config.json").parent / "sessions.json"


def path_key(p) -> str:
    """Stable key for a folder: `~` expanded, symlinks resolved, case folded. One spelling per folder."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(str(p))))


def _cwd_key(cwd) -> str:
    return path_key(cwd)


def _clean_sid(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", value if isinstance(value, str) else "")[:8]


def record_session(session_id, cwd=None, now=None) -> None:
    """Remember the session id for a working folder (shell-independent fallback for MENTAT_SESSION).
    Stores only id8, folder and time. Atomic write, expired entries pruned. Never raises."""
    try:
        sid = _clean_sid(session_id)
        if not sid:
            return
        now = time.time() if now is None else now
        path = _sessions_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data = {k: v for k, v in data.items()
                if isinstance(v, dict) and isinstance(v.get("ts"), (int, float)) and now - v["ts"] <= SESSION_TTL}
        data[_cwd_key(cwd or os.getcwd())] = {"id": sid, "ts": now}
        write_atomic(path, json.dumps(data))
    except Exception:
        pass


def recorded_session(cwd=None, now=None) -> str:
    """Session id recorded for cwd (or its nearest recorded parent folder) in the last 24 h, else ''."""
    try:
        now = time.time() if now is None else now
        data = json.loads(_sessions_path().read_text(encoding="utf-8"))
        here = _cwd_key(cwd or os.getcwd())
        best = None
        for folder, e in data.items():
            if not (here == folder or here.startswith(folder.rstrip(os.sep) + os.sep)):
                continue
            if not isinstance(e, dict) or not isinstance(e.get("ts"), (int, float)):
                continue
            if not 0 <= now - e["ts"] <= SESSION_TTL:
                continue
            if best is None or len(folder) > len(best[0]):
                best = (folder, e)
        return _clean_sid(best[1].get("id")) if best else ""
    except Exception:
        return ""


def default_origin(explicit=None) -> str:
    """Origin for a captured page: --origin wins; else env MENTAT_SESSION, then CLAUDE_SESSION_ID
    (first 8 chars); else the id the SessionStart hook recorded for this folder in the last 24 h;
    else the local capture time as `session:YYYY-MM-DD-HHMM`, so the field is never missing and
    still dates the capture. Limit: two live sessions in the same folder share one slot (last
    SessionStart wins)."""
    if explicit and explicit.strip():
        return explicit
    for var in ("MENTAT_SESSION", "CLAUDE_SESSION_ID"):
        sid = _clean_sid(os.environ.get(var, ""))
        if sid:
            return f"session:{sid}"
    sid = recorded_session()
    if sid:
        return f"session:{sid}"
    return "session:" + datetime.datetime.now().strftime("%Y-%m-%d-%H%M")


def slugify(text: str) -> str:
    """ASCII kebab-case. Accents are stripped (é->e, ö->o); text with no Latin letters gets a stable hash."""
    folded = unicodedata.normalize("NFKD", text.translate(_TR))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")[:60].strip("-")
    device = r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])"
    if re.fullmatch(device, s) or re.match(device + r"\.", folded.strip().lower()):
        return s[:55].rstrip("-") + "-note"
    if s:
        return s
    return "untitled-" + hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:6]


def _scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = re.sub(r"\s+", " ", str(value)).strip()  # one line: no frontmatter injection
    if s.startswith(("-", "?")) or re.search(r"[:#\[\]{}&*!|>'\"%@`]", s):
        return json.dumps(s, ensure_ascii=False)
    return s


def parse_frontmatter(text: str):
    """Return (meta, body). Only flat `key: value` lines are read. CRLF and a UTF-8 BOM are normalised."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
        if not m:
            continue
        val = m.group(2).strip()
        if val.startswith('"'):
            try:
                val = json.JSONDecoder().raw_decode(val)[0]
            except ValueError:
                val = val.strip('"')
        else:
            val = re.sub(r"\s+#.*$", "", val).strip()
            if val.startswith("'") and val.endswith("'") and len(val) > 1:
                val = val[1:-1]
        meta[m.group(1)] = val
    return meta, text[end + 4:].lstrip("\n")


def render_page(meta: dict, body: str) -> str:
    lines = ["---"] + [f"{k}: {_scalar(v)}" for k, v in meta.items()] + ["---", ""]
    return "\n".join(lines) + body.strip() + "\n"


def write_atomic(path: Path, text: str) -> None:
    # On Windows os.replace fails while another process holds the target open (Obsidian, antivirus,
    # a reader), so retry briefly, and never leave temp files behind.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


@contextlib.contextmanager
def lock(state_dir: Path, timeout: float = 10.0):
    """Single-writer lock. Holders finish in milliseconds, so a lock older than 120 s is a crashed
    process; it is broken only if its mtime is unchanged since we looked. Every pass checks the
    timeout and sleeps, so a lock that cannot be removed (open on Windows) never busy-loops."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "lock"
    start = time.time()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                seen = path.stat().st_mtime
                if time.time() - seen > 120 and path.stat().st_mtime == seen:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() - start > timeout:
                raise TimeoutError("vault is locked by another mentat-wiki process")
            time.sleep(0.1)
    try:
        yield
    finally:
        os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass


_PRIVACY = [
    ("API key", r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    ("GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("Stripe live key", r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}"),
    # The API key pattern above also covers OpenAI project keys and Anthropic keys.
    ("Google API key", r"\bAIza[A-Za-z0-9_-]{35}"),
    ("JSON Web Token", r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ("AWS key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer token", r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}"),
    # A keyword that is the whole name (token:) or the tail of a compound name (client_secret=).
    # `max_tokens`, `token_budget` and `tokenizer` are ordinary words, not assignments.
    ("secret assignment",
     r"""(?ix)(?:\b(?:password|passwd|secret|token|api[_-]?key)\b"""
     r"""|[\w.-]+[_.-](?:password|passwd|secret|token|key)\b)"""
     r"""['"]?\s*[:=]\s*['"]?\S{6,}"""),
    ("user home path", r"(?i)(?:\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+|/home/[^/\s]+|/Users/[^/\s]+)"),
]

# RFC 2606 / RFC 6761 names are placeholders in docs, never a real mailbox.
_PLACEHOLDER_TLDS = (".example", ".test", ".invalid", ".localhost")
_PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net")
# A letter-only TLD of 2+ chars: `react@18.2.0` is a version string, not an address.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def _placeholder_email(match, text: str) -> bool:
    """True for docs placeholders and for `git@host:path` SSH remotes (a public remote, no secret)."""
    address = match.group(0)
    domain = address.rpartition("@")[2].lower().rstrip(".")
    if domain.endswith(_PLACEHOLDER_TLDS):
        return True
    if any(domain == d or domain.endswith("." + d) for d in _PLACEHOLDER_DOMAINS):
        return True
    return address.startswith("git@") and text[match.end():match.end() + 1] == ":"


def _has_real_email(text: str) -> bool:
    return any(not _placeholder_email(m, text) for m in _EMAIL.finditer(text))


def privacy_scan(text: str) -> list:
    """Names of sensitive patterns found in text. Empty list means clean."""
    text = text if isinstance(text, str) else str(text)
    hits = ["email address"] if _has_real_email(text) else []
    hits.extend(name for name, pat in _PRIVACY if re.search(pat, text))
    return hits
