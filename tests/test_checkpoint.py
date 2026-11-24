import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from mentat_wiki import checkpoint, config, util
from tests.test_mentat import Base

REPO = Path(__file__).resolve().parent.parent
SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"


class CheckpointBase(Base):
    def setUp(self):
        super().setUp()
        self.store = Path(os.environ["MENTAT_CONFIG"]).parent / "checkpoints.json"
        self.v.register_project("demo")
        config.register(self.work, "demo")

    def _run(self, module, stdin, *args):
        env = dict(os.environ, MENTAT_CONFIG=os.environ["MENTAT_CONFIG"], PYTHONIOENCODING="utf-8")
        env.pop("CLAUDE_ENV_FILE", None)
        return subprocess.run([sys.executable, "-m", module, *args], input=stdin.encode("utf-8"),
                              capture_output=True, cwd=REPO, env=env, timeout=30)

    def _prompt(self, sid=SID_A, cwd=None, **extra):
        return self._run("mentat_wiki.hook", json.dumps({"session_id": sid, "cwd": str(cwd or self.work),
                                                    "prompt": "TOPSECRETPROMPT words", **extra}))


class TestCheckpoint(CheckpointBase):
    def test_hook_records_ids_only_and_counts(self):
        r = self._prompt(transcript_path="t.jsonl")
        self.assertEqual((r.returncode, r.stdout), (0, b""))
        self._prompt()
        raw = self.store.read_text(encoding="utf-8")
        self.assertNotIn("TOPSECRET", raw)
        e = json.loads(raw)[util._cwd_key(self.work)][SID_A]
        self.assertEqual((e["id"], e["n"], e["tp"]), ("aaaaaaaa", 2, "t.jsonl"))
        cp = checkpoint.latest(self.work)
        self.assertEqual((cp["sid"], cp["n"]), (SID_A, 2))

    def test_hook_does_not_touch_index(self):
        self._prompt()
        self.assertFalse((self.v.state / "index.db").exists())

    def test_bad_input_never_fails_or_writes(self):
        for stdin in ("", "not json", "[1,2]", '{"session_id": 5}', '{"session_id": "!!!"}', '{"prompt": "x"}'):
            self.assertEqual(self._run("mentat_wiki.hook", stdin).returncode, 0)
        self.assertFalse(self.store.exists())

    def test_corrupt_store_is_replaced(self):
        self.store.write_text("{{{ nope", encoding="utf-8")
        self._prompt()
        self.assertEqual(checkpoint.latest(self.work)["sid"], SID_A)
        self.store.write_text("[1,2]", encoding="utf-8")
        checkpoint.record({"session_id": SID_B, "cwd": str(self.work)})
        self.assertEqual(checkpoint.latest(self.work)["sid"], SID_B)

    def test_prune_old_and_keep_five_per_folder(self):
        now = time.time()
        checkpoint.record({"session_id": "oldoldold", "cwd": str(self.work)}, now=now - 8 * 86400)
        for i in range(7):
            checkpoint.record({"session_id": f"s{i}xxxxxx", "cwd": str(self.work)}, now=now - 100 + i)
        data = json.loads(self.store.read_text(encoding="utf-8"))
        sessions = data[util._cwd_key(self.work)]
        self.assertEqual(len(sessions), 5)
        self.assertNotIn("oldoldold", sessions)
        self.assertIn("s6xxxxxx", sessions)
        self.assertIsNone(checkpoint.latest(self.work, now=now + 8 * 86400))

    def test_latest_picks_newest_excludes_current_and_uses_parent(self):
        now = time.time()
        checkpoint.record({"session_id": SID_A, "cwd": str(self.work)}, now=now - 50)
        checkpoint.record({"session_id": SID_B, "cwd": str(self.work)}, now=now - 10)
        self.assertEqual(checkpoint.latest(self.work)["sid"], SID_B)
        self.assertEqual(checkpoint.latest(self.work, exclude=SID_B)["sid"], SID_A)
        sub = self.work / "src"
        self.assertEqual(checkpoint.latest(sub)["sid"], SID_B)
        self.assertIsNone(checkpoint.latest(self.work.parent / "other"))

    def test_resume_reports_unwrapped_then_wrapped(self):
        self._prompt(SID_A)
        code, out, _ = self.run_cli("resume", "--folder", str(self.work))
        self.assertEqual(code, 0)
        self.assertIn(f"claude --resume {SID_A}", out)
        self.assertIn("NO, the session ended without /wrap", out)
        self.assertLess(len(out.splitlines()), 25)
        self.v.wrap("demo", "Stopped mid-way", "Next bit", ["Thread one"])
        code, out, _ = self.run_cli("resume", "--folder", str(self.work))
        self.assertIn("Wrapped after it: yes", out)
        self.assertIn("Stopped mid-way", out)
        self.assertIn("Thread one", out)

    def test_resume_without_checkpoint(self):
        code, out, _ = self.run_cli("resume", "--folder", str(self.work))
        self.assertEqual(code, 0)
        self.assertIn("No session checkpoint", out)

    def _ctx(self, sid):
        return self._run("mentat_wiki", json.dumps({"session_id": sid, "cwd": str(self.work)}),
                         "context", "--cwd", str(self.work)).stdout.decode("utf-8")

    def test_context_line_only_when_previous_unwrapped(self):
        self.assertNotIn("without /wrap", self._ctx(SID_B))  # no checkpoint
        self._prompt(SID_A)
        out = self._ctx(SID_B)
        self.assertIn("Last session ended without /wrap (aaaaaaaa", out)
        self.assertIn(f"claude --resume {SID_A}", out)
        self.assertEqual(out.count("without /wrap"), 1)
        self.assertNotIn("without /wrap", self._ctx(SID_A))  # the current session is not "previous"
        self.v.wrap("demo", "done", "next", [])
        self.assertNotIn("without /wrap", self._ctx(SID_B))  # wrapped: silent
        time.sleep(1.1)  # event ts has 1 s resolution
        self._prompt(SID_A)  # more activity after the wrap
        self.assertIn("without /wrap", self._ctx(SID_B))

    def test_context_silent_when_checkpoint_older_than_7_days(self):
        checkpoint.record({"session_id": SID_A, "cwd": str(self.work)}, now=time.time() - 8 * 86400)
        self.assertNotIn("without /wrap", self._ctx(SID_B))


