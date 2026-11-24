"""Plan, apply and undo Claude Code integration changes."""
import difflib
import json
import os
import re
import shutil
import sys
import sysconfig
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

from . import config, util

SKILLS = ("idea", "keep", "wrap")
MARKER = "<!-- managed-by: mentat-wiki -->"
EVENTS = {"SessionStart": "context", "UserPromptSubmit": "hook"}
# Match an invocation, not a mention of mentat-wiki inside another tool's arguments.
PYTHON = r'(?:"(?:[^"]*[/\\])?(?:python[\d.]*|py)(?:\.exe)?"|(?:[^\s"]*[/\\])?(?:python[\d.]*|py)(?:\.exe)?)'
MODULE = PYTHON + r"(?: -[23](?:\.\d+)?)? -m "


def directory(value):
    return Path(value or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").absolute()


def command(override, cfg):
    if override is not None:
        if not override.strip():
            raise ValueError("--command cannot be empty")
        return override.strip()
    saved = (cfg.get("command") or "").strip()
    if os.environ.get("MENTAT_CMD", "").strip() or saved not in ("", "mentat"):  # old script name: re-resolve
        return config.command()
    script = shutil.which("mentat-wiki")
    if script:
        user = sysconfig.get_preferred_scheme("user")
        folders = (sysconfig.get_path("scripts"), sysconfig.get_path("scripts", scheme=user))
        if Path(script).resolve().parent in [Path(p).resolve() for p in folders]:
            return "mentat-wiki"
    # Forward slashes: Claude Code runs hooks through bash on Windows, and bash eats backslashes.
    # Windows itself accepts `C:/...` paths, so the same string works from cmd and PowerShell too.
    exe = sys.executable.replace("\\", "/")
    if any(c.isspace() for c in exe):
        exe = f'"{exe}"'
    return f"{exe} -m mentat_wiki"


def owned(value, suffix, commands):
    if not isinstance(value, str):
        return False
    if suffix == "*" and value.endswith(":*"):  # legacy permission form `Bash(cmd:*)`
        value = value[:-2] + " *"
    if any(value == f"{cmd} {suffix}" for cmd in (*commands, "mentat-wiki", "mentat")):
        return True
    if suffix == "hook" and re.fullmatch(MODULE + r"mentat(?:_wiki)?\.hook", value):
        return True
    return bool(re.fullmatch(MODULE + r"mentat(?:_wiki)? " + re.escape(suffix), value))


def read(path):
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return None


def object_from(raw, path):
    def invalid_number(value):
        raise ValueError(f"invalid number {value}")

    def unique(pairs):
        obj = dict(pairs)
        if len(pairs) != len(obj):
            raise ValueError("duplicate keys")
        return obj

    if raw is None:
        return {}
    try:
        obj = json.loads(raw.removeprefix("\ufeff"), object_pairs_hook=unique,
                         parse_constant=invalid_number)
    except ValueError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return obj


def dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def container(parent, key, kind):
    result = parent.get(key, kind())
    if not isinstance(result, kind):
        raise ValueError(f"invalid settings: unexpected type for {key}")
    return result


def groups(settings, event):
    hooks = container(settings, "hooks", dict)
    return container(hooks, event, list)


def entries(group):
    if isinstance(group, dict):
        return container(group, "hooks", list)
    return []


def invocation(entry):
    if isinstance(entry, dict) and entry.get("type") == "command":
        return entry.get("command")
    return None


def install_settings(settings, manifest, cmd, commands, force):
    changes = manifest["entries"]
    created = manifest["containers"]

    def ensure(parent, key, kind):
        if key not in parent:
            created.append(key)
            parent[key] = kind()
        return container(parent, key, kind)

    allow = ensure(ensure(settings, "permissions", dict), "allow", list)
    permission = f"Bash({cmd} *)"
    old = next((p for p in allow if isinstance(p, str) and p.startswith("Bash(")
                and p.endswith(")") and owned(p[5:-1], "*", commands)), None)
    if permission not in allow:
        if old is None:
            allow.append(permission)
        else:
            allow[allow.index(old)] = permission
        changes.append(dict(key="allow", command=permission, previous=old))

    hooks = ensure(settings, "hooks", dict)
    for event, suffix in EVENTS.items():
        items = ensure(hooks, event, list)
        found = False
        for group_index, group in enumerate(items):
            for index, entry in enumerate(entries(group)):
                if not owned(invocation(entry), suffix, commands):
                    continue
                found = True
                desired = dict(entry, command=f"{cmd} {suffix}")
                if suffix == "hook":
                    desired["timeout"] = 5
                if desired != entry:
                    changes.append(dict(key=event, command=desired["command"],
                                        group_index=group_index, index=index,
                                        group={k: v for k, v in group.items() if k != "hooks"},
                                        installed=desired, previous=entry.copy()))
                    entry.update(desired)
        if not found:
            desired = dict(type="command", command=f"{cmd} {suffix}")
            if suffix == "hook":
                desired["timeout"] = 5
            items.append({"hooks": [desired]})
            changes.append(dict(key=event, command=desired["command"], installed=desired,
                                group={}, group_index=len(items) - 1, index=0))

    previous = settings.get("statusLine")
    if "statusLine" in settings and not owned(invocation(previous), "status-line", commands) and not force:
        print("warning: keeping existing statusLine (use --force-statusline to replace it)")
        return
    desired = {"type": "command", "command": f"{cmd} status-line"}
    if previous != desired:
        change = dict(key="statusLine", command=desired["command"], installed=desired)
        if "statusLine" in settings:
            change["previous"] = previous
        changes.append(change)
        settings["statusLine"] = desired


def undo(settings, change):
    key = change["key"]
    previous = change.get("previous")
    if key == "allow":
        allow = container(container(settings, "permissions", dict), "allow", list)
        if change["command"] in allow:
            i = allow.index(change["command"])
            allow[i:i + 1] = [previous] if previous is not None else []
    elif key == "statusLine":
        if settings.get(key) == change["installed"]:
            if "previous" in change:
                settings[key] = previous
            else:
                del settings[key]
    elif key in EVENTS:
        items = groups(settings, key)
        matches = []
        for group_index, group in enumerate(items):
            if not isinstance(group, dict):
                continue
            if "group" in change and change["group"] != {k: v for k, v in group.items() if k != "hooks"}:
                continue
            matches.extend((group_index, i) for i, entry in enumerate(entries(group))
                           if entry == change["installed"])
        location = (change["group_index"], change["index"])
        if location not in matches:
            if len(matches) != 1:
                return
            location = matches[0]
        group_index, i = location
        group = items[group_index]
        hooks = entries(group)
        hooks[i:i + 1] = [previous] if previous is not None else []
        if not hooks and set(group) == {"hooks"}:
            del items[group_index]


def uninstall_settings(settings, manifest, commands):
    if manifest:
        for change in reversed(manifest["entries"]):
            undo(settings, change)
        created = manifest["containers"]
    else:
        # Without a manifest, keep pre-existing top-level containers.
        created = []
        allow = container(container(settings, "permissions", dict), "allow", list)
        allow[:] = [p for p in allow if not (isinstance(p, str) and p.startswith("Bash(")
                    and p.endswith(")") and owned(p[5:-1], "*", commands))]
        for event, suffix in EVENTS.items():
            items = groups(settings, event)
            had_groups = bool(items)
            for index in reversed(range(len(items))):
                group = items[index]
                hooks = entries(group)
                before = len(hooks)
                hooks[:] = [e for e in hooks if not owned(invocation(e), suffix, commands)]
                if before and not hooks and set(group) == {"hooks"}:
                    del items[index]
            if not items and had_groups:
                settings["hooks"].pop(event, None)
        if owned(invocation(settings.get("statusLine")), "status-line", commands):
            del settings["statusLine"]
    for key in reversed(created):
        parent = settings
        if key in EVENTS:
            parent = settings.get("hooks", {})
        elif key == "allow":
            parent = settings.get("permissions", {})
        if key in parent and parent[key] in ([], {}):
            del parent[key]


def skill_file(root, name):
    path = root / "skills" / name / "SKILL.md"
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"skill path leaves Claude directory: {path}")
    return path


