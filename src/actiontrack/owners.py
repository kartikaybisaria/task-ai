"""Owner resolution: first names / handles / full names -> canonical roster names."""
import re

PLACEHOLDERS = {"everyone", "team", "someone", "tbd", "unassigned"}
_INITIAL = re.compile(r"(\S+)\s+([A-Za-z])\.")


def is_placeholder(tok):
    t = tok.strip().lstrip("@").casefold()
    return not t or t in PLACEHOLDERS


def resolve(token, attendees, roster):
    """-> (owner, review_reason|None, candidates)."""
    tok = token.strip().lstrip("@").strip()
    if is_placeholder(tok):
        return "Unassigned", "unassigned", []
    m = _INITIAL.fullmatch(tok)
    if m:
        first, initial = m[1], m[2]
    elif len(tok.split()) == 1:
        first, initial = tok, None
    else:
        for name in roster:
            if name.casefold() == tok.casefold():
                return name, None, []
        return tok, "unknown_owner", []

    def pick(pool):
        return [n for n in dict.fromkeys(pool)
                if n.split()[0].casefold() == first.casefold()
                and (initial is None or n.split()[-1].casefold().startswith(initial.casefold()))]

    cands = pick(attendees) or pick(roster)
    if len(cands) == 1:
        return cands[0], None, []
    if cands:
        return f"{cands[0].split()[0]} (ambiguous)", "ambiguous_owner", cands
    return tok, "unknown_owner", []
