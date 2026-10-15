"""Acceptance criteria and behaviours of specs/03-cli.md (today = 2026-10-15 unless stated)."""
import pytest
from helpers import FIXTURES, ROOT, SHIPPED, ingest, parse_list, rows, run_cli, summary

SKIPPED = [
    "skipped: 2026-09-09-notes-final-v2.md: empty file",
    "skipped: 2026-09-19-offsite-draft.txt: unsupported extension (.txt)",
    "skipped: scratch.md: binary content (NUL bytes)",
    "skipped: untitled.md: no meeting date",
]


def _list(db, *args, today="2026-10-15"):
    r = run_cli("list", *args, db=db, today=today)
    assert r.returncode == 0, r.stderr
    return parse_list(r.stdout)


def test_AC_03_1_ingest_summary_and_skipped_lines(tmp_path):
    r = run_cli("ingest", SHIPPED, db=tmp_path / "a.db")
    assert r.returncode == 0
    assert r.stdout.startswith("ingest: scanned=36 ingested=32 skipped=4")
    assert [l for l in r.stdout.splitlines() if l.startswith("skipped:")] == SKIPPED
    assert "sightings=117" in r.stdout and "new_sightings=117" in r.stdout


def test_AC_03_2_warnings_not_skips(tmp_path):
    out = run_cli("ingest", SHIPPED, db=tmp_path / "a.db").stdout.splitlines()
    assert "warning: 2026-09-23-standup.md: no attendees listed" in out
    assert ("warning: 2026-10-03-sales-pipeline.md: date 'sometime last week' not parseable; "
            "using filename date 2026-10-03") in out
    skipped = [l for l in out if l.startswith("skipped:")]
    assert not [l for l in skipped if "standup" in l or "sales-pipeline" in l]


def test_BEH_03_ingest_ambiguous_owner_warning(tmp_path):
    out = run_cli("ingest", SHIPPED, db=tmp_path / "a.db").stdout
    assert "warning: 2026-10-07-standup.md:9: owner 'Rahul' is ambiguous (Rahul Mehta, Rahul Verma)" in out


def test_AC_03_3_missing_path_exits_1_without_traceback(tmp_path):
    r = run_cli("ingest", "nonexistent/", db=tmp_path / "a.db")
    assert r.returncode == 1
    assert "error: path not found: nonexistent/" in r.stderr and "Traceback" not in r.stderr


def test_AC_03_4_single_binary_file(tmp_path):
    r = run_cli("ingest", SHIPPED / "scratch.md", db=tmp_path / "a.db")
    assert r.returncode == 0
    assert len([l for l in r.stdout.splitlines() if l.startswith("skipped:")]) == 1


def test_BEH_03_single_txt_file(tmp_path):
    r = run_cli("ingest", SHIPPED / "2026-09-19-offsite-draft.txt", db=tmp_path / "a.db")
    assert r.returncode == 0 and "unsupported extension (.txt)" in r.stdout


def test_AC_03_5_second_ingest_adds_nothing(tmp_path):
    db = tmp_path / "a.db"
    a, b = (run_cli("ingest", SHIPPED, db=db) for _ in range(2))
    assert a.returncode == b.returncode == 0
    assert "new_items=0 new_sightings=0" in b.stdout


def test_BEH_03_only_skipped_files(tmp_path):
    d = tmp_path / "n"
    d.mkdir()
    (d / "a.md").write_bytes(b"")
    (d / "b.txt").write_text("x")
    r = run_cli("ingest", d, db=tmp_path / "a.db")
    assert r.returncode == 0 and "ingested=0" in r.stdout


def test_BEH_03_malformed_fixture_summary(tmp_path):
    r = run_cli("ingest", FIXTURES / "malformed", db=tmp_path / "a.db")
    assert r.returncode == 0
    s = summary(r.stdout)
    assert (s["scanned"], s["ingested"], s["skipped"], s["sightings"]) == ("8", "3", "5", "3")
    assert [l for l in r.stdout.splitlines() if l.startswith("skipped:")] == [
        "skipped: 2026-09-03-empty.md: empty file",
        "skipped: 2026-09-04-binary.md: binary content (NUL bytes)",
        "skipped: 2026-09-05-bad-utf8.md: not valid UTF-8",
        "skipped: 2026-09-06-notes.txt: unsupported extension (.txt)",
        "skipped: undated-scratch.md: no meeting date",
    ]
    assert "warning: 2026-09-02-no-attendees.md: no attendees listed" in r.stdout


