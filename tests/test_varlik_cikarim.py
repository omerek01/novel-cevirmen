"""Varlık grafiği MODEL çıkarımı (`core.varlik_cikarim`) — çevrimdışı, model sahtelenir.

Asıl sınanan: uydurma bağın KANITLA elenmesi ve para emniyeti.
"""
from __future__ import annotations

import inspect
import json

from core import cache, glossary, translate, varlik_cikarim, varlik_grafigi as vg

KITAP = "shadow-slave"
METIN = (
    "Cassie walked beside Sunny through the ruins.\n\n"
    "Nephis was the heir of Clan Immortal Flame, and everyone knew it.\n\n"
    "The Crimson Spire towered over the Forgotten Shore."
)


def _hazirla():
    for k, v in {"Sunny": "Sunny", "Cassie": "Cassie", "Nephis": "Nephis",
                 "Immortal Flame clan": "Ölümsüz Alev klanı", "Clan Immortal Flame": "Ölümsüz Alev Klanı",
                 "Crimson Spire": "Kızıl Kule", "Forgotten Shore": "Unutulmuş Sahil"}.items():
        glossary.set_term(KITAP, k, v)
    cache.save_chapter("https://x/ch-7", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B7", "chapter_no": 7,
        "translation": "Çeviri.", "source": METIN,
    })


class _Yanit:
    def __init__(self, veri):
        self.text = json.dumps(veri)


def _sahte_model(monkeypatch, veri, beklenen_model=None):
    def sahte(_fabrika, models, user, system=None, max_tokens=None):
        if beklenen_model is not None:
            assert models == beklenen_model
        assert "Cassie" in user and "Crimson Spire" in user  # yalnız bölümde geçenler listede
        return _Yanit(veri), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)


def test_kanit_dogrulamasi_uydurma_bagi_eler():
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Cassie", "iliski": "yoldasi", "nesne": "Sunny",
         "kanit": "Cassie walked beside Sunny through the ruins.", "guven": 0.9}, METIN, {}) is None
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Cassie", "iliski": "dusmani", "nesne": "Sunny",
         "kanit": "Cassie hated Sunny.", "guven": 0.9}, METIN, {}) == "kanıt kaynakta birebir geçmiyor"
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Nephis", "iliski": "yoldasi", "nesne": "Sunny",
         "kanit": "Cassie walked beside Sunny through the ruins.", "guven": 0.9}, METIN, {}) \
        == "ozne kanıt cümlesinde geçmiyor"
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Cassie", "iliski": "sevgilisi", "nesne": "Sunny", "kanit": "x" * 20}, METIN, {}) \
        == "bilinmeyen ilişki"
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Cassie", "iliski": "yoldasi", "nesne": "Sunny",
         "kanit": "Cassie walked beside Sunny through the ruins.", "guven": 0.2}, METIN, {}) == "güven düşük"


def test_kanit_tirnak_ve_bosluk_farkina_dayanikli():
    metin = "He said: “Sunny’s blade.”   Effie laughed at Sunny."
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Effie", "iliski": "yoldasi", "nesne": "Sunny",
         "kanit": "Effie laughed at Sunny.", "guven": 0.8}, metin, {}) is None


def test_kitabi_cikar_gecerliyi_aday_yazar_reddi_raporlar(monkeypatch):
    _hazirla()
    _sahte_model(monkeypatch, {
        "baglar": [
            {"ozne": "Cassie", "iliski": "yoldasi", "nesne": "Sunny",
             "kanit": "Cassie walked beside Sunny through the ruins.", "guven": 0.9},
            {"ozne": "Crimson Spire", "iliski": "parcasi", "nesne": "Forgotten Shore",
             "kanit": "The Crimson Spire towered over the Forgotten Shore.", "guven": 0.8},
            {"ozne": "Nephis", "iliski": "dusmani", "nesne": "Sunny",
             "kanit": "Nephis betrayed Sunny.", "guven": 0.9},  # uydurma
        ],
        "yeni_adlar": ["Kai", "Sunny"],
    })
    ozet = varlik_cikarim.kitabi_cikar(KITAP, api_key="x", yaz=True)
    assert len(ozet["gecerli"]) == 2 and len(ozet["red"]) == 1
    assert ozet["yeni_adlar"] == {}  # Kai kaynakta yok, Sunny zaten sözlükte
    baglar = {(b["kaynak"], b["iliski"], b["hedef"]): b for b in vg.baglar(KITAP)}
    # Yoldaşlık SİMETRİK: uçlar kimliğe göre sıralanıp tek bağ olarak saklanır.
    bag = baglar.get(("Cassie", "yoldasi", "Sunny")) or baglar[("Sunny", "yoldasi", "Cassie")]
    assert bag["origin"] == "model" and bag["durum"] == "aday" and bag["ilk_bolum"] == 7
    assert ("Nephis", "dusmani", "Sunny") not in baglar


