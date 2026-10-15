"""Acceptance criteria and behaviours of specs/04-followup-gmail.md (today = 2026-10-15 unless stated)."""
import ast
import fnmatch
import json
import re
import subprocess
import sys

import pytest
from helpers import FIXTURES, ROOT, SHIPPED, TODAY, followup_json, rows, run_cli, sections

KARAN_BODY = """Hi Karan,

Here is where your action items from our meeting notes stand as of 2026-10-15.

Overdue (6)
- Send the vendor invoice list (due 2026-09-11, 34 days overdue; from 2026-09-09-qa-standup)
- Confirm discount ceiling with the CFO (due 2026-09-14, 31 days overdue; from 2026-09-10-acme-renewal-prep)
- Send Acme the revised pricing sheet (due 2026-10-01, 14 days overdue; from 2026-09-28-acme-renewal-checkin)
- Circulate the offsite summary (due 2026-10-01, 14 days overdue; from 2026-09-30-q4-offsite)
- Validate targets against the budget (due 2026-10-05, 10 days overdue; from 2026-09-30-q4-offsite)
- Prepare the board finance slide (due 2026-10-12, 3 days overdue; from 2026-10-02-finance-sync)

Open (4)
- Reconcile September ledger (due 2026-10-15; from 2026-10-12-billing-post-cutover)
- Send the final contract to legal (due 2026-10-15; from 2026-10-14-acme-renewal-wrapup)
- Refund affected customers (no due date; from 2026-09-21-incident-review)
- Freeze invoice edits from 9 Oct (no due date; note says "from 9 Oct"; from 2026-09-29-billing-cutover-planning)

Needs review
These came from meetings you attended and have no clear owner. If any are yours, please let me know:
- Update the CRM notes (written as "Someone"; from 2026-09-10-acme-renewal-prep)
- Submit their Q4 goals (written as "Everyone"; from 2026-09-30-q4-offsite)

Thanks!"""

FIXTURE_KARAN_BODY = """Hi Karan,

Here is where your action items from our meeting notes stand as of 2026-10-15.

Overdue (2)
- Validate targets against the budget (due 2026-10-05, 10 days overdue; from 2026-10-01-planning)
- Fix the login bug (due 2026-10-14, 1 day overdue; from 2026-10-01-planning)

Open (4)
- Ship the release (due 2026-10-15; from 2026-10-01-planning)
- Review the cutover plan (due 2026-10-16; from 2026-10-03-cutover)
- Plan the offsite (no due date; from 2026-10-01-planning)
- Freeze invoice edits from 9 Oct (no due date; note says "from 9 Oct"; from 2026-10-01-planning)

Needs review
These came from meetings you attended and have no clear owner. If any are yours, please let me know:
- Update the CRM notes (written as "Someone"; from 2026-10-01-planning)

Thanks!"""


def test_AC_04_1_json_shape_and_key_order(shipped_db):
    c = FIXTURES / "contacts" / "contacts.csv"
    r = run_cli("followup", "Karan Joshi", "--dry-run", "--contacts", c, db=shipped_db)
    assert r.returncode == 0
    assert list(json.loads(r.stdout).keys()) == ["owner", "to", "subject", "body", "warnings"]
    assert r.stdout.startswith('{\n  "owner"') and r.stdout.endswith("}\n")


def test_AC_04_2_subject_and_recipient(shipped_db):
    j = followup_json(shipped_db, "Karan Joshi")
    assert j["subject"] == "Follow-up: your open action items (10)"
    assert j["to"] == ["karan.joshi@example.com"]


def test_AC_04_3_full_body_matches_worked_example(shipped_db):
    assert followup_json(shipped_db, "Karan Joshi")["body"].rstrip("\n") == KARAN_BODY


def test_AC_04_4_section_order_and_overdue_sorting(shipped_db):
    body = followup_json(shipped_db, "Karan Joshi")["body"]
    assert body.index("Overdue (6)") < body.index("Open (4)") < body.index("Needs review")
    dates = [re.search(r"due (\d{4}-\d{2}-\d{2})", l).group(1) for l in sections(body)["Overdue"]]
    assert dates == ["2026-09-11", "2026-09-14", "2026-10-01", "2026-10-01", "2026-10-05", "2026-10-12"]


def test_AC_04_5_done_items_absent(shipped_db):
    body = followup_json(shipped_db, "Karan Joshi")["body"]
    for t in ("Export last quarter invoices", "Approve the Q4 cloud spend", "Revoke access"):
        assert t not in body


def test_AC_04_6_refund_once(shipped_db):
    assert followup_json(shipped_db, "Karan Joshi")["body"].count("Refund affected customers") == 1


