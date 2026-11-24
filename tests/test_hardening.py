import io
import json
import sys
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from mentat_wiki import config, util
from mentat_wiki.vault import VaultError
from tests.test_mentat import Base
from tests.test_portability import FALSE_POSITIVES


class TestHardening(Base):
    def test_provider_credentials_refused_before_capture(self):
        tokens = [prefix + "a" * 36 for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_")]
        tokens += ["github_pat_" + "A" * 22 + "_" + "b" * 59]
        tokens += [f"xox{kind}-1234567890-ABCDEFGHIJK" for kind in "abprs"]
        tokens += [prefix + "x" * 24 for prefix in ("sk_live_", "rk_live_")]
        tokens += [prefix + "a" * 20 for prefix in ("sk-", "sk-proj-", "sk-ant-")]
        tokens += ["AIza" + "a" * 35, "eyJabc.eyJdef.abc_123-xyz"]
        for token in tokens:
            for body in (token, f"The output included ({token})."):
                with self.subTest(prefix=token[:10]), self.assertRaisesRegex(VaultError, "sensitive"):
                    self.v.keep("thought", "Test capture", "Test summary", body)
        self.assertEqual(list(self.v.pages()), [])
        for phrase in FALSE_POSITIVES:
            self.assertEqual(util.privacy_scan(phrase), [], phrase)

    def test_reserved_slugs(self):
        names = ["con", "prn", "aux", "nul"]
        names += [f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)]
        for name in names:
            self.assertEqual(util.slugify(name.upper()), name + "-note")
            self.assertEqual(util.slugify(name + ".md"), name + "-md-note")
        self.assertEqual(util.slugify("com10"), "com10")
        self.assertEqual(util.slugify("console"), "console")

    def test_context_files_read_independently(self):
        d = self.v.register_project("demo")
        config.register(self.work, "demo")
        files = [d / "status.md", d / "open-threads.md", d / "experiments.md",
                 self.root / "core" / "extra.md"]
        markers = [f"optional file {i}" for i in range(len(files))]
        for path, marker in zip(files, markers):
            util.write_atomic(path, "- " + marker)
        for path, marker in zip(files, markers):
            for invalid in (False, True):
                with self.subTest(path=path.name, invalid=invalid):
                    if invalid:
                        path.write_bytes(b"\xff")
                    else:
                        path.unlink()
                    with patch("sys.stdin", io.StringIO("")):
                        code, out, err = self.run_cli("context", "--cwd", str(self.work), "--max-chars", "50000")
                    self.assertEqual((code, err), (0, ""))
                    self.assertNotIn(marker, out)
                    for other in markers:
                        if other != marker:
                            self.assertIn(other, out)
                    util.write_atomic(path, "- " + marker)

    def test_context_with_malformed_configuration(self):
        with patch("sys.stdin", io.StringIO("")):
            for cfg in ([], {"vault": str(self.root), "projects": None},
                        {"vault": str(self.root), "projects": "demo"}):
                util.write_atomic(config.config_path(), json.dumps(cfg))
                self.assertEqual(self.run_cli("context", "--cwd", str(self.work)), (0, "", ""))
            code, out, err = self.run_cli("context", "--always", "--cwd", str(self.work))
            self.assertEqual((code, err), (0, ""))
            self.assertIn("no project registered", out)

    def test_context_discards_partial_output_on_unexpected_error(self):
        def fail(*_):
            print("partial context")
            print("partial diagnostic", file=sys.stderr)
            raise RuntimeError("context failed")

        with patch("sys.stdin", io.StringIO("")), patch("mentat_wiki.cli.protocol", side_effect=fail):
            self.assertEqual(self.run_cli("context", "--cwd", str(self.root)), (0, "", ""))
            with self.assertRaisesRegex(RuntimeError, "context failed"):
                self.run_cli("context", "--always")

    def test_corrupt_queue_preserved_once_per_recovery(self):
        path = self.v.state / "pending.json"
        self.v.state.mkdir(exist_ok=True)
        contents = [b"[", b'[{"title":"\xff"}]', b"{}"]
        err = io.StringIO()
        with redirect_stderr(err), patch("mentat_wiki.vault.time.strftime", return_value=".bad-20260101-000000"):
            for i, original in enumerate(contents):
                path.write_bytes(original)
                self.assertEqual(self.v.pending(), [])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(len(list(self.v.state.glob("pending.json.bad-*"))), i)
                self.v.propose("idea", "Fresh")
                self.v.propose("idea", "Fresh")
                self.assertEqual([p["title"] for p in self.v.pending()], ["Fresh"])
        backups = sorted(self.v.state.glob("pending.json.bad-*"))
        self.assertEqual([p.read_bytes() for p in backups], contents)
        self.assertEqual(len(err.getvalue().splitlines()), len(contents))
        for backup in backups:
            self.assertIn(backup.name, err.getvalue())

    def test_sweep_repairs_bad_queue_without_a_proposal(self):
        self.v._set_pending([])
        path = self.v.state / "pending.json"
        path.write_bytes(b"?")
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.v.sweep_expired(), 0)
        self.assertRegex(err.getvalue(), r"pending\.json\.bad-\d{8}-\d{6}")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_failed_backup_leaves_original_queue_intact(self):
        self.v._set_pending([])
        path = self.v.state / "pending.json"
        path.write_bytes(b"[")
        with patch.object(Path, "rename", side_effect=PermissionError), self.assertRaises(PermissionError):
            self.v.propose("idea", "Fresh")
        self.assertEqual(path.read_bytes(), b"[")
        self.assertEqual(list(self.v.state.glob("pending.json.bad-*")), [])

    def test_note_refuses_invalid_utf8_and_accepts_bom(self):
        path = self.v.register_project("demo") / "experiments.md"
        original = b"# Attempts\n- \x93earlier\x94\n"
        path.write_bytes(original)
        with self.assertRaisesRegex(VaultError, "re-save experiments.md as UTF-8"):
            self.v.note("demo", "New attempt")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.v.events(), [])
        path.write_bytes("# Attempts\n- caf\u00e9\n".encode("utf-8-sig"))
        self.v.note("demo", "New attempt")
        log = path.read_text(encoding="utf-8-sig")
        self.assertIn("- caf\u00e9\n", log)
        self.assertIn("[info] New attempt", log)


