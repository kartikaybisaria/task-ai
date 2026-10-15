# 01 Parsing

Turns one note file into `(note, error)`: either a parsed note or a skip reason. Never raises
for bad input. Examples are real; paths are in `notes/`. Facts: `findings.md`.

## Purpose
Given the bytes of one file, produce the meeting date, the attendees and a list of raw
sightings (owner text, task text, checked flag, due clause, source, line), or a skip reason.
Matching, owner resolution and storage are in 02.

## Behavior

### 1. Reading the file (malformed handling)
Check in this order; the first hit skips the file and produces a reason string:
1. Extension is not `.md` -> `unsupported extension (.txt)`.
2. Zero bytes -> `empty file`.
3. Any NUL byte -> `binary content (NUL bytes)`.
4. Not decodable as UTF-8 (a leading BOM is accepted) -> `not valid UTF-8`.
5. No meeting date from any source (section 2) -> `no meeting date`.

Then: normalize `\r\n` and lone `\r` to `\n` before splitting lines. Parsing never decodes
with `errors="ignore"` or `"replace"`.

### 2. Meeting date
Sources, in order: (a) a `Date:` line (case-insensitive key); (b) front matter `date:`;
(c) the filename prefix `YYYY-MM-DD-`. Accepted value formats, month names full or 3 letters,
case-insensitive, optional surrounding quotes:

| Format | Real example |
|---|---|
| `YYYY-MM-DD` | `Date: 2026-09-01` |
| `D Month YYYY` | `Date: 9 September 2026` (2026-09-09-qa-standup.md:2) |
| `Weekday, D Month YYYY` | `Date: Monday, 14 September 2026` (2026-09-14-onboarding-flow-design.md:2) |
| front matter | `date: 2026-09-16` between `---` lines (2026-09-16-standup.md) |

Rules: a present-but-unparseable value (`Date: sometime last week`,
2026-10-03-sales-pipeline.md:2) falls back to the filename date and adds the warning
`date 'sometime last week' not parseable; using filename date 2026-10-03`. If header and
filename both parse and differ, the header wins and a warning names both. A weekday word that
contradicts the date adds a warning; the explicit date still wins. Dates are stored ISO.

### 3. Attendees
- `Attendees: A B, C D`: split on commas, trim each. (`Attendees: Priya Nair, Rahul Mehta, ...`)
- Front matter `attendees: [Anita Desai, Lena Fischer, Meera Iyer]`: strip brackets, split on commas.
- Absent (`2026-09-23-standup.md` has none): `[]` plus the warning `no attendees listed`. Not a skip.
- Names are kept as written (full names in this corpus). Duplicates removed, order kept.

### 4. What is an action item
Scan every line of the file, not just `## Action items`. Ignore lines inside:
- a fenced code block (lines from a line starting with three backticks to the next such line):
  `2026-10-09-security-review.md:8-11` (`- [ ] Owner to remediate finding by <date>`);
- an HTML comment, single or multi-line: `2026-10-09-security-review.md:13`;
- a blockquote (line starting with optional spaces then `>`): `2026-09-21-incident-review.md:9`
  (`> - [ ] Karan to refund affected customers by Friday`).

Prose is never an item (`2026-10-02-finance-sync.md:6`, "Sam to propose a 10% cost cut.").

Three item shapes:
1. **Checkbox** (source `checkbox`), any indent, any bullet:
   `^(?P<indent>[ \t]*)(?P<bullet>[-*+])[ \t]+\[(?P<mark>[ xX])\][ \t]+(?P<text>\S.*?)[ \t]*$`
   `mark` of `x` or `X` means checked. Covers `- [ ]`, `- [x]`, `- [X]` (finance-sync:9),
   `* [ ]` and `+ [ ]` (q4-offsite:11-12), nested `  - [ ]` (q4-offsite:10, independent item, parent not stored).
2. **Table row** (source `table`): a row under a header whose cells (case-insensitive) include
   `Owner`, `Action` and `Due`; skip the header and the `|---|` separator row.
   `| Anita | Refresh the brand kit | 2026-10-09 |` -> owner `Anita`, task `Refresh the brand kit`, due 2026-10-09, open.
3. **Action line** (source `action_line`): line starting `ACTION:` (case-insensitive).
   `ACTION: Karan to circulate the offsite summary tomorrow` -> owner `Karan`, due = meeting date + 1.

