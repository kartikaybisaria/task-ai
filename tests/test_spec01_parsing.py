"""Acceptance criteria and behaviours of specs/01-parsing.md.
AC tests: test_AC_01_<n>_...; behaviour/edge-case lines without an AC: test_BEH_01_<section>_..."""
import pytest
from helpers import FIXTURES, SHIPPED, iso, parse_lines, parse_note, strings

N = SHIPPED


def _ok(path):
    note, err = parse_note(path)
    assert err is None, err
    return note


# ---- AC-1..5: skipped files -------------------------------------------------------
@pytest.mark.parametrize("name,reason", [
    ("2026-09-09-notes-final-v2.md", "empty file"),
    ("scratch.md", "binary content (NUL bytes)"),
    ("2026-09-19-offsite-draft.txt", "unsupported extension (.txt)"),
    ("untitled.md", "no meeting date"),
])
def test_AC_01_1_to_4_skipped_files(name, reason):
    assert parse_note(N / name) == (None, reason)


def test_AC_01_5_invalid_utf8_without_nul(tmp_path):
    p = tmp_path / "2026-09-01-bad.md"
    p.write_bytes(b"# Meeting\nDate: 2026-09-01\n- [ ] Sam to x \xff\xfe\n")
    assert parse_note(p) == (None, "not valid UTF-8")


# ---- AC-6..9: date and attendees ----------------------------------------------------
def test_AC_01_6_meeting_date_formats():
    assert iso(_ok(N / "2026-09-09-qa-standup.md").meeting_date) == "2026-09-09"
    assert iso(_ok(N / "2026-09-14-onboarding-flow-design.md").meeting_date) == "2026-09-14"
    fm = _ok(N / "2026-09-16-standup.md")
    assert iso(fm.meeting_date) == "2026-09-16"
    assert list(fm.attendees) == ["Anita Desai", "Lena Fischer", "Meera Iyer"]


def test_AC_01_7_unparseable_date_falls_back_to_filename():
    note = _ok(N / "2026-10-03-sales-pipeline.md")
    assert iso(note.meeting_date) == "2026-10-03"
    assert len(note.warnings) == 1
    msg = note.warnings[0][1]
    assert "sometime last week" in msg and "2026-10-03" in msg


def test_AC_01_8_header_filename_mismatch_header_wins():
    note = _ok(FIXTURES / "dates" / "2026-09-03-x.md")
    assert iso(note.meeting_date) == "2026-09-02"
    assert len(note.warnings) == 1
    assert "2026-09-02" in note.warnings[0][1] and "2026-09-03" in note.warnings[0][1]


def test_AC_01_9_no_attendees_is_a_warning_not_a_skip():
    note = _ok(N / "2026-09-23-standup.md")
    assert list(note.attendees) == []
    assert "no attendees listed" in [m for _, m in note.warnings]


# ---- AC-10..13: real notes ------------------------------------------------------------
def test_AC_01_10_crlf_finance_sync():
    note = _ok(N / "2026-10-02-finance-sync.md")
    s = note.sightings
    assert len(s) == 4
    assert sum(bool(x.checked) for x in s) == 1 and s[0].checked
    assert [x.owner_names[0] for x in s] == ["Karan", "Sam", "Meera", "Karan"]
    assert not [t for t in strings(note) if "\r" in t]


def test_AC_01_11_fence_and_html_comment_ignored():
    s = _ok(N / "2026-10-09-security-review.md").sightings
    assert len(s) == 4
    assert not [x for x in s if "remediate finding" in x.task_text or "hardware tokens" in x.task_text]


def test_AC_01_12_blockquote_ignored():
    s = _ok(N / "2026-09-21-incident-review.md").sightings
    assert len(s) == 4
    refunds = [x for x in s if "refund affected customers" in x.task_text.lower()]
    assert len(refunds) == 1 and refunds[0].due_date is None


