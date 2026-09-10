"""Çeviri kalitesi eklentisi: bölümler arası bağlam taşıma.

Kitap başına ÜSLUP NOTU 2026-09-02'de kaldırıldı (kullanıcı kararı): hiçbir kitapta
yazılı değildi, yani her istekte prompt'a "(yok)" diye 36 token boşuna gidiyordu ve
okuyucudaki kutu ölü bir özellikti.

Ağa/Gemini'ye çıkmaz — bağlamın prompt'a KADAR taşındığını
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


# ---------- translate._tail_words ----------

def test_tail_words_son_kelimeleri_alir():
    assert translate._tail_words("bir iki üç dört beş", 2) == "dört beş"


def test_tail_words_metin_kisaysa_tamamini_verir():
    assert translate._tail_words("tek", 10) == "tek"
    assert translate._tail_words("", 5) == ""
    assert translate._tail_words(None, 5) == ""


# ---------- uçtan uca: pipeline bağlamı translate'e geçirir ----------

def test_pipeline_baglami_translate_e_gecirir(monkeypatch):
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
    monkeypatch.setattr(pipeline, "fetch_chapter", sahte_fetch)
    monkeypatch.setattr(pipeline, "translate_chapter", sahte_translate)

    pipeline.get_or_translate("u2", "anahtar")

    assert yakalanan["prev_context"] == "Önceki bölümün Türkçe sonu."


def test_pipeline_onceki_bolum_yokken_bos_gecer(monkeypatch):
    """İlk bölümde prompt'a boş string gider — None sızıp patlamaz."""
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

    assert yakalanan["prev_context"] == ""
