import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mentat_wiki import config, hook, search
from mentat_wiki.vault import Vault


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "vault"
        self.cfg = str(Path(self.tmp.name) / "config.json")
        os.environ["MENTAT_CONFIG"] = self.cfg
        os.environ.pop("MENTAT_VAULT", None)
        self.v = Vault(self.root)
        self.v.scaffold()
        config.save({"vault": str(self.root)})
        self.v.keep("concept", "Kubernetes pod networking", "How pod networking and services route traffic",
                    "body secret text", domain="engineering")
        search.sync(self.v)  # the hook never builds the index itself

    def test_match_lists_title_path_not_body(self):
        h = hook.hint_for("how does kubernetes pod networking route traffic here?", self.v)
        self.assertIn("kubernetes-pod-networking", h)
        self.assertNotIn("secret text", h)

    def test_silent_cases(self):
        for p in ("", "ok", "/keep something long enough to pass length", "tell me a joke about cats please now"):
            self.assertEqual(hook.hint_for(p, self.v), "")

    def test_single_term_not_enough(self):
        self.assertEqual(hook.hint_for("completely unrelated kubernetes question about billing", self.v), "")

    def test_keep_cue(self):
        self.assertIn("capturing", hook.hint_for("we decided to use sqlite for the index", None))

    def test_keep_cues_and_stop_words_from_config(self):
        prompt = "por favor, guárdalo así: el índice necesita caché"
        self.assertEqual(hook.hint_for(prompt, None), "")
        before = config.load()
        self.addCleanup(config.save, before)
        config.save({**before, "hook": {"keep_cues": ["guárdalo así", 7, ""], "stop_words": ["índice"]}})
        self.assertIn("capturing", hook.hint_for(prompt, None))
        self.assertEqual(hook.hint_for("un prompt cualquiera, bastante largo, sin nada", None), "")
        self.assertIn("indice", hook._terms(prompt))
        self.assertNotIn("indice", hook._terms(prompt, hook._user_words()[1]))
        for bad in ("x", ["x"], {"keep_cues": "x"}, {"keep_cues": None}, None):
            config.save({**before, "hook": bad})  # a malformed section never breaks the hook
            self.assertEqual(hook.hint_for(prompt, None), "")

    def test_keep_cue_matching(self):
        self.assertTrue(hook._keep_cue("idea: use sqlite for this index"))
        self.assertTrue(hook._keep_cue("Decision: keep the lock file"))
        self.assertFalse(hook._keep_cue("ideas for later, undecided"))
        long = "a preamble that is well past the sixty characters a slug would keep, then "
        self.assertTrue(hook._keep_cue(long + "guardalo ahora", ["guárdalo"]))  # accents off, full length
        self.assertFalse(hook._keep_cue("plain C code in a long enough prompt", ["C++"]))
        self.assertTrue(hook._keep_cue("a note about C++ templates", ["C++"]))
        self.assertFalse(hook._keep_cue("guardalos todos por favor", ["guárdalo"]))  # whole words
        self.assertTrue(hook._keep_cue("请保存以下内容", ["保存"]))
        self.assertTrue(hook._keep_cue("ภาษาไทย", ["ไทย"]))
        self.assertFalse(hook._keep_cue("anything at all", ["\u0301", "("]))  # nothing left, or no match

    def test_secret_prompt_ignored(self):
        self.assertEqual(hook.hint_for("remember this password: hunter2hunter2 for kubernetes pod networking", self.v), "")

    def _index(self):
        return self.v.state / "index.db"

    def test_hook_silent_without_index_and_creates_nothing(self):
        shutil.rmtree(self.v.state, ignore_errors=True)
        self.assertEqual(hook.hint_for("how does kubernetes pod networking route traffic here?", self.v), "")
        self.assertFalse(self._index().exists())
        self.assertFalse(self.v.state.exists())

    def test_hook_reads_index_without_modifying_it(self):
        before = (self._index().read_bytes(), self._index().stat().st_mtime_ns)
        # a new page makes the index stale; the hook must not sync it
        self.v.keep("concept", "Fresh topic zebra", "zebra stripes unique", "b", domain="engineering")
        h = hook.hint_for("how does kubernetes pod networking route traffic here?", self.v)
        self.assertIn("kubernetes-pod-networking", h)
        self.assertEqual(hook.hint_for("zebra stripes unique question please", self.v), "")
        self.assertEqual((self._index().read_bytes(), self._index().stat().st_mtime_ns), before)

    def test_find_sync_default_unchanged(self):
        self.assertTrue(search.find(self.v, "kubernetes"))
        self.assertTrue(self._index().exists())

    def _run(self, stdin, env_extra=None):
        env = dict(os.environ, MENTAT_CONFIG=self.cfg, PYTHONIOENCODING="utf-8")
        env.update(env_extra or {})
        repo = Path(__file__).resolve().parent.parent
        return subprocess.run([sys.executable, "-m", "mentat_wiki.hook"], input=stdin.encode("utf-8"),
                              capture_output=True, cwd=repo, env=env, timeout=30)

    def test_process_outputs_json_utf8(self):
        r = self._run(json.dumps({"cwd": str(self.root), "prompt": "please save this, a très useful finding"}))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.decode("utf-8"))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_process_limits_hints_to_vault_and_registered_folders(self):
        project = Path(self.tmp.name) / "project"
        config.register(project, "demo")
        prompt = "remember this kubernetes pod networking route"
        for folder in (project / "src", self.root / "wiki", Path(self.tmp.name) / "vault-other"):
            with self.subTest(folder=folder):
                result = self._run(json.dumps({"cwd": str(folder), "prompt": prompt}))
                self.assertEqual(result.returncode, 0)
                if folder.name == "vault-other":
                    self.assertEqual(result.stdout, b"")
                else:
                    hint = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                    self.assertIn("capturing", hint)
                    self.assertIn("kubernetes-pod-networking", hint)

    def test_process_never_fails(self):
        for stdin in ("not json", "", "[1,2]"):
            r = self._run(stdin)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout, b"")
        r = self._run('{"prompt": "kubernetes pod networking question here"}',
                      {"MENTAT_CONFIG": str(Path(self.tmp.name) / "missing" / "x.json")})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
