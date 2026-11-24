import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mentat_wiki import cli, config, doctor, search, statusline, util
from mentat_wiki.vault import Vault, VaultError

FALLBACK_ORIGIN = r"^session:\d{4}-\d{2}-\d{2}-\d{4}$"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        claude_env = patch.dict(os.environ, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "claude"))
        claude_env.start()
        self.addCleanup(claude_env.stop)
        self.root = Path(self.tmp.name) / "vault"
        self.work = Path(self.tmp.name) / "work" / "demo"
        self.work.mkdir(parents=True)
        os.environ["MENTAT_CONFIG"] = str(Path(self.tmp.name) / "config.json")
        os.environ.pop("MENTAT_VAULT", None)
        os.environ.pop("MENTAT_CMD", None)
        self.v = Vault(self.root)
        self.v.scaffold()
        config.save({"vault": str(self.root)})

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                cli.main(list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()


class TestUtil(unittest.TestCase):
    def test_slugify_accents(self):
        self.assertEqual(util.slugify("Crème Brûlée: Łódź/Straße ñ ı İ?"), "creme-brulee-lodz-strasse-n-i-i")

    def test_frontmatter_roundtrip_quotes_colons(self):
        text = util.render_page({"type": "idea", "summary": "a: b # c", "value": 4}, "# T\n\nbody")
        meta, body = util.parse_frontmatter(text)
        self.assertEqual(meta["summary"], "a: b # c")
        self.assertEqual(meta["value"], "4")
        self.assertTrue(body.startswith("# T"))

    def test_privacy_scan(self):
        self.assertTrue(util.privacy_scan("key sk-abcdefghijklmnopqrstuv"))
        self.assertTrue(util.privacy_scan("mail me at a.b@corp-mail.net"))
        self.assertTrue(util.privacy_scan(r"see C:\Users\someone\file"))
        self.assertTrue(util.privacy_scan("password: hunter22x"))
        self.assertEqual(util.privacy_scan("plain engineering note about caching"), [])


class TestKeep(Base):
    def test_idea_goes_to_right_folder_and_index(self):
        p = self.v.keep("idea", "Offline voice notes", "Record, transcribe locally", "why", value=4, effort=2)
        self.assertEqual(p.relative_to(self.root).as_posix(), "wiki/ideas/offline-voice-notes.md")
        meta, _ = util.parse_frontmatter(p.read_text(encoding="utf-8"))
        self.assertEqual((meta["type"], meta["idea_status"], meta["value"]), ("idea", "parked", "4"))
        idx = self.v.index.read_text(encoding="utf-8")
        self.assertIn("- [[offline-voice-notes]]: Record, transcribe locally (other)", idx)
        self.assertEqual(idx.count("_(none yet)_"), 6)

    def test_duplicate_refused(self):
        self.v.keep("thought", "Same", "s")
        with self.assertRaises(VaultError):
            self.v.keep("thought", "Same", "s")

    def test_secret_refused_and_nothing_written(self):
        with self.assertRaises(VaultError):
            self.v.keep("thought", "Leaky", "has a key", "token: abcdef123456")
        self.assertFalse((self.root / "wiki/thoughts/leaky.md").exists())

    def test_bad_type_and_value(self):
        with self.assertRaises(VaultError):
            self.v.keep("project", "x", "y")
        with self.assertRaises(VaultError):
            self.v.keep("idea", "x", "y", value=9)

    def test_events_pending_and_statusline(self):
        self.v.propose("idea", "Maybe")
        self.assertEqual(len(self.v.pending()), 1)
        self.v.keep("idea", "Maybe", "kept it")
        self.assertEqual(self.v.pending(), [])
        self.v.propose("thought", "No thanks")
        self.v.feedback("thought", "No thanks", "rejected")
        self.assertEqual(self.v.pending(), [])
        outcomes = [e["outcome"] for e in self.v.events()]
        self.assertEqual(outcomes, ["kept", "rejected"])
        line = statusline.render(json.dumps({"cwd": str(self.work)}))
        self.assertIn("kept 1 today", line)
        self.assertIn("💡1", line)

    def test_via_proposal_vs_explicit_and_expiry(self):
        self.v.propose("idea", "Proposed one")
        self.v.keep("idea", "Proposed one", "s")
        self.v.keep("idea", "Direct one", "s")
        vias = [e["via"] for e in self.v.events() if e["outcome"] == "kept"]
        self.assertEqual(vias, ["proposal", "explicit"])
        self.v.propose("thought", "Old")
        items = self.v.pending()
        items[0]["ts"] -= 90000
        self.v._set_pending(items)
        self.assertEqual(self.v.pending(), [])

    def test_decide_clears_pending_by_title(self):
        self.v.register_project("demo")
        self.v.propose("decision", "Hooks first")
        self.v.decide("demo", "Start with SessionStart only", "minimal", title="Hooks first")
        self.assertEqual(self.v.pending(), [])
        self.assertEqual(self.v.events()[-1]["via"], "proposal")

    def test_inbox(self):
        self.v.inbox_add("look into thing later")
        self.assertIn("- [ ]", (self.root / "inbox/inbox.md").read_text(encoding="utf-8"))


class TestProject(Base):
    def test_register_decide_wrap_context(self):
        code, out, _ = self.run_cli("project", "register", "demo", "--path", str(self.work))
        self.assertEqual(code, 0, out)
        self.assertEqual(config.project_for(self.work / "sub"), "demo")
        self.v.decide("demo", "Use SQLite", "stdlib, no deps", "Postgres | too heavy")
        dec = (self.root / "wiki/projects/demo/decisions.md").read_text(encoding="utf-8")
        self.assertIn("Use SQLite", dec)
        self.assertIn("Postgres / too heavy", dec)
        self.v.wrap("demo", "Built the CLI core.", "Write skills", ["hook design", "name check"])
        st = (self.root / "wiki/projects/demo/status.md").read_text(encoding="utf-8")
        self.assertIn("Built the CLI core.", st)
        self.assertIn("- [ ] hook design", (self.root / "wiki/projects/demo/open-threads.md").read_text(encoding="utf-8"))
        self.assertIn("demo: wrap", self.v.log.read_text(encoding="utf-8"))
        code, out, _ = self.run_cli("context", "--cwd", str(self.work))
        self.assertIn("Built the CLI core.", out)
        code, _, err = self.run_cli("wrap", "--project", "demo", "--where", "Done.", "--thread", "")
        self.assertEqual(code, 0, err)  # an empty --thread clears the list, as the /wrap skill says
        threads = (self.root / "wiki/projects/demo/open-threads.md").read_text(encoding="utf-8")
        self.assertNotIn("hook design", threads)
        self.assertTrue(threads.rstrip().endswith("- [ ]"))
        self.assertIn("Mentat capture protocol", out)

    def test_context_silent_when_unregistered(self):
        code, out, _ = self.run_cli("context", "--cwd", str(self.work))
        self.assertEqual((code, out), (0, ""))

    def test_doctor_clean_with_project(self):
        self.v.register_project("demo")
        self.v.wrap("demo", "Started.", "Next", ["one"])
        errs = [m for s, m in doctor.run(self.v) if s == "error"]
        self.assertEqual(errs, [])

    def test_unregistered_project_errors(self):
        with self.assertRaises(VaultError):
            self.v.decide("ghost", "x")

    def test_wrap_from_unregistered_folder(self):
        """/wrap run from the vault folder: no folder mapping, so --project names the project,
        and without it the error lists the known projects."""
        self.v.register_project("alpha")
        self.v.register_project("beta")
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        code, _, err = self.run_cli("wrap", "--where", "x")
        self.assertEqual(code, 2)
        self.assertIn("--project", err)
        self.assertIn("alpha, beta", err)
        code, _, err = self.run_cli("wrap", "--project", "ghost", "--where", "x")
        self.assertEqual(code, 2)
        self.assertIn("Known projects: alpha, beta", err)
        code, out, err = self.run_cli("decide", "--project", "beta", "--decision", "Keep vault unregistered")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("wrap", "--project", "beta", "--where", "Wrapped from the vault.",
                                      "--thread", "t1")
        self.assertEqual(code, 0, err)
        st = (self.root / "wiki/projects/beta/status.md").read_text(encoding="utf-8")
        self.assertIn("Wrapped from the vault.", st)
        self.assertNotIn("Wrapped", (self.root / "wiki/projects/alpha/status.md").read_text(encoding="utf-8"))
        self.assertEqual(self.v.projects(), ["alpha", "beta"])

    def test_statusline_dim_without_project(self):
        line = statusline.render(json.dumps({"cwd": str(self.work)}))
        self.assertIn("🧠 –", line)
        self.assertIn("\x1b[2m", line)


class TestStatusSession(Base):
    def _line(self, **extra):
        return statusline.render(json.dumps({"cwd": str(self.work), **extra}))

    def test_shows_session_id(self):
        self.assertIn("🔑 abcd1234", self._line(session_id="abcd1234-ffff-0000"))

    def test_no_warning_when_slot_matches(self):
        util.record_session("abcd1234", cwd=self.work)
        line = self._line(session_id="abcd1234-ffff-0000")
        self.assertIn("🔑 abcd1234", line)
        self.assertNotIn("⚠", line)

    def test_warns_when_slot_belongs_to_another_session(self):
        util.record_session("ffff0000", cwd=self.work)
        line = self._line(session_id="abcd1234-ffff-0000")
        self.assertIn("🔑 abcd1234", line)
        self.assertIn("⚠ origin slot ffff0000", line)

    def test_dash_without_session_id_or_bad_input(self):
        self.assertIn("🔑 –", self._line())
        self.assertIn("🔑 –", statusline.render("not json"))
        self.assertIn("🔑 –", self._line(session_id=123))


class TestSearchAndDoctor(Base):
    def test_find_ranks_and_ideas_order(self):
        self.v.keep("idea", "Weekly review ritual", "Review the vault every week", value=5, effort=1)
        self.v.keep("idea", "Giant rewrite", "Rewrite everything in Rust", value=3, effort=5)
        self.v.keep("thought", "Caching note", "Why local caching helps")
        rows = search.find(self.v, "caching")
        self.assertEqual(rows[0][0], "wiki/thoughts/caching-note.md")
        self.assertEqual(search.find(self.v, "weekl")[0][3], "Weekly review ritual")
        ranked = search.ideas(self.v)
        self.assertEqual(ranked[0][1], "Weekly review ritual")
        self.assertEqual(search.find(self.v, "nonexistentterm"), [])

    def test_doctor_clean_then_catches_problems(self):
        self.v.keep("idea", "Fine idea", "ok")
        errs = [m for s, m in doctor.run(self.v) if s == "error"]
        self.assertEqual(errs, [])
        bad = self.root / "wiki/ideas/bad.md"
        bad.write_text("---\ntype: thought\ndomain: nope\n---\n\n# Bad\n[[missing-page]]\n", encoding="utf-8")
        msgs = " ".join(m for s, m in doctor.run(self.v) if s == "error")
        self.assertIn("does not belong in wiki/ideas/", msgs)
        self.assertIn("unknown domain", msgs)
        self.assertIn("broken link [[missing-page]]", msgs)
        self.assertIn("not listed in wiki/index.md", msgs)

    def test_cli_exit_codes(self):
        self.v.keep("idea", "Fine idea", "ok")
        self.assertEqual(self.run_cli("doctor")[0], 0)
        code, _, err = self.run_cli("keep", "--type", "idea", "--title", "Leak", "--summary", "x",
                                    "--body", "api_key=abcdefghij")
        self.assertEqual(code, 2)
        self.assertIn("sensitive", err)


class TestNoteAndHandover(Base):
    def setUp(self):
        super().setUp()
        self.v.register_project("demo")
        config.register(self.work, "demo")

    def test_note_creates_then_appends_and_is_clean(self):
        p = self.v.note("demo", "lr 3e-4, batch 32 -> loss 0.41, out/run1", "worked")
        self.v.note("demo", "lr 1e-3 diverged after 200 steps", "failed")
        text = p.read_text(encoding="utf-8")
        self.assertIn("[worked] lr 3e-4", text)
        self.assertIn("[failed] lr 1e-3 diverged", text)
        self.assertEqual(text.count("# demo: experiments"), 1)
        self.assertEqual([m for s, m in doctor.run(self.v) if s == "error"], [])

    def test_note_refuses_secrets_and_bad_result(self):
        with self.assertRaises(VaultError):
            self.v.note("demo", "used api_key=abcdef123456 for the run")
        with self.assertRaises(VaultError):
            self.v.note("demo", "x", "great")
        self.assertFalse((self.root / "wiki/projects/demo/experiments.md").exists())

    def test_handover_is_paste_ready_and_bounded(self):
        self.v.wrap("demo", "Training loop works.", "Try lr 5e-4", ["compare optimizers"])
        self.v.decide("demo", "Use AdamW", "stable", "SGD")
        self.v.note("demo", "AdamW lr 3e-4 -> 0.41", "worked")
        out = self.v.handover("demo")
        for needle in ["Training loop works.", "Try lr 5e-4", "[worked] AdamW", "compare optimizers",
                       "Use AdamW (why: stable)", "Start by restating"]:
            self.assertIn(needle, out)
        self.assertNotIn("See [[", out)
        for i in range(80):
            self.v.note("demo", f"attempt {i} " + "x" * 60)
        self.assertLessEqual(len(self.v.handover("demo", 1000)), 1100)

    def test_context_includes_recent_notes_and_cli_works(self):
        self.v.note("demo", "first try failed on windows path", "failed")
        code, out, _ = self.run_cli("context", "--cwd", str(self.work))
        self.assertIn("first try failed", out)
        code, out, _ = self.run_cli("note", "--result", "info", "second try")
        self.assertEqual(code, 2)  # cwd of the test process is not a registered folder
        code, out, _ = self.run_cli("note", "--project", "demo", "second try")
        self.assertEqual(code, 0)


class TestHardening(Base):
    """Regression tests for defects found by the independent code review."""

    def test_privacy_scan_variants(self):
        for text in ["client_secret=abcdef123456", "GITHUB_TOKEN=xyz12345678",
                     '"api_key": "abcdefghijk"', "AWS_SECRET_ACCESS_KEY=abcdefghij",
                     "C:/Users/someone/x", r"C:\\Users\\someone\\x", "/home/someone/x"]:
            self.assertTrue(util.privacy_scan(text), text)
        self.assertEqual(util.privacy_scan("tokens are counted per request"), [])

    def test_every_user_string_is_scanned(self):
        with self.assertRaises(VaultError):
            self.v.keep("thought", "t", "s", origin="me@corp-mail.net")
        with self.assertRaises(VaultError):
            self.v.keep("idea", "t", "s", est_days="C:/Users/me/x")
        with self.assertRaises(VaultError):
            self.v.propose("idea", "ping me@corp-mail.net")
        with self.assertRaises(VaultError):
            self.v.feedback("idea", "key sk-abcdefghijklmnopqrstu", "rejected")
        self.v.register_project("demo")
        with self.assertRaises(VaultError):
            self.v.decide("demo", "fine", title="mail me@corp-mail.net")
        self.assertEqual(self.v.pending(), [])
        self.assertEqual(self.v.events(), [])

    def test_newlines_cannot_inject_frontmatter(self):
        p = self.v.keep("thought", "t", "s", origin="chat\n---\nsecret notes here")
        meta, _ = util.parse_frontmatter(p.read_text(encoding="utf-8"))
        self.assertEqual(meta["origin"], "chat --- secret notes here")
        self.assertEqual(meta["status"], "draft")

    def test_index_entry_not_masked_by_mention(self):
        self.v.keep("concept", "bar", "relates to [[foo]]")
        self.v.keep("concept", "foo", "the foo page")
        idx = self.v.index.read_text(encoding="utf-8")
        self.assertIn("- [[foo]]: the foo page", idx)
        self.assertNotIn("[[foo]]", idx.split("- [[bar]]")[1].split("\n")[0])
        self.assertEqual([m for s, m in doctor.run(self.v) if s == "error"], [])

    def test_non_latin_titles_do_not_collide(self):
        a = self.v.keep("thought", "日本語のメモ", "s")
        b = self.v.keep("thought", "Привет мир", "s")
        self.assertNotEqual(a.name, b.name)
        self.assertEqual(util.slugify("Größe"), "grosse")

    def test_same_title_refused_other_title_gets_suffix(self):
        self.v.keep("thought", "Foo bar", "s")
        with self.assertRaises(VaultError):
            self.v.keep("thought", "Foo bar", "s")
        other = self.v.keep("thought", "Foo, bar!", "s")
        self.assertEqual(other.name, "foo-bar-2.md")
        cross = self.v.keep("concept", "Foo bar", "s")
        self.assertEqual(cross.name, "foo-bar-3.md")

    def test_find_without_searchable_words_returns_nothing(self):
        self.v.keep("thought", "Something", "s")
        self.assertEqual(search.find(self.v, "???"), [])

    def test_bom_and_bad_encoding_do_not_crash(self):
        d = self.root / "wiki" / "thoughts"
        (d / "bom.md").write_bytes(b"\xef\xbb\xbf---\ntype: thought\ndomain: other\nsummary: bom page\n---\n\n# Bom\n")
        (d / "latin.md").write_bytes("---\ntype: thought\ndomain: other\nsummary: x\n---\n\n# caf\xe9\n".encode("latin-1"))
        self.assertEqual(search.find(self.v, "bom")[0][4], "bom page")
        msgs = [m for s, m in doctor.run(self.v)]
        self.assertTrue(any("not valid UTF-8" in m for m in msgs))

    def test_write_atomic_cleans_up_when_replace_keeps_failing(self):
        from unittest import mock
        target = self.root / "inbox" / "x.md"
        with mock.patch("mentat_wiki.util.os.replace", side_effect=PermissionError), \
                mock.patch("mentat_wiki.util.time.sleep"):
            with self.assertRaises(PermissionError):
                util.write_atomic(target, "hi")
        self.assertEqual([f.name for f in target.parent.iterdir() if f.name.startswith(".tmp-")], [])

    def test_lock_times_out_fast_and_breaks_only_stale(self):
        state = self.root / ".mentat"
        state.mkdir(exist_ok=True)
        lk = state / "lock"
        lk.write_text("x")
        t0 = __import__("time").time()
        with self.assertRaises(TimeoutError):
            with util.lock(state, timeout=0.3):
                pass
        self.assertLess(__import__("time").time() - t0, 3)
        old = __import__("time").time() - 300
        os.utime(lk, (old, old))
        with util.lock(state, timeout=1):
            pass

    def test_context_never_fails_as_a_hook(self):
        config.save({"projects": {os.path.normcase(os.path.abspath(self.work)): "demo"}})
        code, out, err = self.run_cli("context", "--cwd", str(self.work))
        self.assertEqual((code, out), (0, ""))
        config.save({"vault": str(self.root / "missing"), "projects": {
            os.path.normcase(os.path.abspath(self.work)): "demo"}})
        code, out, err = self.run_cli("context", "--cwd", str(self.work))
        self.assertEqual((code, out), (0, ""))

    def test_stdin_is_read_as_utf8(self):
        import subprocess
        import sys
        env = dict(os.environ, MENTAT_VAULT=str(self.root), MENTAT_CONFIG=os.environ["MENTAT_CONFIG"])
        repo = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, "-m", "mentat_wiki", "keep", "--type", "thought", "--title", "u",
                            "--summary", "s", "--body", "-"], input="Crème brûlée Łódź Straße 日本".encode("utf-8"),
                           capture_output=True, cwd=repo, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root / "wiki/thoughts/u.md").read_text(encoding="utf-8")
        self.assertIn("Crème brûlée Łódź Straße 日本", text)


