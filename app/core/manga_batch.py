"""Manga bölümünü ARKA PLANDA tüm-bölüm-tek-çağrı ile çevir + ilerleme takibi.

Motor tüm sayfaları TEK subprocess'te işler (modeller bir kez → sayfa başına ~8s).
Sayfalar bittikçe cache'e yazılır; okuyucu hazır olanı gösterir, bekleyeni "çevriliyor
N/total" ile polling yapar. Durum bellek-içidir (sunucu restart'ında iş kaybolur —
cache'lenen sayfalar kalır, kalanlar tekrar tetiklenir). Aynı kitap için tek iş.
"""
from __future__ import annotations

import threading

_STATE: dict[str, dict] = {}  # slug -> {"running", "done", "total", "error"}
_LOCK = threading.Lock()


def status(slug: str) -> dict:
    with _LOCK:
        st = _STATE.get(slug)
        return dict(st) if st else {"running": False, "done": 0, "total": 0, "error": None}


def _count_pages(slug: str) -> int:
    from . import media

    d = media.book_dir(slug)
    return sum(1 for p in d.glob("src-*") if p.name[4:].isdigit())


def ensure_started(slug: str, api_key: str) -> dict:
    """Bölüm için batch çeviri işini başlat (zaten çalışıyorsa dokunma). Durum döner."""
    with _LOCK:
        st = _STATE.get(slug)
        if st and st.get("running"):
            return dict(st)
        _STATE[slug] = {"running": True, "done": 0, "total": _count_pages(slug), "error": None}
        snapshot = dict(_STATE[slug])
    threading.Thread(target=_run, args=(slug, api_key), daemon=True).start()
    return snapshot


def _run(slug: str, api_key: str) -> None:
    from . import manga_engine

    def on_page(n, done, total):
        with _LOCK:
            if slug in _STATE:
                _STATE[slug]["done"] = done
                _STATE[slug]["total"] = total

    try:
        manga_engine.translate_chapter_engine(slug, api_key, on_page)
    except Exception as exc:  # motor hatası → durumda tut (reader gösterir)
        with _LOCK:
            if slug in _STATE:
                _STATE[slug]["error"] = str(exc)[:200]
    finally:
        with _LOCK:
            if slug in _STATE:
                _STATE[slug]["running"] = False
