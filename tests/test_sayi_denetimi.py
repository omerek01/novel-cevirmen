"""Sayı/ölçek denetimi (Faz A3). Cümleler uydurmadır; her sahte sınıf kalibrasyondan gelir."""
import pytest

from core.sayi_denetimi import degerler, paragraf_uyumsuzluklari, uyumsuzluk


@pytest.mark.parametrize("en, tr", [
    ("Two thousand sailors stood there.", "İki bin denizci orada duruyordu."),
    ("Two thousand sailors stood there.", "2.000 denizci orada duruyordu."),
    ("It cost 2,500 coins.", "2.500 sikkeye mal oldu."),
    ("It cost 2,500 coins.", "2,500 sikkeye mal oldu."),            # İngilizce ayırıcı korunmuş
    ("It cost 2,500 coins.", "İki bin beş yüz sikkeye mal oldu."),
    ("He waited for a hundred years.", "Yüz yıl bekledi."),
    ("There were more than a hundred.", "Yüzden fazlaydı."),          # ekli ölçek sözcüğü
    ("Ten billion people lived there.", "On milyardan fazla insan yaşıyordu."),
    ("He had three hundred and forty.", "Üç yüz kırka ulaşmıştı."),    # ekli birler, dizi içinde
    ("One hundred and thirty-two, exactly.", "Tam olarak yüz otuz iki."),  # tireli sayı
    ("He repeated it a thousand times.", "Bunu binlerce kez tekrarladı."),  # abartı
    ("Thousands of creatures came.", "Binlerce yaratık geldi."),
    ("Hundreds of them fell.", "Yüzlercesi düştü."),
    ("Hundreds of them fell.", "Aşağı yukarı 300 tanesi düştü."),
    ("A dozen meters away.", "Birkaç metre ötede."),                  # dozen: yaklaşık
    ("One of them laughed.", "Biri güldü."),
    ("He learned the Thousand Transformations.", "Bin Dönüşüm'ü öğrendi."),
    ("The ratio was 1.5 to one.", "Oran bire 1,5 idi."),
    ("It cost two thousand, five hundred gold.", "İki bin beş yüz altın tuttu."),  # binlik virgül
    ("A 5*25-yard field.", "5x25 metrelik bir alan."),                # rakam önünde harf
    ("About 130 million people.", "Yaklaşık yüz otuz milyon kişi."),  # karışık yazım
    ("Three billion of us.", "3 milyarımız."),                        # uzun iyelik eki
    ("It broke into a thousand pieces.", "Bin bir parçaya bölündü."),  # "bin bir" kalıbı
    ("It broke into a thousand pieces.", "Binbir parçaya bölündü."),
    ("Sixty-seventy million souls.", "Altmış yetmiş milyon ruh."),     # aralık toplanmaz
])
def test_uyumlu(en, tr):
    assert uyumsuzluk(en, tr) == []


@pytest.mark.parametrize("en, tr, eksik", [
    ("Two thousand sailors stood there.", "İki yüz denizci orada duruyordu.", ["2.000"]),
    ("It cost 2,500 coins.", "250 sikkeye mal oldu.", ["2.500"]),
    ("Thousands of creatures came.", "Yüzlerce yaratık geldi.", ["binlerce"]),
    ("Millions died.", "Pek çok kişi öldü.", ["milyonlarca"]),
    ("Two thousand sailors stood there.", "Binlerce denizci orada duruyordu.", ["2.000"]),
])
def test_olcek_kaymasi_yakalanir(en, tr, eksik):
    assert uyumsuzluk(en, tr) == eksik


def test_ekli_birler_dizi_disinda_sayi_sayilmaz():
    # "onu" zamirdir, "on" (10) değil; "bina" bin değil
    assert degerler("Onu binanın önünde gördü.", "tr") == (set(), set())


def test_ardisik_basamak_sayilari_toplanmaz():
    assert 200.0 not in degerler("One one hundred.", "en")[0]
    assert 100.0 in degerler("One one hundred.", "en")[0]


def test_noktalama_diziyi_boler():
    assert 100.0 in degerler("Ten, a hundred, it did not matter.", "en")[0]


def test_paragraf_eslemesi_hizasizda_olcmez():
    en = ["Two thousand sailors.", "Nothing."]
    tr = ["İki yüz denizci.", "Hiçbir şey."]
    assert paragraf_uyumsuzluklari(tr, en) == {0: ["2.000"]}
    assert paragraf_uyumsuzluklari(tr[:1], en) == {}


# ---- çeviri akışına bağlantı (onarım kabul kapısı + künye) ----
from pathlib import Path  # noqa: E402

from core import cache, translate  # noqa: E402


def _onar(monkeypatch, yeni):
    def sahte(cf, models, deneme, en_paras, indeksler, *a, **k):
        for i in indeksler:
            deneme[i] = yeni
        return True
    monkeypatch.setattr(translate, "_paragraflari_yeniden_cevir", sahte)
    en = ["Two thousand sailors stood on the deck, waiting silently."]
    tr = ["İki yüz denizci güvertede durmuş, sessizce bekliyordu."]
    translate._sayiyi_onar(None, (), tr, en, {0: ["2.000"]}, {}, {}, set(), {}, None)
    return tr[0]


def test_sayi_onarimi_dogrulanirsa_kabul(monkeypatch):
    assert _onar(monkeypatch, "İki bin denizci güvertede durmuş, sessizce bekliyordu.").startswith("İki bin")


def test_sayi_onarimi_degeri_getirmezse_reddedilir(monkeypatch):
    assert _onar(monkeypatch, "Yüzlerce denizci güvertede durmuş, sessizce bekliyordu.").startswith("İki yüz")


def test_sayi_onarimi_kisaltirsa_reddedilir(monkeypatch):
    assert _onar(monkeypatch, "İki bin denizci.").startswith("İki yüz")


def test_sayi_kunyesi_saklanir_ve_iki_noktada_tasinir():
    url = "https://ornek.test/kitap/bolum-2"
    cache.save_chapter(url, {"book_slug": "k", "translation": "x", "sayi_uyumsuzlugu": {"3": ["2.000"]}})
    assert cache.get_chapter(url)["sayi_uyumsuzlugu"] == {"3": ["2.000"]}
    kaynak = (Path(__file__).resolve().parent.parent / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert kaynak.count('"sayi_uyumsuzlugu": result.get("sayi_uyumsuzlugu")') == 2