import unittest  # noqa: E402


class TestContextSurvivesHousekeepingFailure(unittest.TestCase):
    def test_sweep_timeout_keeps_context(self):
        import io, os, tempfile
        from contextlib import redirect_stdout
        from pathlib import Path
        from unittest.mock import patch
        from mentat_wiki import cli, config
        from mentat_wiki.vault import Vault
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, MENTAT_CONFIG=str(Path(tmp) / "c.json")):
                v = Vault(Path(tmp) / "vault")
                v.scaffold()
                config.save({"vault": str(v.root)})
                out = io.StringIO()
                with patch.object(Vault, "sweep_expired", side_effect=TimeoutError("lock busy")), \
                        redirect_stdout(out):
                    cli.main(["context", "--cwd", str(v.root)])
                self.assertIn("Mentat capture protocol.", out.getvalue())


class TestBomAndInboxTolerance(Base):
    def test_decisions_with_bom_and_doctor_with_bad_inbox(self):
        from mentat_wiki import doctor
        self.v.register_project("demo")
        d = self.v.project_dir("demo") / "decisions.md"
        d.write_bytes(b"\xef\xbb\xbf" + d.read_bytes())
        self.v.decide("demo", "use a BOM-safe read", "test", "none", "session:test")
        self.assertFalse(d.read_bytes().startswith(b"\xef\xbb\xbf\xef\xbb\xbf"))
        self.assertIn("use a BOM-safe read", d.read_text(encoding="utf-8-sig"))
        inbox = self.root / "inbox" / "inbox.md"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_bytes(b"- [ ] caf\xe9\n")
        doctor.run(self.v)  # must not raise on a non-UTF-8 inbox