def skill_text(path):
    try:
        return read(path)
    except UnicodeDecodeError:
        # A skill in another encoding is user-owned. Never rewrite it.
        return ""


def skills(root, cmd, installing, manifest, snapshots, writes):
    managed = manifest.get("skills", [])
    for name in SKILLS:
        path = skill_file(root, name)
        rel = path.relative_to(root).as_posix()
        old = skill_text(path)
        if old is not None and MARKER not in old.splitlines():
            print(f"warning: skip user skill {rel}")
            continue
        snapshots[path] = old
        if installing:
            source = Path(__file__).parent / "data" / "skills" / name / "SKILL.md"
            template = source.read_text(encoding="utf-8")
            new = re.sub(r"mentat-wiki (?=[a-z])", lambda _: cmd + " ", template)
            if rel not in managed:
                managed.append(rel)
        else:
            if manifest and rel not in managed:
                continue
            new = None
        if new != old:
            writes[path] = new
            action = "remove" if new is None else "update" if old is not None else "add"
            print(f"{action} {rel}")
        elif installing:
            print(f"skip unchanged {rel}")


def backup_path(path):
    stamp = datetime.now()
    while True:
        backup = path.with_name(f"{path.name}.bak-{stamp:%Y%m%d-%H%M%S}")
        if not os.path.lexists(backup):
            return backup
        stamp += timedelta(seconds=1)