def test_BEH_03_db_defaults_to_env_var(tmp_path):
    db = tmp_path / "envdb.db"
    r = run_cli("ingest", FIXTURES / "dupes", env={"ACTIONTRACK_DB": str(db)})
    assert r.returncode == 0 and db.exists()


# ---- list -------------------------------------------------------------------------------------------------
def test_AC_03_6_header_and_five_fields(shipped_db):
    r = run_cli("list", db=shipped_db)
    assert r.stdout.split("\n")[0] == "ID\tSTATUS\tOWNER\tDUE\tTASK"
    for line in r.stdout.splitlines():
        assert len(line.split("\t")) == 5
    assert f"{len(parse_list(r.stdout))} item(s)" in r.stderr


def test_AC_03_7_karan_counts(shipped_db):
    overdue = _list(shipped_db, "--owner", "Karan Joshi", "--status", "overdue")
    opened = _list(shipped_db, "--owner", "Karan Joshi", "--status", "open")
    done = _list(shipped_db, "--owner", "Karan Joshi", "--status", "done")
    assert (len(overdue), len(opened), len(done)) == (6, 10, 3)
    assert [r["STATUS"] for r in opened].count("overdue") == 6
    assert [r["STATUS"] for r in opened].count("open") == 4


def test_AC_03_8_due_today_open_past_due_overdue(shipped_db):
    rows_ = {r["TASK"]: r for r in _list(shipped_db, "--owner", "Karan Joshi", "--status", "open")}
    a = rows_["Reconcile September ledger"]
    b = rows_["Send Acme the revised pricing sheet"]
    assert (a["DUE"], a["STATUS"]) == ("2026-10-15", "open")
    assert (b["DUE"], b["STATUS"]) == ("2026-10-01", "overdue")


def test_AC_03_9_due_before_is_strict_and_excludes_null(shipped_db):
    got = _list(shipped_db, "--due-before", "2026-10-01")
    assert got and all(r["DUE"] != "-" and r["DUE"] < "2026-10-01" for r in got)
    assert run_cli("list", "--due-before", "2026-10-01x", db=shipped_db).returncode == 2


def test_AC_03_10_ambiguous_and_unknown_owner(shipped_db):
    r = run_cli("list", "--owner", "Priya", db=shipped_db)
    assert r.returncode == 2
    assert "error: owner 'Priya' is ambiguous: Priya Nair, Priya Shah" in r.stderr
    assert run_cli("list", "--owner", "Nobody", db=shipped_db).returncode == 3


def test_AC_03_11_resolved_priya_hides_ambiguous_items(shipped_db):
    r = run_cli("list", "--owner", "Priya Nair", db=shipped_db)
    assert r.returncode == 0
    assert "ambiguous" not in r.stdout
    assert "note: 3 item(s) owned by 'Priya (ambiguous)' not shown" in r.stderr


def test_AC_03_12_co_owner_listed_for_both(shipped_db):
    def pick(owner):
        return [r for r in _list(shipped_db, "--owner", owner) if r["TASK"].startswith("Collect user feedback on the prototype")]
    lena, priya = pick("Lena Fischer"), pick("Priya Nair")
    assert len(lena) == len(priya) == 1 and lena[0]["ID"] == priya[0]["ID"]
    assert lena[0]["OWNER"] == "Lena Fischer" and lena[0]["TASK"].endswith(" (with Priya Nair)")


def test_AC_03_13_unassigned_rows(shipped_db):
    assert len(_list(shipped_db, "--owner", "Unassigned")) == 5


def test_AC_03_14_bad_status_and_empty_result(fx):
    assert run_cli("list", "--status", "bogus", db=fx("overdue")).returncode == 2
    r = run_cli("list", "--status", "overdue", db=fx("overdue"), today="2026-10-14")
    assert r.returncode == 0 and r.stdout == "ID\tSTATUS\tOWNER\tDUE\tTASK\n" and "0 item(s)" in r.stderr


def test_AC_03_15_ordering(shipped_db):
    got = _list(shipped_db)
    key = [("9999-99-99" if r["DUE"] == "-" else r["DUE"], int(r["ID"])) for r in got]
    assert key == sorted(key) and got[-1]["DUE"] == "-"