@pytest.mark.parametrize("today,section,expect", [
    ("2026-10-14", "Open", "Fix the login bug (due 2026-10-14; from"),
    ("2026-10-15", "Overdue", "Fix the login bug (due 2026-10-14, 1 day overdue;"),
    ("2026-10-16", "Overdue", "Fix the login bug (due 2026-10-14, 2 days overdue;"),
])
def test_AC_04_7_due_boundary_and_day_plural(fx, today, section, expect):
    body = followup_json(fx("followup"), "Karan Joshi", today=today)["body"]
    assert any(expect in l for l in sections(body).get(section, [])), body


@pytest.mark.parametrize("db_name", ["followup", None])
def test_AC_04_8_body_is_plain_ascii_lf(fx, shipped_db, db_name):
    body = followup_json(fx(db_name) if db_name else shipped_db, "Karan Joshi")["body"]
    assert "\r" not in body and "\t" not in body and "—" not in body and body.isascii()


def test_AC_04_9_missing_contact_and_missing_file(shipped_db, tmp_path):
    j = followup_json(shipped_db, "Karan Joshi", contacts="contacts_without_karan.csv")
    assert j["to"] == [] and any("no email address for Karan Joshi" in w for w in j["warnings"])
    r = run_cli("followup", "Karan Joshi", "--dry-run", "--contacts", tmp_path / "none.csv", db=shipped_db)
    assert r.returncode == 0 and "contacts file not found" in json.loads(r.stdout)["warnings"][0]


@pytest.mark.parametrize("owner,code", [("Priya", 2), ("Priya (ambiguous)", 2), ("Unassigned", 2),
                                        ("Nobody Here", 3)])
def test_AC_04_10_bad_owners(shipped_db, owner, code):
    r = run_cli("followup", owner, "--dry-run", db=shipped_db)
    assert r.returncode == code and r.stdout == ""
    if owner == "Priya":
        assert "Priya Nair" in r.stderr and "Priya Shah" in r.stderr


def test_AC_04_11_priya_needs_review_not_counted(shipped_db):
    j = followup_json(shipped_db, "Priya Nair")
    s = sections(j["body"])
    assert any("Sign off the cutover checklist" in l for l in s["Needs review"])
    n = len(s.get("Overdue", [])) + len(s.get("Open", []))
    assert j["subject"] == f"Follow-up: your open action items ({n})"


def test_AC_04_12_co_owner_annotations(shipped_db):
    lena = followup_json(shipped_db, "Lena Fischer")
    priya = followup_json(shipped_db, "Priya Nair")
    assert "Collect user feedback on the prototype (with Priya Nair)" in lena["body"]
    assert "Collect user feedback on the prototype (with Lena Fischer)" in priya["body"]
    assert lena["to"] == ["lena.fischer@example.com"]


@pytest.mark.parametrize("owner", ["Meera Iyer", "Priya Shah"])
def test_AC_04_13_nothing_to_send(fx, owner):
    j = followup_json(fx("followup"), owner)
    assert j["subject"] is None and j["body"] is None
    assert "no open or overdue items; no draft needed" in j["warnings"]


def _python_sources():
    dirs = [d for d in (ROOT / "src", ROOT / "actiontrack") if d.is_dir()]
    return [p for d in dirs for p in d.rglob("*.py")]


FORBIDDEN_MODULES = {"smtplib", "imaplib", "http.client", "urllib.request", "socket", "requests",
                     "httpx", "googleapiclient"}
FORBIDDEN_TEXT = re.compile(r"messages\.send|messages\(\)\.send|drafts\.send|send_email|send_message|"
                            r"send_draft|gmail_send|sendmail|\.send\s*\(|def\s+send|mcp__\w*send", re.I)


def violations(source):
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        found += [n for n in names if n in FORBIDDEN_MODULES or n.split(".")[0] in {"smtplib", "imaplib",
                  "socket", "requests", "httpx", "googleapiclient"}]
    found += FORBIDDEN_TEXT.findall(source)
    return found


def test_AC_04_14_no_send_function_or_network_module_in_source():
    assert violations("import smtplib\nfrom urllib import request\nx.drafts.send()\nsend_email()") != []
    files = _python_sources()
    assert files, "no package source found under actiontrack/ or src/ (nothing implemented yet)"
    bad = {str(p.relative_to(ROOT)): violations(p.read_text(encoding="utf-8")) for p in files}
    assert {k: v for k, v in bad.items() if v} == {}


