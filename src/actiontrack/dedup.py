"""Fingerprinting and fuzzy matching of tasks."""
import difflib
import re
import unicodedata

NOISE = {"a", "an", "the", "first", "updated", "revised"}
THRESHOLD = 0.85


def normalize(text):
    t = unicodedata.normalize("NFKC", text).lower().replace("'", "").replace("’", "")
    return " ".join(w for w in re.sub(r"[\W_]+", " ", t).split() if w not in NOISE)


def best_match(task_key, candidates):
    """candidates: iterable of (id, task_key) sharing the owner_key. -> id | None."""
    best = None
    for cid, ckey in candidates:
        r = 1.0 if ckey == task_key else difflib.SequenceMatcher(None, ckey, task_key).ratio()
        if r >= THRESHOLD and (best is None or r > best[0] or (r == best[0] and cid < best[1])):
            best = (r, cid)
    return best[1] if best else None
