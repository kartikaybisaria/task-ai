"""Acceptance criteria and behaviours of specs/02-dedup-owners-dates.md (today = 2026-10-15)."""
import difflib
import json

import pytest
from helpers import (FIXTURES, SHIPPED, TODAY, find_item, ingest, normalize, parse_list, rows,
                     run_cli, sightings_of, summary)


def _owner_of(db, file, fragment):
    got = rows(db, "SELECT i.owner, i.co_owners FROM sightings s JOIN items i ON i.id = s.item_id "
                   "WHERE s.file = ? AND lower(s.task_text) LIKE ?", (file, f"%{fragment.lower()}%"))
    assert len(got) == 1, got
    return got[0]


# ---- AC-1: ten owner-resolution rows ------------------------------------------------------------
OWNER_ROWS = [
    ("2026-09-01-quote-portal-kickoff.md", "quote to acme", "Priya Nair"),
    ("2026-09-08-quote-portal-weekly.md", "quote to acme", "Priya Nair"),
    ("2026-09-29-billing-cutover-planning.md", "invoice rounding tests", "Priya Shah"),
    ("2026-09-17-billing-migration-sync.md", "cutover checklist", "Priya (ambiguous)"),
    ("2026-10-08-billing-go-no-go.md", "go/no-go summary", "Priya (ambiguous)"),
    ("2026-10-07-standup.md", "review anita", "Rahul (ambiguous)"),
    ("2026-09-23-standup.md", "rebase", "Rahul (ambiguous)"),
    ("2026-09-23-standup.md", "rotate the staging", "Sam Okafor"),
    ("2026-09-18-design-review.md", "audit colour contrast", "Anita Desai"),
    ("2026-09-18-design-review.md", "collect user feedback", "Lena Fischer"),
]


@pytest.mark.parametrize("file,frag,owner", OWNER_ROWS, ids=[f"{f[:10]}-{g[:12]}" for f, g, _ in OWNER_ROWS])
def test_AC_02_1_owner_resolution_table(shipped_db, file, frag, owner):
    assert _owner_of(shipped_db, file, frag)["owner"] == owner


def test_AC_02_1_co_owner_resolved(shipped_db):
    r = _owner_of(shipped_db, "2026-09-18-design-review.md", "collect user feedback")
    assert json.loads(r["co_owners"]) == ["Priya Nair"]


def test_AC_02_2_initials_pick_the_right_priya(fx):
    db = fx("priyas")
    got = rows(db, "SELECT owner FROM items WHERE lower(task) LIKE '%update the runbook%'")
    assert sorted(r["owner"] for r in got) == ["Priya Nair", "Priya Shah"]


def test_AC_02_3_six_ambiguous_items(shipped_db):
    got = rows(shipped_db, "SELECT owner, task FROM items WHERE review_reason = 'ambiguous_owner'")
    assert len(got) == 6
    priya = " | ".join(r["task"].lower() for r in got if r["owner"] == "Priya (ambiguous)")
    rahul = " | ".join(r["task"].lower() for r in got if r["owner"] == "Rahul (ambiguous)")
    assert sum(r["owner"] == "Priya (ambiguous)" for r in got) == 3
    assert sum(r["owner"] == "Rahul (ambiguous)" for r in got) == 3
    for frag in ("cutover checklist", "go/no-go summary", "hiring plan"):
        assert frag in priya
    for frag in ("rebase", "review anita", "architecture overview"):
        assert frag in rahul


def test_AC_02_4_five_unassigned_items(shipped_db):
    got = rows(shipped_db, "SELECT owner_raw FROM items WHERE owner = 'Unassigned' AND review_reason = 'unassigned'")
    assert sorted(r["owner_raw"] for r in got) == sorted(["Someone", "Everyone", "Everyone", "TBD", "Team"])
    assert rows(shipped_db, "SELECT count(*) n FROM items WHERE owner = 'Unassigned'")[0]["n"] == 5


