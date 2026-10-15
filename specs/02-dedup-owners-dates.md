# 02 Dedup, owners, dates

How raw sightings from 01 become stable items: owner resolution, fingerprinting, fuzzy matching,
due-date merging, `[x]` propagation, idempotent ingest. Facts: `findings.md` sections 8 and 11.
All "today" values below use `ACTIONTRACK_TODAY=2026-10-15`.

## Purpose
The same task shows up in several meetings, often reworded (`Priya N. to send revised quote to
Acme` vs `Priya to send the revised quote to Acme`). Keep one item per task, remember every
sighting, show the best due date, and mark it done when any note checks it off. Re-running
`ingest` must never duplicate or lose anything.

## Behavior

### 1. Owner resolution (same-first-name problem)
Input per name: the owner text from 01, the note's attendee list A, the roster R
(all distinct attendee names in the notes being ingested; from the database on `list`/`followup`).

1. **Full name** (`Anita Desai`): case-insensitive match in R -> canonical. No match -> kept as typed, `unknown_owner`.
2. **First name or handle** (`Priya`, `@anita`), with optional initial (`Priya N.` -> `N`):
   1. Candidates = people in A whose first name equals the token. If an initial is given, keep only last names starting with it.
   2. If that list is empty (A missing, or no match): candidates = the same filter over R.
   3. Exactly 1 candidate -> that full name. 2 or more -> `<First> (ambiguous)` (e.g. `Priya (ambiguous)`), `review_reason = ambiguous_owner`. 0 -> kept as typed, `unknown_owner`.
3. Placeholders (`Everyone`, `Team`, `Someone`, `TBD`) and no owner -> `Unassigned`, `review_reason = unassigned`.

Case-insensitive throughout; output uses the roster's spelling. The attendee list wins over the roster: Priya Nair is the only Priya in `2026-09-01-quote-portal-kickoff.md`, so a bare `Priya` is Priya Nair even though the roster has two Priyas.

Multiple owners (`Anita & Rahul`, `Lena (with Priya)`): each name is resolved separately. First = `owner`, the rest go in `co_owners`. An unresolved co-owner is stored as `<First> (ambiguous)`.

Real cases:
| Note | Text | Result |
|---|---|---|
| 2026-09-01 (attendees: Priya Nair, Rahul Mehta, ...) | `Priya to send ...` | Priya Nair |
| 2026-09-08 | `Priya N. to send ...` | Priya Nair |
| 2026-09-29 (both Priyas) | `Priya S. to run the invoice rounding tests` | Priya Shah |
| 2026-09-17 (both Priyas) | `Priya to sign off the cutover checklist` | Priya (ambiguous) |
| 2026-10-08 (both Priyas) | `Priya to circulate the go/no-go summary by EOD` | Priya (ambiguous) |
| 2026-10-07 (both Rahuls) | `Rahul to review Anita's PR by tomorrow` | Rahul (ambiguous) |
| 2026-09-23 (no attendees) | `Rahul to rebase the feature branch` | Rahul (ambiguous) (roster has two) |
| 2026-09-23 (no attendees) | `Sam to rotate the staging credentials` | Sam Okafor (unique in roster) |
| 2026-09-18 | `@anita: audit colour contrast ...` | Anita Desai |
| 2026-09-18 | `Lena (with Priya) to collect user feedback ...` | owner Lena Fischer, co-owners [Priya Nair] |

### 2. Fingerprint
`fingerprint = (owner_key, task_key)`.
- `owner_key` = lower-cased `owner` (`priya nair`, `unassigned`, `priya (ambiguous)`). Co-owners are not part of it.
- `task_key` from the task text (01, due clause already removed, non-deadline date phrases kept):
  1. Unicode NFKC, lower-case.
  2. Delete apostrophes (`'` and `’`): `Acme's` -> `acmes`.
  3. Replace every run of non-alphanumeric characters with one space (dashes, `%`, commas, `/`).
  4. Drop the words `a`, `an`, `the`, `first`, `updated`, `revised`.
  5. Join tokens with single spaces.

### 3. Fuzzy matching
A sighting joins an existing item when `owner_key` is equal and either `task_key` is equal or
`difflib.SequenceMatcher(None, a, b).ratio() >= 0.85`. Several candidates: highest ratio, then lowest `id`. None: new item.
- Owners never match across different `owner_key`s: `Priya (ambiguous)` never merges with `Priya Nair` or `Priya Shah`; `Rahul Mehta` never merges with `Rahul Verma`.
- Merges (all verified): `share first wireframes` / `share updated wireframes` = 1.0 (0.78 without the noise words); `send the revised quote to Acme` / `send revised quote to Acme` = 1.0; `estimate SSO work` / `estimate the SSO work` = 1.0.
- Correct non-merges: `ask Acme for their procurement contact` / `send Acme the procurement form` = 0.62; `estimate the SSO work` / `start SSO spike` = 0.62.
- Processing order for a full ingest: files sorted by name, sightings in file order. The item's field values (section 4) do not depend on order; only which id a merged item keeps does.

### 4. Item fields from sightings
Order the item's sightings by `(meeting_date, file, line)`.
- `first_seen`, `task`, `owner_raw`: from the earliest sighting.
- `due_date`: from the **latest** sighting whose `due_date` is not NULL (a re-plan replaces the date; a later sighting without a date does not erase it). `due_raw` comes from that same sighting. If no sighting has a date: NULL, and `due_raw` from the latest sighting with a non-empty `due_raw`, else NULL.
- `status = done` if any sighting has `checked = 1` or `done_manual = 1`; else `open`. Sticky: a later `[ ]` sighting does not reopen it.
- `done_date`: `meeting_date` of the earliest checked sighting; for `done_manual` the date `done` ran (today). Earliest wins if both. NULL while open.
- `co_owners`, `review_reason`: from the earliest sighting.

