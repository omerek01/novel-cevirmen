"""4. aşama: inceleme kuyruğu, ret, terim türü, alternatif yazım, ek anlam.

Belge: "Onay, ret ve birleştirme kararlarını sakla; reddedilen aynı aday her
bölümde yeniden önerilmesin" · "kullanıcının onayladığı alternatif yazımlar;
benzer yazımları otomatik birleştirme" · "birden fazla anlamı ayrı kayıt olarak
temsil et" · terim türleri prompt'a ölçülmeden girmez.
"""
from __future__ import annotations

import pytest

from core import glossary, library, translate

KITAP = "ek-kitap"


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def _satir(source, kitap=KITAP):
    return {r["source"]: r for r in glossary.get_glossary_rows(kitap)}.get(source)


# ---------- inceleme ----------

def test_yeni_otomatik_kayit_incelemeye_girer_elle_ve_isim_turu():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 3, {"Great": "A Great beast."})
    glossary.merge_names(KITAP, ["Sunny"], "auto", 3)
    glossary.set_term(KITAP, "Mira", "Mira")
    assert _satir("Great")["inceleme"] == "bekliyor"
    assert _satir("Sunny")["tur"] == "kisi"
    assert _satir("Mira")["inceleme"] is None


def test_kullanici_duzeltmesi_incelemeyi_kapatir():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 3)
    glossary.set_term(KITAP, "Great", "Yüce")
    assert _satir("Great")["inceleme"] == "onaylandi"


def test_inceleme_listesi_nedenleriyle_eski_temiz_kayit_listede_yok():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 3)
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Temiz", "Temiz Karşılık")
    liste = {x["source"]: [n["tur"] for n in x["nedenler"]] for x in glossary.inceleme_listesi(KITAP)}
    assert liste["Great"] == ["yeni_otomatik"]
    assert "karsilik_cakismasi" in liste["Ore Empire"] and "yakin_yazim" in liste["Ore Empire"]
    assert "Temiz" not in liste
    # Çakışma önce gelir (belge: çakışan/belirsiz olanları öne çıkar).
    assert list(liste)[-1] == "Great"
    glossary.onayla(KITAP, "Great")
    assert "Great" not in {x["source"] for x in glossary.inceleme_listesi(KITAP)}


def test_onay_surumu_artirmaz():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 3)
    once = glossary.kitap_surumu(KITAP)
    glossary.onayla(KITAP, "Great")
    assert glossary.kitap_surumu(KITAP) == once and _satir("Great")["surum"] == 1


def test_red_kaydi_siler_ve_aday_bir_daha_eklenmez_red_kaldirilinca_eklenir():
    glossary.merge_terms(KITAP, {"Nightmare Spell": "Kabus Büyüsü"}, "auto", 1)
    silinen = glossary.reddet(KITAP, "Nightmare Spell")
    assert silinen["target"] == "Kabus Büyüsü"
    assert glossary.merge_terms(KITAP, {"NightmareSpell": "X"}, "auto", 2) == {}
    assert [r["source"] for r in glossary.red_listesi(KITAP)] == ["Nightmare Spell"]
    assert glossary.gecmis(KITAP, "Nightmare Spell")[0]["yol"] == "inceleme"
    assert glossary.reddi_kaldir(KITAP, "Nightmare Spell")
    assert glossary.merge_terms(KITAP, {"Nightmare Spell": "Kabus Büyüsü"}, "auto", 4)


# ---------- tür ----------

def test_tur_yazilir_taninmayan_yok_sayilir_surum_artmaz():
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.terimi_yaz(KITAP, "Saint", "Aziz", tur="rutbe", origin=None)
    s = _satir("Saint")
    assert s["tur"] == "rutbe" and s["surum"] == 1
    glossary.terimi_yaz(KITAP, "Saint", "Aziz", tur="uydurma", origin=None)
    assert _satir("Saint")["tur"] is None


def test_yedek_tur_ve_incelemeyi_tasir():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 3)
    glossary.terimi_yaz(KITAP, "Great", "Ulu", tur="rutbe", origin=None)
    yedek = glossary.disa_aktar(KITAP)
    glossary.ice_aktar("bos-kitap", yedek["kayitlar"], "mevcut")
    s = _satir("Great", "bos-kitap")
    assert s["tur"] == "rutbe" and s["inceleme"] == "bekliyor"


# ---------- alternatif yazım ----------

