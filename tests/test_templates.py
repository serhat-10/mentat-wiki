import io
import os
import subprocess
import sys
import tempfile
import unittest
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from mentat_wiki import cli, config, doctor, templates
from mentat_wiki.vault import DEFAULT_DOMAINS, Vault, VaultError

CORE = ["core/MEMORY.md", "core/SOUL.md", "core/USER.md", "core/capture-policy.md"]
TEMPLATES = ["_templates/" + n for n in (
    "concept.md", "entity.md", "idea.md", "output.md", "project-decisions.md",
    "project-open-threads.md", "project-status.md", "source.md", "thought.md")]
PACKAGE = Path(__file__).resolve().parent.parent / "mentat_wiki"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "vault"
        for key in ("MENTAT_CONFIG", "MENTAT_CMD", "MENTAT_VAULT", "CLAUDE_CONFIG_DIR"):
            self.addCleanup(self._restore, key, os.environ.get(key))
        os.environ["MENTAT_CONFIG"] = str(Path(self.tmp.name) / "config.json")
        os.environ["CLAUDE_CONFIG_DIR"] = str(Path(self.tmp.name) / "claude")  # never read the real ~/.claude
        os.environ.pop("MENTAT_CMD", None)
        os.environ.pop("MENTAT_VAULT", None)
        self.v = Vault(self.root)

    @staticmethod
    def _restore(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def schema(self, domains_section):
        (self.root / "CLAUDE.md").write_text(
            f"# Schema\n\nIntro.\n\n{domains_section}\n## Wiki layout\n\n- `notes`: not a domain\n",
            encoding="utf-8")


class TestScaffold(Base):
    def test_fresh_scaffold_creates_everything(self):
        created = self.v.scaffold()
        expected = ["AGENTS.md", "CLAUDE.md", *CORE, *TEMPLATES, "wiki/index.md", "wiki/log.md"]
        self.assertEqual(sorted(created), sorted(expected))
        for rel in expected:
            self.assertTrue((self.root / rel).is_file(), rel)

    def test_rerun_preserves_edits(self):
        self.v.scaffold()
        (self.root / "CLAUDE.md").write_text("# Mine\n", encoding="utf-8")
        self.assertEqual(self.v.scaffold(), [])
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# Mine\n")

    def test_missing_file_is_restored_alone(self):
        self.v.scaffold()
        (self.root / "core" / "SOUL.md").unlink()
        self.assertEqual(self.v.scaffold(), ["core/SOUL.md"])

    def test_fresh_vault_doctor_clean(self):
        self.v.scaffold()
        bad = [(s, m) for s, m in doctor.run(self.v) if s in ("error", "warn")]
        self.assertEqual(bad, [])

    def test_core_budget(self):
        total = sum(len(templates.read(rel)) for rel in CORE)
        self.assertLessEqual(total, 2200)
        self.v.scaffold()
        (self.root / "core" / "MEMORY.md").write_text("x" * 2000, encoding="utf-8")
        warns = [m for s, m in doctor.run(self.v) if s == "warn"]
        self.assertTrue(any(m.startswith("core/ is") for m in warns), warns)

    def test_schema_lists_default_domains_and_capture_policy_frozen(self):
        self.v.scaffold()
        self.assertEqual(self.v.domains(), DEFAULT_DOMAINS)
        policy = templates.read("core/capture-policy.md")
        for needle in ("min_proposals: 20", "min_acceptance: 0.9", "expiry_hours: 24",
                       "| Category | Policy | Notes |", "| chatter | never |"):
            self.assertIn(needle, policy)

    def test_templates_have_no_personal_paths(self):
        from mentat_wiki import util
        for rel in templates.names():
            self.assertEqual(util.privacy_scan(templates.read(rel)), [], rel)


class TestDomains(Base):
    def setUp(self):
        super().setUp()
        self.v.scaffold()

    def test_parses_custom_bullets(self):
        self.schema("## Domains\n\nText.\n\n- `cooking`: food\n* gardening: plants\n- `music` : sound\n"
                    "* `travel`: trips\n- Not A Domain: ignored\n")
        self.assertEqual(self.v.domains(), ["cooking", "gardening", "music", "travel", "projects", "other"])

    def test_falls_back_when_empty_or_missing(self):
        self.schema("## Domains\n\nNo bullets here.\n")
        self.assertEqual(self.v.domains(), DEFAULT_DOMAINS)
        self.schema("## Other\n\n- `cooking`: food\n")
        self.assertEqual(self.v.domains(), DEFAULT_DOMAINS)
        (self.root / "CLAUDE.md").unlink()
        self.assertEqual(self.v.domains(), DEFAULT_DOMAINS)

    def test_keep_validates_against_vault_domains(self):
        self.schema("## Domains\n\n- `cooking`: food\n- `other`: rest\n")
        p = self.v.keep("thought", "Salt early", "Salt pasta water early", domain="cooking")
        self.assertTrue(p.exists())
        with self.assertRaises(VaultError):
            self.v.keep("thought", "Code note", "s", domain="engineering")

    def test_cli_accepts_custom_domain(self):
        self.schema("## Domains\n\n- `cooking`: food\n")
        config.save({"vault": str(self.root)})
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["keep", "--type", "idea", "--title", "Bread", "--summary", "Bake bread",
                      "--domain", "cooking"])
        self.assertIn("kept wiki/ideas/bread.md", out.getvalue())


