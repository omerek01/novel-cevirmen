"""Sonsuz okuma konum ilerletme (track): önden eklenen bölüm konumu OYNATMAMALI.

Gerçek bulgu: kullanıcı bölüm 7'deyken sonsuz kaydırma bölüm 8'i çevirdi ama önden-
ekleme GET'i kitabın current_url'ini oynatıp aktif-POST'la yarıştı → tutarsızlık.
Düzeltme: önden eklenen bölümler `advance_position=False` (server: /api/chapter?track=0).
Bu testler cache isabetiyle (ağ/Gemini yok) konumun yalnız izlenen bölümde ilerlediğini
doğrular.
"""
from core import cache, library, pipeline


def _seed_two_chapters():
    for url, no in [("https://s/7", 7), ("https://s/8", 8)]:
        cache.save_chapter(url, {
            "title": f"B{no}", "translation": "x" * 80, "source": None,
            "detected_names": [], "chunk_count": 1, "next_url": None, "prev_url": None,
            "book_slug": "kitap", "book_title": "K", "chapter_no": no, "cached": False,
        })
    library.upsert_book("kitap", "K", "https://s/7", "B7", 7)  # konum: bölüm 7


def test_prefetched_chapter_does_not_advance_position():
    _seed_two_chapters()
    # Önden eklenen bölüm 8 (track=0 eşdeğeri) → konum 7'de KALMALI.
    pipeline.get_or_translate("https://s/8", api_key=None, advance_position=False)
    book = library.get_book("kitap")
    assert book["current_url"] == "https://s/7", "önden ekleme konumu oynatmamalı"
    assert book["chapter_no"] == 7


def test_read_chapter_advances_position():
    _seed_two_chapters()
    # Aktif olarak açılan bölüm 8 (track=1 varsayılan) → konum 8'e ilerler.
    pipeline.get_or_translate("https://s/8", api_key=None, advance_position=True)
    book = library.get_book("kitap")
    assert book["current_url"] == "https://s/8"
    assert book["chapter_no"] == 8


def test_default_advances_position():
    _seed_two_chapters()
    # advance_position verilmezse eski davranış (not background = True) → ilerler.
    pipeline.get_or_translate("https://s/8", api_key=None)
    assert library.get_book("kitap")["current_url"] == "https://s/8"


def test_api_chapter_track0_does_not_advance(monkeypatch):
    import pytest
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import server

    _seed_two_chapters()
    client = TestClient(server.app)
    res = client.get("/api/chapter", params={"url": "https://s/8", "track": "0"})
    assert res.status_code == 200
    assert library.get_book("kitap")["current_url"] == "https://s/7"  # oynamadı

    res = client.get("/api/chapter", params={"url": "https://s/8"})  # track varsayılan=1
    assert res.status_code == 200
    assert library.get_book("kitap")["current_url"] == "https://s/8"  # ilerledi
