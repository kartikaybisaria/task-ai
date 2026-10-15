# 04 Follow-up emails (Gmail drafts)

`python -m actiontrack followup <owner> [--dry-run] [--contacts PATH]`. Facts: `findings.md`;
data model and owner resolution: 00 and 02; exit codes: 03.

## Purpose
Prepare one polite follow-up email per person listing their overdue and open action items, as a
Gmail **draft** a human reviews and sends. actiontrack and Claude Code must never send email.

## Why the CLI does not talk to Gmail
A Gmail MCP connector is a tool offered to **Claude Code's session**, not a library. Claude Code is the MCP client: it holds the connection and the OAuth credentials, and the model calls tools through it. `python -m actiontrack` is a separate process started from a shell. It has no handle to that connection, and it should not hold Gmail credentials or make network calls (that would also make it untestable). So the work is split:

```
actiontrack CLI (deterministic, tested, read-only)         Claude Code (follows the followup-email skill)
  followup "<owner>" --dry-run  --->  JSON {to, subject, body}  --->  Gmail MCP create-draft tool  --->  draft in Gmail
                                                                       (never a send tool)             human reviews + sends
```
1. Claude Code runs `python -m actiontrack followup "<owner>" --dry-run` in a shell.
2. It reads the JSON from stdout.
3. It calls the Gmail MCP **create-draft** tool with `to`, `subject`, `body` unchanged.
4. It shows the draft to the user and stops. Sending is a human action in Gmail.
The exact MCP tool names are recorded in `.claude/skills/followup-email/SKILL.md` and denied/allowed in `.claude/settings.json` after checking `/mcp` (Gmail was not yet authorised when these specs were written).

## Behavior

### Selecting the owner and items
- `<owner>` is resolved exactly like `list --owner` (03): full name, or a first name unique in the roster. Ambiguous first name: exit 2 with the candidates. Unknown: exit 3. `Unassigned` or `<First> (ambiguous)`: exit 2, `error: cannot draft a follow-up for '<owner>'`.
- Items for the email: every item whose `owner` or `co_owners` contains the person, `status = open`.
  - **Overdue**: `due_date < today`. **Open**: the rest (due today or later, or no due date).
- Co-owned items are included for each co-owner and annotated `(with <other names>)`.
- **Needs-review note** (not counted in N): (a) open `<First> (ambiguous)` items where `<First>` is the person's first name (they might be theirs); (b) open `Unassigned` items with at least one sighting in a note where the person was an attendee.

### Ordering
Overdue: `due_date` ascending, then `id`. Open: `due_date` ascending with NULL last, then `id`. Needs-review: `first_seen`, then `id`.

### Output with `--dry-run`
One JSON object on stdout, UTF-8, `indent=2`, `ensure_ascii=False`, keys in this order, newline-terminated, nothing else on stdout:
```json
{
  "owner": "Karan Joshi",
  "to": ["karan.joshi@example.com"],
  "subject": "Follow-up: your open action items (10)",
  "body": "...",
  "warnings": []
}
```
- `subject` = `Follow-up: your open action items (N)`, N = number of Overdue + Open items.
- `to` = list with the owner's address from `contacts.csv` (header `name,email`; match on full name, case-insensitive). Addresses are never invented. Not found: `to` is `[]` and `warnings` has `no email address for <owner> in <contacts path>`. File missing: warning `contacts file not found: <path>`. Co-owners are never added to `to`.
- Nothing to send (no Overdue and no Open items, even if the needs-review note would be non-empty): exit 0, `subject` and `body` are `null`, `warnings` has `no open or overdue items; no draft needed`. A consumer must not create a draft then.
- `body` uses `\n` line endings, no `\r`, no tabs, ASCII punctuation only (no em dashes). Only `to`, `subject` and `body` are used to create the draft; `owner` and `warnings` are for the consumer.

