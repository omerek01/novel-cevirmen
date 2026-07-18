"""HTTP katmanı: fetch/çeviri gerektirmeyen endpoint'ler (TestClient).

/api/chapter ve /api/.../bulk başlatma Playwright+Gemini çağırdığı için burada
test edilmez; konum, kütüphane listesi ve iş durumu endpoint'leri kapsanır.
"""
import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    import server  # env (NOVEL_DB_PATH) fixture tarafından ayarlandıktan sonra import
    return TestClient(server.app)


def test_books_empty():
    res = _client().get("/api/books")
    assert res.status_code == 200
    assert res.json() == {"books": []}


def test_position_roundtrip_via_api():
    from core import library

    library.upsert_book("s", "Kitap", "u1", "B1", 1)
    client = _client()
    res = client.post("/api/book/s/position", json={"url": "u1", "ratio": 0.55})
    assert res.status_code == 200 and res.json()["ok"] is True

    books = client.get("/api/books").json()["books"]
    assert abs(books[0]["current_ratio"] - 0.55) < 1e-9


def test_bulk_status_not_found():
    res = _client().get("/api/bulk/yokboyle")
    assert res.status_code == 404


def test_bulk_stop_unknown_returns_false():
    res = _client().post("/api/bulk/yokboyle/stop")
    assert res.status_code == 200 and res.json()["ok"] is False


def test_book_job_empty():
    res = _client().get("/api/book/yok/job")
    assert res.status_code == 200
    assert res.json() == {"job": None}


def test_clearance_refresh_is_mocked_offline(monkeypatch):
    import server

    monkeypatch.setattr(server, "refresh_clearance", lambda: {"ok": True, "mode": "test"})
    res = _client().post("/api/clearance/refresh")
    assert res.status_code == 200
    assert res.json() == {"ok": True, "mode": "test"}


def test_delete_chapter_clears_reading_position():
    """DELETE /api/chapter: bölüm silinir; 'kaldığın yer' o bölümse temizlenir."""
    from core import cache, library

    cache.save_chapter("uSil", {
        "book_slug": "s", "book_title": "K", "title": "B2", "chapter_no": 2,
        "translation": "x", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    library.upsert_book("s", "K", "uSil", "B2", 2)
    client = _client()

    res = client.delete("/api/chapter", params={"url": "uSil"})
    assert res.status_code == 200 and res.json()["ok"] is True
    assert cache.get_chapter("uSil") is None
    book = library.get_book("s")
    assert book["current_url"] is None  # devam-et işareti silinen bölümü göstermez
    assert book["chapter_no"] is None

    # Olmayan bölüm: sessiz, ok=False (hata değil).
    res = client.delete("/api/chapter", params={"url": "yok"})
    assert res.status_code == 200 and res.json()["ok"] is False


def test_chapter_endpoint_maps_typed_errors_to_error_class(monkeypatch):
    """Frontend hata kartı error_class'a dallanır: 502/503 + doğru sınıf adı."""
    import server
    from core.fetch import CloudflareChallenge, FetchError
    from core.translate import TranslateError

    client = _client()

    def _raise(exc):
        def fake(url, api_key, refresh=False, want_source=False, **kw):
            raise exc
        return fake

    monkeypatch.setattr(server, "API_KEY", "anahtar")

    monkeypatch.setattr(
        server.pipeline, "get_or_translate", _raise(CloudflareChallenge("cf"))
    )
    res = client.get("/api/chapter", params={"url": "u1"})
    assert res.status_code == 502
    assert res.json()["detail"]["error_class"] == "CloudflareChallenge"

    monkeypatch.setattr(
        server.pipeline, "get_or_translate",
        _raise(FetchError("Kaynak site yanıt vermiyor (HTTP 522).")),
    )
    res = client.get("/api/chapter", params={"url": "u1"})
    assert res.status_code == 502
    assert res.json()["detail"]["error_class"] == "OriginError"

    monkeypatch.setattr(
        server.pipeline, "get_or_translate", _raise(FetchError("içerik yok"))
    )
    res = client.get("/api/chapter", params={"url": "u1"})
    assert res.status_code == 502
    assert res.json()["detail"]["error_class"] == "FetchError"

    monkeypatch.setattr(
        server.pipeline, "get_or_translate", _raise(TranslateError("model hata"))
    )
    res = client.get("/api/chapter", params={"url": "u1"})
    assert res.status_code == 503
    assert res.json()["detail"]["error_class"] == "TranslateError"

    # Anahtar yoksa TranslateError 500'e düşer (kurulum hatası, geçici değil).
    monkeypatch.setattr(server, "API_KEY", None)
    res = client.get("/api/chapter", params={"url": "u1"})
    assert res.status_code == 500


def test_reading_log_endpoint_dedups_per_day():
    """POST /api/reading-log: günde bölüm başına bir kayıt; istatistik yansır."""
    client = _client()
    body = {"day": "2026-07-18", "slug": "s", "url": "u1"}
    res = client.post("/api/reading-log", json=body)
    assert res.status_code == 200 and res.json()["ok"] is True
    res = client.post("/api/reading-log", json=body)
    assert res.status_code == 200 and res.json()["ok"] is False  # tekrar → no-op

    res = client.get("/api/stats", params={"day": "2026-07-18"})
    assert res.status_code == 200
    assert res.json() == {"today": 1, "total": 1}
    # Başka gün: bugün 0, toplam kalır (raf altı satır "TOPLAM 1" der).
    res = client.get("/api/stats", params={"day": "2026-07-19"})
    assert res.json() == {"today": 0, "total": 1}


def test_book_status_endpoint():
    """POST /api/book/{slug}/status: durum yazılır; books yanıtında görünür."""
    from core import library

    library.upsert_book("s", "K", "u1", "B1", 1)
    client = _client()

    res = client.post("/api/book/s/status", json={"status": "bitti"})
    assert res.status_code == 200 and res.json() == {"ok": True, "status": "bitti"}
    books = client.get("/api/books").json()["books"]
    assert books[0]["status"] == "bitti"

    # Geçersiz durum → 400 (frontend iyimser güncellemeyi geri alır).
    res = client.post("/api/book/s/status", json={"status": "rafta"})
    assert res.status_code == 400
    # Bilinmeyen kitap → 404.
    res = client.post("/api/book/yok/status", json={"status": "bitti"})
    assert res.status_code == 404


def test_books_default_status_okunuyor():
    """Eski satırlar (status NULL) yanıtla 'okunuyor' olarak döner."""
    from core import library

    library.upsert_book("s", "K", "u1", "B1", 1)
    books = _client().get("/api/books").json()["books"]
    assert books[0]["status"] == "okunuyor"
