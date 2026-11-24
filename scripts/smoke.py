"""Install the wheel and the sdist into fresh venvs and run the CLI end to end."""
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

CLEAN_ENV = ("MENTAT_VAULT", "MENTAT_CMD", "MENTAT_SESSION", "CLAUDE_SESSION_ID",
             "PYTHONPATH", "PYTHONHOME")


def venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_mentat(root: Path) -> Path:
    return root / ("Scripts/mentat-wiki.exe" if os.name == "nt" else "bin/mentat-wiki")


def clean_env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV}
    env["MENTAT_CONFIG"] = str(root / "config.json")
    env["CLAUDE_CONFIG_DIR"] = str(root / "claude")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def commands(mentat: Path, root: Path) -> list:
    m = str(mentat)
    return [
        [m, "--version"],
        [m, "init", str(root / "vault")],
        [m, "doctor"],
        [m, "install", "claude", "--dry-run", "--claude-dir", str(root / "claude")],
        [m, "keep", "--type", "idea", "--title", "Smoke idea", "--summary", "smoke test",
         "--value", "3", "--effort", "2"],
        [m, "find", "smoke"],
        [m, "policy"],
    ]


def run(cmd, cwd: Path, env: dict) -> None:
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    output = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        raise SystemExit(f"smoke: `{' '.join(cmd)}` exited {r.returncode}\n{output}")
    if output:
        print(output)


def install(python: Path, artifact: Path, offline: bool) -> None:
    cmd = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if offline:
        cmd.append("--no-index")
    cmd.append(str(artifact))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"smoke: pip install {artifact.name} failed\n{r.stdout}\n{r.stderr}")


def smoke(artifact: Path, label: str) -> None:
    print(f"smoke: {label} {artifact.name}")
    with tempfile.TemporaryDirectory(prefix=f"mentat-smoke-{label}-") as tmp:
        root = Path(tmp)
        env_dir = root / "venv"
        venv.EnvBuilder(with_pip=True).create(str(env_dir))
        # The wheel installs offline; the sdist needs the build backend, so pip may fetch it.
        install(venv_python(env_dir), artifact.resolve(), offline=label == "wheel")
        mentat = venv_mentat(env_dir)
        if not mentat.exists():
            raise SystemExit(f"smoke: {label} venv has no mentat-wiki script at {mentat}")
        work = root / "work"
        work.mkdir()
        env = clean_env(root)
        for cmd in commands(mentat, root):
            run(cmd, work, env)


def main(argv) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f"smoke: expected one wheel and one sdist in {dist}, "
              f"found {len(wheels)} wheel(s) and {len(sdists)} sdist(s)", file=sys.stderr)
        return 1
    smoke(wheels[0], "wheel")
    smoke(sdists[0], "sdist")
    print("smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
