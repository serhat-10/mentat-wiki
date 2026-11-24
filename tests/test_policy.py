import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from mentat_wiki import checkpoint, config, digest, hook, policy, search, statusline
from tests.test_mentat import Base

REPO = Path(__file__).resolve().parent.parent

FROZEN_POLICY = """---
type: policy
summary: What the agent captures (ask, auto, never) and when a category may move to auto
min_proposals: 20
min_acceptance: 0.9
expiry_hours: 24
---

# Capture policy

Levels: `auto` = keep and report in one line; `ask` = propose in one line, wait; `never` = do not capture.

| Category | Policy | Notes |
|---|---|---|
| decision | ask | project decisions in a registered project |
| idea | ask | worth a day someday |
| thought | ask | half-formed thought or observation |
| concept | ask | reusable knowledge from a chat |
| output | ask | analysis worth keeping |
| wrap | ask | project status at session end |
| debugging | ask | unresolved debugging at session end, as an open thread |
| chatter | never | casual chat, trivial one-off fixes, anything with secrets or personal data |

Promotion: a category moves to `auto` only after `min_proposals` proposals with at least
`min_acceptance` accepted, and only with the human's approval. `mentat-wiki policy` reports this; it never
edits this file. Demotion: if the human deletes auto-captured items, move the category back to `ask`.
"""

OLD_BULLET_POLICY = """---
type: policy
summary: Old bullet format capture policy
---

# Capture policy

- decision: ask first
- idea: ask first
- chatter: never capture
"""


def _snapshot(root: Path) -> dict:
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestPolicyParsing(Base):
    def test_missing_file_returns_defaults(self):
        pol = policy.load(self.v)
        self.assertEqual(pol["min_proposals"], 20)
        self.assertEqual(pol["min_acceptance"], 0.9)
        self.assertEqual(pol["expiry_hours"], 24)
        for cat in ("decision", "idea", "thought", "concept", "output", "wrap", "debugging"):
            self.assertEqual(pol["levels"][cat], "ask")
        self.assertEqual(pol["levels"]["chatter"], "never")

    def test_old_bullet_format_returns_defaults(self):
        (self.root / "core" / "capture-policy.md").write_text(OLD_BULLET_POLICY, encoding="utf-8")
        pol = policy.load(self.v)
        self.assertEqual(pol["min_proposals"], 20)
        self.assertEqual(pol["min_acceptance"], 0.9)
        self.assertEqual(pol["expiry_hours"], 24)
        for cat in ("decision", "idea", "thought", "concept", "output", "wrap", "debugging"):
            self.assertEqual(pol["levels"][cat], "ask")
        self.assertEqual(pol["levels"]["chatter"], "never")

    def test_frozen_file_and_custom_overrides(self):
        p = self.root / "core" / "capture-policy.md"
        p.write_text(FROZEN_POLICY, encoding="utf-8")
        pol = policy.load(self.v)
        self.assertEqual((pol["min_proposals"], pol["min_acceptance"], pol["expiry_hours"]), (20, 0.9, 24))
        self.assertEqual(pol["levels"]["idea"], "ask")
        self.assertEqual(pol["levels"]["chatter"], "never")

        custom = FROZEN_POLICY.replace("min_proposals: 20", "min_proposals: 15").replace(
            "min_acceptance: 0.9", "min_acceptance: 0.85").replace(
            "expiry_hours: 24", "expiry_hours: 12").replace(
            "| idea | ask |", "| idea | auto |")
        p.write_text(custom, encoding="utf-8")
        pol2 = policy.load(self.v)
        self.assertEqual((pol2["min_proposals"], pol2["min_acceptance"], pol2["expiry_hours"]), (15, 0.85, 12))
        self.assertEqual(pol2["levels"]["idea"], "auto")


    def test_only_policy_table_applies_and_fractional_minimum_warns(self):
        text = FROZEN_POLICY.replace("min_proposals: 20", "min_proposals: 20.5").replace(
            "| Category | Policy | Notes |", "| Category | Policy |").replace(
            "|---|---|---|", "|---|---|").replace("| thought | ask | half-formed thought or observation |",
                                                    "| thought | never |")
        text += "\n| Example | Level |\n|---|---|\n| idea | auto |\n"
        (self.root / "core/capture-policy.md").write_text(text, encoding="utf-8")
        pol = policy.load(self.v)
        self.assertEqual(pol["levels"]["idea"], "ask")
        self.assertEqual(pol["levels"]["thought"], "never")
        self.assertEqual(pol["min_proposals"], 20)
        self.assertIn("Invalid min_proposals", self.run_cli("policy")[1])