def test_AC_02_5_normalize():
    assert normalize("Share first wireframes") == normalize("share updated wireframes")
    assert normalize("send the revised quote to Acme's team") == "send quote to acmes team"


def test_BEH_02_2_normalize_rules():
    assert normalize("Acme’s") == "acmes"
    assert normalize("Cut cloud costs by 10% — proposal, v2/final") == "cut cloud costs by 10 proposal v2 final"
    assert normalize("Ａcme  TEAM") == "acme team"  # NFKC + lower + whitespace


# ---- AC-6: threshold built by construction -----------------------------------------------------------
def _pair(name):
    out = []
    for f in sorted((FIXTURES / name).iterdir()):
        out.append(f.read_text(encoding="utf-8").split("Anita to ")[1].strip())
    return out


def test_AC_02_6_ratio_085_merges(fx):
    a, b = _pair("threshold_085")
    assert difflib.SequenceMatcher(None, a, b).ratio() == 0.85
    assert len(rows(fx("threshold_085"), "SELECT * FROM items")) == 1
    assert len(rows(fx("threshold_085"), "SELECT * FROM sightings")) == 2


def test_AC_02_6_ratio_084_does_not_merge(fx):
    a, b = _pair("threshold_084")
    assert difflib.SequenceMatcher(None, a, b).ratio() == 0.84
    assert len(rows(fx("threshold_084"), "SELECT * FROM items")) == 2


def test_AC_02_7_reworded_different_tasks_stay_two_items(shipped_db):
    got = rows(shipped_db, "SELECT task FROM items WHERE owner = 'Meera Iyer' AND lower(task) LIKE '%procurement%'")
    assert len(got) == 2


# ---- AC-8..16: shipped notes, specific items ------------------------------------------------------------
def test_AC_02_8_quote_item(shipped_db):
    it = find_item(shipped_db, "Priya Nair", "quote to acme")
    s = sightings_of(shipped_db, it["id"])
    assert [x["meeting_date"] for x in s] == ["2026-09-01", "2026-09-08", "2026-09-15"]
    assert (it["first_seen"], it["due_date"], it["due_raw"]) == ("2026-09-01", "2026-09-11", "by Friday")
    assert (it["status"], it["done_date"]) == ("done", "2026-09-15")


def test_AC_02_9_wireframes_open_and_overdue(shipped_db):
    it = find_item(shipped_db, "Anita Desai", "wireframes")
    assert len(sightings_of(shipped_db, it["id"])) == 3
    assert (it["due_date"], it["status"], it["task"]) == ("2026-09-24", "open", "share first wireframes")
    r = run_cli("list", "--status", "overdue", "--owner", "Anita Desai", db=shipped_db)
    assert str(it["id"]) in [x["ID"] for x in parse_list(r.stdout)]


def test_AC_02_10_later_sighting_without_date_does_not_erase(shipped_db):
    it = find_item(shipped_db, "Rahul Verma", "schema mapping doc")
    assert len(sightings_of(shipped_db, it["id"])) == 2
    assert (it["due_date"], it["status"]) == ("2026-09-07", "open")


def test_AC_02_11_welcome_copy(shipped_db):
    it = find_item(shipped_db, "Anita Desai", "welcome-email copy")
    assert len(sightings_of(shipped_db, it["id"])) == 3
    assert (it["due_date"], it["status"], it["done_date"]) == ("2026-09-25", "done", "2026-10-05")


def test_AC_02_12_replanned_due_date(shipped_db):
    it = find_item(shipped_db, "Lena Fischer", "collect 5 customer quotes")
    assert (it["due_date"], it["status"]) == ("2026-10-02", "open")


def test_AC_02_13_approve_q4_spend_done_by_capital_x(shipped_db):
    it = find_item(shipped_db, "Karan Joshi", "q4 cloud spend")
    assert {x["file"] for x in sightings_of(shipped_db, it["id"])} == {
        "2026-09-30-standup.md", "2026-10-02-finance-sync.md"}
    assert (it["status"], it["done_date"]) == ("done", "2026-10-02")


