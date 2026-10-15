import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    sys.path.insert(0, str(p))

from helpers import FIXTURES, SHIPPED, ingest  # noqa: E402


@pytest.fixture(scope="session")
def shipped_db(tmp_path_factory):
    """Shipped notes/ ingested once (read-only for tests)."""
    db = tmp_path_factory.mktemp("shipped") / "a.db"
    ingest(db, SHIPPED)
    return db


_cache = {}


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """fx('dupes') -> db of that fixture dir, ingested once. Read-only use only."""
    def get(name):
        if name not in _cache:
            db = tmp_path_factory.mktemp(name) / "a.db"
            ingest(db, FIXTURES / name)
            _cache[name] = db
        return _cache[name]
    return get


@pytest.fixture
def fresh(tmp_path):
    """fresh('overdue') -> (db, notes_dir copy) for tests that mutate."""
    def make(name=None):
        d = tmp_path / "notes"
        shutil.copytree(FIXTURES / name if name else SHIPPED, d)
        db = tmp_path / "f.db"
        ingest(db, d)
        return db, d
    return make