class TestOutcomesAndMatching(Base):
    def test_reproposal_replaces_only_matching_edited_item(self):
        for category in ("idea", "thought"):
            self.v.propose(category, "Draft title")
            self.v.feedback(category, "Draft title", "edited")
        old, other = self.v._load_pending()
        self.v.propose("idea", ' "DRAFT   title" ')
        fresh, = self.v.pending()
        self.assertEqual(self.v._load_pending(), [other, fresh])
        self.assertNotEqual(fresh["id"], old["id"])
        self.v.keep("idea", "Draft title", "Summary")
        self.assertEqual(self.v.events()[-1]["proposal"], fresh["id"])

    def test_sweep_repairs_invalid_ids_and_states(self):
        invalid = [None, "", 123, [1, 2]]
        self.v._set_pending([{"type": "idea", "title": str(i), "ts": time.time(),
                              "state": ["unknown"], "id": ident} for i, ident in enumerate(invalid)])
        self.assertEqual(len(self.v.pending()), len(invalid))
        self.v.sweep_expired()
        items = self.v.pending()
        self.assertEqual(len({p["id"] for p in items}), len(invalid))
        for p in items:
            self.assertRegex(p["id"], r"^[a-f0-9]{12}$")
            self.assertEqual(p["state"], "open")
        self.v.sweep_expired()
        self.assertEqual(self.v._load_pending(), items)

    def test_invalid_timestamps_expire_in_report_and_sweep(self):
        timestamps = [float("nan"), float("inf"), float("-inf"), "recent", True, None]
        self.v._set_pending([{"type": "idea", "title": str(i), "ts": ts}
                             for i, ts in enumerate(timestamps)])
        self.assertFalse(self.v.pending())
        row = next(r for r in policy.report(self.v) if r["category"] == "idea")
        self.assertEqual(row["ignored"], len(timestamps))
        self.assertEqual(self.v.sweep_expired(), len(timestamps))
        self.assertEqual(self.v.sweep_expired(), 0)
        self.assertEqual([e["outcome"] for e in self.v.events()], ["ignored"] * len(timestamps))

    def test_terminal_record_does_not_swallow_explicit_capture(self):
        self.v.register_project("demo")
        for category in ("idea", "decision"):
            with self.subTest(category=category):
                self.v.propose(category, "Storage")
                with mock.patch.object(self.v, "_set_pending", side_effect=OSError):
                    with self.assertRaises(OSError):
                        self.v.feedback(category, "Storage", "rejected")
                if category == "idea":
                    self.v.keep(category, "Storage", "Summary")
                else:
                    self.v.decide("demo", "Storage")
                rejected, kept = [e for e in self.v.events() if e["type"] == category]
                self.assertEqual((rejected["via"], rejected["outcome"]), ("proposal", "rejected"))
                self.assertEqual((kept["via"], kept["outcome"]), ("explicit", "kept"))
                self.assertNotIn("proposal", kept)
                self.assertFalse(self.v._load_pending())

    def test_auto_keep_and_cli_decide_leave_proposals_open(self):
        self.v.register_project("demo")
        for category in ("idea", "decision"):
            self.v.propose(category, "Storage")
        pending = self.v.pending()
        self.v.keep("idea", "Storage", "Summary", auto=True)
        code, _, err = self.run_cli("decide", "--decision", "Storage", "--project", "demo", "--auto")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.v.pending(), pending)
        self.assertEqual(len(self.v.events()), 2)
        for e in self.v.events():
            self.assertIs(e["auto"], True)
            self.assertEqual(e["via"], "explicit")
            self.assertNotIn("proposal", e)
        for r in policy.report(self.v):
            if r["category"] in ("idea", "decision"):
                self.assertEqual((r["auto"], r["proposed"], r["explicit"]), (1, 0, 0))

    def test_bom_prefixed_queue_and_ledger_reconcile(self):
        self.v.propose("idea", "Storage")
        item, = self.v.pending()
        self.v.record(type="idea", proposal=item["id"], via="proposal", outcome="rejected")
        for name in ("pending.json", "feedback.jsonl"):
            path = self.v.state / name
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
        self.assertEqual(self.v.pending(), [item])
        self.assertEqual(self.v.events()[0]["proposal"], item["id"])
        self.assertEqual(self.v.sweep_expired(), 1)
        self.assertFalse(self.v.pending())

    def test_refresh_and_resolve_same_title_by_type(self):
        self.v.register_project("demo")
        self.v.propose("idea", "Shared title")
        first, = self.v.pending()
        self.assertRegex(first["id"], r"^[a-f0-9]{12}$")
        first["ts"] -= 60
        self.v._set_pending([first])
        self.v.propose("idea", "shared  TITLE")
        self.v.propose("decision", "Shared title")
        idea, decision = self.v.pending()
        self.assertEqual(idea["id"], first["id"])
        self.assertGreater(idea["ts"], first["ts"])
        self.assertNotEqual(idea["id"], decision["id"])
        self.v.feedback("idea", "Shared title", "edited")
        self.v.decide("demo", "Shared title")
        self.v.keep("idea", "Shared title", "Final summary")
        self.assertEqual([(e["proposal"], e["outcome"]) for e in self.v.events()],
                         [(idea["id"], "edited"), (decision["id"], "kept")])
        self.assertFalse(self.v._load_pending())

    def test_edited_idea_leaves_unproposed_decision_explicit(self):
        self.v.register_project("demo")
        self.v.propose("idea", "Shared")
        self.v.feedback("idea", "Shared", "edited")
        self.v.decide("demo", "Shared")
        idea, decision = self.v.events()
        self.assertEqual((decision["via"], decision["outcome"]), ("explicit", "kept"))
        self.assertEqual(self.v._load_pending()[0]["id"], idea["proposal"])

    def test_sweep_finishes_interrupted_keep_and_decide(self):
        self.v.register_project("demo")
        for category in ("idea", "decision"):
            self.v.propose(category, category)
            with mock.patch.object(self.v, "_set_pending", side_effect=OSError):
                with self.assertRaises(OSError):
                    if category == "idea":
                        self.v.keep(category, category, "Final summary", edited=True)
                    else:
                        self.v.decide("demo", category)
            self.v.sweep_expired()
            self.assertFalse(self.v._load_pending())
        self.assertEqual([e["outcome"] for e in self.v.events()], ["edited", "kept"])

    def test_decide_prefers_title_then_falls_back_to_text(self):
        self.v.register_project("demo")
        self.v.propose("decision", "B")
        self.v.propose("decision", "A")
        b, a = self.v.pending()
        self.v.decide("demo", "B", title="A")
        self.assertEqual(self.v.pending(), [b])
        self.v.decide("demo", "B", title="Other")
        self.assertEqual([e["proposal"] for e in self.v.events()], [a["id"], b["id"]])

    def test_expiry_after_edited_feedback(self):
        for title in ("Capture", "Sweep"):
            self.v.propose("idea", title)
            self.v.feedback("idea", title, "edited")
        items = self.v._load_pending()
        self.assertEqual([p["state"] for p in items], ["edited", "edited"])
        self.assertFalse(self.v.pending(None))
        for p in items:
            p["ts"] -= 90000
        self.v._set_pending(items)
        self.v.keep("idea", "Capture", "Final summary")
        self.assertFalse(self.v._load_pending())
        self.assertEqual([e["outcome"] for e in self.v.events()], ["edited", "edited"])

    def test_interrupted_sweep_assigns_durable_legacy_identity(self):
        self.v._set_pending([{"type": "idea", "title": "Legacy", "ts": 0}])
        save = self.v._set_pending

        def fail_removal(items):
            if not items:
                raise OSError("interrupted")
            save(items)

        with mock.patch.object(self.v, "_set_pending", side_effect=fail_removal):
            with self.assertRaises(OSError):
                self.v.sweep_expired()
        item, = self.v._load_pending()
        event, = self.v.events()
        self.assertEqual((item["id"], "ignored"), (event["proposal"], event["outcome"]))
        row = next(r for r in policy.report(self.v) if r["category"] == "idea")
        self.assertEqual((row["ignored"], row["proposed"]), (1, 1))
        self.v.sweep_expired()
        self.v.sweep_expired()
        self.assertFalse(self.v._load_pending())
        self.assertEqual(self.v.events(), [event])

    def test_recover_interrupted_feedback_and_capture(self):
        for outcome in ("edited", "rejected"):
            self.v.propose("idea", outcome)
            with mock.patch.object(self.v, "_set_pending", side_effect=OSError):
                with self.assertRaises(OSError):
                    self.v.feedback("idea", outcome, outcome)
            self.v.sweep_expired()
            if outcome == "edited":
                self.assertEqual(self.v._load_pending()[0]["state"], "edited")
                self.v.keep("idea", outcome, "Final summary")
            self.assertFalse(self.v._load_pending())
        self.assertEqual([e["outcome"] for e in self.v.events()], ["edited", "rejected"])

    def test_configured_expiry_is_read_only(self):
        (self.root / "core/capture-policy.md").write_text(
            FROZEN_POLICY.replace("expiry_hours: 24", "expiry_hours: 1"), encoding="utf-8")
        legacy = {"type": "idea", "title": "Legacy", "ts": time.time() - 7200}
        self.v._set_pending([legacy])
        self.assertFalse(self.v.pending())
        self.assertEqual(self.v.pending(None), [legacy])

    def test_normalised_title_match_gives_via_proposal_and_preserves_stored_title(self):
        self.v.propose("idea", '  "Offline   Voice Notes" ')
        self.assertEqual(self.v.pending()[0]["title"], '  "Offline   Voice Notes" ')
        self.v.keep("idea", "offline voice   notes", "summary")
        self.assertEqual(self.v.pending(), [])
        ev = self.v.events()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["via"], "proposal")
        self.assertEqual(ev[0]["outcome"], "kept")

        self.v.propose("thought", "\u201cSmart   Quotes\u201d")
        self.v.feedback("thought", "smart quotes", "rejected")
        self.assertEqual(self.v.pending(), [])
        self.assertEqual(self.v.events()[-1]["via"], "proposal")
        self.assertEqual(self.v.events()[-1]["outcome"], "rejected")

        self.v.feedback("thought", "never proposed", "rejected")
        self.assertEqual(self.v.events()[-1]["via"], "explicit")

    def test_keep_edited_gives_one_edited_record(self):
        self.v.propose("idea", "Local search")
        code, _, err = self.run_cli("keep", "--type", "idea", "--title", "Local search",
                                    "--summary", "FTS5 index", "--edited")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.v.pending(), [])
        ev = self.v.events()
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["outcome"], ev[0]["via"]), ("edited", "proposal"))

    def test_decide_edited_gives_one_edited_record(self):
        self.v.register_project("demo")
        self.v.propose("decision", "Use SQLite")
        code, _, err = self.run_cli("decide", "--project", "demo", "--title", "Use SQLite",
                                    "--decision", "Use SQLite with FTS5", "--edited")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.v.pending(), [])
        ev = self.v.events()
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["outcome"], ev[0]["via"]), ("edited", "proposal"))

    def test_old_style_feedback_edited_then_keep_or_decide_gives_one_record(self):
        self.v.propose("idea", "Draft title")
        self.v.feedback("idea", "Draft title", "edited")
        self.v.keep("idea", "Draft title", "Final summary")
        ev = [e for e in self.v.events() if e["type"] == "idea"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["outcome"], ev[0]["via"]), ("edited", "proposal"))
        self.assertTrue((self.root / "wiki/ideas/draft-title.md").is_file())

        self.v.register_project("demo")
        self.v.propose("decision", "Pick DB")
        self.v.feedback("decision", "Pick DB", "edited")
        self.v.decide("demo", "Use SQLite", title="Pick DB")
        dec_ev = [e for e in self.v.events() if e["type"] == "decision"]
        self.assertEqual(len(dec_ev), 1)
        self.assertEqual((dec_ev[0]["outcome"], dec_ev[0]["via"]), ("edited", "proposal"))
        self.assertIn("Use SQLite", (self.root / "wiki/projects/demo/decisions.md").read_text(encoding="utf-8"))

    def test_expired_proposal_becomes_one_ignored_on_next_write_or_context(self):
        for trigger in ("propose", "feedback", "keep", "decide", "context"):
            with self.subTest(trigger=trigger):
                (self.v.state / "feedback.jsonl").unlink(missing_ok=True)
                self.v._set_pending([{"type": "idea", "title": f"Old {trigger}", "ts": int(time.time()) - 90000}])
                if trigger == "propose":
                    self.v.propose("thought", f"New {trigger}")
                elif trigger == "feedback":
                    self.v.feedback("thought", f"New {trigger}", "rejected")
                elif trigger == "keep":
                    self.v.keep("thought", f"New {trigger}", "summary")
                elif trigger == "decide":
                    self.v.register_project("demo")
                    self.v.decide("demo", f"New {trigger}")
                elif trigger == "context":
                    with mock.patch.object(sys, "stdin", io.StringIO("")):
                        self.run_cli("context", "--cwd", str(self.root))
                ignored = [e for e in self.v.events() if e.get("outcome") == "ignored"]
                self.assertEqual(len(ignored), 1)
                self.assertEqual(ignored[0]["title"], f"Old {trigger}")
                self.assertEqual(ignored[0]["via"], "proposal")
                self.assertNotIn(f"Old {trigger}", [p["title"] for p in self.v._load_pending()])