def test_AC_02_14_renewal_call(shipped_db):
    it = find_item(shipped_db, "Meera Iyer", "renewal call")
    assert len(sightings_of(shipped_db, it["id"])) == 3
    assert (it["status"], it["done_date"], it["due_date"]) == ("done", "2026-10-14", "2026-09-30")


def test_AC_02_15_deploy_beta(shipped_db):
    it = find_item(shipped_db, "Rahul Mehta", "beta to staging")
    assert len(sightings_of(shipped_db, it["id"])) == 3
    assert (it["status"], it["done_date"], it["due_date"]) == ("done", "2026-10-13", "2026-10-07")


def test_AC_02_16_from_date_is_never_a_due_date(shipped_db):
    it = find_item(shipped_db, "Karan Joshi", "freeze invoice edits")
    assert len(sightings_of(shipped_db, it["id"])) == 2
    assert it["due_date"] is None and it["due_raw"] == "from 9 Oct"
    r = run_cli("list", "--status", "overdue", db=shipped_db, today="2030-01-01")
    assert str(it["id"]) not in [x["ID"] for x in parse_list(r.stdout)]


def test_AC_02_17_done_is_sticky(fx):
    it = find_item(fx("sticky_done"), "Sam Okafor", "rotate the staging")
    assert len(sightings_of(fx("sticky_done"), it["id"])) == 2
    assert (it["status"], it["done_date"]) == ("done", "2026-09-01")


def _dump(db):
    return [rows(db, f"SELECT * FROM {t} ORDER BY id") for t in ("items", "sightings")]


def test_AC_02_18_ingest_twice_is_identical(tmp_path):
    db = tmp_path / "a.db"
    first = run_cli("ingest", SHIPPED, db=db)
    before = _dump(db)
    second = run_cli("ingest", SHIPPED, db=db)
    assert first.returncode == second.returncode == 0
    s = summary(second.stdout)
    assert (s["new_items"], s["new_sightings"]) == ("0", "0")
    assert _dump(db) == before


def test_BEH_02_5_idempotent_on_fixture(tmp_path):
    db = tmp_path / "a.db"
    ingest(db, FIXTURES / "dupes")
    before = _dump(db)
    assert summary(ingest(db, FIXTURES / "dupes").stdout)["new_items"] == "0"
    assert _dump(db) == before


def test_AC_02_19_line_shift_creates_no_duplicates(fresh):
    db, d = fresh()
    f = d / "2026-09-01-quote-portal-kickoff.md"
    n_items = len(rows(db, "SELECT id FROM items"))
    old = {r["task_text"]: r["line"] for r in rows(db, "SELECT * FROM sightings WHERE file = ?", (f.name,))}
    f.write_bytes(b"\n" + f.read_bytes())
    r = ingest(db, d)
    assert r.returncode == 0 and summary(r.stdout)["new_items"] == "0"
    assert len(rows(db, "SELECT id FROM items")) == n_items
    new = {r["task_text"]: r["line"] for r in rows(db, "SELECT * FROM sightings WHERE file = ?", (f.name,))}
    assert new == {k: v + 1 for k, v in old.items()}


def _drop_line(path, fragment):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [l for l in lines if fragment not in l]
    assert len(kept) == len(lines) - 1
    path.write_text("".join(kept), encoding="utf-8")


def test_AC_02_20_deleted_only_sighting_removes_item(fresh):
    db, d = fresh()
    n = len(rows(db, "SELECT id FROM items"))
    _drop_line(d / "2026-10-09-security-review.md", "Sam to enable MFA")
    ingest(db, d)
    assert len(rows(db, "SELECT id FROM items")) == n - 1


