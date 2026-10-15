# 00 Overview

Status: draft v1. Source of truth for scope, data model and agreed decisions.
Read `findings.md` for the raw facts about `notes/`. Specs 01 to 04 refine this one.

## Purpose
actiontrack reads meeting notes (`notes/*.md`), extracts action items, tracks them in a
local SQLite database across repeated meetings, and prepares follow-up emails as Gmail
**drafts** for a human to review. It never sends email.

## Commands
Run as `python -m actiontrack <cmd>`. Details in `03-cli.md` and `04-followup-gmail.md`.

| Command | What it does |
|---|---|
| `ingest [PATH]` | Parse notes, upsert items and sightings. Idempotent. Reports skipped files. |
| `list` | Show items; filter by `--owner`, `--status open\|done\|overdue`, `--due-before`. |
| `done <id>` | Mark one item done by hand. |
| `followup <owner> [--dry-run]` | Render one follow-up email for one owner. Read-only. `--dry-run` prints JSON for Claude Code to turn into a Gmail draft. |

## Data model
SQLite file (default `./actiontrack.db`). All dates are ISO `YYYY-MM-DD` text or NULL.

**items**: one row per distinct task, however many meetings mention it.

| Column | Meaning |
|---|---|
| `id` | Integer primary key, stable across re-ingest. |
| `owner` | Canonical primary owner: full name, `Unassigned`, or `<First> (ambiguous)`. |
| `co_owners` | JSON array of full names (may be `[]`). See 02. |
| `owner_raw` | Owner text exactly as written in the earliest sighting (`Priya N.`, `@anita`, `Someone`). |
| `task` | Task text from the earliest sighting, due clause removed (01). |
| `task_key` | Normalized task text used for matching (02). |
| `due_date` | Due date of the latest sighting that has one; NULL if none. |
| `due_raw` | Raw due clause that goes with `due_date`; else the latest non-empty raw clause (`from 9 Oct`); else NULL. |
| `status` | `open` or `done`. Overdue is **never stored**; see glossary. |
| `first_seen` | Meeting date of the earliest sighting. |
| `done_date` | Meeting date of the earliest `[x]` sighting, or today's date for `done <id>`; NULL while open. |
| `done_manual` | 1 if marked done by `done <id>`. Survives re-ingest. |
| `review_reason` | NULL, or `unassigned`, `ambiguous_owner`, `unknown_owner`. |

**sightings**: one row per task occurrence in a note. An item has 1..n sightings.

| Column | Meaning |
|---|---|
| `id`, `item_id` | Keys. |
| `file` | Path relative to the ingest root, forward slashes (`2026-09-01-quote-portal-kickoff.md`). |
| `line` | 1-based line number. Informational only; never part of matching. |
| `meeting_date` | Resolved meeting date (01). |
| `attendees` | JSON array of full names in that note (may be `[]`). |
| `checked` | 1 for `[x]`/`[X]`, else 0. |
| `source` | `checkbox`, `table` or `action_line`. |
| `owner_raw`, `task_text`, `due_raw`, `due_date` | Parsed values for this occurrence. |

## Glossary
- **Meeting date**: the date a note is about; the base for all relative dates.
- **Sighting**: one occurrence of an action item in one note.
- **Item**: the de-duplicated task behind one or more sightings.
- **Roster**: all distinct attendee full names across the notes being ingested (9 people today).
- **owner_key**: lower-cased canonical owner. **task_key**: normalized task text. **Fingerprint** = (owner_key, task_key).
- **Placeholder owner**: `Everyone`, `Team`, `Someone`, `TBD`. Becomes `Unassigned`.
- **Ambiguous owner**: a first name shared by 2+ roster people that cannot be resolved, e.g. `Priya (ambiguous)`.
- **Needs review**: items with a `review_reason`.
- **Overdue**: `status = open AND due_date < today`. Computed on read, strictly less than. Done items and NULL due dates are never overdue.
- **Today**: env `ACTIONTRACK_TODAY` (`YYYY-MM-DD`) if set, else the system date. Read in exactly one helper.
- **Skipped note**: a file that is not usable (empty, binary, undecodable, no recoverable date, not `.md`). Reported, never fatal.