class TestSessionPersist(Base):
    def _ctx(self, stdin, env_file=None):
        import subprocess
        import sys
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"}
        env.update(MENTAT_CONFIG=os.environ["MENTAT_CONFIG"], PYTHONIOENCODING="utf-8")
        if env_file:
            env["CLAUDE_ENV_FILE"] = str(env_file)
        repo = Path(__file__).resolve().parent.parent
        return subprocess.run([sys.executable, "-m", "mentat_wiki", "context", "--cwd", str(self.work)],
                              input=stdin.encode("utf-8"), capture_output=True, cwd=repo, env=env, timeout=30)

    def test_writes_export_line(self):
        f = Path(self.tmp.name) / "envfile"
        f.write_text("export OTHER=1\n", encoding="utf-8")
        r = self._ctx(json.dumps({"session_id": "abcd1234-ef56-7890", "cwd": "x"}), f)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))
        self.assertEqual(f.read_text(encoding="utf-8"), "export OTHER=1\nexport MENTAT_SESSION=abcd1234\n")

    def test_sanitizes_id(self):
        f = Path(self.tmp.name) / "envfile"
        self._ctx(json.dumps({"session_id": "$(x);'a b-c_dEFGH"}), f)
        self.assertEqual(f.read_text(encoding="utf-8"), "export MENTAT_SESSION=xab-c_dE\n")

    def test_no_env_file_is_noop(self):
        r = self._ctx(json.dumps({"session_id": "abcd1234"}))
        self.assertEqual((r.returncode, r.stderr), (0, b""))

    def test_bad_stdin_never_fails(self):
        f = Path(self.tmp.name) / "envfile"
        for stdin in ("", "not json", "[1,2]", '{"session_id": 5}', '{"session_id": "!!!"}'):
            r = self._ctx(stdin, f)
            self.assertEqual((r.returncode, r.stderr), (0, b""), stdin)
        self.assertFalse(f.exists())

    def test_unwritable_env_file_never_fails(self):
        r = self._ctx(json.dumps({"session_id": "abcd1234"}), Path(self.tmp.name) / "no" / "dir" / "f")
        self.assertEqual((r.returncode, r.stderr), (0, b""))


