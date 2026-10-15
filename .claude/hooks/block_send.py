"""PreToolUse hook: block any tool call whose name contains "send".

Claude Code passes the hook input as JSON on stdin. Exit code 2 blocks the tool call and
shows stderr to Claude; exit code 0 lets it through. This project may only create Gmail
drafts, never send email (see CLAUDE.md and specs/04-followup-gmail.md).
"""
import json
import sys


def main() -> int:
    try:
        tool_name = str(json.load(sys.stdin).get("tool_name", ""))
    except (ValueError, AttributeError):
        print(
            "BLOCKED by .claude/hooks/block_send.py: could not read the hook input, "
            "so the tool call was refused (fail closed).",
            file=sys.stderr,
        )
        return 2

    if "send" in tool_name.lower():
        print(
            f"BLOCKED by .claude/hooks/block_send.py: tool '{tool_name}' contains 'send'. "
            "actiontrack must never send email. Create a Gmail DRAFT with the create-draft "
            "tool instead and let the human send it.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
