"""User config: which vault, and which working folders map to which project."""
import json
import os
from pathlib import Path

from . import util


def config_path() -> Path:
    return Path(os.environ.get("MENTAT_CONFIG") or Path.home() / ".mentat" / "config.json")


class ConfigError(OSError):
    """The config file exists but cannot be read safely (reported like a file error)."""


def load() -> dict:
    """The config, or {} when missing or unreadable (readers such as hooks must never fail)."""
    try:
        data = json.loads(config_path().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(cfg: dict) -> None:
    """Write the config, refusing to replace an existing file that does not parse: load() reads such a
    file as {}, so saving over it would silently drop the vault path and project registrations."""
    p = config_path()
    try:
        raw = p.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raw = None
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read {p} ({e}); fix or remove it, then retry") from e
    if raw is not None and raw.strip():
        try:
            if not isinstance(json.loads(raw), dict):
                raise ValueError("not a JSON object")
        except ValueError as e:
            raise ConfigError(f"{p} is not valid JSON ({e}); fix or remove it, then retry") from e
    util.write_atomic(p, json.dumps(cfg, indent=2))


def _projects(cfg: dict) -> dict:
    projects = cfg.get("projects")
    return projects if isinstance(projects, dict) else {}


def command() -> str:
    """How agents and hooks run mentat-wiki on this machine. Default `mentat-wiki` (the console script).
    Set it when that script is not on PATH, e.g. `python -m mentat_wiki`."""
    saved = (os.environ.get("MENTAT_CMD") or load().get("command") or "").strip()
    # The console script was `mentat` before 0.1.0; that name belongs to an unrelated package.
    return saved if saved and saved != "mentat" else "mentat-wiki"


def vault_root():
    v = os.environ.get("MENTAT_VAULT") or load().get("vault")
    return Path(v).expanduser() if v else None


def _norm(p) -> str:
    """One spelling per folder: `~` expanded, symlinks resolved (/var and /private/var), case folded."""
    return util.path_key(p)


def _under(here: str, root: str) -> bool:
    """True when `here` is `root` or inside it. A registered `/` or drive root still works."""
    root = root.rstrip("/\\") if os.sep == "\\" else root.rstrip("/")
    return not root or here == root or here.startswith(root + os.sep)


def in_vault(cwd, root) -> bool:
    return _under(_norm(cwd), _norm(root))


def hook_cwd(data):
    cwd = data.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else os.getcwd()


def register(folder, project: str) -> None:
    cfg = load()
    cfg["projects"] = {**_projects(cfg), _norm(folder): project}
    save(cfg)


def project_for(cwd):
    """Project name for the folder (longest matching registered prefix), or None."""
    if not cwd:
        return None
    here = _norm(cwd)
    best = None
    for folder, name in _projects(load()).items():
        if not isinstance(name, str):
            continue
        key = _norm(folder)
        if _under(here, key) and (best is None or len(key) > len(best[0])):
            best = (key, name)
    return best[1] if best else None