class TestPolicyReportAndCLI(Base):
    def _record_proposals(self, category: str, kept: int, edited: int = 0, rejected: int = 0, ignored: int = 0):
        for i in range(kept):
            self.v.record(type=category, title=f"k{i}", outcome="kept", via="proposal")
        for i in range(edited):
            self.v.record(type=category, title=f"e{i}", outcome="edited", via="proposal")
        for i in range(rejected):
            self.v.record(type=category, title=f"r{i}", outcome="rejected", via="proposal")
        for i in range(ignored):
            self.v.record(type=category, title=f"i{i}", outcome="ignored", via="proposal")

    def _row(self, category: str, now=None) -> dict:
        return next(r for r in policy.report(self.v, now=now) if r["category"] == category)

    def test_bad_ledger_lines_dates_and_duplicate_ids(self):
        self.v.state.mkdir(exist_ok=True)
        ledger = self.v.state / "feedback.jsonl"
        ledger.write_bytes(b'not json\xff\n123\n[]\nnull\n')
        self.v.record(type="idea", via="proposal", outcome="kept", proposal="abc", ts=1e100)
        self.v.record(type="idea", via="proposal", outcome="kept", proposal="abc", date="invalid")
        self.assertEqual(len(self.v.events()), 2)
        self.assertEqual(self._row("idea")["proposed"], 1)
        self.assertIn("0/0 (-)", digest.build(self.v))

    def test_acceptance_at_boundary(self):
        self._record_proposals("idea", kept=18, rejected=2)
        self._record_proposals("thought", kept=17, rejected=3)
        self.assertTrue(self._row("idea")["eligible"])
        self.assertFalse(self._row("thought")["eligible"])
        (self.root / "core/capture-policy.md").write_text(
            FROZEN_POLICY.replace("min_acceptance: 0.9", "min_acceptance: 0.9000000005"), encoding="utf-8")
        self.assertFalse(self._row("idea")["eligible"])

    def test_exact_acceptance_is_stable_after_promotion(self):
        self._record_proposals("idea", kept=27, rejected=3)
        self.assertTrue(self._row("idea")["eligible"])
        (self.root / policy.FILE).write_text(
            FROZEN_POLICY.replace("| idea | ask |", "| idea | auto |"), encoding="utf-8")
        self.assertIsNone(self._row("idea")["suggestion"])
        self._record_proposals("idea", kept=0, rejected=1)
        self.assertIn("| idea | ask |", self._row("idea")["suggestion"])

    def test_only_valid_events_and_nonempty_string_ids_deduplicate(self):
        for category, outcome in (("unknown", "rejected"), ("idea", "unknown")):
            self.v.record(type=category, outcome=outcome, via="proposal", proposal="shared")
        for ident in ("shared", "shared", "", "", [1], [1]):
            self.v.record(type="idea", outcome="kept", via="proposal", proposal=ident)
        self.v._set_pending([{"type": "idea", "ts": 0, "id": ident}
                             for ident in ("shared", "", "")])
        row = self._row("idea")
        self.assertEqual((row["kept"], row["ignored"], row["proposed"]), (5, 2, 7))

    def test_thresholds_19_vs_20_and_089_vs_090(self):
        (self.root / "core" / "capture-policy.md").write_text(FROZEN_POLICY, encoding="utf-8")
        # 19 proposals, 100% accepted -> not eligible (< 20)
        self._record_proposals("idea", kept=19)
        r = self._row("idea")
        self.assertEqual((r["proposed"], r["acceptance"], r["eligible"]), (19, 1.0, False))
        self.assertIsNone(r["suggestion"])

        # 20th proposal accepted -> 20 proposals, 100% accepted -> eligible
        self._record_proposals("idea", kept=1)
        r = self._row("idea")
        self.assertEqual((r["proposed"], r["acceptance"], r["eligible"]), (20, 1.0, True))
        self.assertIn("change `| idea | ask |` to `| idea | auto |` in core/capture-policy.md, with your approval",
                      r["suggestion"])

        # 0.89 vs 0.90 acceptance (using 100 proposals: 89 accepted vs 90 accepted)
        self._record_proposals("thought", kept=80, edited=9, rejected=11)
        rt = self._row("thought")
        self.assertEqual(rt["proposed"], 100)
        self.assertAlmostEqual(rt["acceptance"], 0.89)
        self.assertFalse(rt["eligible"])

        self._record_proposals("concept", kept=18, edited=0, rejected=2)
        rc = self._row("concept")
        self.assertEqual(rc["proposed"], 20)
        self.assertAlmostEqual(rc["acceptance"], 0.9)
        self.assertTrue(rc["eligible"])

    def test_explicit_and_auto_do_not_change_acceptance_and_expired_pending_counted(self):
        self._record_proposals("idea", kept=18, rejected=2)
        for i in range(10):
            self.v.record(type="idea", title=f"ex{i}", outcome="kept", via="explicit")
            self.v.record(type="idea", title=f"au{i}", outcome="kept", via="explicit", auto=True)
        r = self._row("idea")
        self.assertEqual((r["proposed"], r["explicit"], r["auto"]), (20, 10, 10))
        self.assertAlmostEqual(r["acceptance"], 0.9)
        self.assertTrue(r["eligible"])

        # An unswept expired item in pending.json counts in memory as ignored and lowers acceptance
        now = time.time()
        self.v._set_pending([{"type": "idea", "title": "stale", "ts": now - 90000}])
        r2 = self._row("idea", now=now)
        self.assertEqual((r2["proposed"], r2["ignored"]), (21, 1))
        self.assertLess(r2["acceptance"], 0.9)
        self.assertFalse(r2["eligible"])
        # Still in pending.json (report is read-only)
        self.assertEqual(len(self.v._load_pending()), 1)

    def test_demotion_suggestion_for_auto_category(self):
        p = self.root / "core" / "capture-policy.md"
        p.write_text(FROZEN_POLICY.replace("| idea | ask |", "| idea | auto |"), encoding="utf-8")
        self.v.record(type="idea", title="a1", outcome="kept", auto=True)
        for i in range(3):
            self.v.record(type="idea", title=f"no{i}", outcome="rejected", via="explicit")
        r = self._row("idea")
        self.assertEqual(r["level"], "auto")
        self.assertFalse(r["eligible"])
        self.assertIn("change `| idea | auto |` to `| idea | ask |` in core/capture-policy.md", r["suggestion"])

    def test_cli_policy_and_json_and_policy_file_byte_identical(self):
        p = self.root / "core" / "capture-policy.md"
        p.write_text(FROZEN_POLICY, encoding="utf-8")
        raw_before = p.read_bytes()
        self._record_proposals("idea", kept=19, edited=1)

        code, out, err = self.run_cli("policy")
        self.assertEqual(code, 0, err)
        self.assertIn("idea", out)
        self.assertIn("100%", out)
        self.assertIn("change `| idea | ask |` to `| idea | auto |`", out)

        code, jout, err = self.run_cli("policy", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(jout)
        self.assertEqual(data["thresholds"]["min_proposals"], 20)
        idea = next(c for c in data["categories"] if c["category"] == "idea")
        self.assertTrue(idea["eligible"])
        self.assertEqual(p.read_bytes(), raw_before)

    def test_statusline_hook_and_policy_do_not_write_files(self):
        p = self.root / "core" / "capture-policy.md"
        p.write_text(FROZEN_POLICY, encoding="utf-8")
        self.v.keep("idea", "Seed idea", "summary")
        self.v._set_pending([{"type": "idea", "title": "Expired pending", "ts": int(time.time()) - 90000}])
        search.sync(self.v)

        before = _snapshot(self.root)
        statusline.render(json.dumps({"cwd": str(self.work), "session_id": "abcd1234"}))
        for bad in ("", "not json", "123", "[1, 2]", "null", "true", '{"cwd": 9, "workspace": "bad"}'):
            statusline.render(bad)
        hook.hint_for("remember this idea about local caching in sqlite", self.v)
        self.run_cli("policy")
        self.run_cli("policy", "--json")
        self.run_cli("digest")
        after = _snapshot(self.root)
        self.assertEqual(before, after)

    def test_statusline_handles_non_utf8_inbox(self):
        inbox = self.root / "inbox" / "inbox.md"
        inbox.write_bytes(b"# Inbox\n- [ ] caf\xe9 item\n")
        line = statusline.render(json.dumps({"cwd": str(self.work)}))
        self.assertIn("inbox 1", line)

    def test_digest_includes_capture_policy_section(self):
        (self.root / "core" / "capture-policy.md").write_text(FROZEN_POLICY, encoding="utf-8")
        self._record_proposals("idea", kept=18, edited=2)
        text = digest.build(self.v, days=7, today=datetime.date.fromisoformat(
            self.v.events()[-1]["date"]))
        self.assertIn("## Capture policy", text)
        self.assertIn("20/20 (100%)", text)
        self.assertIn("Eligible for auto: idea", text)


class TestVaultContextAndStdinCwd(Base):
    def setUp(self):
        super().setUp()
        self.v.register_project("alpha")
        self.v.register_project("beta")
        config.register(self.work, "alpha")
        (self.root / "core" / "capture-policy.md").write_text(FROZEN_POLICY, encoding="utf-8")

    def _sub_ctx(self, stdin_obj, *extra_args, cwd=REPO):
        env = dict(os.environ, MENTAT_CONFIG=os.environ["MENTAT_CONFIG"], PYTHONIOENCODING="utf-8")
        env.pop("CLAUDE_ENV_FILE", None)
        raw = json.dumps(stdin_obj) if isinstance(stdin_obj, dict) else str(stdin_obj)
        r = subprocess.run([sys.executable, "-m", "mentat_wiki", "context", *extra_args],
                           input=raw.encode("utf-8"), capture_output=True, cwd=cwd, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8")

    def test_vault_root_context_prints_protocol_core_vault_line_unwrapped_and_eligible(self):
        for i in range(20):
            self.v.record(type="idea", title=f"i{i}", outcome="kept", via="proposal")
        checkpoint.record({"session_id": "prev1111-0000", "cwd": str(self.root)})
        out = self._sub_ctx({"session_id": "curr2222-0000", "cwd": str(self.root)})
        self.assertIn("Mentat capture protocol.", out)
        self.assertIn("it expires as ignored.", out)
        self.assertIn("Add `--edited` when the user changed it.", out)
        self.assertIn("# Capture policy", out)
        self.assertIn("Vault folder: no project. Pass --project <name> to decide, wrap and note; "
                      "known projects: alpha, beta.", out)
        self.assertNotIn("(no project registered for this folder)", out)
        self.assertIn("Last session ended without /wrap (prev1111", out)
        self.assertIn("Capture policy: idea qualifies for auto (20 proposals, 100% accepted); suggest it once.", out)

    def test_stdin_cwd_is_used_for_project_lookup_and_unrelated_folder_stays_silent(self):
        self.v.wrap("alpha", "In progress on alpha.", "Finish tests", ["check edge cases"])
        out = self._sub_ctx({"session_id": "curr2222-0000", "cwd": str(self.work)})
        self.assertIn("In progress on alpha.", out)
        self.assertIn("Mentat capture protocol.", out)

        other = Path(self.tmp.name) / "unrelated"
        other.mkdir()
        silent = self._sub_ctx({"session_id": "curr2222-0000", "cwd": str(other)})
        self.assertEqual(silent, "")


if __name__ == "__main__":
    unittest.main()
