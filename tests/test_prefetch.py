"""POST /api/prefetch — sonsuz okuma ısıtması (çevrimdışı; pipeline mock'lu).

Prefetch gerçek çeviriyi arka plan thread'inde `pipeline.get_or_translate`'e devreder;
burada o çağrı stub'lanır. Doğrulanan: yalnız http(s) tetiklenir, sentetik/boş atlanır,
çağrı `background=True` ile gelir, cache isabetinde ve uçuş tekrarında yeniden
tetiklenmez.
"""
import threading

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


def _server_with_key(monkeypatch):
    import server  # env (NOVEL_DB_PATH) fixture ayarladıktan sonra import

    monkeypatch.setattr(server, "API_KEY", "test-key")
    return server


def test_prefetch_synthetic_skipped(monkeypatch):
    server = _server_with_key(monkeypatch)
    called = []
    monkeypatch.setattr(server.pipeline, "get_or_translate", lambda *a, **k: called.append(a))
    res = TestClient(server.app).post("/api/prefetch", json={"url": "paste://kitap/1"})
    assert res.status_code == 200
    assert res.json()["queued"] is False
    assert called == []  # sentetik → thread bile açılmaz


def test_prefetch_no_key_skipped(monkeypatch):
    import server

    monkeypatch.setattr(server, "API_KEY", None)
    called = []
    monkeypatch.setattr(server.pipeline, "get_or_translate", lambda *a, **k: called.append(a))
    res = TestClient(server.app).post("/api/prefetch", json={"url": "https://x/1"})
    assert res.json()["queued"] is False
    assert called == []


def test_prefetch_http_triggers_background(monkeypatch):
    server = _server_with_key(monkeypatch)
    done = threading.Event()
    seen = {}

    def _stub(url, api_key, refresh=False, want_source=False, background=False):
        seen["url"] = url
        seen["background"] = background
        done.set()
        return {}

    monkeypatch.setattr(server.pipeline, "get_or_translate", _stub)
    res = TestClient(server.app).post("/api/prefetch", json={"url": "https://site/bolum-2"})
    assert res.status_code == 200 and res.json()["queued"] is True
    assert done.wait(2.0), "prefetch thread'i pipeline'ı çağırmadı"
    assert seen["url"] == "https://site/bolum-2"
    assert seen["background"] is True  # okuyucu önceliği + konum ilerletmeme


def test_prefetch_cache_hit_skipped(monkeypatch):
    server = _server_with_key(monkeypatch)
    from core import cache

    cache.save_chapter(
        "https://site/bolum-9",
        {
            "title": "B9", "translation": "metin", "source": None, "detected_names": [],
            "chunk_count": 1, "next_url": None, "prev_url": None,
            "book_slug": "s", "book_title": "K", "chapter_no": 9, "cached": False,
        },
    )
    called = []
    monkeypatch.setattr(server.pipeline, "get_or_translate", lambda *a, **k: called.append(a))
    res = TestClient(server.app).post("/api/prefetch", json={"url": "https://site/bolum-9"})
    assert res.json().get("cached") is True
    assert called == []  # zaten cache'te → ısıtma yok