### 5. Owner extraction
Applied to the text after the marker (shapes 1 and 3). First match wins:
1. Handle: `^@(\w+):\s*(.+)$` -> owner `anita`, task rest (design-review:11).
2. `<owner phrase> to <task>`: split at the **first** whole word `to`. Owner phrase =
   names or placeholders joined by `&`, `and` or `,`, each optionally followed by an initial
   (`Priya N.`) or the whole phrase followed by a parenthetical `(with X)`. At most 6 words, no
   verbs: if the phrase is longer or lower-case it is not an owner.
3. Otherwise owner is `Unassigned`, task is the whole text (`Book the venue`).

Multiple owners: `Anita & Rahul to agree on the component API` -> primary `Anita`, co-owner
`Rahul`. `Lena (with Priya) to collect user feedback` -> primary `Lena`, co-owner `Priya`.
Placeholders `Everyone`, `Team`, `Someone`, `TBD` (case-insensitive) -> `Unassigned`, raw text kept.
Only the leading phrase is the owner: `Rahul to review Anita's PR by tomorrow` is Rahul's.
Mapping names to full names is in 02.

### 6. Due-date extraction and resolution
Let M = meeting date. Find **deadline clauses**: a trigger word `by | due | before | until | on`
followed by a date expression, anywhere in the task text (including after `—`, `-` or `,`). Use the
**rightmost** match that resolves. Also accepted without a trigger: a trailing bare `tomorrow`,
`today` or `EOD`, and the Due cell of a table row. The clause is removed from the task text, along
with the dash, em dash, comma or space directly before it. `due_raw` keeps the clause as written
(`by Friday`).

Date expressions and how they resolve:

| Phrase (real example) | Result |
|---|---|
| ISO `by 2026-09-08`; `on 2026-10-14` | that date |
| Weekday `by Friday`, `by Wed`, `by Mon`, `by Wednesday`, `by next Tuesday` | first such weekday **strictly after** M. On a Friday, `by Friday` is M+7. `next` adds nothing. |
| `by 10 Sep`, `by 2 Oct`, `due 15 October`, `by Oct 3rd`, `by Oct 5th` | that day in M's year; if that is before M, next year. Ordinal suffixes allowed. Month name required. |
| `by Wed 16 Sep` | the explicit date wins over the weekday |
| `by tomorrow` / `by EOD tomorrow` | M+1 |
| `by EOD` / `today` | M |
| `by EOW`, `by end of week` | first Friday on or after M |
| `by end of next week` | that Friday + 7 days |
| `by end of month` | last day of M's month |
| `by mid-October` | the 15th of that month (same year rule) |

Not deadlines: a date after `from` or `for` (`freeze invoice edits from 9 Oct`,
`schedule cutover for Saturday 10 Oct`, `... review for November`) gives `due_date` NULL, `due_raw`
= that phrase (`from 9 Oct`), and the phrase **stays** in the task text. A trigger followed by
something unresolvable (`by the launch`) gives NULL and `due_raw` = that clause, plus a warning.
`by 10%` is not a date: a day number needs a month name.

Worked examples (M from the file):

| File (M) | Line | due_date |
|---|---|---|
| 2026-09-01 Tue | `by Friday` | 2026-09-04 |
| 2026-09-01 Tue | `by Thursday` | 2026-09-03 |
| 2026-09-03 Thu | `by end of next week` | 2026-09-11 |
| 2026-09-14 Mon | `by end of month` | 2026-09-30 |
| 2026-09-14 Mon | `by Wed 16 Sep` | 2026-09-16 |
| 2026-09-18 Fri | `by Mon` | 2026-09-21 |
| 2026-09-30 Wed | `by Oct 3rd` | 2026-10-03 |
| 2026-10-05 Mon | `by next Tuesday` | 2026-10-06 |
| 2026-10-10 Sat | `by Tuesday` | 2026-10-13 |
| 2026-10-02 Fri | `proposal by 2026-10-09` (after `—`, `by 10%` earlier on the line) | 2026-10-09 |

### 7. Output contract
A parsed note has: `meeting_date`, `attendees`, `warnings` (list of `(line|None, message)`),
`sightings` (in file order; each with owner_raw, owner names, task_text, checked, due_raw,
due_date, source, line). Skipped: `(None, reason)`. The function never raises for file content.

