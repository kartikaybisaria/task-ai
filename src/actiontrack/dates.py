"""Date helpers: today, meeting-date parsing, due-date expression resolution."""
import os
import re
from datetime import date, timedelta

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def today():
    """The one place that knows what 'today' is (ACTIONTRACK_TODAY or the system date)."""
    v = os.environ.get("ACTIONTRACK_TODAY")
    if v is None or v == "":
        return date.today()
    try:
        if not _ISO.fullmatch(v):
            raise ValueError
        return date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"ACTIONTRACK_TODAY must be YYYY-MM-DD, got '{v}'") from None


def _mon(s):
    return MONTHS[s[:3].lower()]


def _wd(s):
    return WEEKDAYS[s[:3].lower()]


def _mk(name):
    return (rf"(?P<{name}>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
            r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")


WD = r"(?P<wd>mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
END = r"(?![\w'’])"
F = re.I

P_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?!\d)")
P_TOMORROW = re.compile(r"(?:eod\s+)?tomorrow" + END, F)
P_EOD = re.compile(r"(?:eod|today)" + END, F)
P_NEXTWEEK = re.compile(r"end\s+of\s+(?:the\s+)?next\s+week" + END, F)
P_EOW = re.compile(r"(?:end\s+of\s+(?:the\s+)?week|eow)" + END, F)
P_EOM = re.compile(r"(?:end\s+of\s+(?:the\s+)?month|eom)" + END, F)
P_MID = re.compile(r"mid[-\s]?" + _mk("mon") + END, F)
P_WD = re.compile(r"(?:(?:next|this)\s+)?" + WD + END, F)
P_DM = re.compile(r"(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _mk("mon") + r"\.?(?:,?\s+(?P<y>\d{4}))?" + END, F)
P_MD = re.compile(_mk("mon") + r"\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<y>\d{4}))?" + END, F)
P_MONTH = re.compile(_mk("mon") + END, F)


def _in_year(m, d, M, year=None):
    if year is not None:
        return date(year, m, d)
    c = date(M.year, m, d)
    return c if c >= M else date(M.year + 1, m, d)


def _dm(m, M):
    try:
        return _in_year(_mon(m["mon"]), int(m["d"]), M, int(m["y"]) if m["y"] else None)
    except ValueError:
        return None


def parse_expr(text, pos, M, loose=False):
    """Match a date expression at text[pos:]. Returns (end, date|None) or None."""
    m = P_ISO.match(text, pos)
    if m:
        try:
            return m.end(), date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return m.end(), None
    if (m := P_TOMORROW.match(text, pos)):
        return m.end(), M + timedelta(days=1)
    if (m := P_EOD.match(text, pos)):
        return m.end(), M
    if (m := P_NEXTWEEK.match(text, pos)):
        return m.end(), M + timedelta(days=(4 - M.weekday()) % 7 + 7)
    if (m := P_EOW.match(text, pos)):
        return m.end(), M + timedelta(days=(4 - M.weekday()) % 7)
    if (m := P_EOM.match(text, pos)):
        nxt = date(M.year + (M.month == 12), M.month % 12 + 1, 1)
        return m.end(), nxt - timedelta(days=1)
    if (m := P_MID.match(text, pos)):
        return m.end(), _in_year(_mon(m["mon"]), 15, M)
    if (m := P_WD.match(text, pos)):
        k = re.compile(r"[\s,]*").match(text, m.end()).end()
        for pat in (P_DM, P_MD):
            m2 = pat.match(text, k)
            if m2:
                return m2.end(), _dm(m2, M)
        return m.end(), M + timedelta(days=(_wd(m["wd"]) - M.weekday()) % 7 or 7)
    for pat in (P_DM, P_MD):
        m = pat.match(text, pos)
        if m:
            return m.end(), _dm(m, M)
    if loose and (m := P_MONTH.match(text, pos)):
        return m.end(), None
    return None


_TRIG = re.compile(r"(?<![\w])(by|due|before|until|on|from|for)\s+", re.I)
_DEADLINE = {"by", "due", "before", "until", "on"}
_STRICT = {"by", "due", "before", "until"}
_BARE = re.compile(r"(?:^|[\s,—–-]+)(tomorrow|today|eod)[\s.]*$", re.I)
_SEP = re.compile(r"[\s,—–-]+$")


def find_due(text, M):
    """-> (task_text, due_raw, due_date, warning|None)."""
    hits = []
    for t in _TRIG.finditer(text):
        trig = t[1].lower()
        r = parse_expr(text, t.end(), M, loose=trig in ("from", "for"))
        hits.append((t.start(), t.end(), trig, r))
    ok = [h for h in hits if h[2] in _DEADLINE and h[3] and h[3][1]]
    if ok:
        s, _, _, (e, d) = ok[-1]
        left = _SEP.sub("", text[:s])
        right = text[e:].strip(" .")
        task = left + (" " + right if right else "")
        return task.strip(), text[s:e], d, None
    non = [h for h in hits if h[2] in ("from", "for") and h[3]]
    if non:
        s, _, _, (e, _d) = non[-1]
        return text, text[s:e], None, None
    bad = [h for h in hits if h[2] in _STRICT and not h[3]
           and not re.match(r"\d+\s*%", text[h[1]:])]
    if bad:
        raw = text[bad[-1][0]:].rstrip(" .")
        return text, raw, None, f"due clause '{raw}' not parseable"
    m = _BARE.search(text)
    if m:
        d = M if m[1].lower() != "tomorrow" else M + timedelta(days=1)
        return text[:m.start()].rstrip(), m[1], d, None
    return text, None, None, None


def resolve_cell(cell, M):
    """Due cell of a table row -> (due_raw, due_date)."""
    cell = cell.strip()
    if not cell:
        return None, None
    m = re.match(r"(?:by|due|on)\s+", cell, re.I)
    r = parse_expr(cell, m.end() if m else 0, M)
    return cell, (r[1] if r else None)


_FULL = re.compile(
    r"^(?:(?P<wd>[A-Za-z]+)\s*,?\s+)?(?:(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+" + _mk("mon")
    + r"\.?\s*,?\s+(?P<y>\d{4})|" + _mk("mon2") + r"\.?\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?\s*,?\s+(?P<y2>\d{4}))$", re.I)


def parse_header_date(value):
    """-> (date, weekday_word|None) or None."""
    v = value.strip().strip("\"'").strip()
    try:
        m = P_ISO.fullmatch(v)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])), None
        m = _FULL.match(v)
        if not m:
            return None
        wd = m["wd"]
        if wd and wd[:3].lower() not in WEEKDAYS:
            return None
        if m["d"]:
            return date(int(m["y"]), _mon(m["mon"]), int(m["d"])), wd
        return date(int(m["y2"]), _mon(m["mon2"]), int(m["d2"])), wd
    except ValueError:
        return None


def weekday_matches(wd, d):
    return WEEKDAYS[wd[:3].lower()] == d.weekday()
