"""Özet kaynak bağları ve analiz adaylarının güvenli yerel kullanımı."""
import json
from types import SimpleNamespace

import pytest
from core import cache


def modul():
    from core import ceviri_baglam
    return ceviri_baglam


KAYNAK = "Sunny crossed the Ash Bridge. He joined the army campaign."


def veri():
    return {"ozet": [{"metin": "Sunny köprüyü geçti.", "paragraf": 0,
                       "alinti": "Sunny crossed the Ash Bridge."}],
            "terimler": [{"kaynak": "Ash Bridge", "hedef": "Kül Köprüsü", "tur": "yer",
                          "paragraf": 0, "alinti": "Sunny crossed the Ash Bridge."}]}


def yanit(v, bitis="STOP"):
    return SimpleNamespace(text=json.dumps(v, ensure_ascii=False),
                           candidates=[SimpleNamespace(finish_reason=bitis)])


def test_analiz_kaynak_kanitini_ve_ayri_gorevi_korur():
    m = modul(); cagrilar = []
    def uret(user, system, asama):
        cagrilar.append((json.loads(user), system, asama)); return yanit(veri()), "model"
    r = m.analiz(KAYNAK, {}, {}, {"ozet": []}, uret)
    assert r["ozet"][0]["alinti"] in KAYNAK
    assert r["terimler"][0]["kaynak"] == "Ash Bridge"
    assert cagrilar[0][2] == "bolum_analizi"
    assert cagrilar[0][0]["onceki_ozet"] == {"ozet": []}


@pytest.mark.parametrize("degistir", [
    lambda v: v["ozet"][0].update(alinti="gelecekteki olay"),
    lambda v: v["ozet"][0].update(paragraf=True),
    lambda v: v.update(ozet=v["ozet"] * 7),
])
def test_sahte_ve_sinir_disi_analiz_reddedilir(degistir):
    m = modul(); v = veri(); degistir(v)
    with pytest.raises(m.AnalizHatasi):
        m.analiz(KAYNAK, {}, {}, None, lambda *a: (yanit(v), "model"))


def test_kesik_yanit_ve_bos_ozet_kabul_edilmez():
    m = modul()
    for v, bitis in [(veri(), "MAX_TOKENS"), ({"ozet": [], "terimler": []}, "STOP")]:
        with pytest.raises(m.AnalizHatasi):
            m.analiz(KAYNAK, {}, {}, None, lambda *a: (yanit(v, bitis), "model"))


def test_yerel_aday_aktif_sozlugu_ezmez():
    m = modul(); v = veri()
    r = m.analiz(KAYNAK, {"Ash Bridge": "Kül Köprüsü"}, {}, None,
                lambda *a: (yanit(v), "model"))
    assert m.yerel_sozluk({"ash bridge": "Köz Köprüsü"}, r)["ash bridge"] == "Köz Köprüsü"
    assert len(m.yerel_sozluk({"ash bridge": "Köz Köprüsü"}, r)) == 1


def test_uretim_sadece_ceviri_ister_ozeti_metin_yerine_koymaz():
    m = modul(); r = m.analiz(KAYNAK, {}, {}, None, lambda *a: (yanit(veri()), "model"))
    user = m.baglam_metni(r, None)
    assert "Sunny köprüyü geçti" in user
    assert "kaynak" in m.STIL_TALIMATI.lower()
    assert "detected_terms" not in m.CEVIRI_CIKTI_TALIMATI
    assert '"translation"' in m.CEVIRI_CIKTI_TALIMATI


def kaydet(url, kitap, no, kaynak=KAYNAK):
    cache.save_chapter(url, {"book_slug": kitap, "chapter_no": no,
                             "source": kaynak, "translation": "Örnek çeviri."})


def test_onceki_kaynak_yanlis_kitap_ve_gelecegi_kullanmaz():
    kaydet("test://diger/2", "diger", 2)
    kaydet("test://kitap/4", "kitap", 4)
    kaydet("test://kitap/1", "kitap", 1)
    assert cache.onceki_kaynak("kitap", "test://diger/2", 3) is None
    assert cache.onceki_kaynak("kitap", "test://kitap/4", 3) is None
    kaydet("test://kitap/2", "kitap", 2)
    assert cache.onceki_kaynak("kitap", "test://diger/2", 3)["url"] == "test://kitap/2"
    assert cache.onceki_kaynak("kitap", None, None) is None


