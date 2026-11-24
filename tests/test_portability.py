"""Portability and privacy-guard regressions: placeholders stay clean, real secrets still block."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from mentat_wiki import config, util

FALSE_POSITIVES = [
    "react@18.2.0",
    "pip install foo==1.2.3",
    "tokenizer: cl100k_base",
    "max_tokens: 100000",
    "token_budget: 1000-tokens",
    "context window of 200k tokens",
    "git@github.com:org/repo.git",
    "add user@example.com to the list",
    "https://docs.example.org/guide",
    "support@example.net",
    "somebody@api.example.com",
]

REAL_SECRETS = [
    "key sk-abcdefghijklmnopqrstuv",
    "ghp_abcdefghijklmnopqrstuvwxyz0123",
    "AKIAABCDEFGHIJKLMNOP",
    "-----BEGIN RSA PRIVATE KEY-----",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    "password: hunter22x",
    "client_secret=abcdef123456",
    "AWS_SECRET_ACCESS_KEY=abcdefghij",
    "token: abcdef123456",
    r"see C:\Users\someone\file",
    "/home/someone/file",
    "/Users/someone/file",
    "mail a.person@corp-mail.net",
    "ping ops@company.io",
]

LF_PAGE = ("---\ntype: idea\nsummary: an: example # note\nvalue: 4\n---\n\n# Title\n\nBody text\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._env = {k: os.environ.get(k) for k in ("MENTAT_CONFIG", "MENTAT_VAULT", "MENTAT_CMD")}
        os.environ["MENTAT_CONFIG"] = str(self.root / "config.json")
        os.environ.pop("MENTAT_VAULT", None)
        os.environ.pop("MENTAT_CMD", None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TestPrivacyPlaceholders(unittest.TestCase):
    def test_false_positives_are_clean(self):
        for text in FALSE_POSITIVES:
            self.assertEqual(util.privacy_scan(text), [], text)

    def test_real_secrets_still_blocked(self):
        for text in REAL_SECRETS:
            self.assertTrue(util.privacy_scan(text), text)

    def test_email_needs_letter_tld(self):
        self.assertEqual(util.privacy_scan("react@18.2.0"), [])
        self.assertEqual(util.privacy_scan("build 1.2.3@4.5.6"), [])
        self.assertTrue(util.privacy_scan("write to someone@host.dev"))

    def test_ssh_remote_is_not_an_email(self):
        self.assertEqual(util.privacy_scan("git remote add origin git@github.com:org/repo.git"), [])


class TestFrontmatterPortability(unittest.TestCase):
    def test_crlf_and_bom_match_lf(self):
        expected = util.parse_frontmatter(LF_PAGE)
        crlf = LF_PAGE.replace("\n", "\r\n")
        for variant in (crlf, "\ufeff" + LF_PAGE, "\ufeff" + crlf):
            self.assertEqual(util.parse_frontmatter(variant), expected, repr(variant[:20]))


class TestPathNormalisation(Base):
    def _link(self, target: Path) -> Path:
        link = self.root / ("link-" + target.name)
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks not permitted here: {exc}")
        return link

    def test_project_for_matches_through_symlink(self):
        real = self.root / "real"
        real.mkdir()
        link = self._link(real)
        config.register(real, "demo")
        self.assertEqual(config.project_for(link / "sub"), "demo")

    def test_recorded_session_matches_through_symlink(self):
        real = self.root / "real"
        real.mkdir()
        link = self._link(real)
        util.record_session("abcd1234", cwd=real)
        self.assertEqual(util.recorded_session(cwd=link, now=time.time()), "abcd1234")

    def test_vault_root_expands_tilde(self):
        os.environ["MENTAT_VAULT"] = "~/mentat-smoke-vault"
        self.assertEqual(config.vault_root(), Path.home() / "mentat-smoke-vault")

    def test_save_is_atomic_and_leaves_no_temp_files(self):
        cfg = {"vault": str(self.root / "vault"), "projects": {}}
        config.save(cfg)
        path = config.config_path()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), cfg)
        self.assertEqual([p.name for p in path.parent.iterdir() if p.name.startswith(".tmp-")], [])

    def test_prefix_does_not_match_sibling_folder(self):
        parent = self.root / "work"
        demo = parent / "demo"
        other = parent / "demo-two"
        demo.mkdir(parents=True)
        other.mkdir()
        config.register(demo, "demo")
        self.assertEqual(config.project_for(demo / "src"), "demo")
        self.assertIsNone(config.project_for(other))

    def test_root_registration_does_not_crash(self):
        if os.name == "nt":
            root = Path(os.path.splitdrive(os.getcwd())[0] + os.sep)
        else:
            root = Path("/")
        config.save({"projects": {str(root): "root-project"}})
        self.assertEqual(config.project_for(os.getcwd()), "root-project")


if __name__ == "__main__":
    unittest.main()