class TestSessionState(Base):
    """Shell-independent session id (sessions.json) and SessionStart index sync."""

    def setUp(self):
        super().setUp()
        self._env = {k: os.environ.pop(k, None) for k in ("MENTAT_SESSION", "CLAUDE_SESSION_ID")}
        self.sessions = Path(os.environ["MENTAT_CONFIG"]).parent / "sessions.json"
        self.cwd0 = os.getcwd()
        self.addCleanup(os.chdir, self.cwd0)

    def tearDown(self):
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        super().tearDown()

    def _ctx(self, stdin, cwd=None):
        import subprocess
        import sys
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"}
        env.update(MENTAT_CONFIG=os.environ["MENTAT_CONFIG"], PYTHONIOENCODING="utf-8")
        repo = Path(__file__).resolve().parent.parent
        return subprocess.run([sys.executable, "-m", "mentat_wiki", "context", "--always"],
                              input=stdin.encode("utf-8"), capture_output=True, cwd=repo, env=env, timeout=30)

    def _origin_in(self, folder):
        os.chdir(folder)
        return util.default_origin()

    def test_context_records_session_for_cwd(self):
        r = self._ctx(json.dumps({"session_id": "abcd1234-ef", "cwd": str(self.work), "prompt": "TOPSECRETPROMPT"}))
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        raw = self.sessions.read_text(encoding="utf-8")
        self.assertNotIn("TOPSECRETPROMPT", raw)
        self.assertEqual(self._origin_in(self.work), "session:abcd1234")

    def test_precedence(self):
        util.record_session("fromfile", self.work)
        os.chdir(self.work)
        self.assertEqual(util.default_origin(), "session:fromfile")
        os.environ["CLAUDE_SESSION_ID"] = "claude123456"
        self.assertEqual(util.default_origin(), "session:claude12")
        os.environ["MENTAT_SESSION"] = "mentat999"
        self.assertEqual(util.default_origin(), "session:mentat99")
        self.assertEqual(util.default_origin("session:x"), "session:x")

    def test_stale_entry_ignored(self):
        import time
        util.record_session("oldoldol", self.work, now=time.time() - 25 * 3600)
        self.assertRegex(self._origin_in(self.work), FALLBACK_ORIGIN)
        util.record_session("freshone", self.work, now=time.time() - 23 * 3600)
        self.assertEqual(self._origin_in(self.work), "session:freshone")

    def test_different_cwd_ignored_and_no_collision(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        util.record_session("aaaaaaaa", self.work)
        util.record_session("bbbbbbbb", other)
        self.assertEqual(self._origin_in(self.work), "session:aaaaaaaa")
        self.assertEqual(self._origin_in(other), "session:bbbbbbbb")
        third = Path(self.tmp.name) / "third"
        third.mkdir()
        self.assertRegex(self._origin_in(third), FALLBACK_ORIGIN)

    def test_subfolder_uses_nearest_recorded_parent(self):
        sub = self.work / "a" / "b"
        sub.mkdir(parents=True)
        util.record_session("parent01", self.work)
        self.assertEqual(self._origin_in(sub), "session:parent01")

    def test_corrupt_state_never_fails(self):
        self.sessions.write_text("{not json", encoding="utf-8")
        self.assertRegex(self._origin_in(self.work), FALLBACK_ORIGIN)
        util.record_session("recover1", self.work)
        self.assertEqual(self._origin_in(self.work), "session:recover1")

    def test_bad_stdin_writes_nothing(self):
        for stdin in ("", "nope", "[1]", '{"session_id": 5}', '{"session_id": "!!!"}'):
            r = self._ctx(stdin)
            self.assertEqual((r.returncode, r.stderr), (0, b""), stdin)
        self.assertFalse(self.sessions.exists())

    def test_context_syncs_index_output_unchanged(self):
        from mentat_wiki import search
        self.v.keep("concept", "Zebra crossing", "stripes on roads", "b", domain="engineering")
        idx = self.v.state / "index.db"
        idx.unlink(missing_ok=True)
        self.assertEqual(search.find(self.v, "zebra", sync=False), [])  # no index yet
        with_sync = self._ctx(json.dumps({"session_id": "abcd1234", "cwd": str(self.work)}))
        self.assertTrue(idx.is_file())
        self.assertEqual(len(search.find(self.v, "zebra", sync=False)), 1)
        no_stdin = self._ctx("")
        self.assertEqual(with_sync.stdout, no_stdin.stdout)
        self.assertEqual(with_sync.stderr, b"")

    def test_hook_stays_read_only(self):
        from mentat_wiki import hook, search
        search.sync(self.v)
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        sess_before = self.sessions.exists()
        hook.hint_for("how does kubernetes pod networking route traffic here?", self.v)
        after = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(sess_before, self.sessions.exists())


class TestOrigin(Base):
    def setUp(self):
        super().setUp()
        self._env = {k: os.environ.pop(k, None) for k in ("MENTAT_SESSION", "CLAUDE_SESSION_ID")}

    def tearDown(self):
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        super().tearDown()

    def meta(self, rel):
        return util.parse_frontmatter((self.root / rel).read_text(encoding="utf-8"))[0]

    def test_default_origin_chain(self):
        self.assertRegex(util.default_origin(), FALLBACK_ORIGIN)
        os.environ["CLAUDE_SESSION_ID"] = "abcdef12-3456"
        self.assertEqual(util.default_origin(), "session:abcdef12")
        os.environ["MENTAT_SESSION"] = "zzzzzzzz9"
        self.assertEqual(util.default_origin(), "session:zzzzzzzz")
        self.assertEqual(util.default_origin("session:mine"), "session:mine")

    def test_keep_cli_fills_origin_for_all_types(self):
        for t, d in (("idea", "ideas"), ("concept", "concepts"), ("thought", "thoughts")):
            code, out, err = self.run_cli("keep", "--type", t, "--title", f"T {t}", "--summary", "s",
                                          "--domain", "engineering", "--body", "b")
            self.assertEqual(code, 0, err)
            m = self.meta(f"wiki/{d}/t-{t}.md")
            self.assertRegex(m["origin"], FALLBACK_ORIGIN)
            for k in ("summary", "domain", "created", "updated", "auto"):
                self.assertIn(k, m)
        self.assertEqual([e["type"] for e in self.v.events() if e["outcome"] == "kept"],
                         ["idea", "concept", "thought"])
        code, _, _ = self.run_cli("keep", "--type", "thought", "--title", "Explicit", "--summary", "s",
                                  "--origin", "session:deadbeef")
        self.assertEqual(self.meta("wiki/thoughts/explicit.md")["origin"], "session:deadbeef")

    def test_decide_cli_fills_origin(self):
        self.v.register_project("demo")
        os.environ["MENTAT_SESSION"] = "feed1234"
        code, _, err = self.run_cli("decide", "--project", "demo", "--decision", "Pick X")
        self.assertEqual(code, 0, err)
        row = [l for l in (self.root / "wiki/projects/demo/decisions.md").read_text(encoding="utf-8").splitlines()
               if "Pick X" in l][0]
        self.assertTrue(row.rstrip().endswith("| session:feed1234 |"))


class TestCommand(Base):
    """The mentat-wiki command shown to agents is configurable (the console script may not be on PATH)."""

    def test_default_command_is_mentat_wiki(self):
        self.assertEqual(config.command(), "mentat-wiki")
        text = cli.protocol()
        self.assertIn("`mentat-wiki propose", text)
        self.assertNotIn("{cmd}", text)
        self.assertNotIn("On this machine", text)

    def test_old_console_script_name_is_not_kept(self):
        """`mentat` was the script name before 0.1.0 and belongs to an unrelated package."""
        config.save({**config.load(), "command": "mentat"})
        self.assertEqual(config.command(), "mentat-wiki")
        self.assertNotIn("On this machine", cli.protocol())

    def test_protocol_logs_user_decisions_directly(self):
        text = cli.protocol()
        self.assertIn("Log decisions the user makes or approves directly", text)
        self.assertIn("propose --type", text)

    def test_config_sets_and_resets_command(self):
        code, out, _ = self.run_cli("config", "--command", "py -3 -m mentat_wiki")
        self.assertEqual(code, 0)
        self.assertIn("command: py -3 -m mentat_wiki", out)
        self.assertEqual(config.load()["vault"], str(self.root))  # vault kept
        text = cli.protocol()
        self.assertIn("`py -3 -m mentat_wiki decide", text)
        self.assertIn("On this machine the command is `py -3 -m mentat_wiki`", text)
        self.assertNotIn("{cmd}", text)
        self.run_cli("config", "--command", "")
        self.assertEqual(config.command(), "mentat-wiki")
        self.assertNotIn("command", config.load())

    def test_env_overrides_config(self):
        self.run_cli("config", "--command", "py -3 -m mentat_wiki")
        os.environ["MENTAT_CMD"] = "uvx mentat-wiki"
        self.addCleanup(os.environ.pop, "MENTAT_CMD", None)
        self.assertEqual(config.command(), "uvx mentat-wiki")

    def test_hook_subcommand_is_silent_and_never_fails(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, "-m", "mentat_wiki", "hook"], input=b"not json",
                           capture_output=True, timeout=30, env=dict(os.environ))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")


if __name__ == "__main__":
    unittest.main()