def test_alternatif_yazim_ceviri_sozlugune_girer_ekrana_girmez_ve_aday_olmaz():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_kosul(KITAP, "Orc Empire", "yalnız ırk adı")
    assert glossary.yazim_ekle(KITAP, "Orc Empire", "Ore Empire") == ["Ore Empire"]
    assert glossary.ceviri_sozlugu(KITAP)["Ore Empire"] == "Ork İmparatorluğu"
    assert glossary.ceviri_kosullari(KITAP)["Ore Empire"] == "yalnız ırk adı"
    assert "Ore Empire" not in glossary.get_glossary(KITAP)
    assert glossary.merge_terms(KITAP, {"OreEmpire": "Cevher İmparatorluğu"}, "auto", 9) == {}
    s = _satir("Orc Empire")
    assert s["surum"] == 3  # ekle (1) + koşul (2) + yazım (3)
    assert glossary.gecmis(KITAP, "Orc Empire")[0]["sonraki"]["yazim_eklendi"] == "Ore Empire"


def test_alternatif_yazim_uyum_denetiminde_de_olculur():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.yazim_ekle(KITAP, "Orc Empire", "Ore Empire")
    ihlal = translate.sozluk_ihlalleri(
        glossary.ceviri_sozlugu(KITAP), "The Ore Empire marched.", "Ore Empire yürüdü.",
        glossary.ceviri_kosullari(KITAP),
    )
    assert "Ore Empire" in ihlal


def test_yazim_cakismalari_reddedilir():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(KITAP, "Ore", "Cevher")
    with pytest.raises(glossary.YazimCakismasi):
        glossary.yazim_ekle(KITAP, "Orc Empire", "OrcEmpire")  # kendi yazımı
    with pytest.raises(glossary.YazimCakismasi):
        glossary.yazim_ekle(KITAP, "Orc Empire", "Ore")  # ayrı kayıt
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.yazim_ekle(KITAP, "Orc Empire", "Ork Empire")
    with pytest.raises(glossary.YazimCakismasi):
        glossary.yazim_ekle(KITAP, "Saint", "Ork-Empire")  # başka kayda bağlı


def test_yazim_silinir_ve_kayit_silinince_yazimlar_da_gider():
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.yazim_ekle(KITAP, "Orc Empire", "Ore Empire")
    assert glossary.yazim_sil(KITAP, "Orc Empire", "Ore Empire") == []
    glossary.yazim_ekle(KITAP, "Orc Empire", "Ore Empire")
    glossary.delete_term(KITAP, "Orc Empire")
    assert glossary.ekler(KITAP) == {}


def test_reddedilen_aday_alternatif_yazim_olunca_red_duser():
    glossary.merge_terms(KITAP, {"Ore Empire": "Cevher İmparatorluğu"}, "auto", 1)
    glossary.reddet(KITAP, "Ore Empire")
    glossary.set_term(KITAP, "Orc Empire", "Ork İmparatorluğu")
    glossary.yazim_ekle(KITAP, "Orc Empire", "Ore Empire")
    assert glossary.red_listesi(KITAP) == []


# ---------- ek anlam ----------

def test_ek_anlam_kosulsuz_reddedilir():
    glossary.set_term(KITAP, "Great", "Ulu")
    with pytest.raises(ValueError):
        glossary.anlamlari_yaz(KITAP, "Great", [{"target": "Harika", "kosul": ""}])


def test_ek_anlam_kosula_islenir_denetimden_cikar_prompta_aciklamayla_girer():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "Kabus Yaratığı rütbesi")
    glossary.anlamlari_yaz(KITAP, "Great", [{"target": "Harika", "kosul": "gündelik ünlem"}])
    kosullar = glossary.ceviri_kosullari(KITAP)
    assert kosullar["Great"] == 'Kabus Yaratığı rütbesi ; BAŞKA ANLAM: "Harika" — gündelik ünlem'
    sozluk = glossary.ceviri_sozlugu(KITAP)
    # Hangi anlamın geçerli olduğu ölçülemez: deterministik denetim DIŞINDA.
    assert translate.sozluk_ihlalleri(sozluk, "Great!", "Great!", kosullar) == {}
    prompt = translate._build_user_prompt(["Great! A Great beast."], sozluk, "", kosullar)
    assert 'BAŞKA ANLAM: "Harika"' in prompt
    assert "birden çok kayıtlı karşılığı vardır" in prompt


def test_ek_anlam_yoksa_prompt_degismez():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "rütbe")
    prompt = translate._build_user_prompt(
        ["A Great beast."], glossary.ceviri_sozlugu(KITAP), "", glossary.ceviri_kosullari(KITAP)
    )
    assert translate.EK_ANLAM_ISARETI not in prompt
    assert "birden çok kayıtlı karşılığı" not in prompt


def test_isaret_iki_modulde_ayni():
    assert glossary.EK_ANLAM_ISARETI == translate.EK_ANLAM_ISARETI


