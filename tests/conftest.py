"""Test ortak ayarları: app/ importlanabilir + her test izole geçici DB.

`NOVEL_DB_PATH` env'i geçici dosyaya yönlendirilir; db.db_path() bunu her
çağrıda okuduğu için modül reload gerekmez.
"""
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_DB_PATH", str(tmp_path / "chapters.db"))
    yield