class TestVaultFolderSessions(CheckpointBase):
    """Sessions run in the vault folder itself (no registered project)."""

    def _root_prompt(self, sid):
        return self._prompt(sid, cwd=self.v.root)

    def _root_ctx(self, sid, folder=None):
        folder = folder or self.v.root
        return self._run("mentat_wiki", json.dumps({"session_id": sid, "cwd": str(folder)}),
                         "context", "--cwd", str(folder)).stdout.decode("utf-8")

    def test_vault_folder_line_uses_latest_wrap_of_any_project(self):
        self._root_prompt(SID_A)
        out = self._root_ctx(SID_B)
        self.assertIn("Last session ended without /wrap (aaaaaaaa", out)
        self.assertEqual(out.count("without /wrap"), 1)
        self.assertIn("Mentat capture protocol", out)
        self.assertIn("Vault folder: no project. Pass --project <name> to decide, wrap and note; known projects: demo.", out)
        self.v.wrap("demo", "done", "next", [])
        after = self._root_ctx(SID_B)
        self.assertIn("Mentat capture protocol", after)
        self.assertNotIn("without /wrap", after)

    def test_other_unregistered_folder_stays_silent(self):
        other = self.work.parent / "elsewhere"
        other.mkdir(exist_ok=True)
        self._prompt(SID_A, cwd=other)
        self.assertEqual(self._root_ctx(SID_B, folder=other).strip(), "")

    def test_resume_in_vault_folder_names_any_project_scope(self):
        self._root_prompt(SID_A)
        code, out, _ = self.run_cli("resume", "--folder", str(self.v.root))
        self.assertEqual(code, 0)
        self.assertIn("Wrapped after it (any project): NO", out)
        self.assertIn(f"claude --resume {SID_A}", out)


if __name__ == "__main__":
    unittest.main()