def test_AC_01_13_q4_offsite_shapes():
    s = _ok(N / "2026-09-30-q4-offsite.md").sightings
    assert len(s) == 9
    assert [x.source for x in s].count("checkbox") == 7
    table = [x for x in s if x.source == "table"]
    action = [x for x in s if x.source == "action_line"]
    assert len(table) == 1 and len(action) == 1
    assert table[0].owner_names[0] == "Anita" and iso(table[0].due_date) == "2026-10-09"
    assert table[0].task_text == "Refresh the brand kit" and not table[0].checked
    assert iso(action[0].due_date) == "2026-10-01" and action[0].owner_names[0] == "Karan"
    fin = _ok(N / "2026-10-02-finance-sync.md").sightings
    assert not [x for x in fin if x.task_text.lower().startswith("propose a 10% cost cut")]


# ---- AC-14: checkbox regex --------------------------------------------------------------
@pytest.mark.parametrize("bullet", ["-", "*", "+"])
@pytest.mark.parametrize("mark", [" ", "x", "X"])
@pytest.mark.parametrize("indent", ["", "  ", "    "])
def test_AC_01_14_checkbox_variants_match(tmp_path, bullet, mark, indent):
    s = parse_lines(tmp_path, [f"{indent}{bullet} [{mark}] Sam to do x"]).sightings
    assert len(s) == 1 and bool(s[0].checked) == (mark in "xX") and s[0].source == "checkbox"


@pytest.mark.parametrize("line", ["-[ ] Sam to do x", "- [] Sam to do x", "- [y] Sam to do x"])
def test_AC_01_14_non_checkboxes_do_not_match(tmp_path, line):
    assert parse_lines(tmp_path, [line]).sightings == []