def test_AC_02_20_deleted_one_of_many_sightings_keeps_item(fresh):
    db, d = fresh()
    it = find_item(db, "Priya Nair", "quote to acme")
    _drop_line(d / "2026-09-01-quote-portal-kickoff.md", "Priya to send the revised quote")
    ingest(db, d)
    it2 = find_item(db, "Priya Nair", "quote to acme")
    assert it2["id"] == it["id"] and len(sightings_of(db, it["id"])) == 2


def test_AC_02_21_manual_done_survives_reingest_and_orphaning(fresh):
    db, d = fresh()
    it = find_item(db, "Sam Okafor", "enable mfa")
    assert run_cli("done", it["id"], db=db).returncode == 0
    ingest(db, d)
    again = find_item(db, "Sam Okafor", "enable mfa")
    assert (again["status"], again["done_manual"]) == ("done", 1)
    _drop_line(d / "2026-10-09-security-review.md", "Sam to enable MFA")
    ingest(db, d)
    assert rows(db, "SELECT id FROM items WHERE id = ?", (it["id"],))


def test_AC_02_22_file_becoming_empty_is_skipped_and_data_kept(fresh):
    db, d = fresh()
    f = d / "2026-10-09-security-review.md"
    before = rows(db, "SELECT * FROM sightings WHERE file = ?", (f.name,))
    f.write_bytes(b"")
    r = ingest(db, d)
    assert r.returncode == 0 and f"skipped: {f.name}: empty file" in r.stdout
    assert rows(db, "SELECT * FROM sightings WHERE file = ?", (f.name,)) == before


def test_AC_02_23_ambiguous_and_resolved_with_same_text_stay_separate(fx):
    got = rows(fx("priyas"), "SELECT owner FROM items WHERE lower(task) LIKE '%review the contract%'")
    assert sorted(r["owner"] for r in got) == ["Priya (ambiguous)", "Priya Nair"]
    amb = rows(fx("priyas"), "SELECT review_reason FROM items WHERE owner = 'Priya (ambiguous)'")
    assert amb[0]["review_reason"] == "ambiguous_owner"


# ---- behaviours -------------------------------------------------------------------------------------------
def test_BEH_02_3_dupes_fixture_merges_across_meetings(fx):
    db = fx("dupes")
    assert len(rows(db, "SELECT id FROM items")) == 3 and len(rows(db, "SELECT id FROM sightings")) == 8
    q = find_item(db, "Priya Nair", "quote to acme")
    assert (q["first_seen"], q["due_date"], q["due_raw"], q["status"], q["done_date"]) == (
        "2026-09-01", "2026-09-11", "by Friday", "done", "2026-09-15")
    st = find_item(db, "Rahul Mehta", "staging environment")
    assert (st["status"], st["done_date"]) == ("done", "2026-09-08")
    w = find_item(db, "Anita Desai", "wireframes")
    assert (w["task"], w["due_date"], w["status"]) == ("share first wireframes", "2026-09-24", "open")


def test_BEH_02_3_unassigned_items_dedup_among_themselves(fx):
    db = fx("no_owner")
    assert len(rows(db, "SELECT id FROM items WHERE owner = 'Unassigned' AND review_reason = 'unassigned'")) == 5
    crm = find_item(db, "Unassigned", "crm notes")
    assert crm["owner_raw"] == "Someone" and len(sightings_of(db, crm["id"])) == 2


def test_BEH_02_1_unknown_owner_kept_as_typed(tmp_path):
    from helpers import write_note
    write_note(tmp_path, ["- [ ] Zed to fix the build"], attendees=("Anita Desai",))
    db = tmp_path / "a.db"
    ingest(db, tmp_path)
    it = rows(db, "SELECT owner, review_reason FROM items")[0]
    assert (it["owner"], it["review_reason"]) == ("Zed", "unknown_owner")


def test_BEH_02_1_roster_fallback_when_note_has_no_attendees(fx):
    it = find_item(fx("malformed"), "Sam Okafor", "rotate the staging")
    assert it["review_reason"] is None
