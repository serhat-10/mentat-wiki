"""Packaged vault template files (schema, core/, _templates/), read with importlib.resources."""
from importlib import resources
from pathlib import Path


SKIP = {"__pycache__", ".DS_Store"}


def _root():
    return resources.files("mentat_wiki") / "data" / "templates"


def _walk(node, prefix=""):
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.name in SKIP or child.name.endswith(".pyc"):
            continue
        if child.is_dir():
            yield from _walk(child, f"{prefix}{child.name}/")
        else:
            yield f"{prefix}{child.name}"


def names() -> list:
    """Relative POSIX paths of every template file, sorted."""
    return list(_walk(_root()))


def read(rel: str) -> str:
    node = _root()
    for part in rel.split("/"):
        node = node / part
    return node.read_text(encoding="utf-8")


def install_into(root) -> list:
    """Write every template file missing under root. Never overwrites. Returns created paths."""
    root = Path(root)
    created = []
    for rel in names():
        target = root.joinpath(*rel.split("/"))
        if target.exists() or target.is_symlink():  # a dangling symlink is still the user's file
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:  # exclusive create: never replace a file that appeared since the check
            with open(target, "x", encoding="utf-8", newline="\n") as f:
                f.write(read(rel))
        except FileExistsError:
            continue
        created.append(rel)
    return created
