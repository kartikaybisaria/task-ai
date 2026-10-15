# 03 CLI

Exact flags, output formats and exit codes for `ingest`, `list`, `done`. (`followup` is in 04.)
Invoked as `python -m actiontrack [--db PATH] <command> ...`. Stack: `argparse` only.

## Purpose
A predictable, scriptable surface: stable columns, stable messages, stable exit codes, so tests
and Claude Code can rely on them. Data and rules come from 00 to 02.

## Behavior

### Global
- `--db PATH`: database file. Default: env `ACTIONTRACK_DB`, else `./actiontrack.db`. Created on first `ingest`.
- `ACTIONTRACK_TODAY=YYYY-MM-DD` sets "today". Invalid value: exit 2, stderr `error: ACTIONTRACK_TODAY must be YYYY-MM-DD, got '<value>'`.
- stdout carries results; stderr carries notes, warnings and errors. Output is UTF-8.
- `list`, `done` and `followup` on a missing database: exit 1, stderr `error: database not found: <path> (run ingest first)`.

### Exit codes (all commands)
| Code | Meaning |
|---|---|
| 0 | Success. **Includes** an ingest that skipped files, an empty `list`, and `done` on an item already done. |
| 1 | Runtime error: path missing, database missing or unwritable. |
| 2 | Usage or value error: unknown flag, bad `--status`, bad date, bad id, bad `ACTIONTRACK_TODAY`, ambiguous `--owner`. |
| 3 | Not found: `done <id>` with an unknown id; `--owner` that matches nobody. |

A Python traceback must never reach the user. Unexpected exceptions: exit 1, stderr `error: <message>`.

### `ingest [PATH]`
`PATH` is a directory or a single file; default `notes`. A directory is scanned non-recursively;
every regular, non-hidden file is considered, so non-`.md` files are reported, not silently ignored.
Files are processed sorted by name (02 section 5). Roster is built from all parseable notes in the target.

stdout, in this order:
```
ingest: scanned=<S> ingested=<I> skipped=<K> items=<total items> sightings=<total sightings> new_items=<n> new_sightings=<n>
skipped: <file>: <reason>          (one line per skipped file, sorted by file)
warning: <file>[:<line>]: <message> (one line per warning, sorted by file then line)
```
`items` and `sightings` are database totals after the run; `new_*` count rows added by this run.
Reasons are exactly those in 01 section 1: `empty file`, `binary content (NUL bytes)`,
`not valid UTF-8`, `unsupported extension (.txt)`, `no meeting date`.
Exit 0 even when `skipped > 0`. Exit 1 if `PATH` does not exist (stderr `error: path not found: <path>`).

Real run on the shipped `notes/`:
```
ingest: scanned=36 ingested=32 skipped=4 items=<n> sightings=117 new_items=<n> new_sightings=117
skipped: 2026-09-09-notes-final-v2.md: empty file
skipped: 2026-09-19-offsite-draft.txt: unsupported extension (.txt)
skipped: scratch.md: binary content (NUL bytes)
skipped: untitled.md: no meeting date
warning: 2026-09-23-standup.md: no attendees listed
warning: 2026-10-03-sales-pipeline.md: date 'sometime last week' not parseable; using filename date 2026-10-03
```
followed by one `warning:` line for each ambiguous owner (02), e.g.
`warning: 2026-10-07-standup.md:9: owner 'Rahul' is ambiguous (Rahul Mehta, Rahul Verma)`.

### `list`
Flags (all optional, combinable with AND):
- `--owner NAME`: matches `owner` or any `co_owners` entry, case-insensitive.
  - Full name (`Priya Nair`), `Unassigned`, or a literal ambiguous label (`"Priya (ambiguous)"`) match as given.
  - A first name that is unique in the roster (`Sam`) resolves to that person.
  - A first name shared by several people (`Priya`): exit 2, stderr `error: owner 'Priya' is ambiguous: Priya Nair, Priya Shah`. (The candidates, comma-separated, in roster order.)
  - Matches nobody known: exit 3, stderr `error: unknown owner: <NAME>`.
  - When the matched person has items under `<First> (ambiguous)`, stderr adds `note: <n> item(s) owned by '<First> (ambiguous)' not shown`.
- `--status {open,done,overdue}`: `open` = status open (overdue items included); `done`; `overdue` = open and `due_date < today`. Default: no filter.
- `--due-before YYYY-MM-DD`: `due_date < DATE`, strictly. NULL due dates are excluded. Bad value: exit 2.

