# actiontrack

actiontrack is a small Python CLI that reads meeting notes from `notes/`, extracts
action items (owner, task, due date, done/open), stores them in a local SQLite
database, and reports on them (open items, overdue, per owner). It can also draft
follow-up emails as Gmail drafts. The notes are messy on purpose: mixed date
formats, checkbox styles, owner phrasings and a few broken files. See
`specs/findings.md` for the catalogue of what the parser must handle.

## Spec-driven workflow
1. Read the relevant spec in `specs/` before writing any code. Start with
   `specs/findings.md` for note-format facts.
2. Never change behavior without updating the spec first. Spec, then tests, then code.
3. Write tests from the spec's acceptance criteria BEFORE the implementation.
   Watch them fail, then make them pass.
4. Commit after each spec is done (one spec = one commit, tests green).
5. If the spec and the notes disagree, the notes win: fix the spec, then the code.

## Hard rules
- NEVER send email. Only create Gmail drafts. No code path may call a send API.
- Malformed notes (empty, binary, undecodable, no usable header) are skipped and
  reported in the run summary with the file name and reason. They never crash a run.
  Read files as bytes and decode defensively; never assume UTF-8 or LF endings.
- Dates are stored as ISO `YYYY-MM-DD`. Unparseable dates are stored as NULL, not guessed.
- "Today" comes from the `ACTIONTRACK_TODAY` env var (ISO date) when set, otherwise
  the system date. All relative dates ("tomorrow", "by Friday") resolve against it,
  so tests are deterministic. Never call `date.today()` outside that one helper.
- Ignore fake tasks: fenced code blocks and HTML comments are not action items.
- Same first name does not mean same person: resolve owners via the attendee list.

## Stack
Python 3.11+, `argparse` for the CLI, `sqlite3` for storage, `pytest` for tests.
No heavy dependencies; standard library first, justify any addition in the spec.
Use the project venv at `.venv/`.

## Commands
- Test: `pytest -q`
- Run: `python -m actiontrack <cmd>`

## Skills
- `.claude/skills/meeting-note-parsing`: how to parse notes (dates, owners, checkboxes, traps).
- `.claude/skills/followup-email`: how to compose follow-up emails as Gmail drafts.

## Layout
- `notes/`: input meeting notes (read-only, never edit them)
- `specs/`: specs and findings (source of truth)
- `actiontrack/`: package code; `tests/`: pytest tests