### Body layout
```
Hi <FirstName>,

Here is where your action items from our meeting notes stand as of <today>.

Overdue (<n>)
- <Task> (due <date>, <k> day(s) overdue; from <source>)
...

Open (<n>)
- <Task> (due <date>; from <source>)
- <Task> (no due date; from <source>)
...

Needs review
These came from meetings you attended and have no clear owner. If any are yours, please let me know:
- <Task> (written as "<owner_raw>"; from <source>)

Thanks!
```
- A section with no items is omitted entirely (heading too). The needs-review text and heading appear only when it has items.
- `<Task>` is `task` with the first letter upper-cased, plus ` (with A, B)` for co-owners. `<source>` is the file name of the earliest sighting without `.md` (where it was first raised). `<k>` is `today - due_date` in days; `day(s)` is `day` for 1, else `days`.
- An item whose `due_date` is NULL but has a `due_raw` (e.g. `from 9 Oct`) is `no due date; note says "from 9 Oct"; from <source>`.
- No sender name or signature beyond `Thanks!`: the user's own Gmail adds that.

### Without `--dry-run`
Prints a human preview (`To:`, `Subject:`, blank line, body) to stdout and the line `note: preview only; nothing was sent or drafted` to stderr. It has the same exit codes. It still does not send, create drafts, or write.

### Safety properties (all modes)
- Read-only: the database is opened read-only and not modified.
- No network or mail code in the package: no `smtplib`, `imaplib`, `http.client`, `urllib.request`, `socket`, `requests`, `httpx`, `googleapiclient`.
- No code path calls a send tool (see AC-14 to AC-17). Drafting is done by Claude Code via a create-draft tool only; send tools are denied in `.claude/settings.json` and blocked by a PreToolUse hook.

## Worked example (shipped notes, `ACTIONTRACK_TODAY=2026-10-15`, owner `Karan Joshi`)
Subject: `Follow-up: your open action items (10)`.

```
Hi Karan,

Here is where your action items from our meeting notes stand as of 2026-10-15.

Overdue (6)
- Send the vendor invoice list (due 2026-09-11, 34 days overdue; from 2026-09-09-qa-standup)
- Confirm discount ceiling with the CFO (due 2026-09-14, 31 days overdue; from 2026-09-10-acme-renewal-prep)
- Send Acme the revised pricing sheet (due 2026-10-01, 14 days overdue; from 2026-09-28-acme-renewal-checkin)
- Circulate the offsite summary (due 2026-10-01, 14 days overdue; from 2026-09-30-q4-offsite)
- Validate targets against the budget (due 2026-10-05, 10 days overdue; from 2026-09-30-q4-offsite)
- Prepare the board finance slide (due 2026-10-12, 3 days overdue; from 2026-10-02-finance-sync)

Open (4)
- Reconcile September ledger (due 2026-10-15; from 2026-10-12-billing-post-cutover)
- Send the final contract to legal (due 2026-10-15; from 2026-10-14-acme-renewal-wrapup)
- Refund affected customers (no due date; from 2026-09-21-incident-review)
- Freeze invoice edits from 9 Oct (no due date; note says "from 9 Oct"; from 2026-09-29-billing-cutover-planning)

Needs review
These came from meetings you attended and have no clear owner. If any are yours, please let me know:
- Update the CRM notes (written as "Someone"; from 2026-09-10-acme-renewal-prep)
- Submit their Q4 goals (written as "Everyone"; from 2026-09-30-q4-offsite)

Thanks!
```
The 3 done Karan items (export invoices, approve Q4 cloud spend, revoke contractor access) are absent. The fenced and blockquoted refund lines are not duplicated: `Refund affected customers` appears once.

