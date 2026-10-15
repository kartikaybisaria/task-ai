---
description: Draft a Gmail follow-up for one owner's open action items (draft only, never send)
argument-hint: <owner name>
---

Follow the `followup-email` skill (`.claude/skills/followup-email/SKILL.md`) for this owner: $ARGUMENTS

Rules for this command:
- Create a Gmail **draft only**. **Never send** the email, and never call any tool whose name contains `send`.
- If no owner was given, ask which one. If the name is ambiguous (for example `Priya`), ask which person; do not guess.
- Run `python -m actiontrack followup "$ARGUMENTS" --dry-run`, use its JSON (`to`, `subject`, `body`) verbatim, create the draft with the Gmail create-draft tool, show the draft to the user, then stop.