## Edge cases
- Empty file `2026-09-09-notes-final-v2.md`: skipped, `empty file`.
- `scratch.md` (NULs, `0xFF 0xFE`): skipped, `binary content (NUL bytes)`; bytes never decoded.
- `2026-10-02-finance-sync.md`: CRLF and an em dash. Parses with no stray `\r` in any field; `Sam to cut cloud costs by 10% — proposal by 2026-10-09` yields due 2026-10-09.
- `2026-09-08-quote-portal-weekly.md:9`: em dash before `by Friday`; task is `send revised quote to Acme`.
- `untitled.md`: two valid checkboxes but no date anywhere: skipped, `no meeting date`.
- `2026-09-19-offsite-draft.txt`: skipped, `unsupported extension (.txt)`.
- `2026-09-30-q4-offsite.md`: 431-char lines, mixed bullets, a table and an `ACTION:` line: 9 sightings (7 checkboxes, 1 table, 1 action).
- Item in a note on a weekend (`2026-10-03` Sat, `2026-10-10` Sat): weekday rules still count from M.
- Two identical checkbox lines in one file produce one sighting (checked if either is).
- A `- [ ]` with empty text is ignored.

## Acceptance Criteria
- AC-1: Reading `2026-09-09-notes-final-v2.md` returns `(None, "empty file")`.
- AC-2: Reading `scratch.md` returns `(None, "binary content (NUL bytes)")` without raising.
- AC-3: Reading `2026-09-19-offsite-draft.txt` returns `(None, "unsupported extension (.txt)")`.
- AC-4: Reading `untitled.md` returns `(None, "no meeting date")`.
- AC-5: A file containing bytes `\xff\xfe` and no NUL returns `(None, "not valid UTF-8")`.
- AC-6: Meeting date is 2026-09-09 for `Date: 9 September 2026`, 2026-09-14 for `Date: Monday, 14 September 2026`, 2026-09-16 for front matter `date: 2026-09-16` (attendees `['Anita Desai','Lena Fischer','Meera Iyer']`).
- AC-7: `2026-10-03-sales-pipeline.md` parses with meeting date 2026-10-03 and exactly one warning containing `sometime last week` and `2026-10-03`.
- AC-8: A header/filename mismatch (header 2026-09-02 in a file named `2026-09-03-x.md`) gives date 2026-09-02 and one warning naming both dates.
- AC-9: `2026-09-23-standup.md` parses with attendees `[]` and the warning `no attendees listed`.
- AC-10: `2026-10-02-finance-sync.md` yields 4 sightings, 1 checked (the `[X]` line), 3 owners `Karan`, `Sam`, `Meera`, `Karan`, and no field contains `\r`.
- AC-11: `2026-10-09-security-review.md` yields exactly 4 sightings and none whose text contains `remediate finding` or `hardware tokens`.
- AC-12: `2026-09-21-incident-review.md` yields exactly 4 sightings; `Karan to refund affected customers` appears once, with due_date NULL.
- AC-13: `2026-09-30-q4-offsite.md` yields 9 sightings: 7 `checkbox`, 1 `table`, 1 `action_line`; the table sighting has owner `Anita`, due 2026-10-09; the action line has due 2026-10-01; the line `Sam to propose a 10% cost cut.`-style prose is never a sighting.
- AC-14: Bullets `-`, `*`, `+`, marks ` `, `x`, `X` and indents of 0, 2 and 4 spaces all match the checkbox regex; `-[ ] x`, `- [] x` and `- [y] x` do not.
- AC-15: Owner extraction: `Priya N. to send ...` -> owner_raw `Priya N.`; `@anita: audit colour contrast ...` -> `anita`; `Anita & Rahul to agree ...` -> primary `Anita`, co `Rahul`; `Lena (with Priya) to collect ...` -> primary `Lena`, co `Priya`; `Rahul to review Anita's PR by tomorrow` -> owner `Rahul` only.
- AC-16: `Someone`, `Everyone`, `Team`, `TBD` owners give `Unassigned` with `owner_raw` preserved; `Book the venue` gives `Unassigned` and the full text as task.
- AC-17: Due resolution matches every row of the worked-example table in section 6, including M on a weekend and `by Friday` on a Friday giving M+7.
- AC-18: `Sam to cut cloud costs by 10% — proposal by 2026-10-09` gives due 2026-10-09, `due_raw` `by 2026-10-09`, and `10%` is never read as a day.
- AC-19: `Karan to freeze invoice edits from 9 Oct` gives due_date NULL, due_raw `from 9 Oct`, and the task text still contains `from 9 Oct`.
- AC-20: `Lena to run the customer survey, results due 15 October` (M 2026-09-30) gives due 2026-10-15, due_raw `due 15 October`, and task `run the customer survey, results` (no trailing space or dash).
- AC-21: For M = 2026-12-20, `by 3 Jan` gives 2027-01-03; for M = 2026-09-01, `by 1 Sep` gives 2026-09-01.
- AC-22: Parsing every file in `notes/` raises no exception, and the 36 files split into 32 parsed and 4 skipped.