def test_BEH_03_combined_filters_and_first_name_owner(shipped_db):
    got = _list(shipped_db, "--status", "overdue", "--due-before", "2026-10-01")
    assert got and all(r["STATUS"] == "overdue" and r["DUE"] < "2026-10-01" for r in got)
    sam = _list(shipped_db, "--owner", "Sam")
    assert sam and {r["OWNER"] for r in sam} <= {"Sam Okafor"} | {r["OWNER"] for r in sam if r["TASK"].find("with Sam") >= 0}


def test_BEH_03_hidden_ambiguous_note_for_rahul_mehta_and_literal_label(shipped_db):
    r = run_cli("list", "--owner", "Rahul Mehta", db=shipped_db)
    assert "note: 3 item(s) owned by 'Rahul (ambiguous)' not shown" in r.stderr
    assert len(_list(shipped_db, "--owner", "Priya (ambiguous)")) == 3


# ---- done -----------------------------------------------------------------------------------------------------
def _id(db, frag):
    return next(r["ID"] for r in _list(db) if frag in r["TASK"])


def test_AC_03_16_done_marks_item(fresh):
    db, _ = fresh("overdue")
    i = _id(db, "Plan the offsite")
    r = run_cli("done", i, db=db)
    assert r.returncode == 0 and r.stdout.startswith(f"done: #{i} ")
    assert i in [x["ID"] for x in _list(db, "--status", "done")]
    row = rows(db, "SELECT done_date, done_manual, status FROM items WHERE id = ?", (int(i),))[0]
    assert (row["done_date"], row["done_manual"], row["status"]) == ("2026-10-15", 1, "done")


def test_AC_03_17_done_twice_keeps_done_date(fresh):
    db, _ = fresh("overdue")
    i = _id(db, "Plan the offsite")
    run_cli("done", i, db=db, today="2026-10-15")
    r = run_cli("done", i, db=db, today="2026-10-20")
    assert r.returncode == 0 and r.stdout.startswith(f"already done: #{i} ")
    assert rows(db, "SELECT done_date FROM items WHERE id = ?", (int(i),))[0]["done_date"] == "2026-10-15"


def test_AC_03_18_done_bad_ids(shipped_db):
    r = run_cli("done", "99999", db=shipped_db)
    assert r.returncode == 3 and "error: no such item: 99999" in r.stderr
    assert run_cli("done", "abc", db=shipped_db).returncode == 2
    assert run_cli("done", "0", db=shipped_db).returncode == 2


# ---- global rules -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", [["ingest", str(FIXTURES / "dupes")], ["list"], ["done", "1"],
                                 ["followup", "Karan Joshi", "--dry-run"]])
def test_AC_03_19_invalid_calendar_date_in_today(fx, cmd):
    r = run_cli(*cmd, db=fx("overdue"), today="2026-13-45")
    assert r.returncode == 2 and "ACTIONTRACK_TODAY" in r.stderr
    assert "error: ACTIONTRACK_TODAY must be YYYY-MM-DD, got '2026-13-45'" in r.stderr


@pytest.mark.parametrize("cmd", [["list"], ["done", "1"], ["followup", "Karan Joshi", "--dry-run"]])
def test_AC_03_20_missing_database(tmp_path, cmd):
    db = tmp_path / "nope.db"
    r = run_cli(*cmd, db=db)
    assert r.returncode == 1
    assert f"error: database not found: {db} (run ingest first)" in r.stderr
    assert not db.exists()


def test_AC_03_21_no_traceback_anywhere(shipped_db, tmp_path):
    assert run_cli("list", db=shipped_db).returncode == 0  # a real run must work first
    calls = [["list", "--owner", "Priya"], ["list", "--owner", "Nobody"], ["list", "--status", "bogus"],
             ["list", "--due-before", "2026-10-01x"], ["done", "99999"], ["done", "abc"], ["done", "0"],
             ["ingest", "nonexistent/"], ["list", "--nope"]]
    for c in calls:
        r = run_cli(*c, db=shipped_db)
        assert r.returncode in (1, 2, 3) and "Traceback" not in r.stderr, c
    r = run_cli("list", db=tmp_path / "missing.db")
    assert "Traceback" not in r.stderr
    r = run_cli("list", db=shipped_db, today="bad")
    assert "Traceback" not in r.stderr
