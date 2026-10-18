"""Sözlük karşılığı değişince eski bölümleri yeniden çevirmeden yerinde güncelleme
(`pipeline.yerinde_guncelle`, `POST /api/book/{slug}/glossary/yerinde`).

Metinler uydurmadır; dilbilgisi kuralları `test_sozluk_yerinde.py`de sınanır, burada
akış: önizleme yazmaz, uygulama arşive düşer, damga güncellenir, seçim uyulur."""
from __future__ import annotations

import json

from core import cache, glossary, library, pipeline

KITAP = "gumus-kule"
EN = [
    "Kaan lit the lantern.",
    "The bell of the Silver Tower rang twice.",
    "Nobody remembered the tower.",
]
TR = [
    "Kaan feneri yaktı.",
    "Gümüş Kulenin çanı iki kez çaldı.",
    "Kimse kuleyi hatırlamıyordu.",
]


def _bolum(no, tr=TR, en=EN, damga=None):
    url = f"https://ornek.test/{KITAP}/chapter-{no}"
    cache.save_chapter(url, {
        "book_slug": KITAP, "book_title": "Gumus Kule", "title": f"Chapter {no}",
        "chapter_no": no, "translation": "\n\n".join(tr), "source": "\n\n".join(en),
        "next_url": None, "prev_url": None, "detected_names": [], "chunk_count": 1,
        "sozluk_damgasi": damga,
    })
    library.upsert_book(KITAP, "Gumus Kule", url, f"Chapter {no}", no)
    return url


def _karsilik_degisti(eski="Gümüş Kule", yeni="Ak Kule"):
    glossary.set_term(KITAP, "Silver Tower", eski)
    glossary.set_term(KITAP, "Silver Tower", yeni)


def _ceviri(url):
    return cache.get_chapter(url)["translation"]


def test_onizleme_sayar_ama_yazmaz():
    url = _bolum(1)
    _karsilik_degisti()
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower")
    assert sonuc["degisen"] == 1 and sonuc["belirsiz"] == 0
    b = sonuc["bolumler"][0]
    assert b["url"] == url and b["degisen"] == 1
    assert b["ornek_once"] == "Gümüş Kulenin çanı iki kez çaldı."
    assert b["ornek_sonra"] == "Ak Kule'nin çanı iki kez çaldı."
    assert _ceviri(url) == "\n\n".join(TR)
    assert cache.arsiv_listesi(url) == []


def test_uygulama_yazar_arsive_dusurur_zamani_tazeler():
    url = _bolum(1)
    once_zaman = cache.get_chapter(url)["ceviri_zamani"]
    _karsilik_degisti()
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    b = sonuc["bolumler"][0]
    assert b["yazildi"] is True and b["arsiv_id"]
    metin = _ceviri(url).split("\n\n")
    # Yalnız terimin geçtiği paragraf değişir; sıradan "kule" (kaynakta terim yok) kalır.
    assert metin == [TR[0], "Ak Kule'nin çanı iki kez çaldı.", TR[2]]
    assert [a["id"] for a in cache.arsiv_listesi(url)] == [b["arsiv_id"]]
    assert cache.get_chapter(url)["ceviri_zamani"] > once_zaman
    # Arşivden dönüş eski metni birebir verir.
    assert cache.arsivden_geri_yukle(url, b["arsiv_id"])
    assert _ceviri(url) == "\n\n".join(TR)


def test_ikinci_uygulama_bir_sey_degistirmez():
    url = _bolum(1)
    _karsilik_degisti()
    pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert sonuc["degisen"] == 0 and sonuc["bolumler"] == []
    assert len(cache.arsiv_listesi(url)) == 1


def test_secilen_bolumler_disina_dokunmaz():
    u1, u2 = _bolum(1), _bolum(2)
    _karsilik_degisti()
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", urls=[u2], uygula=True)
    assert [b["url"] for b in sonuc["bolumler"]] == [u2]
    assert _ceviri(u1) == "\n\n".join(TR)
    assert "Ak Kule'nin" in _ceviri(u2)


def test_damga_tum_gecisler_degisince_guncellenir():
    url = _bolum(1, damga={"Silver Tower": "Gümüş Kule", "Kaan": "Kaan"})
    _karsilik_degisti()
    pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert cache.get_chapter(url)["sozluk_damgasi"] == {"Silver Tower": "Ak Kule", "Kaan": "Kaan"}


