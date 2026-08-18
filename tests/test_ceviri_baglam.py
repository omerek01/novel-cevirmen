"""Çeviri kalitesi eklentileri: bölümler arası bağlam + kitap başına üslup notu.

Ağa/Gemini'ye çıkmaz — bağlamın ve üslup notunun prompt'a KADAR taşındığını
(pipeline -> translate_chapter) ve kaynaklarının (cache/library) doğru satırı
bulduğunu sabitler. Çevirinin kalitesi ölçülmez; taşımanın kopmadığı ölçülür.
"""
import pytest

from core import cache, library, pipeline, translate


def _bolum(url, slug, no, ceviri, content_type=None, prev_url=None):
    cache.save_chapter(url, {
        "book_slug": slug, "book_title": "K", "title": f"B{no}", "chapter_no": no,
        "translation": ceviri, "next_url": None, "prev_url": prev_url,
        "detected_names": [], "chunk_count": 1, "content_type": content_type,
    })


# ---------- cache.prev_translation ----------

def test_prev_translation_prev_url_ile_bulur():
    _bolum("u1", "k", 1, "Birinci bölümün sonu.")
    _bolum("u2", "k", 2, "İkinci.", prev_url="u1")
    assert cache.prev_translation("k", "u1", 2) == "Birinci bölümün sonu."


def test_prev_translation_zincir_kopukken_bolum_no_ile_duser():
    """prev_url yok (elle eklenmiş bölüm) → aynı kitapta bir küçük numaraya düşer."""
    _bolum("u1", "k", 7, "Yedinci.")
    _bolum("u2", "k", 9, "Dokuzuncu.")
    assert cache.prev_translation("k", None, 9) == "Yedinci."


def test_prev_translation_gorsel_bolumu_atlar():
    """PDF/EPUB/manga bölümü HTML tutar; çeviri bağlamı olarak kullanılamaz."""
    _bolum("u1", "k", 1, "Metin bölümü.")
    _bolum("u2", "k", 2, "<img src='/media/x.png'>", content_type="html")
    assert cache.prev_translation("k", "u2", 3) == "Metin bölümü."


def test_prev_translation_yoksa_bos_doner():
    assert cache.prev_translation("k", None, 1) == ""
    assert cache.prev_translation("", None, None) == ""


def test_prev_translation_baska_kitaba_sizmaz():
    _bolum("a1", "kitap-a", 5, "A kitabının metni.")
    _bolum("b1", "kitap-b", 9, "B kitabının metni.")
    assert cache.prev_translation("kitap-b", None, 9) == ""


# ---------- library.set_style_note ----------

def test_style_note_yaz_oku():
    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    assert library.set_style_note("k", "  Birinci şahıs, alaycı ton.  ") is True
    assert library.get_book("k")["style_note"] == "Birinci şahıs, alaycı ton."


def test_style_note_bos_yazmak_notu_kaldirir():
    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    library.set_style_note("k", "bir not")
    library.set_style_note("k", "   ")
    assert library.get_book("k")["style_note"] == ""


def test_style_note_uzunlugu_sinirlanir():
    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    library.set_style_note("k", "x" * 5000)
    assert len(library.get_book("k")["style_note"]) == library.STYLE_NOTE_MAX


def test_style_note_bilinmeyen_kitap_false():
    assert library.set_style_note("yok-boyle-kitap", "not") is False


def test_style_note_upsert_ile_silinmez():
    """Bölüm okundukça upsert_book çalışır; adı geçmeyen sütun sıfırlanmamalı (E-16)."""
    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    library.set_style_note("k", "kalıcı not")
    library.upsert_book("k", "Kitap", "u2", "B2", 2)
    assert library.get_book("k")["style_note"] == "kalıcı not"


# ---------- translate._tail_words ----------

def test_tail_words_son_kelimeleri_alir():
    assert translate._tail_words("bir iki üç dört beş", 2) == "dört beş"


def test_tail_words_metin_kisaysa_tamamini_verir():
    assert translate._tail_words("tek", 10) == "tek"
    assert translate._tail_words("", 5) == ""
    assert translate._tail_words(None, 5) == ""


# ---------- uçtan uca: pipeline bağlamı VE üslup notunu translate'e geçirir ----------

def test_pipeline_baglam_ve_uslubu_translate_e_gecirir(monkeypatch):
    yakalanan = {}

    def sahte_translate(text, api_key=None, glossary=None, **kw):
        yakalanan.update(kw)
        return {"translation": "ç", "source": None, "detected_names": [], "chunk_count": 1}

    def sahte_fetch(url, priority="interactive", ticket=None, **kw):
        return {
            "book_slug": "k", "book_title": "Kitap", "title": "B2", "chapter_no": 2,
            "text": "English text.", "next_url": None, "prev_url": "u1",
        }

    _bolum("u1", "k", 1, "Önceki bölümün Türkçe sonu.")
    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    library.set_style_note("k", "Ağır ve edebî anlatım.")
    monkeypatch.setattr(pipeline, "fetch_chapter", sahte_fetch)
    monkeypatch.setattr(pipeline, "translate_chapter", sahte_translate)

    pipeline.get_or_translate("u2", "anahtar")

    assert yakalanan["style_note"] == "Ağır ve edebî anlatım."
    assert yakalanan["prev_context"] == "Önceki bölümün Türkçe sonu."


def test_pipeline_uslup_notu_yokken_bos_gecer(monkeypatch):
    """Not yazılmamış kitapta prompt'a boş string gider — None sızıp patlamaz."""
    yakalanan = {}

    def sahte_translate(text, api_key=None, glossary=None, **kw):
        yakalanan.update(kw)
        return {"translation": "ç", "source": None, "detected_names": [], "chunk_count": 1}

    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: {
        "book_slug": "yeni", "book_title": "Y", "title": "B1", "chapter_no": 1,
        "text": "t", "next_url": None, "prev_url": None,
    })
    monkeypatch.setattr(pipeline, "translate_chapter", sahte_translate)

    pipeline.get_or_translate("y1", "anahtar")

    assert yakalanan["style_note"] == ""
    assert yakalanan["prev_context"] == ""


# ---------- API uçları ----------

def test_style_api_yaz_oku(monkeypatch):
    import server
    from fastapi.testclient import TestClient

    library.upsert_book("k", "Kitap", "u1", "B1", 1)
    c = TestClient(server.app)
    assert c.get("/api/book/k/style").json()["note"] == ""
    r = c.post("/api/book/k/style", json={"note": "Kısa cümleler."})
    assert r.status_code == 200 and r.json()["note"] == "Kısa cümleler."
    assert c.get("/api/book/k/style").json()["note"] == "Kısa cümleler."


def test_style_api_bilinmeyen_kitap_404():
    import server
    from fastapi.testclient import TestClient

    r = TestClient(server.app).post("/api/book/yok/style", json={"note": "x"})
    assert r.status_code == 404


def test_style_api_alias_kanonige_yazar():
    """Birleştirilmiş kitapta not kanonik slug'a yazılmalı (bölüm/sözlükle aynı kural)."""
    import server
    from fastapi.testclient import TestClient

    library.upsert_book("kanonik", "Kitap", "u1", "B1", 1)
    library.set_alias("eski-slug", "kanonik")
    c = TestClient(server.app)
    assert c.post("/api/book/eski-slug/style", json={"note": "Not."}).status_code == 200
    assert library.get_book("kanonik")["style_note"] == "Not."
