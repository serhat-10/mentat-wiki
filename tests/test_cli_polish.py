import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from mentat_wiki import __version__, config, util
from tests.test_mentat import Base


class TestCliPolish(Base):
    def test_version(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            from mentat_wiki import cli
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"mentat-wiki {__version__}")

    def test_register_defaults_to_folder_name(self):
        code, out, err = self.run_cli("project", "register", "--path", str(self.work))
        self.assertEqual(code, 0, err)
        self.assertIn("project demo <- ", out)
        self.assertEqual(config.project_for(str(self.work)), "demo")

    def test_inferred_name_collision_and_explicit_sharing(self):
        other = Path(self.tmp.name) / "other" / self.work.name
        other.mkdir(parents=True)
        register = ("project", "register")
        self.assertEqual(self.run_cli(*register, "--path", str(self.work))[0], 0)
        before = config.load()
        code, _, err = self.run_cli(*register, "--path", str(other))
        self.assertEqual(code, 2)
        self.assertIn(f'project "demo" is already registered for {util.path_key(self.work)}', err)
        self.assertIn('pass "demo" explicitly', err)
        self.assertEqual(config.load(), before)
        self.assertEqual(self.run_cli(*register, "demo", "--path", str(other))[0], 0)
        self.assertEqual(config.project_for(other), "demo")
        shared = config.load()
        for folder in (self.work, other):
            self.assertEqual(self.run_cli(*register, "--path", str(folder))[0], 0)
            self.assertEqual(config.load(), shared)

    def test_public_help(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("context", out)
        self.assertNotIn("status-line", out)
        self.assertNotIn("hook", out)

    def test_register_refuses_vault_root(self):
        code, _, err = self.run_cli("project", "register", "notes", "--path", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("vault folder itself is not a project", err)
        self.assertIsNone(config.project_for(str(self.root)))

    def test_propose_type_is_validated(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            from mentat_wiki import cli
            cli.main(["propose", "--type", "banana", "--title", "x"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("invalid choice", err.getvalue())

    def test_tilde_paths_expand(self):
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        old = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        try:
            code, _, err = self.run_cli("config", "--vault", "~/vault")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(config.load()["vault"]), (home / "vault").resolve())
