"""Sözlük kaydının KÖKENİ: hangi bölüm, hangi cümle.

Kullanıcı isteği (2026-09-10): "sözlüğe eklenen kelimelerin hangi bölüm ve
cümleden eklendiğini görmek ve o bölüme gidebilmek istiyorum."

`first_chapter` (bölüm no) zaten vardı ama tek başına yetmiyordu: sözlük kaydı
prompt'ta KURAL olarak uygulanıyor ve garip bir karşılık görüldüğünde "bu nereden
geldi" sorusu ancak kaydın çıktığı CÜMLE ile cevaplanabiliyor. Bölüme gitmek için
ayrı bir URL sütunu YOK — bölüm numarası önbellekteki bölüm listesiyle eşleşiyor
ve ikinci bir kaynak, iki kaydın zamanla ayrışması demekti.
"""
import pytest

from core import glossary, translate


def test_cumle_bul_terimin_gectigi_cumleyi_dondurur():
    metin = ("Sunny kapıyı açtı. Ore İmparatorluğu'nun sancağı rüzgârda "
             "dalgalanıyordu. Sonra sessizlik oldu.")
    assert "sancağı" in translate.cumle_bul(metin, "Ore İmparatorluğu")


def test_cumle_bul_terim_yoksa_None():
    assert translate.cumle_bul("Sunny kapıyı açtı.", "Nephis") is None


def test_cumle_bul_YAZIM_VARYANTINI_da_yakalar():
    """Terim eşleştirme zaten varyanta toleranslı (`_term_regex`); köken cümlesi
    de aynı ölçütü kullanmalı, yoksa kayıtlı terim için cümle bulunamazdı."""
    metin = "Karanlıkta Ore-İmparatorluğu askerleri belirdi."
    assert translate.cumle_bul(metin, "Ore İmparatorluğu") is not None


def test_merge_terms_kaynak_cumleyi_saklar():
    glossary.merge_terms("kitap", {"Nephis": "Nephis"},
                         cumleler={"Nephis": "Nephis kılıcını çekti."},
                         chapter_no=12)
    r = next(x for x in glossary.get_glossary_rows("kitap") if x["source"] == "Nephis")
    assert r["kaynak_cumle"] == "Nephis kılıcını çekti."
    assert r["first_chapter"] == 12


def test_set_term_kaynak_cumleyi_KORUR():
    """Okuyucunun çevrimdışı kuyruğu yalnız {source, target} gönderir. Karşılık
    düzeltmek kökeni silmemeli — `kosul` ve `first_chapter` ile aynı tuzak."""
    glossary.merge_terms("kitap", {"Nephis": "Nephis"},
                         cumleler={"Nephis": "Nephis kılıcını çekti."}, chapter_no=12)
    glossary.set_term("kitap", "Nephis", "Nephis (Kız)")
    r = next(x for x in glossary.get_glossary_rows("kitap") if x["source"] == "Nephis")
    assert r["kaynak_cumle"] == "Nephis kılıcını çekti."
    assert r["target"] == "Nephis (Kız)"


def test_kaynak_cumle_ILK_kaydi_korur():
    """Terim sonraki bölümlerde tekrar geçince köken cümlesi DEĞİŞMEMELİ:
    'ilk nerede gördük' sorusunun cevabı sabit kalmalı."""
    glossary.merge_terms("kitap", {"Sunny": "Sunny"},
                         cumleler={"Sunny": "İlk cümle."}, chapter_no=3)
    glossary.merge_terms("kitap", {"Sunny": "Sunny"},
                         cumleler={"Sunny": "Çok sonraki cümle."}, chapter_no=90)
    r = next(x for x in glossary.get_glossary_rows("kitap") if x["source"] == "Sunny")
    assert r["kaynak_cumle"] == "İlk cümle."
    assert r["first_chapter"] == 3


def test_set_kaynak_cumle_YALNIZ_bosa_yazar():
    """Geriye dönük doldurma mevcut kökeni EZMEMELİ: sonradan bulunan bir geçiş,
    'ilk nerede gördük' cevabını değiştirmemeli."""
    glossary.merge_terms("kitap", {"Sunny": "Sunny"},
                         cumleler={"Sunny": "İlk cümle."}, chapter_no=3)
    assert glossary.set_kaynak_cumle("kitap", "Sunny", "Sonradan bulunan.") is False
    glossary.merge_terms("kitap", {"Nephis": "Nephis"}, chapter_no=4)
    assert glossary.set_kaynak_cumle("kitap", "Nephis", "Sonradan bulunan.") is True
    r = {x["source"]: x for x in glossary.get_glossary_rows("kitap")}
    assert r["Sunny"]["kaynak_cumle"] == "İlk cümle."
    assert r["Nephis"]["kaynak_cumle"] == "Sonradan bulunan."
