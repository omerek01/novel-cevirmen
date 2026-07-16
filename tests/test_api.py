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