# ---- AC-15, 16: owners -----------------------------------------------------------------------
def test_AC_01_15_owner_initial(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Priya N. to send the quote by Friday"]).sightings[0]
    assert s.owner_raw == "Priya N."


def test_AC_01_15_owner_handle(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] @anita: audit colour contrast on the dashboard by Mon"]).sightings[0]
    assert list(s.owner_names) == ["anita"]
    assert s.task_text.startswith("audit colour contrast")


@pytest.mark.parametrize("text,owners", [
    ("Anita & Rahul to agree on the component API", ["Anita", "Rahul"]),
    ("Lena (with Priya) to collect user feedback on the prototype", ["Lena", "Priya"]),
    ("Rahul to review Anita's PR by tomorrow", ["Rahul"]),
])
def test_AC_01_15_multiple_owners_and_leading_name_only(tmp_path, text, owners):
    s = parse_lines(tmp_path, [f"- [ ] {text}"]).sightings[0]
    assert list(s.owner_names) == owners


@pytest.mark.parametrize("ph", ["Someone", "Everyone", "Team", "TBD"])
def test_AC_01_16_placeholder_owner_is_unassigned(tmp_path, ph):
    s = parse_lines(tmp_path, [f"- [ ] {ph} to update the CRM notes"]).sightings[0]
    assert list(s.owner_names) == ["Unassigned"] and s.owner_raw == ph


def test_AC_01_16_no_owner_is_unassigned_full_text(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Book the venue"]).sightings[0]
    assert list(s.owner_names) == ["Unassigned"] and s.task_text == "Book the venue"


# ---- AC-17: due resolution (worked-example table + section 6 table) -----------------------------
DUE = [
    ("2026-09-01", "by Friday", "2026-09-04"),
    ("2026-09-01", "by Thursday", "2026-09-03"),
    ("2026-09-03", "by end of next week", "2026-09-11"),
    ("2026-09-14", "by end of month", "2026-09-30"),
    ("2026-09-14", "by Wed 16 Sep", "2026-09-16"),
    ("2026-09-18", "by Mon", "2026-09-21"),
    ("2026-09-30", "by Oct 3rd", "2026-10-03"),
    ("2026-10-05", "by next Tuesday", "2026-10-06"),
    ("2026-10-10", "by Tuesday", "2026-10-13"),          # M on a Saturday
    ("2026-10-02", "— proposal by 2026-10-09", "2026-10-09"),
    ("2026-09-18", "by Friday", "2026-09-25"),           # Friday on a Friday = M+7
    ("2026-09-02", "by Wednesday", "2026-09-09"),        # strictly after M
    ("2026-09-01", "by 2026-09-08", "2026-09-08"),
    ("2026-10-06", "on 2026-10-14", "2026-10-14"),
    ("2026-09-01", "by 10 Sep", "2026-09-10"),
    ("2026-09-30", "due 15 October", "2026-10-15"),
    ("2026-09-30", "by Oct 5th", "2026-10-05"),
    ("2026-09-01", "by tomorrow", "2026-09-02"),
    ("2026-09-21", "by EOD tomorrow", "2026-09-22"),
    ("2026-10-08", "by EOD", "2026-10-08"),
    ("2026-09-01", "by EOW", "2026-09-04"),
    ("2026-09-04", "by EOW", "2026-09-04"),              # first Friday on or after M
    ("2026-09-01", "by end of week", "2026-09-04"),
    ("2026-09-30", "by mid-October", "2026-10-15"),
    ("2026-10-20", "by mid-October", "2027-10-15"),      # before M: next year
    ("2026-09-01", "tomorrow", "2026-09-02"),            # trailing bare
    ("2026-09-01", "today", "2026-09-01"),
    ("2026-09-01", "EOD", "2026-09-01"),
]


@pytest.mark.parametrize("m,clause,expected", DUE, ids=[f"{m}|{c}" for m, c, _ in DUE])
def test_AC_01_17_due_resolution(tmp_path, m, clause, expected):
    s = parse_lines(tmp_path, [f"- [ ] Anita to send the report {clause}"], date=m).sightings
    assert len(s) == 1 and iso(s[0].due_date) == expected


def test_BEH_01_6_relative_dates_resolve_against_meeting_date_not_today(tmp_path):
    # D2: ACTIONTRACK_TODAY must not influence parsing
    import os
    os.environ["ACTIONTRACK_TODAY"] = "2030-01-01"
    try:
        s = parse_lines(tmp_path, ["- [ ] Anita to send the deck by Friday"]).sightings[0]
    finally:
        del os.environ["ACTIONTRACK_TODAY"]
    assert iso(s.due_date) == "2026-09-04"


def test_AC_01_18_percent_is_not_a_day(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Sam to cut cloud costs by 10% — proposal by 2026-10-09"],
                    date="2026-10-02").sightings[0]
    assert iso(s.due_date) == "2026-10-09" and s.due_raw == "by 2026-10-09"
    s2 = parse_lines(tmp_path, ["- [ ] Sam to cut cloud costs by 10%"], date="2026-10-02",
                     name="2026-10-02-b.md").sightings[0]
    assert s2.due_date is None


def test_AC_01_19_from_is_not_a_deadline(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Karan to freeze invoice edits from 9 Oct"]).sightings[0]
    assert s.due_date is None and s.due_raw == "from 9 Oct" and "from 9 Oct" in s.task_text


def test_AC_01_20_due_clause_removed_with_comma(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Lena to run the customer survey, results due 15 October"],
                    date="2026-09-30").sightings[0]
    assert iso(s.due_date) == "2026-10-15" and s.due_raw == "due 15 October"
    assert s.task_text == "run the customer survey, results"


def test_AC_01_21_year_rollover(tmp_path):
    a = parse_lines(tmp_path, ["- [ ] Sam to ship it by 3 Jan"], date="2026-12-20").sightings[0]
    b = parse_lines(tmp_path, ["- [ ] Sam to ship it by 1 Sep"], date="2026-09-01").sightings[0]
    assert iso(a.due_date) == "2027-01-03" and iso(b.due_date) == "2026-09-01"


def test_AC_01_22_every_shipped_note_parses():
    ok = bad = 0
    for p in sorted(N.iterdir()):
        note, err = parse_note(p)
        assert (note is None) != (err is None)
        ok, bad = ok + (note is not None), bad + (note is None)
    assert (ok, bad) == (32, 4)


# ---- behaviours / edge cases without an AC number -------------------------------------------------
def test_BEH_01_1_check_order_extension_before_empty(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"")
    assert parse_note(p) == (None, "unsupported extension (.txt)")


def test_BEH_01_1_nul_checked_before_utf8(tmp_path):
    p = tmp_path / "2026-09-01-x.md"
    p.write_bytes(b"\x00\xff\xfe")
    assert parse_note(p) == (None, "binary content (NUL bytes)")


def test_BEH_01_1_bom_accepted():
    note = _ok(FIXTURES / "malformed" / "2026-09-07-bom.md")
    assert iso(note.meeting_date) == "2026-09-07" and len(note.sightings) == 1


def test_BEH_01_2_quoted_lowercase_three_letter_month():
    assert iso(_ok(FIXTURES / "dates" / "2026-09-10-quoted.md").meeting_date) == "2026-09-10"


def test_BEH_01_2_weekday_contradicting_date_warns_but_date_wins():
    note = _ok(FIXTURES / "dates" / "2026-09-14-weekday-mismatch.md")
    assert iso(note.meeting_date) == "2026-09-14" and len(note.warnings) >= 1


def test_BEH_01_1_lone_cr_line_endings():
    note = _ok(FIXTURES / "format_traps" / "2026-09-02-lone-cr.md")
    assert len(note.sightings) == 2 and not [t for t in strings(note) if "\r" in t]


def test_BEH_01_1_crlf_fixture_em_dash_and_x():
    note = _ok(FIXTURES / "format_traps" / "2026-09-01-crlf.md")
    s = note.sightings
    assert [bool(x.checked) for x in s] == [True, False]
    assert iso(s[1].due_date) == "2026-10-09" and not [t for t in strings(note) if "\r" in t]


def test_BEH_01_4_code_comment_blockquote_fixture():
    s = _ok(FIXTURES / "format_traps" / "2026-09-03-code-block.md").sightings
    assert [x.task_text for x in s] == ["enable MFA"]


def test_BEH_01_4_nested_checkboxes_are_independent_items():
    s = _ok(FIXTURES / "format_traps" / "2026-09-04-nested.md").sightings
    assert [x.owner_names[0] for x in s] == ["Anita", "Karan", "Sam", "Lena"]


def test_BEH_01_4_identical_lines_one_sighting_checked_if_either(tmp_path):
    s = parse_lines(tmp_path, ["- [ ] Sam to do x", "- [x] Sam to do x"]).sightings
    assert len(s) == 1 and s[0].checked


def test_BEH_01_4_empty_checkbox_text_ignored(tmp_path):
    assert parse_lines(tmp_path, ["- [ ]   ", "- [ ] "]).sightings == []


def test_BEH_01_4_table_needs_owner_action_due_header(tmp_path):
    s = parse_lines(tmp_path, ["| Name | Task |", "|---|---|", "| Anita | Refresh the kit |"]).sightings
    assert s == []


def test_BEH_01_4_action_line_is_case_insensitive(tmp_path):
    s = parse_lines(tmp_path, ["action: Karan to circulate the summary tomorrow"]).sightings
    assert len(s) == 1 and s[0].source == "action_line" and iso(s[0].due_date) == "2026-09-02"


def test_BEH_01_4_prose_is_never_an_item(tmp_path):
    assert parse_lines(tmp_path, ["Sam to propose a 10% cost cut."]).sightings == []


def test_BEH_01_6_unresolvable_deadline_gives_null_raw_and_warning(tmp_path):
    note = parse_lines(tmp_path, ["- [ ] Lena to publish the changelog by the launch"])
    s = note.sightings[0]
    assert s.due_date is None and s.due_raw == "by the launch"
    assert any("by the launch" in m for _, m in note.warnings)


def test_BEH_01_6_em_dash_before_deadline_removed():
    s = [x for x in _ok(N / "2026-09-08-quote-portal-weekly.md").sightings if "quote to Acme" in x.task_text]
    assert len(s) == 1 and s[0].task_text == "send revised quote to Acme"


def test_overflowing_date_does_not_crash_ingest(tmp_path):
    from actiontrack.ingest import ingest
    d = tmp_path / "n"
    d.mkdir()
    (d / "9999-12-31-big.md").write_text("- [ ] Karan to do x by tomorrow\n", encoding="utf-8")
    (d / "2026-09-01-ok.md").write_text("- [ ] Karan to do y by Friday\n", encoding="utf-8")
    r = ingest(d, tmp_path / "t.db")
    assert r["scanned"] == 2
