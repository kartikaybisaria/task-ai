# actiontrack

A small CLI that turns meeting notes (`notes/*.md`) into a tracked list of action items:
who owns what, when it is due, what is overdue, and a ready-to-review follow-up email draft per owner.
Stack: Python 3 stdlib only (`argparse`, `sqlite3`, `difflib`).

## Install
```
python -m venv .venv
.venv\Scripts\activate          # Windows (source .venv/bin/activate elsewhere)
pip install pytest
```
Run from the repo root with `PYTHONPATH=src` (or `pip install -e .` if you add packaging): `python -m actiontrack ...`.

## Usage
```
python -m actiontrack ingest notes                 # parse notes into actiontrack.db (idempotent)
python -m actiontrack list --status overdue        # also: --owner "Karan Joshi", --due-before 2026-10-20
python -m actiontrack done 12                      # mark item 12 done (today's date recorded)
python -m actiontrack followup "Karan Joshi" --dry-run   # print the email as JSON; never sends
```
Global: `--db PATH` (or `ACTIONTRACK_DB`), `ACTIONTRACK_TODAY=YYYY-MM-DD` to fix "today" (bad value: exit 2).
Exit codes: 0 ok, 1 runtime error, 2 usage/value error, 3 not found.

## SDD workflow
Specs first (`specs/00`..`04`, with numbered acceptance criteria), then tests (`tests/test_specNN_*.py`,
one test per AC, plus `specs/traceability.md` mapping decisions D1..D15 to ACs), then code in `src/actiontrack`.
The Claude Code conversation exports used to build this are in `exports/export-1..5.txt`.

## Design decisions
- **Overdue** is computed against today, never stored; a task due today is not overdue.
- **Relative dates** ("by Friday", "tomorrow", "eow") resolve against the meeting date, not today; "by Friday" is the first Friday strictly after the meeting.
- **Duplicates**: same owner and equal normalized task, or `difflib` ratio >= 0.85. The earliest item is kept, every sighting is recorded, and a later `[x]` marks it done.
- **Same first name**: resolved to a full name via the note's attendee list, otherwise `<First> (ambiguous)` and flagged; `--owner` errors with candidates.
- **Malformed notes** (empty, binary, undecodable, bad extension, no recoverable date, out-of-range dates) are skipped and reported; ingest still exits 0 and never shows a traceback.
- **Idempotent ingest**: re-running on unchanged notes adds nothing.

## MCP constraint: drafts, never sends
The CLI never talks to Gmail. `followup --dry-run` only renders the email (`to`, `subject`, `body`) as JSON.
Claude Code, following the `followup-email` skill (`/followup <owner>`), reads that JSON and creates a Gmail
**draft** through the Gmail MCP create-draft tool. The human reviews and sends it. Sending is blocked in depth:
no send code in `src/`, permission deny rules in `.claude/settings.json`, and a PreToolUse hook
(`.claude/hooks/block_send.py`) that refuses send tools and send-like shell commands.

## Test result

```
$ pytest -q
219 passed in 48.70s
```
