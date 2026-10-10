"""Birleşik/çoğul adayların otomatik kaydı ve kalıcı ret güvenliği."""
import pytest
from core import db, glossary, sozluk_dogrulama


def test_rutbe_sinif_birlesimi_ayri_kayit_olmaz():
    glossary.set_term("shadow-slave", "Awakened", "Uyanmış")
    glossary.set_term("shadow-slave", "Terror", "Dehşet")
    once = glossary.kitap_surumu("shadow-slave")
    assert glossary.merge_terms("shadow-slave", {"awakened terror": "Uyanmış Dehşet"}) == {}
    assert set(glossary.get_glossary("shadow-slave")) == {"Awakened", "Terror"}
    assert glossary.kitap_surumu("shadow-slave") == once


def test_gercek_ozel_ad_ve_baska_kitap_birlesimi_korunur():
    glossary.set_term("baska-kitap", "Awakened", "Uyanmış")
    glossary.set_term("baska-kitap", "Terror", "Dehşet")
    glossary.merge_terms("baska-kitap", {"Awakened Terror": "Uyanmış Dehşet"})
    assert "Awakened Terror" in glossary.get_glossary("baska-kitap")
    glossary.merge_terms("shadow-slave", {"Fallen Star": "Düşmüş Yıldız"})
    assert "Fallen Star" in glossary.get_glossary("shadow-slave")


def test_siradan_cogul_kural_olmaz_insan_ozel_adi_onaylayabilir():
    glossary.merge_terms("kitap", {"Nightmares": "Kabuslar", "Chains of Longing": "Özlem Zincirleri"})
    assert "Nightmares" not in glossary.ceviri_sozlugu("kitap")
    assert "Chains of Longing" not in glossary.ceviri_sozlugu("kitap")
    assert glossary.onayla("kitap", "Chains of Longing")
    assert glossary.ceviri_sozlugu("kitap")["Chains of Longing"] == "Özlem Zincirleri"


def test_cogul_model_onayi_ozel_ad_kaniti_olmadan_gecmez():
    sonuc, _ = sozluk_dogrulama.karar_ver(
        {"source": "Nightmares", "target": "Kabuslar"}, {"uygun": True, "karar": "onay"})
    assert sonuc == "inceleme"


def test_cogul_ozel_ad_model_onayi_kaynak_kaniti_ister():
    kayit = {"source": "Chains of Longing", "target": "Özlem Zincirleri"}
    assert sozluk_dogrulama.karar_ver(kayit, {
        "uygun": True, "karar": "onay", "cogul_ozel_ad": True})[0] == "inceleme"
    assert sozluk_dogrulama.karar_ver(kayit, {
        "uygun": True, "karar": "onay", "cogul_ozel_ad": True,
        "kanit": [{"baglam_id": "b1", "alinti": "Memory Name: [Chains of Longing]."}]})[0] == "gecti"


def test_ret_alternatif_yazimi_da_yeniden_eklenmekten_korur():
    glossary.set_term("kitap", "Abel", "Abel")
    glossary.yazim_ekle("kitap", "Abel", "Abele")
    glossary.reddet("kitap", "Abel")
    assert glossary.merge_names("kitap", ["Abel", "Abele"]) == {}
    assert glossary.get_glossary("kitap") == {}


def test_inceleme_kokenli_normal_silme_ret_kurali_yazmaz():
    # Temizlik aracının birleştirme yolu da inceleme kökeni taşır, kullanıcı reddi değildir.
    glossary.set_term("kitap", "Abel", "Abel")
    glossary.delete_term("kitap", "Abel", yol="inceleme")
    assert glossary.red_listesi("kitap") == []


def test_reddi_geri_almak_ayni_islemdeki_alternatiflerin_reddini_de_kaldirir(monkeypatch):
    monkeypatch.setattr(glossary.time, "time", lambda: 1791600000.0)
    glossary.set_term("kitap", "Abel", "Abel")
    glossary.yazim_ekle("kitap", "Abel", "Abele")
    glossary.set_term("kitap", "Great", "Abel")
    glossary.reddet("kitap", "Great")
    glossary.reddet("kitap", "Abel")
    assert glossary.reddi_kaldir("kitap", "Abel")
    assert {r["source"] for r in glossary.red_listesi("kitap")} == {"Great"}


def test_ret_yazimi_basarisizsa_silme_geri_alinir(monkeypatch):
    glossary.set_term("kitap", "Abel", "Abel")
    baglan = glossary._connect

    class Baglanti:
        def __init__(self):
            self.conn = baglan()

        def execute(self, sql, *args):
            if "INSERT OR REPLACE INTO sozluk_red" in sql:
                raise RuntimeError("ret yazılamadı")
            return self.conn.execute(sql, *args)

        def __getattr__(self, ad):
            return getattr(self.conn, ad)

    monkeypatch.setattr(glossary, "_connect", Baglanti)
    with pytest.raises(RuntimeError, match="ret yazılamadı"):
        glossary.reddet("kitap", "Abel")
    assert glossary.get_glossary("kitap") == {"Abel": "Abel"}


@pytest.mark.parametrize("ozel_ad", [False, True])
def test_kaynak_bagli_cogul_ozel_ad_onayi_yazma_kapisindan_gecer(ozel_ad):
    glossary.merge_terms("kitap", {"Chains of Longing": "Özlem Zincirleri"})
    glossary.dogrulama_yaz("kitap", "Chains of Longing", "gecti", {
        "sozlesme": "baglam-v2", "uygun": True, "baglam_hash": "kaynak-ozeti",
        "kanit": [{"baglam_id": "b1", "alinti": "Memory Name: [Chains of Longing]."}],
        "cogul_ozel_ad": ozel_ad,
    })
    assert ("Chains of Longing" in glossary.ceviri_sozlugu("kitap")) is ozel_ad


@pytest.mark.parametrize("kaynak", ["Children", "Women", "Men", "People", "Feet", "Teeth"])
def test_duzensiz_cogul_de_ozel_ad_kaniti_olmadan_kural_olmaz(kaynak):
    glossary.merge_terms("kitap", {kaynak: kaynak})
    assert kaynak not in glossary.ceviri_sozlugu("kitap")


def test_eski_ret_semayi_yukseltirken_veri_korunur_ve_geri_alma_tekildir():
    conn = db.connect()
    conn.execute("CREATE TABLE sozluk_red (book_slug TEXT, anahtar TEXT, source TEXT, target TEXT, zaman REAL, PRIMARY KEY(book_slug,anahtar))")
    conn.executemany("INSERT INTO sozluk_red VALUES (?,?,?,?,?)", [
        ("kitap", "abel", "Abel", "aynı", 1.0), ("kitap", "abele", "Abele", "aynı", 1.0)])
    conn.commit()
    conn.close()
    assert {r["source"] for r in glossary.red_listesi("kitap")} == {"Abel", "Abele"}
    glossary.reddi_kaldir("kitap", "Abel")
    assert {r["source"] for r in glossary.red_listesi("kitap")} == {"Abele"}
