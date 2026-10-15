"""Ingest note files into the database (idempotent, per-file transactions)."""
import json
from pathlib import Path

from . import db
from .dedup import best_match, normalize
from .owners import resolve
from .parser import parse_note

COLS = ("line", "meeting_date", "attendees", "checked", "source", "owner_raw", "task_text",
        "due_raw", "due_date", "owner", "co_owners", "review_reason")


def _iso(d):
    return None if d is None else d.isoformat()


def build_rows(note, roster):
    """Resolve owners and return (rows, warnings) for one parsed note."""
    rows, warns = [], []
    for s in note.sightings:
        res = [resolve(n, note.attendees, roster) for n in s.owner_names]
        for n, (owner, reason, cands) in zip(s.owner_names, res):
            if reason == "ambiguous_owner":
                warns.append((s.line, f"owner '{n}' is ambiguous ({', '.join(cands)})"))
        rows.append({
            "line": s.line, "meeting_date": _iso(note.meeting_date),
            "attendees": json.dumps(note.attendees, ensure_ascii=False),
            "checked": int(bool(s.checked)), "source": s.source, "owner_raw": s.owner_raw,
            "task_text": s.task_text, "due_raw": s.due_raw, "due_date": _iso(s.due_date),
            "owner": res[0][0], "co_owners": json.dumps([r[0] if r[1] != "unknown_owner" else r[0] for r in res[1:]],
                                                        ensure_ascii=False),
            "review_reason": res[0][1],
        })
    return rows, warns


def recompute(con, item_id):
    ss = con.execute("SELECT * FROM sightings WHERE item_id = ? ORDER BY meeting_date, file, line",
                     (item_id,)).fetchall()
    if not ss:
        return
    it = con.execute("SELECT done_manual, done_manual_date FROM items WHERE id = ?", (item_id,)).fetchone()
    first = ss[0]
    dated = [s for s in ss if s["due_date"]]
    if dated:
        due, raw = dated[-1]["due_date"], dated[-1]["due_raw"]
    else:
        raws = [s["due_raw"] for s in ss if s["due_raw"]]
        due, raw = None, (raws[-1] if raws else None)
    done_dates = [s["meeting_date"] for s in ss if s["checked"]][:1]
    if it["done_manual"] and it["done_manual_date"]:
        done_dates.append(it["done_manual_date"])
    done = bool(done_dates) or bool(it["done_manual"])
    con.execute(
        "UPDATE items SET owner=?, co_owners=?, owner_raw=?, task=?, task_key=?, due_date=?, due_raw=?, "
        "status=?, first_seen=?, done_date=?, review_reason=? WHERE id=?",
        (first["owner"], first["co_owners"], first["owner_raw"], first["task_text"],
         normalize(first["task_text"]), due, raw, "done" if done else "open", first["meeting_date"],
         min(done_dates) if done_dates else None, first["review_reason"], item_id))


def _place(con, row, file, new_ids):
    key = normalize(row["task_text"])
    cands = con.execute("SELECT id, task_key FROM items WHERE lower(owner) = ?",
                        (row["owner"].lower(),)).fetchall()
    item_id = best_match(key, [(c["id"], c["task_key"]) for c in cands])
    if item_id is None:
        cur = con.execute("INSERT INTO items (owner, co_owners, owner_raw, task, task_key, first_seen) "
                          "VALUES (?,?,?,?,?,?)",
                          (row["owner"], row["co_owners"], row["owner_raw"], row["task_text"], key,
                           row["meeting_date"]))
        item_id = cur.lastrowid
        new_ids.append(item_id)
    names = ["file", "item_id"] + list(COLS)
    con.execute(f"INSERT INTO sightings ({','.join(names)}) VALUES ({','.join('?' * len(names))})",
                [file, item_id] + [row[c] for c in COLS])
    return item_id


def list_files(path):
    p = Path(path)
    if p.is_dir():
        return sorted((f for f in p.iterdir() if f.is_file() and not f.name.startswith(".")),
                      key=lambda f: f.name)
    return [p]


def ingest(path, dbpath):
    """-> dict(scanned, ingested, skipped[(file, reason)], warnings[(file, line, msg)], items, sightings,
    new_items, new_sightings)."""
    files = list_files(path)
    parsed = {f.name: parse_note(f) for f in files}
    con = db.connect(dbpath)
    roster = set(db.roster(con))
    for note, _ in parsed.values():
        if note:
            roster.update(note.attendees)
    roster = sorted(roster)
    skipped, warnings = [], []
    new_items = new_sightings = ingested = 0
    for name in sorted(parsed):
        note, err = parsed[name]
        if err:
            skipped.append((name, err))
            continue
        ingested += 1
        warnings += [(name, ln, msg) for ln, msg in note.warnings]
        rows, owner_warns = build_rows(note, roster)
        warnings += [(name, ln, msg) for ln, msg in owner_warns]
        existing = [dict(r) for r in con.execute(
            f"SELECT {','.join(COLS)} FROM sightings WHERE file = ? ORDER BY line, id", (name,))]
        if existing == rows:
            continue
        with con:
            touched = {r[0] for r in con.execute("SELECT DISTINCT item_id FROM sightings WHERE file = ?", (name,))}
            con.execute("DELETE FROM sightings WHERE file = ?", (name,))
            new_ids = []
            for row in rows:
                touched.add(_place(con, row, name, new_ids))
            new_items += len(new_ids)
            new_sightings += len(rows)
            con.execute("DELETE FROM items WHERE done_manual = 0 AND id NOT IN (SELECT item_id FROM sightings)")
            for i in touched:
                recompute(con, i)
    warnings.sort(key=lambda w: (w[0], w[1] or 0))
    total_items = con.execute("SELECT count(*) FROM items").fetchone()[0]
    total_s = con.execute("SELECT count(*) FROM sightings").fetchone()[0]
    con.close()
    return {"scanned": len(files), "ingested": ingested, "skipped": sorted(skipped), "warnings": warnings,
            "items": total_items, "sightings": total_s, "new_items": new_items, "new_sightings": new_sightings}