def test_AC_04_15_network_disabled_output_unchanged(shipped_db):
    c = str(FIXTURES / "contacts" / "contacts.csv")
    args = ["followup", "Karan Joshi", "--dry-run", "--contacts", c]
    base = run_cli(*args, db=shipped_db)
    code = ("import socket, sys, runpy, json\n"
            "def boom(*a, **k): raise RuntimeError('network disabled')\n"
            "socket.socket = boom; socket.create_connection = boom; socket.getaddrinfo = boom\n"
            "sys.argv = ['actiontrack', '--db', sys.argv[1]] + json.loads(sys.argv[2])\n"
            "runpy.run_module('actiontrack', run_name='__main__')\n")
    import os
    env = {**os.environ, "ACTIONTRACK_TODAY": TODAY, "PYTHONUTF8": "1",
           "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "src")])}
    r = subprocess.run([sys.executable, "-c", code, str(shipped_db), json.dumps(args)], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert base.returncode == 0
    assert (r.returncode, r.stdout) == (base.returncode, base.stdout)


@pytest.mark.parametrize("extra", [["--dry-run"], []])
def test_AC_04_16_database_untouched(shipped_db, tmp_path, extra):
    import shutil
    db = tmp_path / "copy.db"
    shutil.copy(shipped_db, db)
    st, names = db.stat(), sorted(p.name for p in tmp_path.iterdir())
    before = db.read_bytes()
    r = run_cli("followup", "Karan Joshi", *extra, "--contacts", FIXTURES / "contacts" / "contacts.csv", db=db)
    assert r.returncode == 0
    assert db.read_bytes() == before and db.stat().st_mtime_ns == st.st_mtime_ns
    assert sorted(p.name for p in tmp_path.iterdir()) == names


def test_AC_04_16_connection_opened_read_only():
    files = _python_sources()
    assert files, "no package source found"
    assert any("mode=ro" in p.read_text(encoding="utf-8") for p in files)


def test_AC_04_17_send_is_denied_and_blocked():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    for tool in ("mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_Gmail__send_draft"):
        assert any(fnmatch.fnmatch(tool, pat) for pat in deny), tool
    assert any("block_send.py" in h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"])
    hook = ROOT / ".claude" / "hooks" / "block_send.py"

    def run(tool):
        return subprocess.run([sys.executable, str(hook)], input=json.dumps({"tool_name": tool}),
                              capture_output=True, text=True).returncode
    assert run("mcp__claude_ai_Gmail__send_message") == 2
    assert run("mcp__gmail__SendDraft") == 2
    assert run("mcp__claude_ai_Gmail__create_draft") == 0
    skill = (ROOT / ".claude" / "skills" / "followup-email" / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"create[_-]draft", skill)
    front = skill.split("---")[1]
    assert "send" not in "".join(l for l in front.splitlines() if l.startswith("allowed-tools")).lower()


def test_AC_04_18_preview_without_dry_run(shipped_db):
    c = FIXTURES / "contacts" / "contacts.csv"
    r = run_cli("followup", "Karan Joshi", "--contacts", c, db=shipped_db)
    assert r.returncode == 0
    assert r.stdout.startswith("To: karan.joshi@example.com\nSubject: Follow-up: your open action items (10)\n\n")
    assert "Hi Karan," in r.stdout
    assert "note: preview only; nothing was sent or drafted" in r.stderr


# ---- behaviours / edge cases ----------------------------------------------------------------------------------------
def test_BEH_04_full_body_on_fixture(fx):
    j = followup_json(fx("followup"), "Karan Joshi")
    assert j["subject"] == "Follow-up: your open action items (6)"
    assert j["body"].rstrip("\n") == FIXTURE_KARAN_BODY


def test_BEH_04_first_name_unique_resolves_like_list(shipped_db):
    assert followup_json(shipped_db, "Karan")["owner"] == "Karan Joshi"


def test_BEH_04_empty_section_omitted_and_needs_review_order(fx):
    lena = followup_json(fx("followup"), "Lena Fischer")["body"]
    assert "Overdue" not in lena and "Open (1)" in lena
    priya = sections(followup_json(fx("followup"), "Priya Nair")["body"])
    assert len(priya["Open"]) == 1 and "(with Lena Fischer)" in priya["Open"][0]
    assert [l.split(" (written")[0] for l in priya["Needs review"]] == [
        "- Book the review room", "- Sign off the cutover checklist"]


def test_BEH_04_contacts_bom_crlf_and_duplicates(fx):
    assert followup_json(fx("followup"), "Karan Joshi", contacts="contacts_bom_crlf.csv")["to"] == [
        "karan.joshi@example.com"]
    j = followup_json(fx("followup"), "Karan Joshi", contacts="contacts_duplicate.csv")
    assert j["to"] == ["karan.first@example.com"] and j["warnings"]
