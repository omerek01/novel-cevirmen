"""Paylaşılan SQLite yardımcıları.

- `db_path()`: chapters.db yolunu döndürür; `NOVEL_DB_PATH` ortam değişkeniyle
  geçersiz kılınabilir (testler geçici DB'ye yönlendirir).
- `ensure_column()`: idempotent sütun migration (SQLite'ta `ADD COLUMN IF NOT
  EXISTS` yoktur; PRAGMA + try/except ile güvenli).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "cache" / "chapters.db"


def db_path() -> Path:
    """Aktif DB yolu. Test/CI `NOVEL_DB_PATH` ile geçici dosyaya yönlendirebilir."""
    override = os.getenv("NOVEL_DB_PATH")
    return Path(override) if override else _DEFAULT_DB


def ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """`table.column` yoksa ekler (idempotent).

    decl: tam sütun bildirimi, örn. "prev_url TEXT". Eşzamanlı iki bağlantı aynı
    anda eklemeye çalışırsa ikincisi "duplicate column" verir; sessizce yutulur.
    """
    try:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return  # tablo henüz yok (CREATE TABLE'dan önce çağrıldı)
    if column not in cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {decl}")
        except sqlite3.OperationalError:
            pass
