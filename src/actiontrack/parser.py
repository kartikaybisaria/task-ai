"""Parse one meeting-note file into a Note or a skip reason. Never raises for file content."""
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import dates
from .owners import is_placeholder


@dataclass
class Sighting:
    owner_raw: str | None
    owner_names: list
    task_text: str
    checked: bool
    due_raw: str | None
    due_date: date | None
    source: str
    line: int


@dataclass
class Note:
    meeting_date: date
    attendees: list
    warnings: list = field(default_factory=list)
    sightings: list = field(default_factory=list)


_CHECKBOX = re.compile(r"^(?P<indent>[ \t]*)(?P<bullet>[-*+])[ \t]+\[(?P<mark>[ xX])\][ \t]+(?P<text>\S.*?)[ \t]*$")
_ACTION = re.compile(r"^\s*ACTION:\s*(?P<text>\S.*?)\s*$", re.I)
_HANDLE = re.compile(r"^@(\w+):\s*(?P<task>\S.*)$")
_NAME = r"(?:[A-Z][\w'’-]*|someone|everyone|team|tbd)"
_PERSON = rf"{_NAME}(?:\s+[A-Z]\.)?"
_LIST = rf"{_PERSON}(?:\s*(?:&|,|\band\b)\s*{_PERSON})*"
_OWNER = re.compile(rf"^(?P<phrase>{_LIST}(?:\s*\(with\s+{_LIST}\))?)\s+to\s+(?P<task>\S.*)$")
_DATE_LINE = re.compile(r"^\s*date\s*:\s*(.*?)\s*$", re.I)
_ATT_LINE = re.compile(r"^\s*attendees\s*:\s*(.*?)\s*$", re.I)
_FILE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
_SPLIT = re.compile(r"\s*(?:&|,|\band\b|\(with|\))\s*")


def _names(phrase):
    names = [n.strip() for n in _SPLIT.split(phrase) if n.strip()]
    if not names or all(is_placeholder(n) for n in names):
        return ["Unassigned"]
    return names


def split_owner(text):
    """-> (owner_raw|None, owner_names, task)."""
    m = _HANDLE.match(text)
    if m:
        return "@" + m[1], [m[1]], m["task"].strip()
    m = _OWNER.match(text)
    if m:
        return m["phrase"], _names(m["phrase"]), m["task"].strip()
    return None, ["Unassigned"], text.strip()


def parse_note(path):
    try:
        return _parse(Path(path))
    except OSError as e:
        return None, f"unreadable: {e.strerror or e}"
    except (OverflowError, ValueError, RecursionError) as e:
        return None, f"unparseable: {e}"


def _parse(path):
    if path.suffix.lower() != ".md":
        return None, f"unsupported extension ({path.suffix})"
    data = path.read_bytes()
    if not data:
        return None, "empty file"
    if b"\x00" in data:
        return None, "binary content (NUL bytes)"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "not valid UTF-8"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    warnings = []

    fm = _FILE_DATE.match(path.name)
    file_date = None
    if fm:
        try:
            file_date = date.fromisoformat(fm[1])
        except ValueError:
            pass
    meeting = None
    for i, ln in enumerate(lines, 1):
        m = _DATE_LINE.match(ln)
        if not m:
            continue
        r = dates.parse_header_date(m[1])
        if r:
            meeting = r[0]
            if r[1] and not dates.weekday_matches(r[1], r[0]):
                warnings.append((None, f"weekday '{r[1]}' does not match date {r[0]}"))
            if file_date and file_date != meeting:
                warnings.append((None, f"header date {meeting} differs from filename date {file_date}; using header"))
        elif file_date:
            meeting = file_date
            warnings.append((None, f"date '{m[1]}' not parseable; using filename date {file_date}"))
        break
    if meeting is None:
        meeting = file_date
    if meeting is None:
        return None, "no meeting date"

    attendees = []
    for ln in lines:
        m = _ATT_LINE.match(ln)
        if m:
            raw = m[1].strip().strip("[]")
            attendees = list(dict.fromkeys(a.strip().strip("\"'") for a in raw.split(",") if a.strip()))
            break
    if not attendees:
        warnings.append((None, "no attendees listed"))

    sightings, seen = [], {}
    in_fence = in_comment = False
    table = None

    def add(source, no, text, checked, owner=None, due=None):
        if owner is not None:
            owner_raw, names, task = owner[0], owner[1], text.strip()
        else:
            owner_raw, names, task = split_owner(text)
        if due is not None:
            due_raw, due_date = due
        else:
            task, due_raw, due_date, warn = dates.find_due(task, meeting)
            if warn:
                warnings.append((no, warn))
        key = (source, owner_raw, text)
        if key in seen:
            if checked:
                seen[key].checked = True
            return
        s = Sighting(owner_raw, names, task, checked, due_raw, due_date, source, no)
        seen[key] = s
        sightings.append(s)

    for no, ln in enumerate(lines, 1):
        if in_fence:
            if ln.lstrip().startswith("```"):
                in_fence = False
            continue
        if not in_comment and ln.lstrip().startswith("```"):
            in_fence = True
            continue
        out, i = "", 0
        while i < len(ln):
            if in_comment:
                j = ln.find("-->", i)
                if j < 0:
                    i = len(ln)
                else:
                    in_comment, i = False, j + 3
            else:
                j = ln.find("<!--", i)
                if j < 0:
                    out += ln[i:]
                    break
                out += ln[i:j]
                in_comment, i = True, j + 4
        if re.match(r"\s*>", out):
            continue
        m = _CHECKBOX.match(out)
        if m:
            table = None
            add("checkbox", no, m["text"], m["mark"] in "xX")
            continue
        m = _ACTION.match(out)
        if m:
            table = None
            add("action_line", no, m["text"], False)
            continue
        st = out.strip()
        if st.startswith("|"):
            cells = [c.strip() for c in st.strip("|").split("|")]
            low = [c.lower() for c in cells]
            if {"owner", "action", "due"} <= set(low):
                table = (low.index("owner"), low.index("action"), low.index("due"))
            elif table and len(cells) > max(table) and not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                o, a, d = (cells[k] for k in table)
                if a:
                    add("table", no, a, False, owner=(o or None, _names(o)),
                        due=dates.resolve_cell(d, meeting))
            continue
        table = None
    return Note(meeting, attendees, warnings, sightings), None
