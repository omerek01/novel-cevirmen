"""Seçili bölümleri yeniden çeviren arka plan işi (retranslate).

Belge: "Kullanıcı etkilenen bölümü tek dokunuşla açar; yalnız seçtiği bölümler
çevrilir." İş toplu çeviri altyapısını (checkpoint, durdurma, rozet) kullanır ama
zincir izlemez: yalnız verilen URL'leri `refresh=True` ile çevirir ve her bölüm
için sonucu (hizalama, sözlük ihlali, İngilizce kalıntı, model) kaydeder — yeniden
üretimin denetlenebilmesi için.
"""
from __future__ import annotations

import time

import pytest

from core import cache, jobs, library
from core.translate import TranslateError

KITAP = "gumus-kule"


def _wait(job_id, states, timeout=3.0):
    son = time.monotonic() + timeout
    while time.monotonic() < son:
        s = jobs.get_status(job_id)
        if s and s["state"] in states:
            return s
        time.sleep(0.01)
    pytest.fail(f"İş zamanında bitmedi: {jobs.get_status(job_id)}")


@pytest.fixture(autouse=True)
def is_bellegi_temiz():
    with jobs._LOCK:
        jobs._JOBS.clear()
        jobs._THREADS.clear()
    yield
    with jobs._LOCK:
        kimlikler = list(jobs._JOBS)
    for k in kimlikler:
        jobs.stop(k)
    son = time.monotonic() + 1
    while time.monotonic() < son:
        with jobs._LOCK:
            if not any(t.is_alive() for t in jobs._THREADS.values()):
                break
        time.sleep(0.01)
    with jobs._LOCK:
        jobs._JOBS.clear()
        jobs._THREADS.clear()


def _sahte_ceviri(cagrilar, hatali=()):
    def fake(url, api_key, **kw):
        cagrilar.append((url, kw))
        if url in hatali:
            raise TranslateError("kalıcı hata")
        return {
            "title": url, "source": "EN" if url != "u2" else None,
            "model": "gemini-3.6-flash", "glossary_leaks": {"Saint": "Aziz"} if url == "u1" else {},
            "ingilizce_kalinti": {}, "cached": False, "next_url": "BAŞKA",
        }
    return fake


def test_yalniz_verilen_bolumler_refresh_ile_cevrilir_zincir_izlenmez(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(jobs.pipeline, "get_or_translate", _sahte_ceviri(cagrilar))
    monkeypatch.setattr(jobs, "BULK_GECICI_BEKLEME", (0.0, 0.0))
    job_id = jobs.start_retranslate(KITAP, ["u1", "u2"], None)
    s = _wait(job_id, {"done"})
    assert [u for u, _ in cagrilar] == ["u1", "u2"]
    assert all(kw.get("refresh") is True and kw.get("background") is True for _, kw in cagrilar)
    assert s["type"] == "retranslate" and s["done"] == 2 and s["total"] == 2
    sonuc = s["params"]["sonuclar"]
    assert sonuc["u1"] == {"durum": "tamam", "hizali": True, "ihlal": 1, "kalinti": 0,
                           "model": "gemini-3.6-flash", "arsiv_id": None}
    assert sonuc["u2"]["hizali"] is False


def test_bir_bolumun_kalici_hatasi_isi_durdurmaz_kaydedilir(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(jobs.pipeline, "get_or_translate", _sahte_ceviri(cagrilar, hatali={"u1"}))
    monkeypatch.setattr(jobs, "BULK_GECICI_BEKLEME", (0.0, 0.0))
    job_id = jobs.start_retranslate(KITAP, ["u1", "u3"], None)
    s = _wait(job_id, {"done"}, timeout=5)
    assert s["params"]["sonuclar"]["u1"]["durum"] == "hata"
    assert s["params"]["sonuclar"]["u3"]["durum"] == "tamam"


def test_ayni_kitapta_kosan_is_varken_yenisi_acilmaz(monkeypatch):
    import threading

    kapi = threading.Event()

    def yavas(url, api_key, **kw):
        kapi.wait(2)
        return {"title": url, "source": "x", "cached": False}

    monkeypatch.setattr(jobs.pipeline, "get_or_translate", yavas)
    ilk = jobs.start_retranslate(KITAP, ["u1"], None)
    ikinci = jobs.start_retranslate(KITAP, ["u2"], None)
    kapi.set()
    assert ikinci == ilk


def _bolum(url, slug=KITAP, cevrili=True):
    cache.save_chapter(url, {
        "book_slug": slug, "book_title": "K", "title": "B", "chapter_no": 1,
        "translation": "çeviri metni" if cevrili else None, "next_url": None,
        "prev_url": None, "detected_names": [], "chunk_count": 1,
    })
    library.upsert_book(slug, "K", url, "B", 1)


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def test_uc_baska_kitabin_ya_da_cevrilmemis_bolumu_reddeder(monkeypatch):
    monkeypatch.setattr(jobs, "start_retranslate", lambda *a, **k: "is")
    _bolum("https://ornek.test/a/1")
    _bolum("https://ornek.test/b/1", slug="baska")
    _bolum("https://ornek.test/a/2", cevrili=False)
    c = _client()
    assert c.post(f"/api/book/{KITAP}/retranslate", json={"urls": []}).status_code == 400
    assert c.post(f"/api/book/{KITAP}/retranslate",
                  json={"urls": ["https://ornek.test/b/1"]}).status_code == 400
    assert c.post(f"/api/book/{KITAP}/retranslate",
                  json={"urls": ["https://ornek.test/a/2"]}).status_code == 400
    r = c.post(f"/api/book/{KITAP}/retranslate", json={"urls": ["https://ornek.test/a/1"]})
    assert r.status_code == 200 and r.json()["job_id"] == "is"