def test_kuru_koşu_yazmaz_ve_model_bayragi_gecer(monkeypatch):
    _hazirla()
    _sahte_model(monkeypatch, {"baglar": [
        {"ozne": "Cassie", "iliski": "yoldasi", "nesne": "Sunny",
         "kanit": "Cassie walked beside Sunny through the ruins.", "guven": 0.9}]},
        beklenen_model=("vertex/gemini-3.6-flash",))
    ozet = varlik_cikarim.kitabi_cikar(KITAP, api_key="x", models=("vertex/gemini-3.6-flash",), yaz=False)
    assert len(ozet["gecerli"]) == 1 and vg.baglar(KITAP) == []


def test_kategori_ve_run_celiskisi_reddedilir():
    _hazirla()
    for k in ("Abilities", "Shadow Step", "Soul Serpent", "Fallen Terror", "Terror", "Fallen"):
        glossary.set_term(KITAP, k, k)
    cozucu = vg.DugumCozucu(KITAP)
    kat = vg.kategori_kimlikleri(KITAP, cozucu)
    k = cozucu.coz
    assert k("Abilities") in kat and k("Fallen Terror") in kat  # bileşik: rütbe + sınıf
    assert k("Shadow Step") not in kat and k("Sunny") not in kat
    sistem = {(k("Sunny"), k("Soul Serpent")): {"golgesi"}}
    red = varlik_cikarim.yapisal_red
    assert red({"iliski": "yetenegi"}, k("Sunny"), k("Abilities"), kat, {}) == "kategori bu ilişkinin nesnesi olamaz"
    assert red({"iliski": "oldurdu"}, k("Nephis"), k("Fallen Terror"), kat, {}) is not None
    assert red({"iliski": "turu"}, k("Abilities"), k("Terror"), kat, {}) == "kategori özne olamaz"
    assert red({"iliski": "rutbesi"}, k("Cassie"), k("Fallen"), kat, {}) is None
    assert red({"iliski": "yetenegi"}, k("Sunny"), k("Shadow Step"), kat, {}) is None
    assert red({"iliski": "anisi"}, k("Sunny"), k("Soul Serpent"), kat, sistem).startswith("rün bağıyla")


