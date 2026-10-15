# actiontrack: findings from notes/

36 files, ~16.7 KB total. 119 checkbox lines (13 checked) outside scratch.md.
Line numbers are 1-based. File names are in `notes/`.

## 1. Size
Largest: 2026-09-30-q4-offsite.md (1685 B), 2026-10-09-security-review.md (1076),
2026-09-18-design-review.md (942), 2026-09-21-incident-review.md (767),
2026-09-01-quote-portal-kickoff.md (575).
Smallest: 2026-09-09-notes-final-v2.md (0), 2026-09-19-offsite-draft.txt (71),
untitled.md (105), 2026-10-03-sales-pipeline.md (185), scratch.md (249).

## 2. Date formats
- Standard: `Date: 2026-09-01` on line 2 (most files). Header is `# Meeting: <title>`.
- YAML front matter, lowercase key: `date: 2026-09-16` (2026-09-16-standup.md:3, 2026-09-30-standup.md:3).
- Long form: `Date: 9 September 2026` (2026-09-09-qa-standup.md:2);
  `Date: Monday, 14 September 2026` (2026-09-14-onboarding-flow-design.md:2).
- Unparseable: `Date: sometime last week` (2026-10-03-sales-pipeline.md:2). Filename says 2026-10-03.
- Missing: untitled.md, scratch.md, the empty file, offsite-draft.txt.
- Filename always starts `YYYY-MM-DD-` for 2026-*.md; matches header where parseable.
- Some meeting dates are weekends (2026-10-03 Sat, 2026-10-10 Sat). Matters for "by Friday".

## 3. Attendees
- Main form: `Attendees: A B, C D` (comma list, line 3).
- Front matter: `attendees: [Anita Desai, Lena Fischer, Meera Iyer]` (2026-09-16-standup.md:4).
- Missing: untitled.md:4 ("no header, no date, no attendees"), offsite-draft.txt, scratch.md.
- Names are always full names. Roster is 9 people: Priya Nair, Priya Shah, Rahul Mehta,
  Rahul Verma, Anita Desai, Sam Okafor, Meera Iyer, Karan Joshi, Lena Fischer.

## 4. Checkbox variants
- Standard: `- [ ] ` open, `- [x] ` done, under `## Action items` (31 files).
- Capital X: `- [X] Karan to approve the Q4 cloud spend` (2026-10-02-finance-sync.md:9).
- Other bullets: `* [ ]` (2026-09-30-q4-offsite.md:11, 2026-10-02-finance-sync.md:10);
  `+ [ ]` (q4-offsite:12, finance-sync:11).
- Nested/indented: `  - [ ] Karan to validate targets...` (q4-offsite:10), child of line 9.
- Action items outside the `## Action items` section: q4-offsite.md:9-12, 16-18 are under
  "Morning"/"Afternoon" headings; table row `| Anita | Refresh the brand kit | 2026-10-09 |` (q4-offsite:22);
  `ACTION: Karan to circulate the offsite summary tomorrow` (q4-offsite:24);
  prose "Sam to propose a 10% cost cut." (finance-sync:6; same task as finance-sync:10).
- Traps that look like tasks but are not: fenced code `- [ ] Owner to remediate finding by <date>`
  (security-review:8-11); HTML comment `<!-- - [ ] Sam to buy hardware tokens ... (cut ..., not agreed) -->`
  (security-review:13).

## 5. Owner phrasing
- Dominant: `<First> to <verb> ...` e.g. `Priya to send the revised quote to Acme by Friday` (kickoff:9).
- Initial disambiguator: `Priya N.` (2026-09-08:9, 2026-09-29:10, 2026-10-08:12), `Priya S.` (2026-09-29:9).
- Handle style: `@anita: audit colour contrast...` (2026-09-18-design-review.md:11).
- Multiple owners: `Anita & Rahul to agree...` (design-review:12); `Lena (with Priya) to collect...` (design-review:13).
- Group/placeholder owners: `Everyone` (design-review:14, q4-offsite:18), `Team` (2026-10-01:12),
  `Someone` (2026-09-10-acme-renewal-prep.md:12), `TBD` (design-review:15).
- Other-person references mid-line: `Rahul to review Anita's PR` (2026-10-07-standup.md:9): Anita is not the owner.

## 6. Due-date phrasing
- ISO: `by 2026-09-08` (kickoff:10), `on 2026-10-14` (2026-10-06:10; an event date, not "by").
- Weekdays: `by Friday`, `by Thursday`, `by Monday`, `by Wed`, `by Mon` (design-review:11), `Wednesday`.
- Day Month: `by 10 Sep`, `by 18 Sep`, `by 25 Sep`, `by 2 Oct`, `by 12 Oct`, `by 23 Oct`;
  with weekday `by Wed 16 Sep` (2026-09-14:9).
- Month Day with ordinal: `by Oct 3rd`, `by Oct 5th` (q4-offsite:9,10).
- Relative: `by tomorrow` (2026-09-02:9), `by EOD` (2026-10-08:9), `by EOD tomorrow` (2026-09-21:14),
  `by next Tuesday` (2026-10-05:9), `by end of next week` (2026-09-03:11), `by end of month` (2026-09-14:12),
  `by mid-October` (q4-offsite:12), `for November` (2026-10-14:10, no "by").
- Embedded after punctuation: `— by Friday` (2026-09-08:9, em dash); `, results due 15 October` (q4-offsite:11);
  `— proposal by 2026-10-09` (finance-sync:10, em dash).
- Not due dates despite a date: `schedule cutover for Saturday 10 Oct` (2026-09-29:11),
  `freeze invoice edits from 9 Oct` (2026-09-29:12, 2026-10-08:11).
- 78 of 119 checkbox lines contain by/due/on; the rest have no date.