def test_belirsiz_gecis_kalirsa_damga_eski_kalir():
    # İngilizcede bir geçiş, Türkçede iki: hangisinin terim olduğu bilinmez, ikisi de kalır.
    # Öteki paragraf değişir: bölüm yazılır ama damga eski kalır (bölümde eski karşılık
    # hâlâ var, künye farkı göstermeye devam etmeli).
    tr = [TR[0], "Gümüş Kulenin çanı Gümüş Kuleye ulaştı.", "Gümüş Kuleyi gördüler."]
    en = [EN[0], "The bell of the Silver Tower reached far.", "They saw the Silver Tower."]
    url = _bolum(1, tr=tr, en=en, damga={"Silver Tower": "Gümüş Kule"})
    _karsilik_degisti()
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert sonuc["degisen"] == 1 and sonuc["belirsiz"] == 2
    assert _ceviri(url).split("\n\n") == [tr[0], tr[1], "Ak Kule'yi gördüler."]
    assert cache.get_chapter(url)["sozluk_damgasi"] == {"Silver Tower": "Gümüş Kule"}


def test_kaynakta_terim_olmayan_gecis_belirsiz_sayilmaz():
    # İngilizcede terim yoksa Türkçedeki sözcük bu terimin karşılığı değildir: sayılmaz,
    # dokunulmaz, damgayı da bekletmez.
    tr = [TR[0], "Gümüş Kulenin çanı iki kez çaldı.", "Gümüş Kule bir şarkıydı."]
    en = [EN[0], EN[1], "Silver was the song."]
    url = _bolum(1, tr=tr, en=en, damga={"Silver Tower": "Gümüş Kule"})
    _karsilik_degisti()
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert sonuc["degisen"] == 1 and sonuc["belirsiz"] == 0
    assert _ceviri(url).split("\n\n")[2] == tr[2]
    assert cache.get_chapter(url)["sozluk_damgasi"] == {"Silver Tower": "Ak Kule"}


def test_eski_karsilik_yenisinin_parcasiysa_atlanir():
    # "Kule" -> "Ak Kule": "Ak Kule" içindeki "Kule" yeniden değiştirilirse "Ak Ak Kule" olurdu.
    tr = [TR[0], "Ak Kulenin çanı iki kez çaldı.", TR[2]]
    url = _bolum(1, tr=tr)
    _karsilik_degisti(eski="Kule", yeni="Ak Kule")
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert sonuc["degisen"] == 0
    assert _ceviri(url) == "\n\n".join(tr)


def test_okurken_degisen_bolum_ezilmez(monkeypatch):
    # Hesapla yazma arasında bölüm değişirse (yeniden çeviri bitti) yazılmaz.
    url = _bolum(1)
    _karsilik_degisti()
    gercek = cache.kaynak_bolumleri

    def eski_kopya(slug):
        bolumler = gercek(slug)
        cache.set_translation(url, "\n\n".join([TR[0], "Yeni çeviri geldi.", TR[2]]))
        return bolumler

    monkeypatch.setattr(cache, "kaynak_bolumleri", eski_kopya)
    sonuc = pipeline.yerinde_guncelle(KITAP, "Silver Tower", uygula=True)
    assert sonuc["bolumler"][0]["yazildi"] is False
    assert "Yeni çeviri geldi." in _ceviri(url)


def test_uc_onizleme_ve_uygulama():
    from fastapi.testclient import TestClient

    import server

    url = _bolum(1)
    _karsilik_degisti()
    with TestClient(server.app) as client:
        r = client.post(f"/api/book/{KITAP}/glossary/yerinde",
                        json={"source": "Silver Tower"})
        assert r.status_code == 200 and r.json()["degisen"] == 1
        assert _ceviri(url) == "\n\n".join(TR)
        r = client.post(f"/api/book/{KITAP}/glossary/yerinde",
                        json={"source": "Silver Tower", "urls": [url], "uygula": True})
        veri = r.json()
        assert veri["bolumler"][0]["yazildi"] is True
        assert veri["bolumler"][0]["ceviri_zamani"]
        json.dumps(veri)  # yanıt JSON'a dökülebilmeli
    assert "Ak Kule'nin" in _ceviri(url)


def test_uc_bos_kaynak_reddedilir():
    from fastapi.testclient import TestClient

    import server

    with TestClient(server.app) as client:
        assert client.post(f"/api/book/{KITAP}/glossary/yerinde",
                           json={"source": " "}).status_code == 400