def test_ozet_kaynak_degisince_bayat_olarak_kullanilmaz():
    from core import ceviri_izleri as iz
    r = modul().dogrula(veri(), KAYNAK)
    iz.ozet_yaz("test://k/2", "kitap", 2, KAYNAK, r)
    assert iz.ozet_oku("test://k/2", "kitap", 2, KAYNAK)["ozet"] == r["ozet"]
    assert iz.ozet_oku("test://k/2", "kitap", 2, "Yeni kaynak.") is None
    assert iz.ozet_oku("test://k/2", "baska", 2, KAYNAK) is None
    assert iz.ozet_oku("test://k/2", "kitap", 3, KAYNAK) is None


def test_iz_son_bes_deneme_ve_hata_durumu_korunur():
    from core import ceviri_izleri as iz
    for i in range(7):
        iz.iz_kaydet(str(i), "test://k/3", {"durum": "basarisiz", "ham_ceviri": str(i)})
    r = iz.iz_oku("test://k/3")
    assert len(r) == 5
    assert {x["id"] for x in r} == {"2", "3", "4", "5", "6"}
    iz.iz_kaydet("6", "test://k/3", {"durum": "tamamlandi", "ham_ceviri": "6"})
    assert iz.iz_oku("test://k/3")[0]["veri"]["durum"] == "tamamlandi"


def test_hatalı_ozet_depolanamaz():
    from core import ceviri_izleri as iz
    r = modul().dogrula(veri(), KAYNAK); r["kaynak_sha256"] = "yanlis"
    with pytest.raises(modul().AnalizHatasi):
        iz.ozet_yaz("test://k/2", "kitap", 2, KAYNAK, r)


def test_turkcelesmis_kisi_adayi_ozeti_degıl_adayi_reddeder():
    m = modul(); v = veri()
    v["terimler"][0].update(tur="kisi")
    r = m.dogrula(v, KAYNAK)
    assert r["ozet"] == v["ozet"]
    assert r["terimler"] == []
    assert r["reddedilen_adaylar"][0]["kaynak"] == "Ash Bridge"


def test_kullanilan_aday_baska_paragraf_ve_kelime_icinden_turemez():
    m = modul(); v = veri()
    v["terimler"][0].update(hedef="Kül")
    r = m.dogrula(v, KAYNAK)
    assert m.kullanilan_adaylar(r, [KAYNAK, "Another."], ["Sunny köprüden geçti.", "Kül yayıldı."]) == []
    assert m.kullanilan_adaylar(r, [KAYNAK], ["Sunny Külliye'ye geldi."]) == []
    assert m.kullanilan_adaylar(r, [KAYNAK], ["Sunny Kül'den geçti."]) == r["terimler"]


@pytest.mark.parametrize("degistir", [
    lambda v: v["terimler"][0].update(kaynak="Future Castle"),
    lambda v: v["terimler"][0].update(hedef=""),
    lambda v: v["terimler"][0].update(tur="sehir"),
])
def test_kanitsiz_terim_yalniz_kendisi_atilir(degistir):
    m = modul(); v = veri(); degistir(v)
    r = m.analiz(KAYNAK, {}, {}, None, lambda *a: (yanit(v), "model"))
    assert r["ozet"] == veri()["ozet"]
    assert r["terimler"] == []
    assert r["reddedilen_adaylar"][0]["neden"]


def test_kanitsiz_ozet_maddesi_atilir_digerleri_kullanilir():
    m = modul(); v = veri()
    v["ozet"].append({"metin": "Uydurma olay.", "paragraf": 0, "alinti": "never happened"})
    r = m.analiz(KAYNAK, {}, {}, None, lambda *a: (yanit(v), "model"))
    assert r["ozet"] == veri()["ozet"]
    assert r["reddedilen_ozet"][0]["metin"] == "Uydurma olay."
    assert r["terimler"][0]["kaynak"] == "Ash Bridge"


def test_onceki_ozet_terim_getirirse_terimler_yok_sayilir():
    m = modul()
    r = m.ozetle(KAYNAK, lambda *a: (yanit(veri()), "model"))
    assert r["ozet"] == veri()["ozet"]
    assert r["terimler"] == [] and r["reddedilen_adaylar"] == []


def test_onceki_ozet_terim_kurallarini_degil_ozet_talimatini_kullanir():
    m = modul(); sistemler = []
    def uret(user, system, asama):
        sistemler.append((system, asama)); return yanit(veri()), "model"
    m.ozetle(KAYNAK, uret)
    sistem, asama = sistemler[0]
    assert asama == "onceki_bolum_ozeti"
    assert "HİYERARŞİ" not in sistem and "30" not in sistem
    assert "BİREBİR" in sistem