## Edge cases
- `Priya Nair`: needs-review includes her `Priya (ambiguous)` items, e.g. `Sign off the cutover checklist` and `Own the hiring plan for the two QA roles` if open, plus Unassigned items from her meetings.
- `Priya` (bare): exit 2 listing `Priya Nair, Priya Shah`.
- `Lena Fischer`: she is primary on `Collect user feedback on the prototype (with Priya Nair)`; Priya Nair's email shows the same task as `... (with Lena Fischer)`.
- An owner with only done items (none exist in the notes except by editing): no draft.
- Owner present in `contacts.csv` twice: first row wins and a warning is added.
- `--contacts` file with a UTF-8 BOM or CRLF: handled.
- Singular `1 day overdue`; an item due today is Open, not Overdue; an item due `tomorrow` is Open.

## Acceptance Criteria
- AC-1: `followup "Karan Joshi" --dry-run` with the shipped notes, `ACTIONTRACK_TODAY=2026-10-15` and a contacts file for Karan exits 0 and prints one valid JSON object with keys exactly `owner, to, subject, body, warnings` in that order.
- AC-2: That JSON has `subject == "Follow-up: your open action items (10)"` and `to == ["<the contacts address>"]`.
- AC-3: The `body` equals the worked example above except for no ids (the test compares the full text).
- AC-4: In `body`, the line `Overdue (6)` appears before `Open (4)`, which appears before `Needs review`; overdue lines are in due-date order (09-11, 09-14, 10-01, 10-01, 10-05, 10-12).
- AC-5: A done item never appears: `Export last quarter invoices`, `Approve the Q4 cloud spend`, `Revoke access` are absent from `body`.
- AC-6: `Refund affected customers` appears exactly once in `body`.
- AC-7: With `ACTIONTRACK_TODAY=2026-10-14`, an item due 2026-10-14 is under Open, not Overdue; with `2026-10-16` it is Overdue with `2 days overdue`; 1 day gives `1 day overdue`.
- AC-8: `body` contains no `\r`, no tab, no em dash, and every line ending is `\n`.
- AC-9: A contacts file without Karan gives `to == []` and a warning containing `no email address for Karan Joshi`; a missing contacts file gives `contacts file not found`; exit is 0 in both.
- AC-10: `followup "Priya" --dry-run` exits 2 and stderr names `Priya Nair` and `Priya Shah`; `followup "Priya (ambiguous)"` and `followup Unassigned` exit 2; `followup "Nobody Here"` exits 3; nothing is printed to stdout in these cases.
- AC-11: For `Priya Nair`, the Needs-review section lists her `Priya (ambiguous)` items and does not count them in N; the subject N equals the number of lines under Overdue plus Open.
- AC-12: `Lena Fischer` and `Priya Nair` each list `Collect user feedback on the prototype`, annotated with the other person's name; the email to Lena has `to` with Lena's address only.
- AC-13: An owner with no open items gives exit 0, `subject: null`, `body: null`, and the warning `no open or overdue items; no draft needed`.
- AC-14: No code path calls a send tool: a test scans every `.py` file under `actiontrack/` and fails on an import of `smtplib`, `imaplib`, `http.client`, `urllib.request`, `socket`, `requests`, `httpx` or `googleapiclient`, or on any (case-insensitive) occurrence of `messages.send`, `drafts.send`, `send_email`, `send_message`, `send_draft`, `gmail_send`.
- AC-15: Running `followup` with `socket.socket` monkeypatched to raise leaves the command's output and exit code unchanged.
- AC-16: The database file's bytes and modification time are identical before and after any `followup` call (both modes); the connection is opened read-only (`mode=ro`).
- AC-17: `.claude/settings.json` parses as JSON, has a `permissions.deny` entry for every Gmail tool whose name contains `send`, and a `PreToolUse` hook that exits 2 for a tool name containing `send` (case-insensitive) and 0 for `mcp__claude_ai_Gmail__create_draft`-style names; `.claude/skills/followup-email/SKILL.md` names a create-draft tool and no send tool as allowed.
- AC-18: Without `--dry-run` the command prints `To:`, `Subject:` and the body, the stderr line `note: preview only; nothing was sent or drafted`, and exits 0.
