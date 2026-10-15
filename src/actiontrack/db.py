"""SQLite storage."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL, co_owners TEXT NOT NULL DEFAULT '[]', owner_raw TEXT,
  task TEXT NOT NULL, task_key TEXT NOT NULL,
  due_date TEXT, due_raw TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  first_seen TEXT, done_date TEXT,
  done_manual INTEGER NOT NULL DEFAULT 0, done_manual_date TEXT,
  review_reason TEXT
);
CREATE TABLE IF NOT EXISTS sightings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  file TEXT NOT NULL, line INTEGER NOT NULL,
  meeting_date TEXT NOT NULL, attendees TEXT NOT NULL DEFAULT '[]',
  checked INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL,
  owner_raw TEXT, task_text TEXT NOT NULL, due_raw TEXT, due_date TEXT,
  owner TEXT, co_owners TEXT, review_reason TEXT
);
CREATE INDEX IF NOT EXISTS sightings_file ON sightings(file);
CREATE INDEX IF NOT EXISTS sightings_item ON sightings(item_id);
"""


def connect(path, readonly=False):
    if readonly:
        con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        con = sqlite3.connect(str(path))
        con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def roster(con):
    """Distinct attendee names across all stored sightings, sorted."""
    import json
    names = set()
    for (a,) in con.execute("SELECT DISTINCT attendees FROM sightings"):
        names.update(json.loads(a))
    return sorted(names)
