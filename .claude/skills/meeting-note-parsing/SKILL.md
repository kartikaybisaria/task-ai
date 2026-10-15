---
name: meeting-note-parsing
description: Use when writing, changing, testing or debugging the actiontrack note parser, i.e. anything that reads files in notes/ and extracts the meeting date, attendees, owners, action-item checkboxes or due dates. Also use when deciding how a messy note line should be interpreted.
---

# Meeting-note parsing rules (actiontrack)

Authoritative spec: `specs/01-parsing.md` (owner matching: `specs/02-dedup-owners-dates.md`).
Real examples: `specs/findings.md`. If this skill and the spec disagree, the spec wins; fix this skill.
Read the spec first, write tests from its acceptance criteria, then code.

## Never crash
`parse_note(path) -> (note, error)`. Exactly one is None. Bad input returns `(None, reason)`; it never raises.
Read bytes, check in this order, first hit wins:
1. extension not `.md` -> `unsupported extension (.txt)` (`2026-09-19-offsite-draft.txt`)
2. 0 bytes -> `empty file` (`2026-09-09-notes-final-v2.md`)
3. any NUL byte -> `binary content (NUL bytes)` (`scratch.md`)
4. not UTF-8 (BOM ok) -> `not valid UTF-8`. Never `errors="ignore"/"replace"`.
5. no meeting date from any source -> `no meeting date` (`untitled.md`)
Then normalize `\r\n` and `\r` to `\n` (`2026-10-02-finance-sync.md` is CRLF and has an em dash).

## Meeting date (stored ISO `YYYY-MM-DD`)
Order: `Date:` line, front matter `date:`, filename prefix `YYYY-MM-DD-`.
Formats: `2026-09-01`; `9 September 2026`; `Monday, 14 September 2026`; front matter `date: 2026-09-16`.
Unparseable (`Date: sometime last week`) -> use filename date + warning. Header vs filename mismatch -> header wins + warning.

## Attendees
`Attendees: Priya Nair, Rahul Mehta` (comma list) or front matter `attendees: [Anita Desai, Lena Fischer]`.
Missing (`2026-09-23-standup.md`) -> `[]` + warning `no attendees listed`; not a skip.

## Action items: what counts
Scan the whole file, not just `## Action items`. Ignore anything inside:
- fenced code (```): `2026-10-09-security-review.md:8-11` (`Owner to remediate finding by <date>`)
- HTML comments, one or many lines: `2026-10-09-security-review.md:13`
- blockquotes (`>`): `2026-09-21-incident-review.md:9` (customer wish, not agreed)
- prose sentences such as `Sam to propose a 10% cost cut.`

Three shapes count:
- Checkbox, regex `^(?P<indent>[ \t]*)(?P<bullet>[-*+])[ \t]+\[(?P<mark>[ xX])\][ \t]+(?P<text>\S.*?)[ \t]*$`. `x`/`X` = done. Any indent (nested items are independent).
- Table row under a header with `Owner | Action | Due`: `| Anita | Refresh the brand kit | 2026-10-09 |`.
- Line starting `ACTION:`: `ACTION: Karan to circulate the offsite summary tomorrow`.

## Owner extraction (leading phrase only)
- `@anita: audit colour contrast ...` -> `anita`
- `<owner phrase> to <task>`, split at the first whole word `to`. Initials: `Priya N.`. Multiple: `Anita & Rahul to ...` (primary Anita, co Rahul), `Lena (with Priya) to ...` (primary Lena, co Priya).
- `Rahul to review Anita's PR` is Rahul's, Anita is only mentioned.
- `Everyone`, `Team`, `Someone`, `TBD`, or no `to` (`Book the venue`) -> `Unassigned`, keep the raw text.
- Mapping first names to full names uses the attendee list, then the roster; two Priyas and two Rahuls exist, so unresolved = `Priya (ambiguous)`.

## Due-date phrases
Deadline = trigger `by | due | before | until | on` + date expression (anywhere in the text, also after `—`). Take the rightmost that resolves. Also a trailing bare `tomorrow`/`today`/`EOD`, and the table Due cell.
Remove the clause (and a dash/comma before it) from the task; keep it in `due_raw`.

Resolve against the **meeting date M**, never today:
- ISO `by 2026-09-08`, `on 2026-10-14` -> as written
- weekday (`Friday`, `Wed`, `Mon`, `next Tuesday`) -> first such weekday strictly after M; on a Friday `by Friday` = M+7
- `10 Sep`, `2 Oct`, `15 October`, `Oct 3rd`, `Oct 5th` -> M's year, next year if before M; month name required
- `Wed 16 Sep` -> explicit date wins
- `tomorrow`, `EOD tomorrow` -> M+1; `EOD`, `today` -> M
- `EOW` -> first Friday on/after M; `end of next week` -> that + 7; `end of month` -> month's last day; `mid-October` -> the 15th
- NOT deadlines: `from 9 Oct`, `for Saturday 10 Oct`, `for November` -> due NULL, `due_raw` kept, phrase stays in the task
- `by 10%` is not a date (`2026-10-02-finance-sync.md:10`: `... by 10% — proposal by 2026-10-09` -> 2026-10-09)
Unresolvable -> NULL + `due_raw` + warning. Some meetings are on Saturdays (2026-10-03, 2026-10-10): count from M anyway.

## Edge cases to test (each has a fixture in notes/)
empty file; binary `scratch.md`; `.txt`; `untitled.md`; CRLF finance-sync; em dash before `by Friday` (2026-09-08:9);
bad header date (2026-10-03); long-line q4-offsite with `*`, `+`, nested, table, `ACTION:`;
fence/comment/blockquote traps; `[X]` capital; no-attendee standup; both Priyas / both Rahuls in one meeting;
`by 10%`; `from 9 Oct`; weekend meeting dates; same task twice in one file.
Dates are always stored ISO; `ACTIONTRACK_TODAY` is the only source of "today".
