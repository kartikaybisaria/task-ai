"""Shared test helpers. Interface ASSUMPTIONS (not named in the specs; add to spec 01 s7 / 02):
  actiontrack.parser.parse_note(path) -> (note | None, error | None)
      note: meeting_date, attendees, warnings [(line|None, msg)], sightings
      sighting: owner_raw, owner_names, task_text, checked, due_raw, due_date, source, line
  actiontrack.matching.normalize(text) -> task_key
Everything else goes through the CLI (`python -m actiontrack`) and the SQLite file.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
SHIPPED = ROOT / "notes"
TODAY = "2026-10-15"


def parse_note(path):
    from actiontrack.parser import parse_note as f
    return f(Path(path))


def normalize(text):
    from actiontrack.matching import normalize as f
    return f(text)


def iso(v):
    return None if v is None else str(v)


def run_cli(*args, db=None, today=TODAY, env=None, cwd=None):
    e = os.environ.copy()
    e.pop("ACTIONTRACK_TODAY", None)
    e.pop("ACTIONTRACK_DB", None)
    e["PYTHONUTF8"] = "1"
    e["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src")])
    if today is not None:
        e["ACTIONTRACK_TODAY"] = today
    e.update(env or {})
    cmd = [sys.executable, "-m", "actiontrack"]
    if db is not None:
        cmd += ["--db", str(db)]
    cmd += [str(a) for a in args]
    return subprocess.run(cmd, cwd=cwd or ROOT, env=e, capture_output=True,
                          text=True, encoding="utf-8")


def ingest(db, path, today=TODAY):
    return run_cli("ingest", path, db=db, today=today)


def rows(db, sql, params=()):
    con = sqlite3.connect(Path(db).as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def find_item(db, owner, fragment):
    got = rows(db, "SELECT * FROM items WHERE owner = ? AND lower(task) LIKE ?",
               (owner, f"%{fragment.lower()}%"))
    assert len(got) == 1, f"expected 1 item for {owner!r}/{fragment!r}, got {len(got)}"
    return got[0]


def sightings_of(db, item_id):
    return rows(db, "SELECT * FROM sightings WHERE item_id = ? ORDER BY meeting_date, file, line",
                (item_id,))


def parse_list(stdout):
    lines = stdout.split("\n")
    assert lines[-1] == ""
    header, body = lines[0], lines[1:-1]
    cols = ["ID", "STATUS", "OWNER", "DUE", "TASK"]
    assert header == "\t".join(cols), header
    return [dict(zip(cols, r.split("\t"))) for r in body]


def summary(stdout):
    first = stdout.splitlines()[0]
    assert first.startswith("ingest: ")
    return dict(kv.split("=") for kv in first[len("ingest: "):].split())


def write_note(tmp_path, lines, date="2026-09-01",
               attendees=("Anita Desai", "Rahul Mehta", "Sam Okafor"), name=None):
    p = Path(tmp_path) / (name or f"{date}-t.md")
    head = ["# Meeting: t", f"Date: {date}"]
    if attendees:
        head.append("Attendees: " + ", ".join(attendees))
    p.write_text("\n".join(head + ["", "## Action items"] + list(lines)) + "\n", encoding="utf-8")
    return p


def parse_lines(tmp_path, lines, **kw):
    note, err = parse_note(write_note(tmp_path, lines, **kw))
    assert err is None, err
    return note


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from strings(v)
    elif hasattr(obj, "__dict__"):
        yield from strings(vars(obj))


def sections(body):
    """Split an email body into {heading-prefix: [bullet lines]} (Overdue/Open/Needs review)."""
    out, cur = {}, None
    for ln in body.split("\n"):
        if ln.startswith("Overdue ("):
            cur = out.setdefault("Overdue", [])
        elif ln.startswith("Open ("):
            cur = out.setdefault("Open", [])
        elif ln == "Needs review":
            cur = out.setdefault("Needs review", [])
        elif ln == "Thanks!":
            cur = None
        elif ln.startswith("- ") and cur is not None:
            cur.append(ln)
    return out


def followup_json(db, owner, *extra, today=TODAY, contacts="contacts.csv"):
    c = FIXTURES / "contacts" / contacts
    r = run_cli("followup", owner, "--dry-run", "--contacts", c, *extra, db=db, today=today)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)
