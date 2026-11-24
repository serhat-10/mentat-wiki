import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import __version__, checkpoint, config, digest, doctor, installer, search, statusline, util
from .vault import DOMAINS, TYPE_DIR, Vault, VaultError

PROPOSAL_TYPES = ["decision", "idea", "thought", "concept", "output"]


def _vault() -> Vault:
    root = config.vault_root()
    if root is None:
        raise VaultError("no vault configured. Run `mentat-wiki config --vault <path>`.")
    v = Vault(root)
    v.check()
    return v


def _project(args, v: Vault = None) -> str:
    name = getattr(args, "project", None) or config.project_for(os.getcwd())
    if not name:
        known = ", ".join(v.projects()) if v else ""
        raise VaultError("no project for this folder: pass --project <name>"
                         + (f" (known: {known})" if known else "")
                         + " or register this folder with `mentat-wiki project register`.")
    return util.slugify(name)


def _body(args) -> str:
    if args.body == "-":
        return sys.stdin.read()
    return args.body or ""


def cmd_config(a):
    cfg = config.load()
    if a.vault:
        root = Path(a.vault).expanduser().resolve()
        cfg["vault"] = str(root)
    if a.command is not None:
        if a.command.strip():
            cfg["command"] = a.command.strip()
        else:
            cfg.pop("command", None)
    if a.vault or a.command is not None:
        config.save(cfg)
    print(f"vault: {cfg.get('vault', '(not set)')}")
    print(f"command: {config.command()}")


def cmd_init(a):
    v = Vault(Path(a.path).expanduser().resolve())
    created = v.scaffold()
    cmd = config.command()
    print(f"vault ready: {v.root}")
    if created:
        print("created:")
        for rel in created:
            print(f"  {rel}")
    else:
        print("vault already initialised, nothing created")
    cfg = config.load()
    old = cfg.get("vault")
    if not old:
        cfg["vault"] = str(v.root)
        config.save(cfg)
        print(f"config vault set to {v.root}")
    elif util.path_key(old) != util.path_key(v.root):
        new = f'"{v.root}"' if " " in str(v.root) else str(v.root)
        print(f"config vault stays {old}; run {cmd} config --vault {new} to switch")
    print("next steps:")
    print(f"  {cmd} install claude")
    print(f"  {cmd} project register <name>   (run it from a working folder)")


def cmd_project(a):
    v = _vault()
    if a.action == "register":
        folder = Path(a.path or os.getcwd()).expanduser().resolve()
        if util.path_key(folder) == util.path_key(v.root):
            raise VaultError("the vault folder itself is not a project (sessions there already get "
                             "the vault context); run this from a working folder or pass --path")
        name = util.slugify(a.name or folder.name)
        if not name:
            raise VaultError("could not derive a project name from the folder; pass one")
        if not a.name:
            folder_key = util.path_key(folder)
            registered = [path for path, project in config._projects(config.load()).items() if project == name]
            if registered and all(util.path_key(path) != folder_key for path in registered):
                raise VaultError(
                    f'project "{name}" is already registered for {registered[0]}. Pass another name '
                    f'(mentat-wiki project register <name>), or pass "{name}" explicitly to share it '
                    '(for example a worktree of the same repo).')
        v.register_project(name)
        config.register(folder, name)
        print(f"project {name} <- {folder}")
    else:
        for folder, name in sorted(config._projects(config.load()).items()):
            print(f"{name}\t{folder}")


def cmd_keep(a):
    v = _vault()
    project = getattr(a, "project", None) or config.project_for(os.getcwd())
    path = v.keep(a.type, a.title, a.summary, _body(a), domain=a.domain,
                  project=util.slugify(project) if project else None, origin=util.default_origin(a.origin),
                  auto=a.auto, value=a.value, effort=a.effort, est_days=a.est_days, edited=a.edited)
    print(f"kept {path.relative_to(v.root).as_posix()}")


