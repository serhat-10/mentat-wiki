import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mentat_wiki import doctor, search, util
from mentat_wiki.vault import Vault

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-vault"


class TestDemoVault(unittest.TestCase):
    """The shipped example must stay a clean vault: doctor finds no errors or warnings."""

    def test_doctor_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MENTAT_CONFIG": str(Path(tmp) / "config.json"),
                   "CLAUDE_CONFIG_DIR": str(Path(tmp) / "claude")}
            with patch.dict(os.environ, env):
                issues = doctor.run(Vault(DEMO))
        bad = [(s, m) for s, m in issues if s in ("error", "warn")]
        self.assertEqual(bad, [])

    def test_no_personal_data(self):
        for p in DEMO.rglob("*.md"):
            self.assertEqual(util.privacy_scan(p.read_text(encoding="utf-8")), [], p)
