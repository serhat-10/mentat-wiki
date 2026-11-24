"""Vault operations. Code decides the folder and format; the agent supplies content."""
import json
import math
import re
import sys
import time
import uuid
from pathlib import Path

from . import templates, util

TYPE_DIR = {
    "idea": "wiki/ideas",
    "thought": "wiki/thoughts",
    "concept": "wiki/concepts",
    "output": "wiki/outputs",
}
SECTION = {
    "idea": "Ideas",
    "thought": "Thoughts",
    "concept": "Concepts",
    "output": "Outputs",
    "project": "Projects",
}
DEFAULT_DOMAINS = ["engineering", "ai-tools", "research", "academic", "reading", "projects",
                   "hobbies", "other"]
DOMAINS = DEFAULT_DOMAINS  # old name, kept for imports
DOMAIN_BULLET = re.compile(r"^[-*]\s+`?([a-z0-9][a-z0-9-]*)`?\s*:")
IDEA_STATUS = ["parked", "active", "done", "dropped"]
INDEX_SECTIONS = ["Sources", "Concepts", "Entities", "Ideas", "Thoughts", "Projects", "Outputs"]
NONE_YET = "_(none yet)_"


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, root):
        self.root = Path(root)
        self.wiki = self.root / "wiki"
        self.state = self.root / ".mentat"
        self.index = self.wiki / "index.md"
        self.log = self.wiki / "log.md"

    # -- setup ---------------------------------------------------------
    def scaffold(self) -> list:
        """Create folders and any missing template files. Returns created files (relative paths)."""
        for d in ["core", "raw/assets", "inbox", "_templates", *[f"wiki/{s}" for s in
                  ["sources", "concepts", "entities", "ideas", "thoughts", "projects", "outputs"]]]:
            (self.root / d).mkdir(parents=True, exist_ok=True)
        created = templates.install_into(self.root)
        if not self.index.exists():
            body = "\n".join(f"## {s}\n\n{NONE_YET}\n" for s in INDEX_SECTIONS)
            util.write_atomic(self.index, (
                f"---\ntype: index\nupdated: {util.today()}\n---\n\n# Index\n\n"
                "Catalog of every wiki page. Format: `- [[page]]: one-line summary (domain)`.\n\n" + body))
            created.append("wiki/index.md")
        if not self.log.exists():
            util.write_atomic(self.log, (
                "# Log\n\nAppend-only. Format: `## [YYYY-MM-DD] <ingest|query|lint|session> | <title>`\n"))
            created.append("wiki/log.md")
        return created

    def check(self) -> None:
        if not self.index.exists():
            raise VaultError(f"not a vault (no wiki/index.md): {self.root}")

    def domains(self) -> list:
        """Domain names from the `## Domains` bullets in CLAUDE.md, else DEFAULT_DOMAINS."""
        try:
            text = (self.root / "CLAUDE.md").read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return list(DEFAULT_DOMAINS)
        names, inside = [], False
        for line in text.splitlines():
            if line.startswith("## "):
                if inside:
                    break
                inside = line[3:].strip().casefold() == "domains"
                continue
            m = DOMAIN_BULLET.match(line) if inside else None
            if m and m.group(1) not in names:
                names.append(m.group(1))
        found = names or list(DEFAULT_DOMAINS)
        for reserved in ("projects", "other"):  # project pages and the default capture domain
            if reserved not in found:
                found.append(reserved)
        return found

    # -- index and log -------------------------------------------------
    @staticmethod
    def _read(path: Path) -> str:
        """Text with a BOM dropped and CRLF line ends normalised to LF."""
        return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")

    def _index_add(self, section: str, link: str, summary: str, domain: str) -> None:
        lines = self._read(self.index).split("\n")
        entry = f"- [[{link}]]: {summary} ({domain})"
        head = next((i for i, l in enumerate(lines) if l.strip() == f"## {section}"), None)
        if head is None:
            lines += ["", f"## {section}", "", entry, ""]
        else:
            end = next((i for i in range(head + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
            body = [l for l in lines[head + 1:end] if l.strip() != NONE_YET]
            items = [i for i, l in enumerate(body) if l.startswith("- [[")]
            if any(l.startswith(f"- [[{link}]]") for l in body):
                return
            at = items[-1] + 1 if items else 0
            body.insert(at, entry)
            while body and body[0].strip() == "":
                body.pop(0)
            while body and body[-1].strip() == "":
                body.pop()
            lines[head + 1:end] = [""] + body + [""]
        util.write_atomic(self.index, "\n".join(lines))

    def append_log(self, kind: str, title: str, note: str = "") -> None:
        text = self._read(self.log).rstrip("\n")
        text += f"\n\n## [{util.today()}] {kind} | {title}\n"
        if note:
            text += note.strip() + "\n"
        util.write_atomic(self.log, text)

    # -- feedback ledger and pending proposals --------------------------
    def record(self, **event) -> None:
        event = {"ts": int(time.time()), "date": util.today(), **event}
        self.state.mkdir(parents=True, exist_ok=True)
        with open(self.state / "feedback.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def events(self) -> list:
        p = self.state / "feedback.jsonl"
        out = []
        if p.exists():
            for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        out.append(event)
                except ValueError:
                    continue
        return out

    OUTCOMES = ("kept", "edited", "rejected", "ignored")
    _QUOTES = "\"'`\u201c\u201d\u2018\u2019\u00ab\u00bb"

    @staticmethod
    def title_key(title) -> str:
        """Title as matched between a proposal and its answer: casefold, one space, no outer quotes."""
        return " ".join(str(title or "").strip(Vault._QUOTES + " \t\r\n").split()).casefold()

    @staticmethod
    def _age(item, now) -> float:
        ts = item.get("ts")
        if type(ts) not in (int, float) or (isinstance(ts, float) and not math.isfinite(ts)):
            return float("inf")
        try:
            return now - ts
        except OverflowError:
            return float("-inf") if ts > now else float("inf")

    def _load_pending(self, *, recover=False) -> list:
        """Every stored proposal. Only a caller holding the writer lock may recover the queue."""
        path = self.state / "pending.json"
        try:
            items = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(items, list):
                raise ValueError("expected a proposal list")
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            if recover:
                if not path.is_file():
                    raise
                name = path.name + time.strftime(".bad-%Y%m%d-%H%M%S")
                backup = path.with_name(name)
                suffix = 1
                while backup.exists():
                    backup = path.with_name(f"{name}-{suffix}")
                    suffix += 1
                path.rename(backup)
                print(f"mentat-wiki: saved unreadable pending.json as {backup.name}; starting a fresh queue.",
                      file=sys.stderr)
                self._set_pending([])
            return []
        return [p for p in items if isinstance(p, dict)]

    _POLICY_AGE = object()

    def pending(self, max_age_hours=_POLICY_AGE) -> list:
        """Read open proposals within the configured age limit. None includes expired items."""
        if max_age_hours is self._POLICY_AGE:
            max_age_hours = self._expiry_hours()
        now = time.time()
        return [p for p in self._load_pending() if p.get("state") != "edited"
                and (max_age_hours is None or self._age(p, now) < max_age_hours * 3600)]

    def _set_pending(self, items: list) -> None:
        util.write_atomic(self.state / "pending.json", json.dumps(items, ensure_ascii=False))

    def _expiry_hours(self) -> float:
        from . import policy
        return policy.load(self)["expiry_hours"]

    def _match(self, items, type_, titles):
        for title in titles:
            key = self.title_key(title)
            for p in items:
                if key and p.get("type") == type_ and self.title_key(p.get("title")) == key:
                    return p
        return None

    def sweep_expired(self, now=None) -> int:
        """Reconcile pending proposals with the ledger and expire unanswered ones."""
        if not (self.state / "pending.json").exists():
            return 0
        with util.lock(self.state):
            _, _, removed = self._prepare(now=now)
            return removed

    def _prepare(self, type_=None, titles=(), capture=False, now=None):
        """Under the writer lock, recover interrupted writes and select one answerable proposal."""
        items = self._load_pending(recover=True)
        if not items:
            return items, None, 0
        upgraded = False
        for p in items:
            if not isinstance(p.get("id"), str) or not p["id"]:
                p["id"] = uuid.uuid4().hex[:12]
                upgraded = True
            if p.get("state") not in ("open", "edited"):
                p["state"] = "open"
                upgraded = True
        if upgraded:
            self._set_pending(items)  # Persist legacy identities before appending any outcomes.

        outcomes = {e["proposal"]: e for e in self.events()
                    if isinstance(e.get("proposal"), str) and e.get("outcome") in self.OUTCOMES}
        now = time.time() if now is None else now
        limit = self._expiry_hours() * 3600
        expired = {p["id"] for p in items if self._age(p, now) >= limit}
        changed = False
        for p in items:
            event = outcomes.get(p["id"])
            if event and event.get("awaiting_capture") and p["state"] == "open":
                p["state"] = "edited"
                changed = True

        # A delayed capture can still consume its edited item during this sweep.
        candidates = [p for p in items if (capture and p["state"] == "edited") or
                      (p["state"] == "open" and p["id"] not in expired and p["id"] not in outcomes)]
        hit = self._match(candidates, type_, titles)
        active = []
        for p in items:
            recorded = p["id"] in outcomes
            if p is hit:
                active.append(p)
            elif p["id"] in expired:
                if p["state"] == "open" and not recorded:
                    self.record(type=p.get("type"), title=p.get("title"), outcome="ignored",
                                via="proposal", proposal=p["id"])
                    outcomes[p["id"]] = {"outcome": "ignored"}
            elif not recorded or p["state"] == "edited":
                active.append(p)
        removed = len(items) - len(active)
        if changed or removed:
            self._set_pending(active)
        return active, hit, removed

    def _answer(self, items, hit, type_, title, outcome, awaiting_capture=False, **extra):
        """Append at most one terminal outcome per identity while holding the writer lock."""
        if hit is None:
            self.record(type=type_, title=title, outcome=outcome, via="explicit", **extra)
            return
        if hit["state"] == "open" and not any(
                e.get("proposal") == hit["id"] and e.get("outcome") in self.OUTCOMES
                for e in self.events()):
            if awaiting_capture:
                extra["awaiting_capture"] = True
            self.record(type=type_, title=title, outcome=outcome, via="proposal",
                        proposal=hit["id"], **extra)
        if awaiting_capture:
            hit["state"] = "edited"
        else:
            items.remove(hit)
        self._set_pending(items)

    def _guard(self, *texts) -> None:
        """Refuse before any write if a user-supplied string looks sensitive."""
        hits = util.privacy_scan("\n".join(str(t) for t in texts if t))
        if hits:
            raise VaultError(f"refused, possible sensitive content ({', '.join(hits)}). Redact and retry.")

    def propose(self, type_: str, title: str) -> None:
        self._guard(title)
        with util.lock(self.state):
            items, hit, _ = self._prepare(type_, (title,))
            key = self.title_key(title)
            items = [p for p in items if not (p["state"] == "edited" and p.get("type") == type_
                                              and self.title_key(p.get("title")) == key)]
            if hit is None:
                hit = {"id": uuid.uuid4().hex[:12], "type": type_, "title": title, "state": "open"}
                items.append(hit)
            hit["ts"] = int(time.time())
            self._set_pending(items)

    def feedback(self, type_: str, title: str, outcome: str, **extra) -> None:
        """Record the answer to a proposal (or an explicit outcome when nothing matches)."""
        if outcome not in self.OUTCOMES:
            raise VaultError(f"outcome must be one of {list(self.OUTCOMES)}")
        self._guard(title)
        with util.lock(self.state):
            items, hit, _ = self._prepare(type_, (title,))
            self._answer(items, hit, type_, title, outcome, awaiting_capture=outcome == "edited", **extra)

    # -- capture ---------------------------------------------------------
    def keep(self, type_, title, summary, body="", domain=None, project=None, origin=None,
             auto=False, value=3, effort=3, est_days=None, edited=False) -> Path:
        self.check()
        if type_ not in TYPE_DIR:
            raise VaultError(f"type must be one of {sorted(TYPE_DIR)}; use `inbox` for unclear items")
        domain = domain or ("projects" if project else "other")
        if domain not in self.domains():
            raise VaultError(f"domain must be one of {self.domains()} (see ## Domains in CLAUDE.md)")
        summary = " ".join(summary.split()).replace("[[", "[").replace("]]", "]")
        title = " ".join(title.split())
        origin = " ".join(origin.split()) if origin else origin
        est_days = " ".join(str(est_days).split()) if est_days is not None else None
        if not summary:
            raise VaultError("summary is required (one line)")
        self._guard(title, summary, body, origin, est_days, project)
        if type_ == "idea":
            if not (1 <= int(value) <= 5 and 1 <= int(effort) <= 5):
                raise VaultError("value and effort must be 1-5")
        with util.lock(self.state):
            items, hit, _ = self._prepare(type_, () if auto else (title,), capture=True)
            slug, path = self._unique_slug(type_, title)
            meta = {"type": type_, "domain": domain, "created": util.today(),
                    "updated": util.today(), "summary": summary}
            if type_ == "idea":
                meta.update(value=int(value), effort=int(effort), est_days=est_days,
                            idea_status="parked")
            if project:
                meta["project"] = project
            if origin:
                meta["origin"] = origin
            meta.update(auto=bool(auto), status="draft")
            util.write_atomic(path, util.render_page(meta, f"# {title.strip()}\n\n{body.strip()}"))
            self._index_add(SECTION[type_], slug, summary, domain)
            self._answer(items, hit, type_, title, "edited" if edited else "kept",
                         auto=bool(auto), domain=domain, project=project)
        return path

    def _unique_slug(self, type_: str, title: str):
        """Filename unique across the whole wiki, since Obsidian resolves [[name]] by name. The same
        title in the same folder is a duplicate and refused; another title that slugs the same gets -2."""
        base = util.slugify(title)
        folder = self.root / TYPE_DIR[type_]
        for n in range(1, 50):
            slug = base if n == 1 else f"{base[:56]}-{n}"
            hits = list(self.wiki.rglob(f"{slug}.md"))
            if not hits:
                return slug, folder / f"{slug}.md"
            for h in hits:
                m = re.search(r"^#\s+(.+)$", h.read_text(encoding="utf-8-sig", errors="replace"), re.M)
                if h.parent == folder and m and " ".join(m.group(1).split()).casefold() == title.casefold():
                    raise VaultError(f"already exists: {h.relative_to(self.root).as_posix()}. "
                                     "Update that page instead.")
        raise VaultError("could not find a free filename for this title")

    def inbox_add(self, line: str) -> Path:
        self.check()
        line = " ".join(line.split())
        hits = util.privacy_scan(line)
        if hits:
            raise VaultError(f"refused, possible sensitive content ({', '.join(hits)}).")
        path = self.root / "inbox" / "inbox.md"
        with util.lock(self.state):
            text = path.read_text(encoding="utf-8-sig") if path.exists() else "# Inbox\n\nOne line per item. Triage weekly.\n\n"
            util.write_atomic(path, text.rstrip("\n") + f"\n- [ ] {util.today()} {line}\n")
            self.record(type="inbox", title=line[:60], outcome="kept")
        return path

    # -- projects --------------------------------------------------------
    def project_dir(self, name: str) -> Path:
        return self.wiki / "projects" / util.slugify(name)

    def register_project(self, name: str) -> Path:
        self.check()
        slug = util.slugify(name)
        d = self.project_dir(slug)
        if d.exists():
            return d
        t = util.today()
        head = lambda summary: (f"---\ntype: project-status\ndomain: projects\nsummary: {summary}\n"
                                f"updated: {t}\n---\n\n")
        with util.lock(self.state):
            util.write_atomic(d / "status.md", head(f"Current status of {slug}") + (
                f"# {slug}: status\n\n## Where we left off\n_(nothing recorded yet)_\n\n"
                f"## Next step\n- \n\nSee [[projects/{slug}/decisions]] and [[projects/{slug}/open-threads]].\n"))
            util.write_atomic(d / "decisions.md", head(f"Decision log for {slug}") + (
                f"# {slug}: decisions\n\nAppend only. One row per decision.\n\n"
                "| Date | Decision | Why | Rejected alternatives | Origin |\n|---|---|---|---|---|\n"))
            util.write_atomic(d / "open-threads.md", head(f"Open questions and next steps for {slug}") + (
                f"# {slug}: open threads\n\nRewrite as threads open and close. Keep under ~300 words.\n\n- [ ] \n"))
            self._index_add("Projects", f"projects/{slug}/status", f"Status of {slug}", "projects")
        return d

    def projects(self) -> list:
        """Slugs of projects in the vault (folders under wiki/projects with a status.md)."""
        base = self.wiki / "projects"
        return sorted(p.parent.name for p in base.glob("*/status.md")) if base.is_dir() else []

    def _project(self, name: str) -> Path:
        d = self.project_dir(name)
        if not (d / "status.md").exists():
            known = ", ".join(self.projects()) or "none"
            raise VaultError(f"project not registered in vault: {name}. Known projects: {known}. "
                             "Run `mentat-wiki project register`.")
        return d

    def decide(self, project, decision, why="", rejected="", origin="", title=None, edited=False,
               auto=False) -> None:
        self.check()
        d = self._project(project)
        cells = [util.today(), decision, why, rejected, origin]
        self._guard(*cells, title)
        row = "| " + " | ".join(" ".join(c.split()).replace("|", "/") for c in cells) + " |"
        path = d / "decisions.md"
        name = (title or decision)[:60]
        with util.lock(self.state):
            items, hit, _ = self._prepare("decision", () if auto else (title, decision), capture=True)
            util.write_atomic(path, path.read_text(encoding="utf-8-sig").rstrip("\n") + "\n" + row + "\n")
            self._answer(items, hit, "decision", name, "edited" if edited else "kept",
                         project=project, auto=bool(auto))

    def wrap(self, project, where, next_step="", threads=None) -> None:
        self.check()
        d = self._project(project)
        slug = d.name
        hits = util.privacy_scan(" ".join([where, next_step, *(threads or [])]))
        if hits:
            raise VaultError(f"refused, possible sensitive content ({', '.join(hits)}).")
        t = util.today()
        head = lambda summary: (f"---\ntype: project-status\ndomain: projects\nsummary: {summary}\n"
                                f"updated: {t}\n---\n\n")
        nxt = f"- {next_step.strip()}\n" if next_step.strip() else "- \n"
        with util.lock(self.state):
            util.write_atomic(d / "status.md", head(f"Current status of {slug}") + (
                f"# {slug}: status\n\n## Where we left off\n{where.strip()}\n\n## Next step\n{nxt}\n"
                f"See [[projects/{slug}/decisions]] and [[projects/{slug}/open-threads]].\n"))
            if threads is not None:
                items = "".join(f"- [ ] {x.strip()}\n" for x in threads) or "- [ ] \n"
                util.write_atomic(d / "open-threads.md", head(f"Open questions and next steps for {slug}") + (
                    f"# {slug}: open threads\n\nRewrite as threads open and close. Keep under ~300 words.\n\n{items}"))
            self.append_log("session", f"{slug}: wrap", where.strip().split("\n")[0][:200])
            self.record(type="wrap", title=slug, outcome="kept", project=slug)

    # -- experiment notes and handover -----------------------------------
    def note(self, project, text, result="info") -> Path:
        """Append one line to the project's experiments.md. Instant, so nothing is lost if the
        session dies before /wrap."""
        self.check()
        d = self._project(project)
        text = " ".join(text.split())
        if not text:
            raise VaultError("note text is required")
        if result not in ("worked", "failed", "info"):
            raise VaultError("result must be worked, failed or info")
        self._guard(text)
        p = d / "experiments.md"
        with util.lock(self.state):
            if p.exists():
                try:
                    body = self._read(p).rstrip("\n")
                except UnicodeDecodeError as e:
                    raise VaultError(f"re-save {p.name} as UTF-8 before adding a note") from e
                body = re.sub(r"(?m)^updated: .*$", f"updated: {util.today()}", body, count=1)
            else:
                body = (f"---\ntype: project-status\ndomain: projects\nsummary: Experiment log for {d.name}\n"
                        f"updated: {util.today()}\n---\n\n# {d.name}: experiments\n\n"
                        "One line per attempt, newest last: what was tried (command, parameters, output "
                        "path) and what happened. Failures count.\n")
            stamp = time.strftime("%Y-%m-%d %H:%M")
            util.write_atomic(p, body + f"\n- {stamp} [{result}] {text}\n")
            self.record(type="note", title=text[:60], outcome="kept", result=result, project=d.name)
        return p

    def tail(self, path: Path, prefix: str, n: int) -> list:
        """Last n lines of a file that start with prefix."""
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        return [l for l in lines if l.startswith(prefix)][-n:]

    def handover(self, project, max_chars=3500) -> str:
        """A paste-ready prompt to continue the project in any tool. Read-only."""
        self.check()
        d = self._project(project)

        def body(name):
            f = d / name
            if not f.exists():
                return ""
            return util.parse_frontmatter(f.read_text(encoding="utf-8-sig", errors="replace"))[1].strip()

        status = re.sub(r"\n*See \[\[.*$", "", body("status.md"), flags=re.S)
        status = re.sub(r"^# .*\n+", "", status).strip()
        notes = self.tail(d / "experiments.md", "- ", 10)
        threads = [l for l in self.tail(d / "open-threads.md", "- [ ]", 10) if len(l.strip()) > 6]
        rows = []
        for l in self.tail(d / "decisions.md", "| 20", 5):
            cells = [c.strip() for c in l.strip("|").split("|")]
            rows.append(f"- {cells[0]}: {cells[1]}" + (f" (why: {cells[2]})" if len(cells) > 2 and cells[2] else ""))
        parts = [f"# Handover: {d.name}",
                 "Continue this project from where the last session stopped. The context below comes from "
                 "my notes; trust it, but verify anything you rely on before acting.",
                 status]
        if notes:
            parts += ["## Recent experiment notes", "\n".join(notes)]
        if threads:
            parts += ["## Open threads", "\n".join(threads)]
        if rows:
            parts += ["## Recent decisions", "\n".join(rows)]
        parts.append("Start by restating where we are in two lines, then propose the next step.")
        text = "\n\n".join(p for p in parts if p)
        if len(text) > max_chars:
            text = text[:max_chars].rsplit("\n", 1)[0] + "\n[truncated]"
        return text

    # -- pages -----------------------------------------------------------
    def pages(self):
        """All content pages (excludes index and log)."""
        for p in sorted(self.wiki.rglob("*.md")):
            if p.name in ("index.md", "log.md") and p.parent == self.wiki:
                continue
            yield p


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))
