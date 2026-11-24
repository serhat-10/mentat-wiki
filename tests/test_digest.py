import datetime
import unittest

from mentat_wiki import digest
from tests.test_mentat import Base


def idea(v, slug, summary, value, effort, updated, status="parked"):
    (v.wiki / "ideas" / f"{slug}.md").write_text(
        f"---\ntype: idea\nsummary: {summary}\nvalue: {value}\neffort: {effort}\n"
        f"created: {updated}\nupdated: {updated}\nidea_status: {status}\n---\n# {slug}\n", encoding="utf-8")


class DigestTest(Base):
    def test_digest(self):
        today = datetime.date(2026, 10, 28)
        idea(self.v, "fresh", "new one", 3, 3, "2026-10-27")
        idea(self.v, "old-good", "old but great", 5, 1, "2026-01-01")
        idea(self.v, "old-bad", "meh", 1, 5, "2026-01-01")
        idea(self.v, "done-one", "finished", 5, 1, "2026-01-01", status="done")
        idea(self.v, "busy-one", "in progress", 5, 1, "2026-01-01", status="active")
        text = digest.build(self.v, today=today)
        recent, top = text.split("## Top parked ideas")
        self.assertNotIn("busy-one", top)
        self.assertIn("[[fresh]]", recent)
        self.assertNotIn("old-good", recent)
        self.assertLess(top.index("old-good"), top.index("fresh"))
        self.assertNotIn("done-one", text)

    def test_cli_read_only_and_empty(self):
        before = sorted(p.name for p in self.root.rglob("*"))
        code, out, _ = self.run_cli("digest")
        self.assertEqual(code, 0)
        self.assertIn("_(none)_", out)
        self.assertEqual(before, sorted(p.name for p in self.root.rglob("*")))


if __name__ == "__main__":
    unittest.main()