### 5. Idempotent ingest
Per file, in one transaction:
1. Delete that file's sightings.
2. Insert the parsed sightings, each matched or created as in section 3.
3. Delete items left with no sightings, unless `done_manual = 1`.
4. Recompute fields of every touched item (section 4).

Consequences: re-ingesting an unchanged corpus changes nothing (same ids, same rows). Editing a file so lines shift creates no duplicates (line numbers are never matching keys). A file that fails to parse leaves its old sightings untouched and is reported as skipped. `done <id>` survives re-ingest. A failed ingest of one file never rolls back other files.

## Edge cases
- Same task twice in one note: one sighting (01).
- `Sam to propose a 10% cost cut.` (prose, finance-sync:6) and its checkbox (:10) do not double count: prose is never parsed.
- A task is reworded to a different task by the same owner (`Meera ... procurement contact` vs `... procurement form`): stays two items.
- Task text differs only in a date phrase that is part of the task (`from 9 Oct` in both): equal keys, one item.
- Item with owner `Unassigned`: dedup works among Unassigned items only.
- A checked sighting is the **first** one seen: item is done immediately, `done_date` = that meeting date.
- The roster changes between ingests (a new person appears): owners are recomputed only for files that are re-ingested, so old items keep their resolved owner.

## Acceptance Criteria
- AC-1: The ten rows of the owner-resolution table in section 1 hold, using each note's real attendees (or none for 2026-09-23).
- AC-2: A fixture note with attendees `Priya Nair, Priya Shah` and `- [ ] Priya N. to x` / `- [ ] Priya S. to x` gives owners `Priya Nair` and `Priya Shah` and two separate items.
- AC-3: After ingesting `notes/`, exactly 6 items have `review_reason = ambiguous_owner`: 3 with `Priya (ambiguous)` (2026-09-17 sign-off, 2026-10-08 go/no-go summary, 2026-09-30 hiring plan) and 3 with `Rahul (ambiguous)` (2026-09-23 rebase, 2026-10-07 review Anita's PR, 2026-09-30 architecture overview).
- AC-4: After ingesting `notes/`, exactly 5 items are `Unassigned` with `review_reason = unassigned`, `owner_raw` in {`Someone`, `Everyone`, `Everyone`, `TBD`, `Team`}.
- AC-5: `normalize("Share first wireframes")` equals `normalize("share updated wireframes")`; `normalize("send the revised quote to Acme's team")` equals `send quote to acmes team`.
- AC-6: Two sightings with ratio exactly 0.85 merge; a pair at 0.84 does not (fixtures built by construction, not from notes).
- AC-7: `ask Acme for their procurement contact` and `send Acme the procurement form` (both Meera Iyer) stay two items.
- AC-8: Item `Priya Nair / send revised quote to Acme`: 3 sightings (2026-09-01, 2026-09-08, 2026-09-15), `first_seen` 2026-09-01, `due_date` 2026-09-11, `due_raw` `by Friday`, `status` done, `done_date` 2026-09-15.
- AC-9: Item `Anita Desai / share first wireframes`: 3 sightings, `due_date` 2026-09-24, status open, task text `share first wireframes`, overdue on 2026-10-15.
- AC-10: Item `Rahul Verma / review the schema mapping doc`: 2 sightings, `due_date` 2026-09-07 (the later sighting has no date and does not erase it), open.
- AC-11: Item `Anita Desai / finalise the welcome-email copy`: 3 sightings, `due_date` 2026-09-25 (latest of 2026-09-16, 2026-09-25), done, `done_date` 2026-10-05.
- AC-12: Item `Lena Fischer / collect 5 customer quotes ...`: `due_date` 2026-10-02 (end of month 2026-09-30 replaced), open.
- AC-13: Item `Karan Joshi / approve the Q4 cloud spend`: sightings 2026-09-30-standup.md and 2026-10-02-finance-sync.md (`[X]`), done, `done_date` 2026-10-02.
- AC-14: Item `Meera Iyer / book the renewal call with Acme's CTO`: 3 sightings, done, `done_date` 2026-10-14, `due_date` 2026-09-30.
- AC-15: Item `Rahul Mehta / deploy the beta to staging`: 3 sightings, done, `done_date` 2026-10-13, `due_date` 2026-10-07.
- AC-16: Item `Karan Joshi / freeze invoice edits from 9 Oct`: 2 sightings, `due_date` NULL, `due_raw` `from 9 Oct`, never overdue.
- AC-17: Done is sticky: a fixture where note 1 has `[x]` and a later note 2 has `[ ]` for the same task leaves the item done with `done_date` = note 1's date.
- AC-18: Ingesting `notes/` twice: the second run reports no new items or sightings, and a full dump of both tables (ordered by id) is byte-identical to the first.
- AC-19: Insert a blank line at the top of a copied note, re-ingest: item count unchanged, `sightings.line` values shifted by 1, no new items.
- AC-20: Delete a task line from a copied note, re-ingest: the item (if only seen there) disappears; if it had other sightings it stays with one fewer sighting.
- AC-21: `done <id>` then re-ingest: the item is still done and `done_manual` is 1. Items with `done_manual = 1` are not deleted when their last sighting vanishes.
- AC-22: A note that later becomes empty (0 bytes) is reported skipped and its old sightings stay.
- AC-23: `Priya (ambiguous)` and `Priya Nair` items with identical task text stay separate items.