stdout: a header line then one line per item, **tab-separated**:
```
ID	STATUS	OWNER	DUE	TASK
```
- `STATUS` is `overdue` for open items past due, else `open` or `done`.
- `DUE` is `YYYY-MM-DD` or `-`.
- `OWNER` is the primary owner; co-owners are appended to TASK as ` (with A, B)`.
- `TASK` is the item's task text with its first letter upper-cased.
- Rows sorted by `DUE` ascending (NULL last), then `ID` ascending.
- Empty result: the header line only, exit 0. stderr summary line: `<n> item(s)`.

### `done <id>`
- `id` is a positive integer (`argparse` type); otherwise exit 2.
- Open item: set `status=done`, `done_manual=1`, `done_date=today`; stdout `done: #<id> <task>`; exit 0.
- Already done: no change; stdout `already done: #<id> <task>`; exit 0. (`done_date` is not overwritten.)
- Unknown id: exit 3, stderr `error: no such item: <id>`.

## Edge cases
- `ingest` on a path with only skipped files: summary shows `ingested=0`, exit 0.
- `ingest` of one `.txt` file path: one `skipped:` line, exit 0.
- Re-running `ingest` after a file becomes unreadable: old data kept (02), file listed as skipped.
- `list --owner "Rahul Mehta"` does not show `Rahul (ambiguous)` items but prints the stderr note (3 hidden with the shipped notes).
- `list --owner Sam`: Sam Okafor is the only Sam, so it resolves.
- `list --status overdue --due-before 2026-10-01` combines both filters.
- Tabs inside task text (should not occur) are replaced by a space on output.
- `--status` given twice: last value wins (argparse default).

## Acceptance Criteria
- AC-1: `ingest` on the shipped `notes/` prints a summary line starting `ingest: scanned=36 ingested=32 skipped=4`, the four `skipped:` lines above, and exits 0.
- AC-2: `ingest` prints the `no attendees listed` warning for 2026-09-23-standup.md and the `sometime last week` warning for 2026-10-03-sales-pipeline.md, and nothing about those files is in `skipped:`.
- AC-3: `ingest nonexistent/` exits 1 with `error: path not found: nonexistent/` on stderr and no traceback.
- AC-4: `ingest notes/scratch.md` exits 0 with exactly one `skipped:` line.
- AC-5: Running `ingest` twice: the second summary has `new_items=0 new_sightings=0`, and both runs exit 0.
- AC-6: `list` prints the header `ID	STATUS	OWNER	DUE	TASK` first and every row has exactly 5 tab-separated fields.
- AC-7: With `ACTIONTRACK_TODAY=2026-10-15`, `list --owner "Karan Joshi" --status overdue` prints 6 rows; `--status open` prints 10 rows (6 overdue + 4 not overdue); `--status done` prints 3 rows.
- AC-8: Same date, `list --owner "Karan Joshi" --status open`: the row `Reconcile September ledger` (due 2026-10-15) has STATUS `open`, and the row `Send Acme the revised pricing sheet` (due 2026-10-01) has STATUS `overdue`.
- AC-9: `list --due-before 2026-10-01` includes only items with `DUE` < 2026-10-01 and never a `-` row; `list --due-before 2026-10-01x` exits 2.
- AC-10: `list --owner Priya` exits 2 and stderr contains `Priya Nair` and `Priya Shah`. `list --owner Nobody` exits 3.
- AC-11: `list --owner "Priya Nair"` exits 0, omits every `Priya (ambiguous)` item, and stderr contains `note: 3 item(s) owned by 'Priya (ambiguous)' not shown`.
- AC-12: `list --owner "Lena Fischer"` and `list --owner "Priya Nair"` both include the same item id for `Collect user feedback on the prototype`; its OWNER column is `Lena Fischer` and its TASK ends with ` (with Priya Nair)`.
- AC-13: `list --owner Unassigned` returns exactly 5 rows.
- AC-14: `list --status bogus` exits 2 (argparse). `list --status overdue` with no overdue items prints the header only and exits 0.
- AC-15: Rows are ordered by DUE ascending with `-` last, ties by ID ascending.
- AC-16: `done 12` on an open item prints `done: #12 ...`, exits 0, and a later `list --status done` includes it with `done_date` today in the database.
- AC-17: `done 12` twice: second call prints `already done: #12 ...`, exits 0, `done_date` unchanged.
- AC-18: `done 99999` exits 3 with `error: no such item: 99999`; `done abc` and `done 0` exit 2.
- AC-19: Every command exits 2 with `ACTIONTRACK_TODAY` named in stderr when it is set to `2026-13-45`.
- AC-20: `list` before any `ingest` (no database file) exits 1 with the `run ingest first` message.
- AC-21: No command ever prints a Python traceback for any of the above inputs.
