"""Yapıştır-metin içe aktarımı: zincir (E-23), staged (E-17), raw_source (E-18),
sentetik miss (E-7), merge reddi (E-8), slugify (E-13) + API ucu."""
import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from core import cache, fetch, library, pipeline, synthetic  # noqa: E402


def _client():
    import server
    return TestClient(server.app)


def test_chain_synthesis_and_append(monkeypatch):
    """Madde 11 (E-23): n±1 zincir; sona ekleme önceki kuyruğun next'ini bağlar."""
    a = synthetic.append_chapter("paste-k", "K", "B1", "one")
    b = synthetic.append_chapter("paste-k", "K", "B2", "two")
    c = synthetic.append_chapter("paste-k", "K", "B3", "three")
    assert (a["chapter_no"], b["chapter_no"], c["chapter_no"]) == (1, 2, 3)
    sa, sb, sc = (cache.get_staged(x["url"]) for x in (a, b, c))
    assert sa["prev_url"] is None and sa["next_url"] == b["url"]
    assert sb["prev_url"] == a["url"] and sb["next_url"] == c["url"]
    assert sc["prev_url"] == b["url"] and sc["next_url"] is None


def test_synthetic_miss_never_reaches_fetch(monkeypatch):
    """Madde 12 (E-7): kaynak yok → ImportedChapterMissing; kapıya inilmez."""
    def fail_fetch(*a, **k):
        raise AssertionError("sentetik URL fetch'e inmemeli")

    monkeypatch.setattr(pipeline, "fetch_chapter", fail_fetch)
    with pytest.raises(synthetic.ImportedChapterMissing):
        pipeline.get_or_translate("paste://yok/1", "anahtar")
    # API katmanı 404 + error_class döndürür.
    res = _client().get("/api/chapter", params={"url": "paste://yok/1"})
    assert res.status_code == 404
    assert res.json()["detail"]["error_class"] == "ImportedChapterMissing"


def test_staged_row_is_miss_on_read_path_but_visible_to_job():
    """Madde 13 (E-17): sahneli satır okuma yolunda MISS; iş yolunda görünür."""
    ch = synthetic.append_chapter("paste-k", "K", "B1", "raw text")
    assert cache.get_chapter(ch["url"]) is None  # okuyucu boş bölüm ALMAZ
    staged = cache.get_staged(ch["url"])
    assert staged["raw_source"] == "raw text" and staged["translation"] is None


def test_translate_from_raw_source_and_immutability(monkeypatch):
    """Madde 14 (E-18): çeviri raw_source'tan; kayıt raw_source'u EZMEZ."""
    ch = synthetic.append_chapter("paste-k", "K", "B1", "hello raw")
    seen = []

    def fake_translate(text, api_key=None, glossary=None):
        seen.append(text)
        return {"translation": "çeviri", "source": None,
                "detected_names": [], "chunk_count": 1}

    monkeypatch.setattr(pipeline, "translate_chapter", fake_translate)
    out = pipeline.get_or_translate(ch["url"], "anahtar")
    assert seen == ["hello raw"]  # kaynak raw_source'tan geldi
    assert out["translation"] == "çeviri"
    # Çeviri yazıldı ama ham kaynak DEĞİŞMEDİ (E-16'lı save sayesinde).
    staged = cache.get_staged(ch["url"])
    assert staged["translation"] == "çeviri"
    assert staged["raw_source"] == "hello raw"
    # Refresh de raw_source'tan yeniden çevirir, fetch'e gitmez.
    out2 = pipeline.get_or_translate(ch["url"], "anahtar", refresh=True)
    assert seen == ["hello raw", "hello raw"]
    assert cache.get_staged(ch["url"])["raw_source"] == "hello raw"


def test_merge_rejects_synthetic_on_server():
    """Madde 15 (E-8): sentetik slug merge SUNUCUDA reddedilir (400)."""
    library.upsert_book("paste-k", "K", "u1", "B1", 1)
    library.upsert_book("normal", "N", "u2", "B1", 1)
    res = _client().post("/api/book/paste-k/merge-into", json={"target": "normal"})
    assert res.status_code == 400
    res = _client().post("/api/book/normal/merge-into", json={"target": "paste-k"})
    assert res.status_code == 400


def test_delete_only_last_chapter_nulls_prev_next():
    """Madde 16 (E-7/E-23): yalnız son bölüm silinir; öncekinin next'i NULL'lanır."""
    a = synthetic.append_chapter("paste-k", "K", "B1", "one")
    b = synthetic.append_chapter("paste-k", "K", "B2", "two")
    assert synthetic.delete_last_chapter("paste-k", a["url"]) is False  # ortadan silinemez
    assert synthetic.delete_last_chapter("paste-k", b["url"]) is True
    assert cache.get_staged(b["url"]) is None
    assert cache.get_staged(a["url"])["next_url"] is None


def test_empty_slugify_gets_random_suffix():
    """Madde 17 (E-13): boş/sembolik başlık → paste-<rastgele6>."""
    s = synthetic.slugify_title("!!! ???")
    assert s.startswith("paste-") and len(s) == len("paste-") + 6
    assert synthetic.slugify_title("My Book") == "paste-my-book"


def test_import_paste_endpoint_stages_and_starts_job(monkeypatch):
    """API ucu: sahneli satır + kütüphane kaydı + paste-import işi (thread'siz)."""
    from core import jobs

    monkeypatch.setattr(jobs, "_start_thread", lambda job_id, api_key: True)
    res = _client().post("/api/import/paste", json={
        "title": "Chapter 1", "text": "hello world", "book_title": "My Paste Book",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["slug"] == "paste-my-paste-book" and data["chapter_no"] == 1
    assert cache.get_staged(data["url"])["raw_source"] == "hello world"
    book = library.get_book(data["slug"])
    assert book is not None and book["title"] == "My Paste Book"
    job = jobs.get_status(data["job_id"])
    assert job["type"] == "paste-import" and job["state"] == "running"
    # Boş metin reddedilir.
    res = _client().post("/api/import/paste", json={"title": "x", "text": "  "})
    assert res.status_code == 400