def write(path, value):
    if value is None:
        path.unlink(missing_ok=True)
    else:
        util.write_atomic(path, value)


def apply(snapshots, writes, settings_path, backup):
    with util.lock(config.config_path().parent):
        if any(read(p) != raw for p, raw in snapshots.items()):
            raise ValueError("files changed since preview; re-run to review")
        if backup:
            backup.touch(exist_ok=False)
            try:
                util.write_atomic(backup, snapshots[settings_path])
            except OSError:
                backup.unlink(missing_ok=True)
                raise
        applied = []
        try:
            for target, value in writes.items():
                if target.is_symlink() or read(target) != snapshots[target]:
                    raise ValueError(f"{target} changed since preview; re-run to review")
                write(target, value)
                applied.append(target)
        except (ValueError, OSError):
            for target in reversed(applied):
                if not target.is_symlink() and read(target) == writes[target]:
                    write(target, snapshots[target])
            raise


def claude(args):
    root = directory(args.claude_dir)
    path = root / "settings.json"
    cfg_path = config.config_path().absolute()
    record = cfg_path.with_name("install-claude.json")
    if len({p.resolve() for p in (path, cfg_path, record)}) != 3:
        raise ValueError("settings, config and manifest paths must be distinct")
    snapshots = {p: read(p) for p in (path, cfg_path, record)}
    settings, cfg, manifest = (object_from(raw, p) for p, raw in snapshots.items())
    if manifest and manifest.get("directory") != str(root):
        raise ValueError("manifest belongs to another Claude directory")
    old_settings = deepcopy(settings)
    installing = args.cmd == "install"
    cmd = command(getattr(args, "command", None), cfg)
    commands = [cmd, manifest.get("command", cmd)]
    writes = {}
    if installing:
        if not manifest:
            manifest = dict(directory=str(root), entries=[], containers=[], skills=[], backup=None,
                            created_settings=snapshots[path] is None)
        install_settings(settings, manifest, cmd, commands, args.force_statusline)
        manifest["command"] = cmd
        if cfg.get("command", "mentat-wiki") != cmd:
            manifest.setdefault("previous_command", cfg.get("command"))
            if cmd == "mentat-wiki":
                cfg.pop("command", None)
            else:
                cfg["command"] = cmd
            writes[cfg_path] = dump(cfg)
    else:
        if not manifest and not getattr(args, "legacy", False):
            # Without a manifest nothing here is provably ours: a hand-written mentat-wiki hook may predate
            # any install. Removing those entries needs an explicit opt-in.
            print("no install manifest: nothing here was added by `mentat-wiki install claude`. "
                  "To remove hand-written mentat-wiki hooks, permission and marked skills, re-run with --legacy.")
            return
        uninstall_settings(settings, manifest, commands)
        if "previous_command" in manifest and cfg.get("command", "mentat-wiki") == manifest.get("command"):
            previous = manifest["previous_command"]
            if previous is None:
                cfg.pop("command", None)
            else:
                cfg["command"] = previous
            writes[cfg_path] = dump(cfg)

    backup = None
    if old_settings != settings:
        # Uninstall leaves no empty settings.json behind if the install created the file.
        remove = not installing and settings == {} and manifest.get("created_settings")
        new = writes[path] = None if remove else dump(settings)
        if remove:
            print(f"remove {path} (created by mentat-wiki install)")
            new = ""
        old = snapshots[path] or ""
        print("\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(),
                         fromfile=f"a/{path.name}", tofile=f"b/{path.name}", lineterm="")))
        if snapshots[path] is not None:
            backup = backup_path(path)
            if installing and not manifest["backup"]:
                manifest["backup"] = str(backup)
    skills(root, cmd, installing, manifest, snapshots, writes)
    desired = dump(manifest) if installing else None
    if snapshots[record] != desired:
        writes[record] = desired
    if not writes:
        print("already installed" if installing else "already uninstalled")
        return
    for target in writes:
        if target in (cfg_path, record):
            print(f"{'remove' if writes[target] is None else 'update'} {target}")
        if target.is_symlink():
            raise ValueError(f"refusing to replace symlink: {target}")
    if backup:
        print(f"backup {backup}")
    if args.dry_run:
        return
    if not args.yes:
        if not sys.stdin.isatty():
            print("Re-run with --yes to apply.", file=sys.stderr)
            raise SystemExit(1)
        if input("Apply? [y/N] ").strip().lower() not in ("y", "yes"):
            return

    apply(snapshots, writes, path, backup)