def cmd_inbox(a):
    v = _vault()
    print(f"added to {v.inbox_add(a.text).relative_to(v.root).as_posix()}")


def cmd_decide(a):
    v = _vault()
    v.decide(_project(a, v), a.decision, a.why, a.rejected, util.default_origin(a.origin),
             title=a.title, edited=a.edited, auto=a.auto)
    print("decision recorded")


def cmd_wrap(a):
    v = _vault()
    v.wrap(_project(a, v), a.where, a.next or "", a.thread)
    print("status updated")


def cmd_note(a):
    v = _vault()
    p = v.note(_project(a, v), a.text, a.result)
    print(f"noted in {p.relative_to(v.root).as_posix()}")


def cmd_handover(a):
    v = _vault()
    print(v.handover(_project(a, v), a.max_chars))


def cmd_propose(a):
    _vault().propose(a.type, a.title)
    print("pending")


def cmd_feedback(a):
    _vault().feedback(a.type, a.title, a.outcome)
    print("recorded")


def cmd_find(a):
    v = _vault()
    if a.ideas:
        for path, title, summary, value, effort in search.ideas(v, a.limit):
            print(f"{path} | v{value} e{effort} | {title}: {summary}")
        return
    rows = search.find(v, a.query, a.type, a.limit)
    for path, type_, domain, title, summary in rows:
        print(f"{path} | {type_} | {title}: {summary}")
    if not rows:
        print("no matches")


def cmd_doctor(a):
    issues = doctor.run(_vault())
    order = {"error": 0, "warn": 1, "info": 2}
    for sev, msg in sorted(issues, key=lambda x: order[x[0]]):
        print(f"{sev.upper():5} {msg}")
    sys.exit(1 if any(s == "error" for s, _ in issues) else 0)


def cmd_digest(a):
    print(digest.build(_vault(), a.days, a.top))


def cmd_status_line(a):
    statusline.main()


def cmd_hook(a):
    from . import hook
    hook.main()


PROTOCOL = (
    "Mentat capture protocol. Log decisions the user makes or approves directly with "
    "`{cmd} decide --decision ... --why ... --rejected ...`. When any other durable item comes up (a "
    "decision you would record on your own, an idea worth a day, reusable knowledge, a thought), do not "
    "offer it in prose. Run `{cmd} propose --type <decision|idea|thought|concept|output> --title "
    "\"<title>\"`, then ask ONE line: Keep as <type> \"<title>\"? "
    "Yes: decision -> `{cmd} decide --title \"<title>\" --decision ... --why ... --rejected ...`; "
    "other types -> `{cmd} keep --type <type> --title \"<title>\" ...` (the /keep skill in Claude Code). "
    "Add `--edited` when the user changed it. "
    "No: `{cmd} feedback --type <type> --title \"<title>\" --outcome rejected`. "
    "No answer: leave it; it expires as ignored. "
    "Follow the capture policy below (ask, auto, never). Never capture secrets or personal data. "
    "Near the end of a session suggest /wrap (or `{cmd} wrap`). When trying something that may fail, "
    "log each attempt right away in one line with the command, a relative output path and the result: "
    "`{cmd} note --result worked|failed|info \"<text>\"`."
)


def protocol() -> str:
    """The capture protocol with this machine's mentat-wiki command filled in."""
    cmd = config.command()
    text = PROTOCOL.replace("{cmd}", cmd)
    if cmd != "mentat-wiki":
        text += f" On this machine the command is `{cmd}`; use it wherever a skill or doc says `mentat-wiki` or `mentat`."
    return text


def _read_stdin_json(timeout=2.0):
    """Hook JSON from stdin, or None. Reads in a daemon thread so a manual run on a pipe never hangs."""
    import threading
    if sys.stdin is None or sys.stdin.isatty():
        return None
    box = []

    def run():
        try:
            box.append(json.loads(sys.stdin.read() or "null"))
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return box[0] if box else None