## 7. Malformed or odd files
- 2026-09-09-notes-final-v2.md: 0 bytes. Empty.
- scratch.md: binary (`file` says "data"). Starts with null bytes and 0xFF 0xFE, then `# Meeting`,
  then a PNG-like header and a 0x80-0xFF byte ramp. Not valid UTF-8. Must not be decoded blindly.
- untitled.md: two valid checkboxes (:1-2) but no header, date or attendees.
- 2026-09-19-offsite-draft.txt: `.txt`, self-described "Not a meeting note", one stray checkbox
  `Book the venue` (:2). No date or attendees.
- 2026-10-03-sales-pipeline.md: attendees OK, date unparseable (see 2).
- 2026-10-02-finance-sync.md: CRLF line endings, plus a UTF-8 em dash (:10). Parser must strip `\r`.
- 2026-09-08-quote-portal-weekly.md: UTF-8 em dash (:9). Fine if read as UTF-8.
- 2026-09-30-q4-offsite.md: long lines (431 chars), mixed bullet styles, table, ACTION: line.
- 2026-10-09-security-review.md: code fence and HTML comment containing fake tasks.
- Only scratch.md, the empty file and the `.txt` are unusable. untitled.md is the borderline case.

## 8. Repeated tasks across meetings (same owner + same task)
- Priya, send revised quote to Acme: 2026-09-01:9, 2026-09-08:9 (`Priya N.`, reworded), 2026-09-15:9 [x].
- Rahul, set up staging environment: 2026-09-01:10, 2026-09-08:12 [x].
- Sam, confirm cloud budget with finance: 2026-09-01:12, 2026-09-15:11, 2026-09-22:10 [x].
- Anita, share (updated) wireframes: 2026-09-01:11, 2026-09-15:10, 2026-09-22:9. Never checked.
- Karan, export last quarter invoices: 2026-09-03:9, 2026-09-17:11 [x].
- Rahul, review schema mapping doc: 2026-09-03:10, 2026-09-17:12. Never done.
- Rahul, fix the pagination bug: 2026-09-15:12, 2026-09-22:12 (gains `by Wednesday`).
- Anita, finalise welcome-email copy: 2026-09-14:9, 2026-09-24:9, 2026-10-05:11 [x]. Due date moves each time.
- Lena, collect 5 customer quotes: 2026-09-14:12 (end of month), 2026-09-24:11 (2 Oct). Due date changed.
- Rahul, estimate SSO work: 2026-09-14:11, 2026-09-24:12 (reworded, "SSO work" vs "the SSO work").
- Meera, book renewal call with Acme's CTO: 2026-09-10:11, 2026-09-28:9, 2026-10-14:11 [x].
- Rahul, deploy beta to staging: 2026-10-01:10, 2026-10-06:9, 2026-10-13:9 [x].
- Priya, renewal one-pager: 2026-09-28:12, 2026-10-14:12.
- Karan, freeze invoice edits from 9 Oct: 2026-09-29:12, 2026-10-08:11.
- Karan, approve Q4 cloud spend: 2026-09-30-standup.md:11, 2026-10-02-finance-sync.md:9 [X].
- Sam, cut cloud costs 10%: finance-sync:6 (prose) and finance-sync:10 (checkbox), same file.
- Different task, same words: `Meera ... procurement` (2026-09-08:11 ask for contact vs 2026-09-22:11 send form).

## 9. Items without an owner
- `Someone to update the CRM notes` (2026-09-10:12).
- `Everyone to review the prototype...` (design-review:14); `Everyone to submit their Q4 goals by 7 Oct` (q4-offsite:18).
- `TBD to write the design-system changelog` (design-review:15).
- `Team to decide on the launch date` (2026-10-01:12).
- `Book the venue` (offsite-draft.txt:2): bare verb, and not a meeting note.
- `Owner to remediate finding by <date>` (security-review:10): template inside a fence, ignore.

## 10. Items without a due date (examples)
kickoff:12 (Sam, confirm cloud budget); 2026-09-02:10; 2026-09-03:12; 2026-09-09-qa-standup.md:10;
2026-09-10:11; 2026-09-15:12; 2026-09-21:17 (refund customers); 2026-09-23:9; 2026-10-06:11;
2026-10-07:10; 2026-10-12:12; 2026-10-13:12; 2026-10-14:12. Also `Lena to clean up duplicate leads`
(2026-10-03:7, in the note with the bad date).

## 11. Same first name (Priya x2, Rahul x2)
- Priya Nair: quote portal, Acme, billing sync. Priya Shah: QA, onboarding, billing, incident, security.
- Rahul Mehta: quote portal, design review, standup. Rahul Verma: billing, QA, onboarding, security.
- Both Priyas attend 2026-09-17 (:9 `Priya to sign off the cutover checklist`), 2026-09-29, 2026-10-08
  (:9 `Priya to circulate the go/no-go summary by EOD`), q4-offsite (:16 `Priya to own the hiring plan`).
  Prose confirms it: "both Priyas were in the room" (q4-offsite:15).
- Both Rahuls attend 2026-10-07-standup.md (:9 `Rahul to review Anita's PR`) and q4-offsite
  (:17 `Rahul to prepare the architecture overview`; :15 "it is unclear which Rahul meant").
- Resolvable via attendee list: most meetings have only one of each pair, e.g. 2026-09-01 (Priya Nair, Rahul Mehta),
  2026-09-09-qa-standup.md (Priya Shah, Rahul Verma).
- Initials help only sometimes: `Priya N.` / `Priya S.`; 2026-09-08:9 `Priya N.` and 2026-09-15:9 plain `Priya`
  are the same task with different spelling.
- Same person, different owner text: `@anita`, `Anita`, `Anita & Rahul`.
