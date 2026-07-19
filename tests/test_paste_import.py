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


def test_same_book_title_appends_not_duplicates(monkeypatch):
    """Aynı başlıkla ikinci içe aktarım YENİ kitap (-2) açmaz, mevcut kitaba ekler."""
    from core import jobs

    monkeypatch.setattr(jobs, "_start_thread", lambda job_id, api_key: True)
    c = _client()
    first = c.post("/api/import/paste", json={
        "title": "Bölüm 1", "text": "one", "book_title": "Same Book",
    }).json()
    second = c.post("/api/import/paste", json={
        "title": "Bölüm 2", "text": "two", "book_title": "Same Book",
    }).json()
    # Aynı slug, artan bölüm no; tek kütüphane kaydı.
    assert first["slug"] == second["slug"] == "paste-same-book"
    assert (first["chapter_no"], second["chapter_no"]) == (1, 2)
    paste_books = [b for b in library.list_books() if b["slug"].startswith("paste-")]
    assert len(paste_books) == 1
    assert len(cache.list_chapters("paste-same-book")) == 2


def test_paste_url_fills_blocked_web_chapter(monkeypatch):
    """A: web kitabında takılan bölümün metni GERÇEK URL'ye yapıştırılır; pipeline
    web'e inmeden raw_source'tan çevirir (raw_source-öncelikli routing)."""
    # N: çekilmiş bölüm, next'i engellenen URL'ye işaret ediyor.
    cache.save_chapter("http://site/1", {
        "book_slug": "solo", "book_title": "Solo", "title": "B1", "chapter_no": 1,
        "translation": "çeviri1", "next_url": "http://site/2", "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    library.upsert_book("solo", "Solo", "http://site/1", "B1", 1)
    # Engellenen bölümün metnini gerçek URL'ye yapıştır.
    ch = synthetic.stage_url_chapter("solo", "Solo", "B2", "raw two", "http://site/2")
    assert ch["url"] == "http://site/2" and ch["chapter_no"] == 2
    staged = cache.get_staged("http://site/2")
    assert staged["raw_source"] == "raw two" and staged["translation"] is None
    assert staged["prev_url"] == "http://site/1"  # pointer (next_url) üzerinden bağlandı

    # Okuma yolu: fetch'e İNMEDEN raw_source'tan çevir.
    def fail_fetch(*a, **k):
        raise AssertionError("yapıştırılmış URL fetch'e inmemeli")

    monkeypatch.setattr(pipeline, "fetch_chapter", fail_fetch)
    seen = []

    def fake_translate(text, api_key=None, glossary=None):
        seen.append(text)
        return {"translation": "çeviri2", "source": None,
                "detected_names": [], "chunk_count": 1}

    monkeypatch.setattr(pipeline, "translate_chapter", fake_translate)
    out = pipeline.get_or_translate("http://site/2", "anahtar")
    assert seen == ["raw two"] and out["translation"] == "çeviri2"


def test_paste_url_refill_updates_raw_and_renulls_translation():
    """Aynı URL yeniden yapıştırılırsa raw_source güncellenir, translation NULL'lanır."""
    synthetic.stage_url_chapter("solo", "Solo", "B2", "ilk", "http://s/2")
    cache.save_chapter("http://s/2", {  # çevrilmiş gibi işaretle
        "book_slug": "solo", "book_title": "Solo", "title": "B2", "chapter_no": 1,
        "translation": "eski", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    synthetic.stage_url_chapter("solo", "Solo", "B2", "yeni metin", "http://s/2")
    staged = cache.get_staged("http://s/2")
    assert staged["raw_source"] == "yeni metin" and staged["translation"] is None


def test_paste_url_endpoint_stages_and_validates(monkeypatch):
    from core import jobs

    monkeypatch.setattr(jobs, "_start_thread", lambda job_id, api_key: True)
    library.upsert_book("webk", "Web Kitap", "http://s/1", "B1", 1)
    res = _client().post("/api/import/paste-url", json={
        "url": "http://s/2", "slug": "webk", "text": "hello two", "title": "B2",
    })
    assert res.status_code == 200
    assert res.json()["url"] == "http://s/2" and res.json()["slug"] == "webk"
    assert cache.get_staged("http://s/2")["raw_source"] == "hello two"
    # Sentetik URL reddedilir (web kitabı gerekiyor).
    assert _client().post("/api/import/paste-url", json={
        "url": "paste://x/1", "slug": "webk", "text": "x"}).status_code == 400
    # Boş metin reddedilir.
    assert _client().post("/api/import/paste-url", json={
        "url": "http://s/3", "slug": "webk", "text": " "}).status_code == 400
    # Bilinmeyen kitap → 404.
    assert _client().post("/api/import/paste-url", json={
        "url": "http://s/9", "slug": "yok", "text": "x"}).status_code == 404


def test_fetch_into_book_links_and_keeps_web_next(monkeypatch):
    """B: URL kitaba sonraki bölüm olarak çekilir; sayfanın gerçek next'i korunur
    (web'den devam), kuyruk buna bağlanır, book_slug hedefe ZORLANIR."""
    synthetic.append_chapter("paste-k", "K", "B1", "one")
    library.upsert_book("paste-k", "K", "paste://paste-k/1", "B1", 1)

    def fake_fetch(url, **k):
        return {"book_slug": "host-turevli", "book_title": "Host", "title": "Web B2",
                "chapter_no": 999, "text": "web two",
                "next_url": "http://site/3", "prev_url": None}

    monkeypatch.setattr(pipeline, "fetch_chapter", fake_fetch)
    monkeypatch.setattr(pipeline, "translate_chapter",
                        lambda t, api_key=None, glossary=None: {
                            "translation": "çeviri2", "source": None,
                            "detected_names": [], "chunk_count": 1})
    out = pipeline.fetch_into_book("http://site/2", "paste-k", "anahtar")
    assert out["book_slug"] == "paste-k"       # slug hedefe zorlandı
    assert out["chapter_no"] == 2              # kuyruk + 1
    assert out["next_url"] == "http://site/3"  # sayfanın gerçek next'i korunur

    saved = cache.get_chapter("http://site/2")
    assert saved["book_slug"] == "paste-k" and saved["prev_url"] == "paste://paste-k/1"
    assert cache.get_staged("paste://paste-k/1")["next_url"] == "http://site/2"
    assert {c["url"] for c in cache.list_chapters("paste-k")} == {
        "paste://paste-k/1", "http://site/2"}


def test_fetch_next_endpoint_validates(monkeypatch):
    library.upsert_book("wk", "WK", "http://s/1", "B1", 1)
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **k: {
        "book_slug": "h", "book_title": "H", "title": "B2", "chapter_no": 5,
        "text": "t", "next_url": "http://s/3", "prev_url": None})
    monkeypatch.setattr(pipeline, "translate_chapter",
                        lambda t, api_key=None, glossary=None: {
                            "translation": "ç", "source": None,
                            "detected_names": [], "chunk_count": 1})
    res = _client().post("/api/book/wk/fetch-next", json={"url": "http://s/2"})
    assert res.status_code == 200 and res.json()["url"] == "http://s/2"
    # sentetik url reddedilir, bilinmeyen kitap 404.
    assert _client().post("/api/book/wk/fetch-next",
                          json={"url": "paste://x/1"}).status_code == 400
    assert _client().post("/api/book/yok/fetch-next",
                          json={"url": "http://s/9"}).status_code == 404


def test_refresh_nav_synthetic_no_fetch(monkeypatch):
    """C: sentetik bölümde refresh-nav fetch'e inmez, sahneli next'i döndürür."""
    a = synthetic.append_chapter("paste-k", "K", "B1", "one")
    b = synthetic.append_chapter("paste-k", "K", "B2", "two")

    def fail_fetch(*a, **k):
        raise AssertionError("sentetik refresh-nav fetch'e inmemeli")

    monkeypatch.setattr(pipeline, "fetch_chapter", fail_fetch)
    res = _client().post("/api/chapter/refresh-nav", json={"url": a["url"]})
    assert res.status_code == 200 and res.json()["next_url"] == b["url"]


def test_refresh_nav_http_updates_cache(monkeypatch):
    """C: yapıştırılan/eski http bölümün next'i web'den öğrenilip cache'e yazılır."""
    cache.save_chapter("http://s/1", {
        "book_slug": "b", "book_title": "B", "title": "B1", "chapter_no": 1,
        "translation": "ç1", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1})
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **k: {
        "title": "B1", "text": "t", "next_url": "http://s/2", "prev_url": None,
        "book_slug": "b", "book_title": "B", "chapter_no": 1})
    res = _client().post("/api/chapter/refresh-nav", json={"url": "http://s/1"})
    assert res.status_code == 200 and res.json()["next_url"] == "http://s/2"
    assert cache.get_chapter("http://s/1")["next_url"] == "http://s/2"