def _persist_session():
    """SessionStart hook: save the session id so captures get a real origin.
    Two channels: an `export` line in CLAUDE_ENV_FILE (when Claude Code sets it; not under PowerShell hooks),
    and sessions.json keyed by cwd (shell-independent, read by util.default_origin).
    Never raises, never prints. Stores id8 and folder only, never prompt text.
    Returns the hook JSON (a dict) or None."""
    data = None
    try:
        data = _read_stdin_json()
        if not isinstance(data, dict):
            return None
        sid = re.sub(r"[^A-Za-z0-9_-]", "", data.get("session_id") if isinstance(data.get("session_id"), str) else "")[:8]
        if not sid:
            return data
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else None
        util.record_session(sid, cwd)
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            with open(env_file, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"export MENTAT_SESSION={sid}\n")
    except Exception:
        pass
    return data if isinstance(data, dict) else None


def _sync_index():
    """Refresh the FTS index once per session so the read-only per-prompt hook sees current pages."""
    try:
        v = _vault()
        search.sync(v)
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise


def _unwrapped_line(v, project, cwd, current_sid):
    """One line when the previous session in this folder has activity after the project's last wrap."""
    prev = checkpoint.latest(cwd, exclude=current_sid)
    if not prev or checkpoint.last_wrap_ts(v, project) >= int(prev["ts"]):
        return ""
    return (f"Last session ended without /wrap ({prev['id']}, {checkpoint.stamp(prev['ts'])}); "
            f"resume: claude --resume {prev['sid']} or run `{config.command()} resume`.")


def _vault_folder_line(v: Vault, cwd) -> str:
    """In the vault folder itself (no registered project), remind the agent to pass --project."""
    if config.in_vault(cwd, v.root):
        known = ", ".join(v.projects()) or "none"
        return f"Vault folder: no project. Pass --project <name> to decide, wrap and note; known projects: {known}."
    return ""


