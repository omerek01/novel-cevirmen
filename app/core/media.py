"""İçe aktarılan kitapların medyası: kaynak PDF, render'lı çevrilmiş sayfa PNG'leri,
EPUB gömülü resimleri.

DB'nin yanında `cache/media/<slug>/` altında saklanır (NOVEL_DB_PATH ile taşınır).
`/media` ile YALNIZ çevrimiçi servis edilir (SW DATA_CACHE'ine girmez — plan). Slug ve
dosya adları temizlenir; `/media` çözümü media kökü dışına çıkamaz (path traversal yok).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import db


def media_root() -> Path:
    return db.db_path().parent / "media"


def safe_name(name: str) -> str:
    """Yalnız güvenli karakterler (harf/rakam/._-); `..`, `/`, `\\` elenir."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name or "") or "x"


def book_dir(slug: str) -> Path:
    d = media_root() / safe_name(slug)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_bytes(slug: str, name: str, data: bytes) -> str:
    """Baytları media/<slug>/<name>'e yaz; `<slug>/<name>` (media-göreli) döner."""
    slug_s, name_s = safe_name(slug), safe_name(name)
    (book_dir(slug_s) / name_s).write_bytes(data)
    return f"{slug_s}/{name_s}"


def resolve(rel: str) -> Path | None:
    """`/media/<rel>` → media kökü altındaki güvenli mutlak yol; dışına çıkarsa/yoksa None."""
    root = media_root().resolve()
    try:
        p = (root / (rel or "")).resolve()
    except (OSError, ValueError):
        return None
    if p != root and root not in p.parents:
        return None
    return p if p.is_file() else None


def delete_book_media(slug: str) -> None:
    """Kitabın tüm medyasını sil (kitap silinince). Best-effort."""
    import shutil

    d = media_root() / safe_name(slug)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
