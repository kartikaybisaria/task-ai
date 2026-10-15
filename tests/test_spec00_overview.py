"""Acceptance criteria of specs/00-overview.md. Names: test_AC_00_<n>_<description>."""
import re
from collections import Counter

import pytest
from helpers import FIXTURES, ROOT, SHIPPED, TODAY, iso, parse_list, rows, run_cli, summary

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_AC_00_1_help_lists_exactly_four_commands():
    r = run_cli("--help")
    assert r.returncode == 0
    m = re.search(r"\{([^}]*)\}", r.stdout)
    assert m, r.stdout
    assert set(m.group(1).split(",")) == {"ingest", "list", "done", "followup"}


def test_AC_00_2_tables_and_columns(fx):
    db = fx("dupes")
    items = {c["name"] for c in rows(db, "PRAGMA table_info(items)")}
    sights = {c["name"] for c in rows(db, "PRAGMA table_info(sightings)")}
    assert items >= {"id", "owner", "co_owners", "owner_raw", "task", "task_key", "due_date",
                     "due_raw", "status", "first_seen", "done_date", "done_manual", "review_reason"}
    assert sights >= {"id", "item_id", "file", "line", "meeting_date", "attendees", "checked",
                      "source", "owner_raw", "task_text", "due_raw", "due_date"}
    assert not [c for c in items | sights if "overdue" in c.lower()]


def test_AC_00_3_every_date_column_is_iso_or_null(shipped_db):
    for table, cols in (("items", ["due_date", "first_seen", "done_date"]),
                        ("sightings", ["meeting_date", "due_date"])):
        for col in cols:
            for r in rows(shipped_db, f"SELECT {col} AS v FROM {table}"):
                assert r["v"] is None or ISO.match(r["v"]), (table, col, r["v"])


def test_AC_00_4_shipped_notes_ingest_counts(tmp_path):
    db = tmp_path / "a.db"
    r = run_cli("ingest", SHIPPED, db=db)
    assert r.returncode == 0
    s = summary(r.stdout)
    assert (s["scanned"], s["ingested"], s["skipped"]) == ("36", "32", "4")
    skipped = sorted(l.split(": ")[1] for l in r.stdout.splitlines() if l.startswith("skipped:"))
    assert skipped == sorted(["scratch.md", "2026-09-09-notes-final-v2.md", "untitled.md",
                              "2026-09-19-offsite-draft.txt"])
    assert rows(db, "SELECT count(*) n FROM sightings")[0]["n"] == 117
    assert rows(db, "SELECT count(*) n FROM sightings WHERE checked = 1")[0]["n"] == 13
    by_source = Counter({r["source"]: r["n"] for r in
                         rows(db, "SELECT source, count(*) n FROM sightings GROUP BY source")})
    assert by_source == {"checkbox": 115, "table": 1, "action_line": 1}


def test_AC_00_5_due_today_not_overdue_due_yesterday_is(fx):
    r = run_cli("list", "--status", "overdue", db=fx("overdue"), today="2026-10-15")
    tasks = [x["TASK"] for x in parse_list(r.stdout)]
    assert any("Fix the login bug" in t for t in tasks)          # due 2026-10-14
    assert not any("Ship the release" in t for t in tasks)       # due 2026-10-15
    assert not any("Tidy the wiki" in t for t in tasks)          # due 2026-10-16


@pytest.mark.parametrize("cmd", [["ingest", str(FIXTURES / "dupes")], ["list"], ["done", "1"],
                                 ["followup", "Karan Joshi", "--dry-run"]])
def test_AC_00_6_bad_today_exits_2_naming_variable(fx, cmd):
    r = run_cli(*cmd, db=fx("overdue"), today="not-a-date")
    assert r.returncode == 2
    assert "ACTIONTRACK_TODAY" in r.stderr


def test_AC_00_7_every_decision_has_an_ac_in_traceability():
    trace = ROOT / "specs" / "traceability.md"
    assert trace.exists(), "specs/traceability.md is missing"
    text = trace.read_text(encoding="utf-8")
    decisions = re.findall(r"^D(\d+)\.", (ROOT / "specs" / "00-overview.md").read_text(encoding="utf-8"), re.M)
    assert len(decisions) == 15
    for d in decisions:
        lines = [l for l in text.splitlines() if re.search(rf"\bD{d}\b", l)]
        assert any(re.search(r"AC-\d+", l) for l in lines), f"D{d} has no AC in traceability.md"