def cmd_resume(a):
    folder = os.path.abspath(a.folder or os.getcwd())
    project = config.project_for(folder)
    cp = checkpoint.latest(folder)
    if not cp:
        print(f"## Resume\nNo session checkpoint for {folder} in the last 7 days. "
              "Try `claude --continue` or `claude --resume`.")
        return
    out = [f"## Resume: {project or folder}",
           f"- Last session: {cp['id']}, last active {checkpoint.stamp(cp['ts'])} ({cp['n']} prompts)"]
    v = None
    try:
        v = _vault()
    except VaultError:
        pass
    if v:
        w = checkpoint.last_wrap_ts(v, project)  # no project: the latest wrap of any project
        scope = "" if project else " (any project)"
        out.append(f"- Wrapped after it{scope}: yes ({checkpoint.stamp(w)})" if w >= int(cp["ts"])
                   else f"- Wrapped after it{scope}: NO, the session ended without /wrap")
    else:
        out.append("- Wrapped after it: unknown (no vault)")
    out.append(f"- Resume: `claude --resume {cp['sid']}`")
    try:
        import subprocess
        r = subprocess.run(["git", "-C", folder, "status", "--short"], capture_output=True, text=True,
                           timeout=3, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            out.append(f"- Git: {len([l for l in r.stdout.splitlines() if l.strip()])} changed files")
    except Exception:
        pass
    if v and project and (v.project_dir(project) / "status.md").exists():
        d = v.project_dir(project)
        _, st = util.parse_frontmatter((d / "status.md").read_text(encoding="utf-8-sig", errors="replace"))
        m = re.search(r"## Where we left off\n(.*?)(?=\n## |\Z)", st, re.S)
        if m and m.group(1).strip():
            out += ["", "Where we left off (last /wrap):", m.group(1).strip()[:600]]
        if (d / "open-threads.md").exists():
            threads = [l[6:].strip()[:100] for l in v.tail(d / "open-threads.md", "- [ ]", 5) if len(l.strip()) > 6]
            if threads:
                out += ["", "Open threads:"] + [f"- {t}" for t in threads]
    print("\n".join(out))


def cmd_context(a):
    data = _persist_session()
    current = checkpoint.clean_sid((data or {}).get("session_id"))
    _sync_index()
    cwd = a.cwd or config.hook_cwd(data or {})
    cfg = config.load()
    if not isinstance(cfg, dict) or any(cfg.get(k) is not None and not isinstance(cfg[k], str)
                                        for k in ("vault", "command")):
        raise VaultError("invalid vault configuration")
    project = config.project_for(cwd) if isinstance(cfg.get("projects"), dict) else None
    if not isinstance(project, str):
        project = None
    v = _vault()
    try:  # housekeeping: a lock timeout (another session starting) must not cost this session its context
        v.sweep_expired()
    except (OSError, TimeoutError, ValueError, VaultError):
        pass
    vault_line = "" if project else _vault_folder_line(v, cwd)
    if not project and not vault_line and not a.always:
        return  # unregistered folder: no context, spend no tokens
    parts = [protocol() + " Domains: " + ", ".join(v.domains()) + "."]

    def optional_text(path):
        try:
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return ""

    files = sorted((v.root / "core").glob("*.md"))
    if project:
        d = v.project_dir(project)
        files.extend((d / "status.md", d / "open-threads.md"))
    for f in files:
        _, body = util.parse_frontmatter(optional_text(f))
        if body.strip():
            parts.append(body.strip())
    if project:
        recent = [line for line in optional_text(d / "experiments.md").splitlines() if line.startswith("- ")][-6:]
        if recent:
            parts.append("Recent experiment notes:\n" + "\n".join(recent))
    else:
        parts.append(vault_line or "(no project registered for this folder)")
    text = "\n\n---\n\n".join(parts)
    if len(text) > a.max_chars:
        text = text[:a.max_chars] + "\n[truncated]"
    if project or vault_line:
        try:
            extra = _unwrapped_line(v, project, cwd, current)
        except Exception:  # optional line; never drop the whole context for it
            extra = ""
        if extra:
            text += "\n\n" + extra
    try:
        from . import policy
        for r in policy.report(v):
            if r.get("eligible"):
                text += (f"\n\nCapture policy: {r['category']} qualifies for auto "
                         f"({r['proposed']} proposals, {policy.pct(r['acceptance'])} accepted); "
                         "suggest it once.")
    except Exception:  # optional line, same rule
        pass
    print(text)


def build_parser():
    p = argparse.ArgumentParser(prog="mentat-wiki", description="Project continuity for LLM coding agents, kept in a local Markdown wiki.")
    p.add_argument("--version", action="version", version=f"mentat-wiki {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    installer.add_parser(sub)

    s = sub.add_parser("config", help="show or set the vault path and the mentat-wiki command")
    s.add_argument("--vault")
    s.add_argument("--command", help="how agents run mentat-wiki here (default `mentat-wiki`; empty string resets), "
                                     "e.g. \"python -m mentat_wiki\" when the script is not on PATH")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("init", help="create a new empty vault")
    s.add_argument("path")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("project", help="register a working folder as a project, or list")
    s.add_argument("action", choices=["register", "list"])
    s.add_argument("name", nargs="?", help="project name (default: the folder's name)")
    s.add_argument("--path")
    s.set_defaults(fn=cmd_project)

    s = sub.add_parser("keep", help="file an idea, thought, concept or output")
    s.add_argument("--type", required=True, choices=sorted(TYPE_DIR))
    s.add_argument("--title", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--body", help="text, or - to read stdin")
    s.add_argument("--domain", help="a domain listed under ## Domains in the vault's CLAUDE.md")
    s.add_argument("--project")
    s.add_argument("--origin", help="session:<id8>; defaults from $MENTAT_SESSION / $CLAUDE_SESSION_ID, else the capture time, session:YYYY-MM-DD-HHMM")
    s.add_argument("--auto", action="store_true", help="captured without asking")
    s.add_argument("--edited", action="store_true", help="user changed the proposal before keeping")
    s.add_argument("--value", type=int, default=3)
    s.add_argument("--effort", type=int, default=3)
    s.add_argument("--est-days", dest="est_days")
    s.set_defaults(fn=cmd_keep)

    s = sub.add_parser("inbox", help="park a one-line item of unclear type")
    s.add_argument("text")
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("decide", help="append a project decision")
    s.add_argument("--project")
    s.add_argument("--decision", required=True)
    s.add_argument("--title", help="title used in the earlier `propose`, to clear it")
    s.add_argument("--edited", action="store_true", help="user changed the proposed decision")
    s.add_argument("--auto", action="store_true", help="captured without asking")
    s.add_argument("--why", default="")
    s.add_argument("--rejected", default="")
    s.add_argument("--origin")
    s.set_defaults(fn=cmd_decide)

    s = sub.add_parser("wrap", help="end of session: rewrite project status")
    s.add_argument("--project")
    s.add_argument("--where", required=True, help="where we left off")
    s.add_argument("--next", help="next step")
    s.add_argument("--thread", action="append", help="open thread (repeat); replaces open-threads")
    s.set_defaults(fn=cmd_wrap)

    s = sub.add_parser("note", help="log one experiment attempt (instant, one line)")
    s.add_argument("text")
    s.add_argument("--result", default="info", choices=["worked", "failed", "info"])
    s.add_argument("--project")
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("handover", help="print a paste-ready prompt to continue the project anywhere")
    s.add_argument("--project")
    s.add_argument("--max-chars", type=int, default=3500)
    s.set_defaults(fn=cmd_handover)

    s = sub.add_parser("propose", help="register a pending suggestion (shows in the status line)")
    s.add_argument("--type", required=True, choices=PROPOSAL_TYPES)
    s.add_argument("--title", required=True)
    s.set_defaults(fn=cmd_propose)

    s = sub.add_parser("feedback", help="record the outcome of a suggestion")
    s.add_argument("--type", required=True, choices=PROPOSAL_TYPES)
    s.add_argument("--title", required=True)
    s.add_argument("--outcome", required=True, choices=["rejected", "edited"])
    s.set_defaults(fn=cmd_feedback)

    s = sub.add_parser("find", help="search titles and summaries")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--type")
    s.add_argument("--ideas", action="store_true", help="parked ideas ranked by value minus effort")
    s.add_argument("--limit", type=int, default=5)
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("doctor", help="check vault health")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("digest", help="ideas created or updated recently, plus top open ideas (read-only)")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--top", type=int, default=3)
    s.set_defaults(fn=cmd_digest)

    s = sub.add_parser("resume", help="where the last session in this folder stopped, and how to resume it (read-only)")
    s.add_argument("--folder")
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("context", help="print the session-start context")
    s.add_argument("--cwd")
    s.add_argument("--max-chars", type=int, default=6000)
    s.add_argument("--always", action="store_true", help="print even for an unregistered folder")
    s.set_defaults(fn=cmd_context)

    from . import policy
    policy.add_parser(sub)
    sub.metavar = "{" + ",".join(sub.choices) + "}"
    sub.add_parser("status-line").set_defaults(fn=cmd_status_line)
    sub.add_parser("hook").set_defaults(fn=cmd_hook)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "context" and not args.always:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        try:
            util.utf8_stdio()
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                args.fn(args)
            sys.stderr.write(err.getvalue())
            sys.stdout.write(out.getvalue())
        except Exception:
            pass
        return
    try:
        util.utf8_stdio()
        args.fn(args)
    except (VaultError, TimeoutError) as e:
        print(f"mentat-wiki: {e}", file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"mentat-wiki: file error: {e}", file=sys.stderr)
        sys.exit(2)
