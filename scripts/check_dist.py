"""Check that the built wheel and sdist contain the data files the CLI needs."""
import configparser
import sys
import tarfile
import zipfile
from pathlib import Path

REQUIRED = [
    "mentat_wiki/data/templates/CLAUDE.md",
    "mentat_wiki/data/templates/core/capture-policy.md",
    "mentat_wiki/data/skills/keep/SKILL.md",
    "LICENSE",
]


def check_entry_points(content: bytes) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(content.decode("utf-8"))
    expected = {"mentat-wiki": "mentat_wiki.cli:main"}
    if dict(parser["console_scripts"]) != expected:
        raise ValueError("expected mentat-wiki as the only console script")


def wheel_names(path: Path) -> list:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
        if entry is None:
            raise ValueError("missing wheel entry_points.txt")
        check_entry_points(zf.read(entry))
        return names


def sdist_names(path: Path) -> list:
    with tarfile.open(path, "r:*") as tf:
        names = tf.getnames()
        entry = next((n for n in names if n.endswith(".egg-info/entry_points.txt")), None)
        if entry is None:
            raise ValueError("missing sdist entry_points.txt")
        with tf.extractfile(entry) as stream:
            check_entry_points(stream.read())
        return names


def missing(names, required) -> list:
    """Members are checked by suffix: the sdist puts everything under a versioned folder."""
    cleaned = [n.replace("\\", "/") for n in names]
    return [r for r in required
            if not any(n == r or n.endswith("/" + r) for n in cleaned)]


def check(archive: Path, names, required) -> list:
    absent = missing(names, required)
    for item in required:
        print(f"  {'missing' if item in absent else 'ok     '} {item}")
    return absent


def main(argv) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f"check_dist: expected one wheel and one sdist in {dist}, "
              f"found {len(wheels)} wheel(s) and {len(sdists)} sdist(s)", file=sys.stderr)
        return 1
    failed = []
    for archive, names in ((wheels[0], wheel_names), (sdists[0], sdist_names)):
        print(f"checking {archive}")
        try:
            absent = check(archive, names(archive), REQUIRED)
        except (OSError, ValueError, KeyError, configparser.Error, zipfile.BadZipFile, tarfile.TarError) as exc:
            print(f"check_dist: cannot read {archive}: {exc}", file=sys.stderr)
            return 1
        if absent:
            failed.extend(f"{archive.name}: {item}" for item in absent)
    if failed:
        print("check_dist: missing files:", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("check_dist: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
