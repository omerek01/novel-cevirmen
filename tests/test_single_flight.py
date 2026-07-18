"""Tek-uçuş (E-1/E-2/E-14/E-24) + refresh_metadata (E-3) — çevrimdışı, deterministik."""
import threading

import pytest

from core import cache, fetch, pipeline


def _mk_chapter(url, next_url="uN"):
    return {
        "book_slug": "s", "book_title": "K", "title": "B1", "chapter_no": 1,
        "text": "hello", "next_url": next_url, "prev_url": None,
    }


def _mk_translation(**kw):
    out = {"translation": "çeviri", "source": None, "detected_names": [], "chunk_count": 1}
    out.update(kw)
    return out


def test_concurrent_same_url_single_fetch_and_translate(monkeypatch):
    """T1: aynı URL'ye eşzamanlı 2 çağrı → tek fetch+translate, iki sonuç."""
    fetch_calls = []
    translate_calls = []
    entered = threading.Event()
    joined = threading.Event()

    def fake_fetch(url, priority="interactive", ticket=None, **kw):
        fetch_calls.append(url)
        entered.set()
        assert joined.wait(5)  # ikinci çağrı uçuşa katılana dek ilkini beklet
        return _mk_chapter(url)

    def fake_translate(text, api_key=None, glossary=None):
        translate_calls.append(text)
        return _mk_translation()

    monkeypatch.setattr(pipeline, "fetch_chapter", fake_fetch)
    monkeypatch.setattr(pipeline, "translate_chapter", fake_translate)

    results = []
    t1 = threading.Thread(target=lambda: results.append(pipeline.get_or_translate("u1", "k")))
    t1.start()
    assert entered.wait(5)
    t2 = threading.Thread(target=lambda: results.append(pipeline.get_or_translate("u1", "k")))
    t2.start()
    # t2'nin uçuşa katılması için kısa bekleme; sonra uçuşu serbest bırak.
    for _ in range(100):
        if "u1" in pipeline._FLIGHTS and t2.is_alive():
            break
    joined.set()
    t1.join(5), t2.join(5)

    assert len(results) == 2 and all(r["translation"] == "çeviri" for r in results)
    assert fetch_calls == ["u1"]  # TEK fetch
    assert translate_calls == ["hello"]  # TEK çeviri
    assert pipeline._FLIGHTS == {}  # harita temiz


def test_flight_error_cleans_map_and_next_call_retries(monkeypatch):
    """E-14: uçuş istisnayla ölür → harita silinir, hata yayılır, sonraki dener."""
    calls = []

    def fake_fetch(url, priority="interactive", ticket=None, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise fetch.FetchError("çöktü")
        return _mk_chapter(url)

    monkeypatch.setattr(pipeline, "fetch_chapter", fake_fetch)
    monkeypatch.setattr(
        pipeline, "translate_chapter", lambda *a, **k: _mk_translation()
    )
    with pytest.raises(fetch.FetchError):
        pipeline.get_or_translate("u1", "k")
    assert pipeline._FLIGHTS == {}  # kilitli URL kalmadı
    assert pipeline.get_or_translate("u1", "k")["translation"] == "çeviri"


def test_side_effects_per_caller_background_flag(monkeypatch):
    """E-2: salt-prefetch konumu İLERLETMEZ; interaktif çağrı ilerletir."""
    seen = []
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: _mk_chapter(url))
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _mk_translation())
    monkeypatch.setattr(
        pipeline.library, "upsert_book",
        lambda *a, update_position=True: seen.append(update_position),
    )
    pipeline.get_or_translate("u1", "k", background=True)
    pipeline.get_or_translate("u2", "k", background=False)
    assert seen == [False, True]


def test_unknown_priority_raises_valueerror():
    """E-24: 'check-updates' gibi tanımsız öncelik interactive SAYILMAZ."""
    with pytest.raises(ValueError):
        fetch.fetch_chapter("u1", priority="check-updates")


def test_gate_ticket_boost_promotes_waiting_bulk():
    """E-1: kapıda bekleyen bulk bileti boost'lanınca okuyucu önceliği kazanır."""
    gate = fetch._PriorityGate()
    gate._interactive_waiting = 1  # başka yerde bekleyen bir okuyucu simülasyonu
    ticket = gate.ticket("bulk")
    acquired = threading.Event()

    def worker():
        gate.acquire("bulk", ticket)
        acquired.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    assert not acquired.wait(0.3)  # bulk, bekleyen okuyucu varken kapıyı alamaz
    ticket.boost()  # okuyucu uçuşa katıldı → öncelik devri
    assert acquired.wait(5)
    gate.release()
    gate._interactive_waiting -= 1  # simülasyonu geri al
    assert gate._interactive_waiting == 0  # boost sayacı sızdırmadı


def test_refresh_metadata_updates_only_nav(monkeypatch):
    """E-3: yalnız next/prev güncellenir; translation/source'a dokunulmaz, Gemini yok."""
    cache.save_chapter("u1", {
        "book_slug": "s", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "eski çeviri", "source": "old src", "next_url": None,
        "prev_url": None, "detected_names": [], "chunk_count": 1,
    })

    def fail_translate(*a, **k):
        raise AssertionError("refresh_metadata Gemini'ye gitmemeli")

    monkeypatch.setattr(pipeline, "translate_chapter", fail_translate)
    monkeypatch.setattr(
        pipeline, "fetch_chapter",
        lambda url, priority=None, **kw: _mk_chapter(url, next_url="uYeni"),
    )
    nav = pipeline.refresh_metadata("u1")
    assert nav["next_url"] == "uYeni"
    row = cache.get_chapter("u1")
    assert row["next_url"] == "uYeni"
    assert row["translation"] == "eski çeviri"  # DOKUNULMADI
    assert row["source"] == "old src"