## Decisions (agreed)
D1. Overdue is computed, not stored; a task due today is not overdue.
D2. "by Friday" = first Friday strictly after the meeting date. Relative phrases resolve against the **meeting date**, not today (01).
D3. No owner means `Unassigned`. No date means `due_date` NULL, with the raw text kept in `due_raw`.
D4. Duplicates: same owner_key and (task_key equal or `difflib` ratio >= 0.85). Keep the earliest item, record every sighting, a later `[x]` marks it done.
D5. Same first name: resolve through the note's attendee list to a full name; otherwise `<First> (ambiguous)`, flagged. `--owner` accepts a full name, or errors with the candidates.
D6. A malformed note is skipped and reported (file and reason). Ingest still exits 0.
D7. Ingest is idempotent.
D8. `ACTIONTRACK_TODAY` makes "today" injectable; a bad value is an error (exit 2).
D9. Only `.md` files are ingested. Files are read as UTF-8 after stripping `\r`.
D10. Meeting date source order: `Date:` header, front matter `date:`, filename. A bad header date falls back to the filename with a warning (recoverable, so not skipped).
D11. The table row and the `ACTION:` line in `2026-09-30-q4-offsite.md` are action items. Prose sentences are not. Fenced code, HTML comments and `>` blockquotes are ignored.
D12. Only the leading name is the owner (`Rahul to review Anita's PR` is Rahul's). Multiple owners: first is primary, the rest are co-owners; `--owner` matches either.
D13. Only `by | due | before | until | on` + a date is a deadline. `from 9 Oct`, `for Saturday 10 Oct`, `for November` are not: due NULL, raw text kept.
D14. Overdue/Open split, subject line and email layout are fixed in 04.
D15. The CLI never sends email and never talks to Gmail. Claude Code creates the draft (04).

## Decisions I made on the open questions (please confirm or overrule)
The five questions in session 2 were not answered in the record I had. I chose:
Q1. A re-planned task keeps the **latest** non-null due date (first-seen stays earliest). Example: Anita's welcome-email copy moves `Wed 16 Sep`, then `Friday`.
Q2. `Everyone`, `Team`, `Someone`, `TBD` all become `Unassigned` (raw text kept in `owner_raw`); not expanded to attendees.
Q3. `Priya (ambiguous)` items are **not** shown under `--owner "Priya Nair"` (a stderr note says how many were hidden) and are not in her Overdue/Open lists; they appear in the needs-review note of her email (04).
Q4. Recipient addresses come from `contacts.csv` (`name,email`), never invented. One email per owner across all meetings.
Q5. `2026-10-03-sales-pipeline.md` (`Date: sometime last week`) is ingested using its filename date, with a warning. `untitled.md` is skipped (no date anywhere).
Also added: the normalizer drops the words `a an the first updated revised` so the wireframes repeat (`first` / `updated`, measured 0.78 without it) merges at the agreed 0.85 threshold.
Also added: `>` blockquoted checkboxes are ignored (`2026-09-21-incident-review.md:9` is a customer wish, not an agreed action).

## Out of scope
Sending email, reading Gmail, editing notes, reopening done items, a UI, recurring jobs.

## Acceptance Criteria
- AC-1: `python -m actiontrack --help` lists exactly the four commands `ingest`, `list`, `done`, `followup`.
- AC-2: After `ingest` the database has tables `items` and `sightings` with the columns above; no `overdue` column exists.
- AC-3: Every date column in both tables is NULL or matches `^\d{4}-\d{2}-\d{2}$`.
- AC-4: `ingest` of the shipped `notes/` directory scans 36 files, ingests 32, skips 4 (`scratch.md`, `2026-09-09-notes-final-v2.md`, `untitled.md`, `2026-09-19-offsite-draft.txt`), exits 0, and stores 117 sightings (115 checkbox lines, plus the table row and the `ACTION:` line), 13 of them checked.
- AC-5: With `ACTIONTRACK_TODAY=2026-10-15`, an open item due `2026-10-15` is not overdue and one due `2026-10-14` is.
- AC-6: With `ACTIONTRACK_TODAY=not-a-date`, every command exits 2 and names the variable in its error.
- AC-7: Every decision D1..D15 is covered by at least one AC in specs 01 to 04; `specs/traceability.md` lists the mapping and a test fails if a D-number has no AC.