ADAPTERS = {"claude": claude}


def run(args):
    try:
        ADAPTERS[args.client](args)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"mentat-wiki: {exc}", file=sys.stderr)
        raise SystemExit(1)


def add_parser(subparsers):
    for action in ("install", "uninstall"):
        parser = subparsers.add_parser(action, help=f"{action} client integration")
        parser.add_argument("client", choices=ADAPTERS)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--yes", action="store_true")
        parser.add_argument("--claude-dir", type=Path)
        if action == "install":
            parser.add_argument("--command")
            parser.add_argument("--force-statusline", action="store_true")
        else:
            parser.add_argument("--legacy", action="store_true",
                                help="without an install manifest, remove hand-written mentat-wiki entries too")
        parser.set_defaults(fn=run)


def check_install(claude_dir=None):
    root = directory(claude_dir)
    try:
        path = root / "settings.json"
        settings = object_from(read(path), path)
        record = config.config_path().with_name("install-claude.json")
        manifest = object_from(read(record), record)
        if manifest.get("directory") != str(root):
            manifest = {}
        cmds = [config.command(), manifest.get("command", "mentat-wiki")]
        present = {}
        for event, suffix in EVENTS.items():
            present[event] = [invocation(e) for g in groups(settings, event) for e in entries(g)
                              if owned(invocation(e), suffix, cmds)]
        status = invocation(settings.get("statusLine"))
        present["statusLine"] = [status] if owned(status, "status-line", cmds) else []
        managed = [name for name in SKILLS if MARKER in
                   (skill_text(skill_file(root, name)) or "").splitlines()]
        allow = container(container(settings, "permissions", dict), "allow", list)
        permitted = any(isinstance(p, str) and p.startswith("Bash(") and p.endswith(")")
                        and owned(p[5:-1], "*", cmds) for p in allow)
        if not (manifest or managed or permitted or any(present.values())):
            return [("info", "Claude Code integration is absent")]
        issues = []
        managed_status = any(c["key"] == "statusLine" for c in manifest.get("entries", []))
        for key, values in present.items():
            if not values and (key != "statusLine" or key not in settings or managed_status):
                issues.append(("warn", f"Claude Code: missing {key}"))
            for value in values:
                match = re.match(r'(?:"([^"]+)"|\x27([^\x27]+)\x27|(\S+))', value)
                exe = next(x for x in match.groups() if x)
                if not shutil.which(exe):
                    issues.append(("warn", f"Claude Code: executable unavailable: {exe}"))
        if not permitted:
            issues.append(("warn", "Claude Code: missing mentat-wiki permission"))
        expected = manifest.get("skills", [f"skills/{n}/SKILL.md" for n in SKILLS])
        for name in SKILLS:
            if f"skills/{name}/SKILL.md" in expected and name not in managed:
                issues.append(("warn", f"Claude Code: missing managed skill {name}"))
        return list(dict.fromkeys(issues))
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        return [("warn", f"Claude Code: {exc}")]
