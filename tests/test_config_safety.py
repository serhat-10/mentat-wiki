import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mentat_wiki import config


class TestConfigSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config.json"
        env = patch.dict(os.environ, MENTAT_CONFIG=str(self.path))
        env.start()
        self.addCleanup(env.stop)

    def test_bom_config_is_read(self):
        self.path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"vault": "v"}).encode("utf-8"))
        self.assertEqual(config.load()["vault"], "v")
        config.register(self.tmp.name, "demo")
        self.assertEqual(config.load()["vault"], "v")  # nothing lost on the next save

    def test_invalid_config_is_never_overwritten(self):
        self.path.write_text('{"vault": "v", broken', encoding="utf-8")
        self.assertEqual(config.load(), {})  # readers degrade quietly
        with self.assertRaises(config.ConfigError):
            config.register(self.tmp.name, "demo")
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"vault": "v", broken')

    def test_null_projects_do_not_crash(self):
        self.path.write_text(json.dumps({"vault": "v", "projects": None}), encoding="utf-8")
        self.assertIsNone(config.project_for(self.tmp.name))
        config.register(self.tmp.name, "demo")
        self.assertEqual(config.project_for(self.tmp.name), "demo")
