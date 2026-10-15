"""Command-line interface: ingest, list, done, followup. Read-only except ingest/done."""
import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import dates, db
from .ingest import ingest


class CliError(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def _iso_date(v):
    try:
        if len(v) != 10:
            raise ValueError
        return date.fromisoformat(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date: '{v}' (want YYYY-MM-DD)") from None


def _pos_int(v):
    try:
        n = int(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid id: '{v}'") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"invalid id: '{v}'")
    return n


def _dbpath(args):
    return args.db or os.environ.get("ACTIONTRACK_DB") or "actiontrack.db"


def _open_existing(args, readonly=True):
    p = _dbpath(args)
    if not Path(p).is_file():
        raise CliError(f"database not found: {p} (run ingest first)")
    return db.connect(p, readonly=readonly)


# ---- ingest ---------------------------------------------------------------------------------
def cmd_ingest(args):
    if not Path(args.path).exists():
        raise CliError(f"path not found: {args.path}")
    r = ingest(args.path, _dbpath(args))
    print(f"ingest: scanned={r['scanned']} ingested={r['ingested']} skipped={len(r['skipped'])} "
          f"items={r['items']} sightings={r['sightings']} new_items={r['new_items']} "
          f"new_sightings={r['new_sightings']}")
    for f, reason in r["skipped"]:
        print(f"skipped: {f}: {reason}")
    for f, ln, msg in r["warnings"]:
        print(f"warning: {f}{':' + str(ln) if ln else ''}: {msg}")
    return 0


# ---- owner lookup (shared by list and followup) ----------------------------------------------
def resolve_owner(con, name):
    """-> canonical owner string as stored. Raises CliError(2|3)."""
    roster = db.roster(con)
    stored = set()
    for r in con.execute("SELECT owner, co_owners FROM items"):
        stored.add(r["owner"])
        stored.update(json.loads(r["co_owners"] or "[]"))
    known = sorted(set(roster) | stored)
    key = name.strip().casefold()
    for n in known:
        if n.casefold() == key:
            return n
    if len(key.split()) == 1:
        cands = [n for n in roster if n.split()[0].casefold() == key]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            raise CliError(f"owner '{name}' is ambiguous: {', '.join(cands)}", 2)
    raise CliError(f"unknown owner: {name}", 3)


def _cap(task):
    return task[:1].upper() + task[1:]


def _owns(item, person):
    return item["owner"] == person or person in json.loads(item["co_owners"] or "[]")


def _hidden_note(con, person):
    if " " not in person:
        return
    label = f"{person.split()[0]} (ambiguous)"
    n = con.execute("SELECT count(*) FROM items WHERE owner = ?", (label,)).fetchone()[0]
    if n:
        print(f"note: {n} item(s) owned by '{label}' not shown", file=sys.stderr)


# ---- list -----------------------------------------------------------------------------------
def cmd_list(args):
    today = dates.today().isoformat()
    con = _open_existing(args)
    person = resolve_owner(con, args.owner) if args.owner else None
    out = []
    for it in con.execute("SELECT * FROM items ORDER BY due_date IS NULL, due_date, id"):
        overdue = it["status"] == "open" and it["due_date"] is not None and it["due_date"] < today
        status = "overdue" if overdue else it["status"]
        if person and not _owns(it, person):
            continue
        if args.status == "open" and it["status"] != "open":
            continue
        if args.status == "done" and it["status"] != "done":
            continue
        if args.status == "overdue" and not overdue:
            continue
        if args.due_before and not (it["due_date"] and it["due_date"] < args.due_before.isoformat()):
            continue
        task = _cap(it["task"])
        co = json.loads(it["co_owners"] or "[]")
        if co:
            task += f" (with {', '.join(co)})"
        out.append("\t".join([str(it["id"]), status, it["owner"], it["due_date"] or "-",
                              task.replace("\t", " ")]))
    print("ID\tSTATUS\tOWNER\tDUE\tTASK")
    for line in out:
        print(line)
    if person:
        _hidden_note(con, person)
    print(f"{len(out)} item(s)", file=sys.stderr)
    return 0


# ---- done -----------------------------------------------------------------------------------
def cmd_done(args):
    today = dates.today().isoformat()
    con = _open_existing(args, readonly=False)
    it = con.execute("SELECT * FROM items WHERE id = ?", (args.id,)).fetchone()
    if not it:
        raise CliError(f"no such item: {args.id}", 3)
    if it["status"] == "done":
        print(f"already done: #{it['id']} {it['task']}")
        return 0
    with con:
        con.execute("UPDATE items SET status='done', done_manual=1, done_manual_date=?, done_date=? WHERE id=?",
                    (today, today, args.id))
    print(f"done: #{it['id']} {it['task']}")
    return 0


# ---- followup (read-only; produces JSON for Claude Code to turn into a Gmail draft) -------------
def _load_contacts(path, warnings):
    p = Path(path)
    if not p.is_file():
        warnings.append(f"contacts file not found: {path}")
        return None
    out = {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if not name:
                continue
            if name.casefold() in out:
                warnings.append(f"duplicate contact for {name} in {path}; using the first")
                continue
            out[name.casefold()] = email
    return out


_ASCII = str.maketrans({"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"',
                        "”": '"', "…": "...", "\t": " ", " ": " "})


def _source(con, item_id):
    r = con.execute("SELECT file FROM sightings WHERE item_id = ? ORDER BY meeting_date, file, line LIMIT 1",
                    (item_id,)).fetchone()
    f = r["file"] if r else "unknown"
    return f[:-3] if f.endswith(".md") else f


def build_followup(con, person, today, contacts_path):
    warnings = []
    contacts = _load_contacts(contacts_path, warnings)
    to = []
    if contacts is not None:
        email = contacts.get(person.casefold())
        if email:
            to = [email]
        else:
            warnings.append(f"no email address for {person} in {contacts_path}")
    items = [dict(i) for i in con.execute("SELECT * FROM items WHERE status = 'open'")
             if _owns(i, person)]
    iso = today.isoformat()
    over = sorted((i for i in items if i["due_date"] and i["due_date"] < iso), key=lambda i: (i["due_date"], i["id"]))
    rest = sorted((i for i in items if not (i["due_date"] and i["due_date"] < iso)),
                  key=lambda i: (i["due_date"] is None, i["due_date"] or "", i["id"]))
    if not over and not rest:
        warnings.append("no open or overdue items; no draft needed")
        return {"owner": person, "to": to, "subject": None, "body": None, "warnings": warnings}

    def label(i):
        others = [n for n in [i["owner"]] + json.loads(i["co_owners"] or "[]") if n != person]
        t = _cap(i["task"])
        return t + (f" (with {', '.join(others)})" if others and (len(others) < len(json.loads(i["co_owners"] or "[]")) + 1) else "")

    first = person.split()[0]
    lines = [f"Hi {first},", "", f"Here is where your action items from our meeting notes stand as of {iso}.", ""]
    if over:
        lines.append(f"Overdue ({len(over)})")
        for i in over:
            k = (today - date.fromisoformat(i["due_date"])).days
            lines.append(f"- {label(i)} (due {i['due_date']}, {k} {'day' if k == 1 else 'days'} overdue; "
                         f"from {_source(con, i['id'])})")
        lines.append("")
    if rest:
        lines.append(f"Open ({len(rest)})")
        for i in rest:
            if i["due_date"]:
                d = f"due {i['due_date']}"
            elif i["due_raw"]:
                d = f'no due date; note says "{i["due_raw"]}"'
            else:
                d = "no due date"
            lines.append(f"- {label(i)} ({d}; from {_source(con, i['id'])})")
        lines.append("")
    review = []
    for i in con.execute("SELECT * FROM items WHERE status = 'open' ORDER BY first_seen, id"):
        if i["owner"] == f"{first} (ambiguous)":
            review.append(i)
        elif i["owner"] == "Unassigned" and any(
                person in json.loads(s["attendees"]) for s in
                con.execute("SELECT attendees FROM sightings WHERE item_id = ?", (i["id"],))):
            review.append(i)
    if review:
        lines += ["Needs review",
                  "These came from meetings you attended and have no clear owner. If any are yours, please let me know:"]
        for i in review:
            w = f'written as "{i["owner_raw"]}"' if i["owner_raw"] else "no owner named"
            lines.append(f"- {_cap(i['task'])} ({w}; from {_source(con, i['id'])})")
        lines.append("")
    lines.append("Thanks!")
    body = "\n".join(lines).translate(_ASCII)
    return {"owner": person, "to": to, "subject": f"Follow-up: your open action items ({len(over) + len(rest)})",
            "body": body, "warnings": warnings}


def cmd_followup(args):
    today = dates.today()
    con = _open_existing(args)
    low = args.owner.strip().casefold()
    if low == "unassigned" or low.endswith("(ambiguous)"):
        raise CliError(f"cannot draft a follow-up for '{args.owner}'", 2)
    person = resolve_owner(con, args.owner)
    res = build_followup(con, person, today, args.contacts)
    if args.dry_run:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"To: {', '.join(res['to'])}")
        print(f"Subject: {res['subject']}")
        print()
        print(res["body"] or "")
        print("note: preview only; nothing was sent or drafted", file=sys.stderr)
    return 0


# ---- entry point ------------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="actiontrack", description="Track action items from meeting notes.")
    p.add_argument("--db", help="database file (default: $ACTIONTRACK_DB or ./actiontrack.db)")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("ingest", help="parse notes into the database")
    s.add_argument("path", nargs="?", default="notes")
    s.set_defaults(func=cmd_ingest)
    s = sub.add_parser("list", help="list items")
    s.add_argument("--owner")
    s.add_argument("--status", choices=["open", "done", "overdue"])
    s.add_argument("--due-before", type=_iso_date)
    s.set_defaults(func=cmd_list)
    s = sub.add_parser("done", help="mark an item done")
    s.add_argument("id", type=_pos_int)
    s.set_defaults(func=cmd_done)
    s = sub.add_parser("followup", help="preview a follow-up email (JSON with --dry-run); never sends")
    s.add_argument("owner")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--contacts", default="contacts.csv")
    s.set_defaults(func=cmd_followup)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    try:
        dates.today()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except Exception as e:  # never show a traceback
        print(f"error: {e}", file=sys.stderr)
        return 1