class TestDoctorCode(Base):
    def test_links_in_code_are_ignored(self):
        self.v.scaffold()
        self.v.keep("concept", "Wikilinks", "How links work", "", domain="engineering")
        page = self.root / "wiki/concepts/wikilinks.md"
        page.write_text(page.read_text(encoding="utf-8") + (
            "Write `[[x]]` to link.\n\n```\n[[y]]\n```\n\n~~~md\n[[z]]\n~~~\n\nReal: [[missing]]\n"),
            encoding="utf-8")
        errs = [m for s, m in doctor.run(self.v) if s == "error"]
        self.assertEqual(errs, ["wiki/concepts/wikilinks.md: broken link [[missing]]"])


class TestCrlf(Base):
    def test_index_and_log_tolerate_crlf_and_bom(self):
        self.v.scaffold()
        for p in (self.v.index, self.v.log):
            p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes().replace(b"\n", b"\r\n"))
        self.v.keep("thought", "Line ends", "CRLF safe")
        self.v.append_log("query", "test")
        idx = self.v.index.read_bytes()
        self.assertNotIn(b"\r", idx)
        self.assertEqual(idx.decode("utf-8").count("## Thoughts"), 1)
        self.assertIn("- [[line-ends]]: CRLF safe (other)", idx.decode("utf-8"))
        self.assertNotIn(b"\r", self.v.log.read_bytes())


class TestInitCli(Base):
    def run_init(self, path):
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["init", str(path)])
        return out.getvalue()

    def test_init_prints_created_then_nothing(self):
        out = self.run_init(self.root)
        self.assertIn("  CLAUDE.md", out)
        self.assertIn("mentat-wiki install claude", out)
        self.assertIn("mentat-wiki project register <name>", out)
        self.assertEqual(config.load()["vault"], str(self.root.resolve()))
        out = self.run_init(self.root)
        self.assertIn("vault already initialised, nothing created", out)
        self.assertNotIn("config vault stays", out)

    def test_init_does_not_switch_config_silently(self):
        self.run_init(self.root)
        other = Path(self.tmp.name) / "second"
        out = self.run_init(other)
        self.assertIn(f"config vault stays {self.root.resolve()}; run mentat-wiki config --vault", out)
        self.assertEqual(config.load()["vault"], str(self.root.resolve()))


class TestResources(unittest.TestCase):
    def test_names_cover_tree(self):
        names = templates.names()
        self.assertIn("CLAUDE.md", names)
        self.assertTrue(all("\\" not in n and "__pycache__" not in n for n in names))

    def test_works_from_a_copy_without_repo_path(self):
        """Import the package from a copy elsewhere: resources must not depend on the source folder.
        (A copied folder, not a zip: antivirus scanning of fresh archives made the zip variant stall.)"""
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            shutil.copytree(PACKAGE, site / PACKAGE.name, ignore=shutil.ignore_patterns("__pycache__"))
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "import mentat_wiki.templates as t; "
                    "assert t.__file__.startswith(sys.argv[1]), t.__file__; "
                    "print(len(t.install_into(sys.argv[2])))")
            r = subprocess.run([sys.executable, "-I", "-c", code, str(site), str(Path(tmp) / "v")],
                               capture_output=True, text=True, cwd=tmp, timeout=120,
                               stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(int(r.stdout), len(templates.names()))
            self.assertTrue((Path(tmp) / "v" / "core" / "capture-policy.md").is_file())


class TestLeadFixes(Base):
    """Findings from the cross-family review of T1."""

    def _doctor_links(self, extra):
        self.v.scaffold()
        self.v.keep("concept", "Fences", "Fence handling", "", domain="engineering")
        page = self.root / "wiki/concepts/fences.md"
        page.write_text(page.read_text(encoding="utf-8") + extra, encoding="utf-8")
        return [m for s, m in doctor.run(self.v) if s == "error" and "broken link" in m]

    def test_longer_closing_fence_closes_block(self):
        errs = self._doctor_links("```\n[[inside]]\n````\n\nAfter: [[gone]]\n")
        self.assertEqual(errs, ["wiki/concepts/fences.md: broken link [[gone]]"])

    def test_inline_code_across_line_break(self):
        errs = self._doctor_links("Use `a [[x]]\nb` here.\n\nReal [[real-missing]]\n")
        self.assertEqual(errs, ["wiki/concepts/fences.md: broken link [[real-missing]]"])

    def test_dangling_symlink_is_not_replaced(self):
        self.root.mkdir(parents=True, exist_ok=True)
        link = self.root / "CLAUDE.md"
        try:
            os.symlink(str(self.root / "nowhere.md"), str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted here")
        created = self.v.scaffold()
        self.assertNotIn("CLAUDE.md", created)
        self.assertTrue(link.is_symlink())

    def test_projects_and_other_always_valid(self):
        self.v.scaffold()
        (self.root / "CLAUDE.md").write_text("## Domains\n\n- `cooking`: food\n", encoding="utf-8")
        self.assertEqual(self.v.domains(), ["cooking", "projects", "other"])
        self.v.keep("thought", "Default domain", "uses other")  # implicit `other` must be accepted


if __name__ == "__main__":
    unittest.main()
