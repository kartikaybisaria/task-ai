---
name: followup-email
description: Use when the user wants a follow-up email for a person's open or overdue action items from the meeting notes. Creates a Gmail DRAFT from the actiontrack CLI's JSON output. Never sends email.
---

# Follow-up email as a Gmail draft

Spec: `specs/04-followup-gmail.md`. The CLI cannot call an MCP connector, so this skill is the bridge:
the CLI renders the draft, Claude Code (you) creates it in Gmail.

## Hard rule
**Create a draft only. Never send.** Use the Gmail create-draft tool and nothing else from Gmail that writes.
Never call any tool whose name contains `send`. `.claude/settings.json` denies them and a hook blocks them;
if a call is blocked, do not look for a workaround, tell the user.

## Steps
1. Make sure the database exists (`python -m actiontrack ingest` if not; ask first if unsure).
2. Run: `python -m actiontrack followup "<owner>" --dry-run`
   (full name or a first name that is unique; use `--contacts PATH` if the user names a contacts file).
   - Exit 2 with an ambiguity error (`Priya` -> Priya Nair, Priya Shah): ask the user which person. Never guess.
   - Exit 2 for `Unassigned` / `... (ambiguous)`: explain that no email can be drafted for a placeholder owner.
   - Exit 3: unknown owner; show the error.
3. Read the JSON: `owner`, `to`, `subject`, `body`, `warnings`.
   - `subject` and `body` are null -> nothing to draft; tell the user why (`warnings`) and stop.
   - `to` is `[]` or a warning says no email address: ask the user for the address. Do not invent one (no `first.last@...`).
4. Create the draft with the Gmail **create-draft** MCP tool (find its exact name via `/mcp`, typically `mcp__claude_ai_Gmail__...create_draft`):
   `to` = the JSON `to`, `subject` and `body` **verbatim** (plain text; do not rewrite, add, or drop items).
   If the create-draft tool is not available (Gmail not authorised), say so and show the JSON instead. Do not use another channel.
5. Show the user the draft: recipient, subject, body, and the draft link or id if the tool returned one.
   Tell them to review it in Gmail and send it themselves.
6. Stop. One owner per run; do not loop over people unless the user asked, and then repeat steps 2 to 5 per person.

## Tone (already built into the CLI body; keep it when summarizing)
- Short and polite, no pressure language, no blame.
- Overdue first, then Open, then the "Needs review" note about unowned items.
- Each item shows the task, the due date and the source meeting (e.g. `from 2026-09-09-qa-standup`).
- Items with no firm date say so (`no due date`; `note says "from 9 Oct"`).
- Greeting by first name; sign-off `Thanks!` only. No invented sender name.

## Example
`python -m actiontrack followup "Karan Joshi" --dry-run` with `ACTIONTRACK_TODAY=2026-10-15`
gives subject `Follow-up: your open action items (10)`: 6 overdue (first: `Send the vendor invoice list`, due 2026-09-11),
4 open, 2 items under Needs review. Create exactly that as one draft.