def test_bilinen_baglar_prompta_girer_spoilersiz(monkeypatch):
    _hazirla()
    cozucu = vg.DugumCozucu(KITAP)
    vg.bag_ekle(KITAP, cozucu.coz("Cassie"), "yoldasi", cozucu.coz("Sunny"), 3, None, "manual")
    vg.bag_ekle(KITAP, cozucu.coz("Nephis"), "dusmani", cozucu.coz("Sunny"), 99, None, "manual")
    gorulen = {}

    def sahte(_f, models, user, system=None, max_tokens=None):
        gorulen["user"] = user
        return _Yanit({"baglar": []}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    varlik_cikarim.kitabi_cikar(KITAP, api_key="x", yaz=False)
    assert "BİLİNEN BAĞLAR" in gorulen["user"]
    assert "yoldasi" in gorulen["user"]
    assert "dusmani" not in gorulen["user"]  # bölüm 99'un bağı bölüm 7'ye sızmaz


def test_ad_etiketi_temizlenir_ve_rutbe_sinif_duzelir():
    assert varlik_cikarim.ad_temizle("Aspect (kategori)") == "Aspect"
    assert varlik_cikarim.ad_temizle("Mountain King [kisi]") == "Mountain King"
    assert varlik_cikarim.ad_temizle("Song of the Fallen") == "Song of the Fallen"
    diziler = vg.KITAP_PROFILLERI["shadow-slave"]["diziler"]
    duz = varlik_cikarim.duzen_iliskisini_duzelt
    assert duz({"iliski": "rutbesi", "nesne": "Tyrant"}, diziler)["iliski"] == "sinifi"
    assert duz({"iliski": "sinifi", "nesne": "Awakened"}, diziler)["iliski"] == "rutbesi"
    assert duz({"iliski": "rutbesi", "nesne": "Fallen"}, diziler)["iliski"] == "rutbesi"


def test_tur4_duzeltmeleri():
    diziler = vg.KITAP_PROFILLERI["shadow-slave"]["diziler"]
    duz = varlik_cikarim.duzen_iliskisini_duzelt
    assert duz({"iliski": "sinifi", "nesne": "Flaw"}, diziler)["iliski"] == "turu"
    assert duz({"iliski": "sinifi", "nesne": "awakened beasts"}, diziler)["iliski"] == "sinifi"
    metin = "If he were to assume that Cassie was Sunny's friend, all was fine."
    assert varlik_cikarim.kaniti_dogrula(
        {"ozne": "Cassie", "iliski": "yoldasi", "nesne": "Sunny", "kanit": metin, "guven": 0.9},
        metin, {}) == "varsayım cümlesi kanıt olamaz"
    _hazirla()
    glossary.set_term(KITAP, "Shadow Slave", "Gölge Kölesi")
    k = vg.DugumCozucu(KITAP).coz
    sistem = {(k("Sunny"), k("Shadow Slave")): {"gorunusu"}}
    assert varlik_cikarim.yapisal_red({"iliski": "unvani"}, k("Sunny"), k("Shadow Slave"), set(), sistem) \
        .startswith("rün bağıyla")


def test_takma_ad_asil_kisiye_indirilir(monkeypatch):
    _hazirla()
    glossary.set_term(KITAP, "Sunless", "Sunless")
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Sunny"), "takma_adi", k("Sunless"), 1, None, "manual")
    cache.save_chapter("https://x/ch-7", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B7", "chapter_no": 7,
        "translation": "Çeviri.", "source": METIN + "\n\nSunless and Cassie talked.",
    })
    _sahte_model(monkeypatch, {"baglar": [
        {"ozne": "Sunless", "iliski": "yoldasi", "nesne": "Cassie",
         "kanit": "Sunless and Cassie talked.", "guven": 0.9}]})
    ozet = varlik_cikarim.kitabi_cikar(KITAP, api_key="x", yaz=True)
    assert ozet["gecerli"][0]["ozne_kimlik"] == k("Sunny")


def test_siradan_tek_sozcuk_korpustan_kategori_sayilir():
    _hazirla()
    glossary.set_term(KITAP, "Armor", "Zırh")
    glossary.set_term(KITAP, "Saint", "Aziz")
    korpus = ("He fixed his armor. The armor shone. Old armor broke. Her armor held. "
              "The armor glinted. Saint moved. Saint bowed.")
    cozucu = vg.DugumCozucu(KITAP)
    kat = vg.kategori_kimlikleri(KITAP, cozucu, korpus)
    assert cozucu.coz("Armor") in kat
    assert cozucu.coz("Saint") not in kat  # gölge ADI: kategori listesinde de yok
    assert cozucu.coz("Cassie") not in kat  # İngilizce korunan kişi adı ölçülmez


def test_hiz_sinirinda_geri_cekilip_sonra_yeniden_dener(monkeypatch):
    _hazirla()
    monkeypatch.setattr(varlik_cikarim.time, "sleep", lambda _s: None)
    sayac = {"n": 0}

    def sahte(_f, models, user, system=None, max_tokens=None):
        sayac["n"] += 1
        if sayac["n"] <= 4:  # ilk geçişte 4 deneme de düşer -> ertelenir
            raise translate.TranslateError("429")
        return _Yanit({"baglar": []}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    ozet = varlik_cikarim.kitabi_cikar(KITAP, api_key="x", yaz=False)
    assert ozet["bolum"] == 1 and ozet["hata"] == [] and sayac["n"] == 5


def test_rutbe_olmayan_ad_unvana_cevrilir():
    p = vg.KITAP_PROFILLERI["shadow-slave"]
    duz = varlik_cikarim.duzen_iliskisini_duzelt
    for nesne in ("Chain Lord", "Artisan", "Prince of War", "Lord"):
        assert duz({"iliski": "rutbesi", "nesne": nesne}, p["diziler"], p["ek_rutbeler"])["iliski"] == "unvani"
    for nesne in ("Master", "Ascended", "Ascended human", "Saint", "Sleeper", "Transcendent"):
        assert duz({"iliski": "rutbesi", "nesne": nesne}, p["diziler"], p["ek_rutbeler"])["iliski"] == "rutbesi"


def test_varsayilan_zincir_ucretsiz():
    kaynak = inspect.getsource(varlik_cikarim)
    assert "secili_zincir(" not in kaynak
    assert "models or sozluk_dogrulama.ucretsiz_zincir()" in kaynak
