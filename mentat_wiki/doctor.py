"""Deterministic vault health checks. No model calls."""
import re
from pathlib import Path

from . import util
from .vault import IDEA_STATUS, Vault

FOLDER_TYPES = {
    "sources": {"source"}, "concepts": {"concept"}, "entities": {"entity"},
    "ideas": {"idea"}, "thoughts": {"thought"}, "outputs": {"output"},
    "projects": {"project-status"},
}
CORE_BUDGET = 2200  # characters; core/ is injected into every session
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# Equal-length backtick runs; a span may cross a line break but not a blank line (CommonMark).
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)\1(?!`)", re.S)


def _tokens(text: str) -> int:
    return len(text) // 4


def _strip_code(text: str) -> str:
    """Text without fenced code blocks and inline code spans, so examples are not read as links.
    Line based: a fence closes on a run of the same character at least as long as the opener.
    CRLF is normalised first."""
    kept, fence = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        if fence is None:
            m = FENCE_OPEN.match(line)
            if m:
                fence = m.group(1)
            else:
                kept.append(line)
            continue
        close = line.strip()
        if (len(line) - len(line.lstrip(" ")) <= 3 and len(close) >= len(fence)
                and set(close) == {fence[0]}):
            fence = None
    return INLINE_CODE.sub("", "\n".join(kept))


def run(v: Vault) -> list:
    """Return a list of (severity, message). Severity: error | warn | info."""
    v.check()
    out = []
    domains = v.domains()
    pages = list(v.pages())
    stems = {p.stem for p in pages}
    paths = {p.relative_to(v.wiki).with_suffix("").as_posix() for p in pages}
    inbound = {p.relative_to(v.wiki).with_suffix("").as_posix(): 0 for p in pages}
    index_text = v.index.read_text(encoding="utf-8-sig", errors="replace")
    indexed_links = set(re.findall(r"^- \[\[([^\]|#]+)", index_text, re.M))

    for p in pages:
        rel = p.relative_to(v.root).as_posix()
        wrel = p.relative_to(v.wiki).with_suffix("").as_posix()
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            out.append(("warn", f"{rel}: not valid UTF-8 (re-save it as UTF-8)"))
            text = raw.decode("utf-8-sig", errors="replace")
        meta, body = util.parse_frontmatter(text)
        if not meta:
            out.append(("error", f"{rel}: no frontmatter"))
            continue
        for key in ("type", "domain", "summary"):
            if not meta.get(key):
                out.append(("warn" if key == "summary" else "error", f"{rel}: missing `{key}`"))
        folder = wrel.split("/")[0]
        if meta.get("type") and folder in FOLDER_TYPES and meta["type"] not in FOLDER_TYPES[folder]:
            out.append(("error", f"{rel}: type `{meta['type']}` does not belong in wiki/{folder}/"))
        if meta.get("domain") and meta["domain"] not in domains:
            out.append(("error", f"{rel}: unknown domain `{meta['domain']}`"))
        if meta.get("type") == "idea":
            for key in ("value", "effort"):
                if not re.fullmatch(r"[1-5]", str(meta.get(key, ""))):
                    out.append(("error", f"{rel}: `{key}` must be 1-5"))
            if meta.get("idea_status") not in IDEA_STATUS:
                out.append(("error", f"{rel}: idea_status must be one of {IDEA_STATUS}"))
        if p.name == "status.md" and _tokens(text) > 500:
            out.append(("warn", f"{rel}: over ~500 tokens, trim it"))
        elif _tokens(text) > 2000:
            out.append(("warn", f"{rel}: over ~1500 words, consider splitting"))
        hits = util.privacy_scan(text)
        if hits:
            out.append(("error", f"{rel}: possible sensitive content ({', '.join(hits)})"))
        for link in re.findall(r"\[\[([^\]|#]+)", _strip_code(text)):
            link = link.strip()
            target = link if link in paths else (link if link in stems else None)
            if target is None:
                out.append(("error", f"{rel}: broken link [[{link}]]"))
            else:
                key = target if target in inbound else next(
                    (k for k in inbound if k.rsplit("/", 1)[-1] == target), None)
                if key and key != wrel:
                    inbound[key] += 1
        indexed = p.stem in indexed_links or wrel in indexed_links
        if not indexed and not (wrel.startswith("projects/") and p.name != "status.md"):
            out.append(("error", f"{rel}: not listed in wiki/index.md"))

    for link in indexed_links:
        if link != "page" and link not in stems and link not in paths:
            out.append(("error", f"wiki/index.md: entry points nowhere [[{link}]]"))
    for key, n in inbound.items():
        if n == 0 and key.split("/")[0] in ("sources", "concepts", "entities"):
            out.append(("warn", f"wiki/{key}.md: orphan (no inbound links besides the index)"))

    core = v.root / "core"
    if core.exists():
        total = sum(len(f.read_text(encoding="utf-8-sig", errors="replace")) for f in core.glob("*.md"))
        sev = "warn" if total > CORE_BUDGET else "info"
        out.append((sev, f"core/ is {total} characters, ~{total // 4} tokens "
                         f"(budget {CORE_BUDGET:,} characters, loaded every session)"))
    inbox = v.root / "inbox" / "inbox.md"
    if inbox.exists():
        n = inbox.read_text(encoding="utf-8-sig", errors="replace").count("- [ ]")  # read-only count
        if n:
            out.append(("info", f"inbox: {n} item(s) waiting for triage"))
    for f in v.root.glob("*.md"):
        if f.stat().st_size == 0:
            out.append(("warn", f"{f.name}: empty file in vault root"))
    out.append(("info", f"{len(pages)} pages checked"))
    from . import installer
    out.extend(installer.check_install())
    return out
