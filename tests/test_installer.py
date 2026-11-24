import io
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mentat_wiki import cli, config, installer, util


def hook(command):
    return {"type": "command", "command": command}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "claude"
        self.settings = self.root / "settings.json"
        self.manifest = self.base / "install-claude.json"
        env = patch.dict(os.environ, MENTAT_CONFIG=str(self.base / "config.json"),
                         CLAUDE_CONFIG_DIR=str(self.root), MENTAT_CMD="")
        env.start()
        self.addCleanup(env.stop)

    def cli(self, action, *args, code=0):
        out = io.StringIO()
        err = io.StringIO()
        status = 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                cli.main([action, "claude", "--claude-dir", str(self.root), *args])
            except SystemExit as exc:
                status = exc.code
        self.assertEqual(status, code, err.getvalue())
        return out.getvalue() + err.getvalue()

    def install(self, *args):
        return self.cli("install", "--yes", "--command", "mentat-wiki", *args)

    def snapshot(self):
        return {p: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.base.rglob("*") if p.is_file()}

    def test_preview_and_noninteractive_refusal(self):
        out = self.cli("install", "--dry-run")
        self.assertIn("+++ b/settings.json", out)
        self.assertIn("add skills/idea/SKILL.md", out)
        result = subprocess.run([sys.executable, "-m", "mentat_wiki", "install", "claude",
                                 "--claude-dir", str(self.root)], input=b"", capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"--yes", result.stderr)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_install_noop_and_uninstall(self):
        original = {"permissions": {"allow": [], "deny": ["Bash(other *)"]},
                    "hooks": {"SessionStart": [{"hooks": []},
                                               {"matcher": "resume", "hooks": [hook("other")]}],
                              "UserPromptSubmit": [], "Stop": []},
                    "theme": "dark"}
        raw = json.dumps(original) + "\r\n"
        util.write_atomic(self.settings, raw)
        self.install()
        state = json.loads(self.settings.read_bytes())
        self.assertEqual(state["permissions"]["allow"], ["Bash(mentat-wiki *)"])
        start = state["hooks"]["SessionStart"]
        self.assertEqual(start[:-1], original["hooks"]["SessionStart"])
        self.assertEqual(start[-1], {"hooks": [hook("mentat-wiki context")]})
        self.assertEqual(state["hooks"]["UserPromptSubmit"],
                         [{"hooks": [dict(hook("mentat-wiki hook"), timeout=5)]}])
        self.assertEqual(state["statusLine"], hook("mentat-wiki status-line"))
        manifest = json.loads(self.manifest.read_bytes())
        self.assertEqual(Path(manifest["backup"]).read_bytes(), raw.encode())
        self.assertEqual(len(manifest["entries"]), 4)
        for name in installer.SKILLS:
            rel = f"skills/{name}/SKILL.md"
            self.assertIn(rel, manifest["skills"])
            self.assertIn(installer.MARKER, (self.root / rel).read_text(encoding="utf-8"))
        snap = self.snapshot()
        self.assertIn("already installed", self.install())
        self.assertEqual(self.snapshot(), snap)
        self.assertIn("remove skills", self.cli("uninstall", "--dry-run"))
        self.assertEqual(self.snapshot(), snap)
        self.cli("uninstall", "--yes")
        self.assertEqual(json.loads(self.settings.read_bytes()), original)
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.root.rglob("SKILL.md")), [])
        self.assertEqual(len(list(self.root.glob("*.bak-*"))), 2)

    def test_invalid_settings_leave_everything_untouched(self):
        for content in ('{"hooks":', "null", "[]", '{"hooks": 42}', '{"a": 1, "a": 2}', '{"a":NaN}'):
            util.write_atomic(self.settings, content)
            snap = self.snapshot()
            self.cli("install", "--yes", code=1)
            self.assertEqual(self.snapshot(), snap)

    def test_non_utf8_user_skill_and_updated_managed_skill(self):
        own = self.root / "skills/idea/SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_bytes(b"custom\xff")
        self.install()
        keep = self.root / "skills/keep/SKILL.md"
        before = keep.read_bytes()
        util.write_atomic(keep, installer.MARKER + "\nold version")
        self.assertIn("update skills/keep/SKILL.md", self.install())
        self.assertEqual(keep.read_bytes(), before)
        self.cli("uninstall", "--yes")
        self.assertEqual(own.read_bytes(), b"custom\xff")

    def test_switch_command_preserves_prior_configuration(self):
        config.save({"command": "original", "other": True})
        self.install("--command", "first")
        self.install("--command", "second")
        self.assertNotIn("first", self.settings.read_text(encoding="utf-8"))
        self.assertEqual(config.command(), "second")
        self.install()
        self.assertEqual(config.command(), "mentat-wiki")
        self.cli("uninstall", "--yes")
        self.assertEqual(config.load(), {"command": "original", "other": True})
        self.assertFalse(self.settings.exists())  # the install created it, so uninstall removes it

    def test_multiple_legacy_entries_retain_original_order(self):
        group = {"hooks": [hook("python -m mentat context"), hook("python -m mentat_wiki context")]}
        original = {"hooks": {"SessionStart": [group]}}
        util.write_atomic(self.settings, json.dumps(original))
        self.install()
        self.cli("uninstall", "--yes")
        self.assertEqual(json.loads(self.settings.read_bytes()), original)

    def test_foreign_status_and_skill(self):
        status = dict(hook("custom status"), padding=2)
        util.write_atomic(self.settings, json.dumps({"statusLine": status}))
        skill = self.root / "skills/keep/SKILL.md"
        util.write_atomic(skill, "My skill")
        out = self.install()
        self.assertIn("warning: keeping existing statusLine", out)
        self.assertIn("warning: skip user skill", out)
        self.assertEqual(json.loads(self.settings.read_bytes())["statusLine"], status)
        self.install("--force-statusline")
        self.assertEqual(json.loads(self.settings.read_bytes())["statusLine"], hook("mentat-wiki status-line"))
        util.write_atomic(self.root / "skills/wrap/SKILL.md", "User replacement")
        self.cli("uninstall", "--yes")
        self.assertEqual(json.loads(self.settings.read_bytes()), {"statusLine": status})
        self.assertEqual(skill.read_bytes(), b"My skill")
        self.assertEqual((self.root / "skills/wrap/SKILL.md").read_bytes(), b"User replacement")

    def test_upgrade_and_restore_legacy_in_place(self):
        old = "py -3 -m mentat context"
        group = {"matcher": "startup", "hooks": [hook("before"), hook(old), hook("after")]}
        original = {"hooks": {"SessionStart": [group]}}
        util.write_atomic(self.settings, json.dumps(original))
        self.install()
        state = json.loads(self.settings.read_bytes())
        self.assertEqual(state["hooks"]["SessionStart"], [
            dict(group, hooks=[hook("before"), hook("mentat-wiki context"), hook("after")])])
        state["another"] = True
        util.write_atomic(self.settings, json.dumps(state))
        self.cli("uninstall", "--yes")
        self.assertEqual(json.loads(self.settings.read_bytes()), dict(original, another=True))

    def test_legacy_colon_permission_upgraded_in_place(self):
        original = {"permissions": {"allow": ["Bash(git *)", "Bash(py -3 -m mentat_wiki:*)"]}}
        util.write_atomic(self.settings, json.dumps(original))
        self.install()
        allow = json.loads(self.settings.read_bytes())["permissions"]["allow"]
        self.assertEqual(allow, ["Bash(git *)", "Bash(mentat-wiki *)"])
        self.cli("uninstall", "--yes")
        restored = json.loads(self.settings.read_bytes())["permissions"]["allow"]
        self.assertEqual(restored, original["permissions"]["allow"])

    def test_command_selection(self):
        script = Path(sysconfig.get_path("scripts")) / "mentat-wiki"
        user = Path(sysconfig.get_path("scripts", scheme=sysconfig.get_preferred_scheme("user")))
        for path in (script, user / "mentat-wiki"):
            with patch.object(installer.shutil, "which", return_value=str(path)) as which:
                self.assertEqual(installer.command(None, {}), "mentat-wiki")
                which.assert_called_once_with("mentat-wiki")
        config.save({"command": "runner"})
        self.assertEqual(installer.command(None, config.load()), "runner")
        with patch.object(installer.shutil, "which", return_value=None):  # old script name: re-resolve
            self.assertEqual(installer.command(None, {"command": "mentat"}),
                             installer.command(None, {}))
            with patch.dict(os.environ, MENTAT_CMD="env-cmd"):  # the same override the runtime uses
                self.assertEqual(installer.command(None, {"command": "mentat"}), "env-cmd")
        self.assertEqual(installer.command("custom", config.load()), "custom")

    def test_foreign_scripts_on_path_use_module_fallback(self):
        with patch.dict(os.environ, PATH=str(self.base)), patch.object(sys, "executable", "python"):
            for name in ("mentat", "mentat-wiki"):
                script = self.base / (name + ".exe" if os.name == "nt" else name)
                script.touch()
                script.chmod(0o755)
                self.assertEqual(installer.command(None, {}), "python -m mentat_wiki")

    def test_fallback_path_with_spaces(self):
        exe = str(self.base / "Interpreter Files" / "python")
        cmd = '"' + exe.replace(chr(92), '/') + '" -m mentat_wiki'  # forward slashes for bash
        with patch.object(sys, "executable", exe), patch.object(installer.shutil, "which",
                                                                return_value=str(self.base / "mentat-wiki")):
            self.cli("install", "--yes")
        state = json.loads(self.settings.read_bytes())
        self.assertEqual(config.command(), cmd)
        self.assertEqual(state["permissions"]["allow"], [f"Bash({cmd} *)"])
        for event, suffix in installer.EVENTS.items():
            self.assertEqual(state["hooks"][event][0]["hooks"][0]["command"], f"{cmd} {suffix}")
        for skill in self.root.rglob("SKILL.md"):
            self.assertIn(installer.MARKER, skill.read_text(encoding="utf-8"))
            self.assertIn(cmd + " ", skill.read_text(encoding="utf-8"))
        keep = (self.root / "skills/keep/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--edited", keep)
        self.assertNotIn("--outcome edited", keep)

    def test_doctor(self):
        check = lambda: installer.check_install(self.root)
        self.assertEqual([s for s, _ in check()], ["info"])
        cmd = f'"{sys.executable}" -m mentat_wiki'
        self.cli("install", "--command", cmd, "--yes")
        self.assertEqual(check(), [])
        (self.root / "skills/keep/SKILL.md").unlink()
        state = json.loads(self.settings.read_bytes())
        del state["hooks"]["SessionStart"]
        util.write_atomic(self.settings, json.dumps(state))
        with patch.object(installer.shutil, "which", return_value=None):
            issues = check()
        self.assertTrue(all(s == "warn" for s, _ in issues))
        messages = str(issues)
        for word in ("executable", "SessionStart", "keep"):
            self.assertIn(word, messages)

    def test_fallback_uninstall(self):
        self.install()
        self.manifest.unlink()
        state = json.loads(self.settings.read_bytes())
        foreign = hook("echo -m mentat context")
        state["hooks"]["SessionStart"][0]["hooks"].append(foreign)
        util.write_atomic(self.settings, json.dumps(state))
        self.cli("uninstall", "--yes", "--legacy")
        state = json.loads(self.settings.read_bytes())
        self.assertEqual(state["hooks"], {"SessionStart": [{"hooks": [foreign]}]})
        self.assertNotIn("statusLine", state)

    def test_stale_preview_refused(self):
        def edit(_):
            util.write_atomic(self.settings, '{"theme": "light"}')
            return "y"
        with patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", edit):
            self.assertIn("changed since preview", self.cli("install", code=1))
        self.assertEqual(self.settings.read_bytes(), b'{"theme": "light"}')
        self.assertFalse(self.manifest.exists())

    def test_declining_tty_prompt_writes_nothing(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value=""):
            self.cli("install")
        self.assertEqual(list(self.base.iterdir()), [])

    def test_failure_rolls_back_install(self):
        original = '{"theme":"dark"}'
        util.write_atomic(self.settings, original)
        atomic = util.write_atomic

        def fail_manifest(path, content):
            if path == self.manifest:
                raise OSError("manifest unavailable")
            atomic(path, content)

        with patch.object(util, "write_atomic", fail_manifest):
            self.cli("install", "--yes", "--command", "runner", code=2)
        self.assertEqual(self.settings.read_bytes(), original.encode())
        self.assertFalse(config.config_path().exists())
        self.assertEqual(list(self.root.rglob("SKILL.md")), [])

    def test_skill_created_during_apply_is_preserved(self):
        atomic = util.write_atomic
        skill = self.root / "skills/keep/SKILL.md"

        def competing_write(path, content):
            atomic(path, content)
            if path == self.settings:
                atomic(skill, "User skill")

        with patch.object(util, "write_atomic", competing_write):
            self.cli("install", "--command", "mentat-wiki", "--yes", code=1)
        self.assertEqual(skill.read_bytes(), b"User skill")
        self.assertFalse(self.settings.exists())
        self.assertFalse(self.manifest.exists())

    def test_uninstall_removes_settings_it_created(self):
        self.assertFalse(self.settings.exists())
        self.install()
        self.assertTrue(self.settings.exists())
        out = self.cli("uninstall", "--yes")
        self.assertIn("created by mentat-wiki install", out)
        self.assertFalse(self.settings.exists())

    def test_uninstall_keeps_preexisting_settings(self):
        util.write_atomic(self.settings, json.dumps({}))
        self.install()
        self.cli("uninstall", "--yes")
        self.assertEqual(json.loads(self.settings.read_bytes()), {})

    def test_uninstall_without_manifest_needs_legacy(self):
        hand = {"hooks": {"SessionStart": [{"hooks": [hook("mentat context")]}]}}
        util.write_atomic(self.settings, json.dumps(hand))
        out = self.cli("uninstall", "--yes")
        self.assertIn("--legacy", out)
        self.assertEqual(json.loads(self.settings.read_bytes()), hand)
        self.cli("uninstall", "--yes", "--legacy")
        self.assertNotIn("mentat", self.settings.read_text(encoding="utf-8"))

    def test_fallback_path_uses_forward_slashes(self):
        exe = r"C:\Tools\Python\python.exe"
        with patch.object(sys, "executable", exe), patch.object(installer.shutil, "which",
                                                                return_value=None):
            self.assertEqual(installer.command(None, {}), "C:/Tools/Python/python.exe -m mentat_wiki")

