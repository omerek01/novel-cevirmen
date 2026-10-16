"""Karşılık sapması (Faz A2): terim çevrilmiş ama kayıttan FARKLI karşılıkla.

Cümleler uydurmadır; kalibrasyonda elenen üç sahte sınıf (sıradan kullanım, fiil
kullanımı, uzun kayıt içinde geçiş) ayrı ayrı tutulur."""
from pathlib import Path

from core import cache, translate

SOZ = {
    "Hollow Mountain": "Oyuk Dağı",
    "Black Knight": "Kara Şövalye",
    "Master": "Efendi",
    "Battle Master": "Savaş Ustası",
    "Awakened": "Uyanmış",
    "Lost": "Kayıp",
    "Stone Saint": "Stone Saint",
    "Mira": "Mira",
}


def sapma(en, tr, soz=SOZ, kosullar=None):
    return translate.karsilik_sapmalari(soz, en, tr, kosullar)


def test_farkli_turkce_karsilik_yakalanir():
    assert sapma("They climbed the Hollow Mountain at dawn.",
                 "Şafakta Kovan Dağları'na tırmandılar.") == {"Hollow Mountain": "Oyuk Dağı"}


def test_kayitli_karsilik_cekimli_gecerse_temiz():
    assert sapma("They climbed the Hollow Mountain at dawn.",
                 "Şafakta Oyuk Dağı'na tırmandılar.") == {}
    assert sapma("The Black Knight waited.", "KARA ŞÖVALYE'nin bekleyişi sürdü.") == {}


def test_ingilizce_kalan_terim_burada_sayilmaz():
    # O sınıf sozluk_ihlalleri'nin; iki bayrak aynı geçişi iki kez saymaz.
    assert sapma("The Black Knight waited.", "Black Knight bekledi.") == {}


def test_uzun_kayit_icindeki_gecis_sayilmaz():
    assert sapma("It had the [Battle Master] attribute.", "[Savaş Ustası] niteliği vardı.") == {}


def test_fiil_kullanimi_sayilmaz():
    assert sapma("After he had Awakened, nothing was the same.",
                 "Uyandıktan sonra hiçbir şey aynı değildi.") == {}


def test_tek_sozcuk_siradan_kullanim_ve_cumle_basi_sayilmaz():
    assert sapma("He felt lost in the crowd.", "Kalabalıkta kendini yitik hissetti.") == {}
    assert sapma("Lost, he wandered.", "Yolunu yitirmiş hâlde dolaştı.") == {}


def test_tek_sozcuk_cumle_ortasinda_ad_olarak_sayilir():
    assert sapma("They bowed to the Master quietly.",
                 "Usta'ya sessizce eğildiler.") == {"Master": "Efendi"}


def test_ingilizce_korunan_cok_sozcuklu_ad_turkcelesirse_yakalanir():
    assert sapma("He looked at the Stone Saint.", "Taş Aziz'e baktı.") == {"Stone Saint": "Stone Saint"}
    assert sapma("He looked at the Stone Saint.", "Stone Saint'e baktı.") == {}


def test_tek_sozcuklu_korunan_ad_zamirle_anilabilir():
    assert sapma("He saw that Mira was tired.", "Onun yorgun olduğunu gördü.") == {}


def test_kosullu_kayit_denetlenmez():
    assert sapma("They climbed the Hollow Mountain.", "Kovan Dağları'na tırmandılar.",
                 kosullar={"Hollow Mountain": "yalnız eski adıyla"}) == {}


def test_paragraf_eslemesi():
    en = ["The Black Knight waited.", "They climbed the Hollow Mountain."]
    tr = ["Kara Şövalye bekledi.", "Kovan Dağları'na tırmandılar."]
    assert translate.karsilik_sapmasi_paragraflari(SOZ, tr, en) == {1: {"Hollow Mountain": "Oyuk Dağı"}}
    assert translate.karsilik_sapmasi_paragraflari(SOZ, tr[:1], en) == {}  # hizasız: ölçülmez


def _onarim(monkeypatch, yeni_metin):
    def sahte(cf, models, deneme, en_paras, indeksler, *a, **k):
        for i in indeksler:
            deneme[i] = yeni_metin
        return True
    monkeypatch.setattr(translate, "_paragraflari_yeniden_cevir", sahte)
    en = ["Prologue line here.", "They climbed the Hollow Mountain at dawn, slowly and carefully."]
    tr = ["Giriş satırı.", "Şafakta Kovan Dağları'na yavaşça ve dikkatle tırmandılar."]
    sapmali = translate.karsilik_sapmasi_paragraflari(SOZ, tr, en)
    kalan = translate._sapmayi_onar(None, (), tr, en, sapmali, SOZ, {}, set(), {}, None)
    return tr, kalan


def test_onarim_yalniz_dogrulanirsa_kabul(monkeypatch):
    tr, kalan = _onarim(monkeypatch, "Şafakta Oyuk Dağı'na yavaşça ve dikkatle tırmandılar.")
    assert kalan == {} and "Oyuk Dağı" in tr[1]


def test_sapmayi_gidermeyen_onarim_reddedilir(monkeypatch):
    tr, kalan = _onarim(monkeypatch, "Şafakta Kovan Tepesi'ne yavaşça ve dikkatle tırmandılar.")
    assert 1 in kalan and "Kovan Dağları" in tr[1]


def test_kisaltan_onarim_reddedilir(monkeypatch):
    tr, kalan = _onarim(monkeypatch, "Oyuk Dağı'na çıktılar.")
    assert 1 in kalan and "Kovan Dağları" in tr[1]


def test_kunye_onbellekte_saklanir():
    url = "https://ornek.test/kitap/bolum-1"
    cache.save_chapter(url, {"book_slug": "k", "translation": "x", "karsilik_sapmasi": {"A": "B"}})
    assert cache.get_chapter(url)["karsilik_sapmasi"] == {"A": "B"}


def test_iki_uretim_noktasi_da_alani_tasir():
    kaynak = (Path(__file__).resolve().parent.parent / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert kaynak.count('"karsilik_sapmasi": result.get("karsilik_sapmasi")') == 2