def test_ek_anlam_surum_gecmis_ve_aynisi_yazilinca_artmaz():
    glossary.set_term(KITAP, "Great", "Ulu")
    anlamlar = [{"target": "Harika", "kosul": "gündelik ünlem"}]
    glossary.anlamlari_yaz(KITAP, "Great", anlamlar)
    glossary.anlamlari_yaz(KITAP, "Great", anlamlar)
    assert _satir("Great")["surum"] == 2
    assert glossary.gecmis(KITAP, "Great")[0]["islem"] == "anlam"
    with pytest.raises(glossary.SurumCakismasi):
        glossary.anlamlari_yaz(KITAP, "Great", [], taban_surum=1)


# ---------- birleştirme / silme ----------

def test_birlestirme_yazim_anlam_ve_reddi_tasir_kitap_silme_temizler():
    glossary.set_term("kaynak-k", "Great", "Ulu")
    glossary.yazim_ekle("kaynak-k", "Great", "Grate")
    glossary.anlamlari_yaz("kaynak-k", "Great", [{"target": "Harika", "kosul": "ünlem"}])
    glossary.merge_terms("kaynak-k", {"Bad": "Kötü"}, "auto", 1)
    glossary.reddet("kaynak-k", "Bad")
    library.upsert_book("kaynak-k", "K", "https://k/1", "c", 1)
    library.upsert_book(KITAP, "H", "https://h/1", "c", 1)
    library.merge_books("kaynak-k", KITAP)
    assert glossary.ekler(KITAP)["Great"] == {
        "yazimlar": ["Grate"], "anlamlar": [{"target": "Harika", "kosul": "ünlem"}],
    }
    assert [r["source"] for r in glossary.red_listesi(KITAP)] == ["Bad"]
    library.delete_book(KITAP)
    assert glossary.ekler(KITAP) == {} and glossary.red_listesi(KITAP) == []


# ---------- uçlar ----------

def test_uclar():
    c = _client()
    c.post(f"/api/book/{KITAP}/glossary", json={"source": "Orc Empire", "target": "Ork İmparatorluğu",
                                               "tur": "orgut"})
    assert _satir("Orc Empire")["tur"] == "orgut"
    r = c.post(f"/api/book/{KITAP}/glossary/yazim", json={"source": "Orc Empire", "yazim": "Ore Empire"})
    assert r.status_code == 200 and r.json()["yazimlar"] == ["Ore Empire"]
    assert r.json()["kayit"]["surum"] == 2
    assert c.post(f"/api/book/{KITAP}/glossary/yazim",
                  json={"source": "Orc Empire", "yazim": "OrcEmpire"}).status_code == 400
    assert c.post(f"/api/book/{KITAP}/glossary/yazim",
                  json={"source": "Yok", "yazim": "X"}).status_code == 404
    veri = c.get(f"/api/book/{KITAP}/glossary").json()
    assert veri["ekler"]["Orc Empire"]["yazimlar"] == ["Ore Empire"]
    r = c.delete(f"/api/book/{KITAP}/glossary/yazim", params={"source": "Orc Empire", "yazim": "Ore Empire"})
    assert r.json()["yazimlar"] == []

    r = c.put(f"/api/book/{KITAP}/glossary/anlamlar",
              json={"source": "Orc Empire", "anlamlar": [{"target": "Ork", "kosul": ""}]})
    assert r.status_code == 400
    r = c.put(f"/api/book/{KITAP}/glossary/anlamlar",
              json={"source": "Orc Empire", "anlamlar": [{"target": "Ork", "kosul": "kısaltma"}],
                    "taban_surum": 3})
    assert r.status_code == 200 and r.json()["anlamlar"] == [{"target": "Ork", "kosul": "kısaltma"}]

    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 1)
    liste = c.get(f"/api/book/{KITAP}/glossary/review").json()
    assert [x["source"] for x in liste["liste"]] == ["Great"]
    assert c.post(f"/api/book/{KITAP}/glossary/review", json={"source": "Great", "karar": "x"}).status_code == 400
    r = c.post(f"/api/book/{KITAP}/glossary/review", json={"source": "Great", "karar": "reddet"})
    assert r.json()["silinen"]["target"] == "Ulu"
    assert c.get(f"/api/book/{KITAP}/glossary/review").json()["red"][0]["source"] == "Great"
    assert c.delete(f"/api/book/{KITAP}/glossary/red", params={"source": "Great"}).json()["ok"]


def test_stil_uyarisi_yalniz_kaynagindan_ayrisan_uyeyi_isaretler():
    glossary.set_term(KITAP, "dormant beast", "uykudaki mahluk")
    glossary.set_term(KITAP, "bone beast", "kemik mahluk")
    glossary.set_term(KITAP, "beast", "Mahluk")  # küçük harfli kaynak, büyük harfli karşılık
    liste = {x["source"]: x for x in glossary.inceleme_listesi(KITAP)}
    stil = {k for k, x in liste.items() if any(n["tur"] == "kardes_tutarsizligi" for n in x["nedenler"])}
    assert stil == {"beast"}
