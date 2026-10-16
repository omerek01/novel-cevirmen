"""Yeni kitapta otomatik kitap profili + sözlük ön taraması (plan Faz 3) — çevrimdışı, sahte model.

Metinler testte yazılmış kısa sentetik bölümlerdir (gerçek kitap metni değil)."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from core import cache, glossary, kitap_profili, pipeline, profil_cikarim as pc, sozluk_tarama
from core import varlik_grafigi as vg

KITAP = "deneme-kitap"
BEKLEME_ACIK = True  # ön tarama ÜRÜN bekleme kuralını sınar (conftest `_sozluk_bekleme`)


def _bolum(no, paragraflar, zaman=None):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (f"https://y/{no}-{zaman or 0}", KITAP, no, None, "\n\n".join(paragraflar), zaman or time.time()),
    )
    conn.commit()
    conn.close()


def _kitap(n=4):
    for no in range(1, n + 1):
        _bolum(no, [
            f"Mira Vale woke before dawn in chapter {no}. Mira Vale had trained with the Iron Spear for years.",
            "System: Daily quest available.",
            "Reward: 10 Gold",
            "Mira checked her Skill list. Her rank was still Bronze, below Silver and Gold.",
            "[Skill acquired: Swift Step]",
        ])
    return pc.ilk_bolumler(KITAP)


YANIT = {
    "kitap_turu": {"deger": "sistem", "kanit": "System: Daily quest available."},
    "ana_karakter": {"deger": "Mira Vale", "kanit": "Mira Vale woke before dawn in chapter 1."},
    "sistem_sesi": [{"deger": "System", "kanit": "System: Daily quest available."},
                    {"deger": "Herald", "kanit": "Herald: nope."}],
    "diziler": [{"ad": "Rütbe dizisi", "deger": ["Bronze", "Silver", "Gold"],
                 "kanit": "Her rank was still Bronze, below Silver and Gold."},
                {"ad": "uydurma", "deger": ["Bronze", "Silver", "Diamond"],
                 "kanit": "Her rank was still Bronze, below Silver and Gold."}],
    "kategori_terimleri": [{"deger": "Skill", "kanit": "Mira checked her Skill list."},
                           {"deger": "Talent", "kanit": "Mira checked her Talent list."}],
    "gercek_ad_sozcugu": None,
}


def _cagir(yanit):
    def cagir(user, system, api_key=""):
        return json.dumps(yanit), "sahte-model"
    return cagir


def test_dogrula_kanitsiz_ve_sayimi_tutmayan_oneriyi_atar():
    bolumler = _kitap()
    alanlar = pc.dogrula(YANIT, pc.ornek_kur(bolumler), bolumler)
    assert alanlar["kitap_turu"]["deger"] == "sistem"
    assert alanlar["ana_karakter"]["deger"] == "Mira Vale" and alanlar["ana_karakter"]["kanit"][0]["bolum"] == 1
    assert alanlar["sistem_sesi"]["deger"] == ["System"]  # "Herald" kanıtı örnekte yok
    assert alanlar["diziler"]["deger"] == {"rütbe_dizisi": ["Bronze", "Silver", "Gold"]}
    assert "Diamond" in alanlar["diziler"]["elenen"][0]["neden"]
    assert alanlar["kategori_terimleri"]["deger"] == ["Skill"]  # Talent kanıtı uydurma
    # Anahtarlar model önerisi değil, YEREL sayım: sistem bloğundaki "Reward" 4 bölümde.
    assert alanlar["sistem_anahtarlari"]["deger"] == ["Reward"]
    assert "gercek_ad_sozcugu" not in alanlar


def test_kanit_bos_ya_da_degeri_icermiyorsa_atilir():
    bolumler = _kitap()
    yanit = {"ana_karakter": {"deger": "Mira Vale", "kanit": ""},
             # Örnekte BİREBİR geçen gerçek cümle, ama değeri taşımıyor.
             "kategori_terimleri": [{"deger": "Gold", "kanit": "System: Daily quest available."}]}
    alanlar = pc.dogrula(yanit, pc.ornek_kur(bolumler), bolumler)
    assert "ana_karakter" not in alanlar and "kategori_terimleri" not in alanlar


def test_ana_karakter_ilk_bolumlerde_az_geciyorsa_atilir():
    bolumler = _kitap(2)  # "Mira Vale" 2 bölümde 2'şer = 4 < ANA_KARAKTER_MIN
    assert "ana_karakter" not in pc.dogrula(YANIT, pc.ornek_kur(bolumler), bolumler)


def test_sistem_sesi_tek_satirda_kaliyorsa_atilir():
    _bolum(1, ["Mira Vale ran.", "System: Once only."])
    bolumler = pc.ilk_bolumler(KITAP)
    yanit = {"sistem_sesi": [{"deger": "System", "kanit": "System: Once only."}]}
    assert "sistem_sesi" not in pc.dogrula(yanit, pc.ornek_kur(bolumler), bolumler)


def test_profil_oner_aday_yazar_onaysiz_profile_girmez():
    _kitap()
    sonuc = pc.profil_oner(KITAP, cagir=_cagir(YANIT))
    assert set(sonuc["yazilan"]) == {"kitap_turu", "ana_karakter", "sistem_sesi", "sistem_anahtarlari", "diziler",
                                     "kategori_terimleri"}
    assert vg.profil(KITAP) is None
    satir = next(r for r in kitap_profili.satirlar(KITAP) if r["alan"] == "ana_karakter")
    assert satir["origin"] == "model" and satir["durum"] == "aday" and satir["kanit"][0]["alinti"].startswith("Mira")
    assert pc.karar_ver(KITAP, "ana_karakter", "onayla")
    assert vg.profil(KITAP) == {"ana_karakter": "Mira Vale"}


def test_kullanici_karari_ve_kod_kaydi_ezilmez():
    _kitap()
    pc.profil_oner(KITAP, cagir=_cagir(YANIT))
    pc.karar_ver(KITAP, "ana_karakter", "reddet")
    pc.karar_ver(KITAP, "diziler", "duzelt", {"rutbe": ["Bronze", "Silver", "Gold", "Platinum"]})
    yeni = {**YANIT, "ana_karakter": {"deger": "Mira", "kanit": "Mira checked her Skill list."}}
    sonuc = pc.profil_oner(KITAP, cagir=_cagir(yeni))
    assert "ana_karakter" not in sonuc["yazilan"] and "diziler" not in sonuc["yazilan"]
    assert vg.profil(KITAP)["diziler"] == {"rutbe": ("Bronze", "Silver", "Gold", "Platinum")}
    # Koddaki profili olan kitapta (SS) o alanlar hiç önerilmez.
    assert pc._yazilabilir("shadow-slave") == {"sistem_anahtarlari", "kitap_turu", "kategori_terimleri"} - set(
        vg.KITAP_PROFILLERI["shadow-slave"])


@pytest.mark.parametrize("alan, deger", [
    ("kitap_turu", "romantik"), ("ana_karakter", "  "), ("diziler", {"x": ["Tek"]}), ("sistem_sesi", []),
    ("bilinmeyen", ["x"]),
])
def test_elle_duzeltme_bicimi_denetlenir(alan, deger):
    with pytest.raises(ValueError):
        pc.karar_ver(KITAP, alan, "duzelt", deger)


def test_cikar_is_kaydi_tutar_ve_hatayi_yutar():
    _kitap()

    def patlar(user, system, api_key=""):
        raise RuntimeError("kota")

    sonuc = pc.cikar(KITAP, on_tarama=False, cagir=patlar)
    assert "kota" in sonuc["hata"] and pc.son_cikarim(KITAP)["hata"] == sonuc["hata"]
    assert pc.son_cikarim("baska-kitap") is None


def test_otomatik_tetik_kosullari(monkeypatch):
    baslayan = []
    monkeypatch.setattr(pc, "arka_planda", lambda slug, on_tarama=None: baslayan.append(slug) or True)
    _kitap(2)
    monkeypatch.setenv("KITAP_PROFIL_OTOMATIK", "1")
    assert pc.gerekirse_baslat(KITAP) is False  # 2 bölüm < OTOMATIK_MIN
    _bolum(3, ["Mira Vale slept."])
    _bolum(3, ["Mira Vale slept again."], zaman=time.time() + 1)  # aynı bölümün ikinci kaydı sayılmaz
    assert pc.gerekirse_baslat(KITAP) is True and baslayan == [KITAP]
    assert pc.gerekirse_baslat("shadow-slave") is False  # kodda profili var
    monkeypatch.setenv("KITAP_PROFIL_OTOMATIK", "0")
    assert pc.gerekirse_baslat(KITAP) is False
    monkeypatch.setenv("KITAP_PROFIL_OTOMATIK", "1")
    pc._kaydet(KITAP, {"bolumler": [1, 2, 3]})
    assert pc.gerekirse_baslat(KITAP) is False  # bir kez koştu
    monkeypatch.setattr(pc, "OTOMATIK_UST", 2)
    assert pc._kaynakli_bolum_sayisi(KITAP) == 3


def test_pipeline_bolum_islenince_tetigi_cagirir(monkeypatch):
    cagrilan = []
    monkeypatch.setattr(pc, "gerekirse_baslat", lambda slug: cagrilan.append(slug))
    pipeline._sozluge_isle(KITAP, {"detected_names": [], "detected_terms": {}}, 1, "Mira Vale ran.")
    assert cagrilan == [KITAP]


# ---------- sözlük ön taraması ----------
def _terim_cagir(terimler, ele=()):
    def cagir(user, system, api_key=""):
        if system == sozluk_tarama.ELEME_INSTRUCTION:
            return json.dumps({"ele": [{"source": s, "neden": "genel"} for s in ele]}), "sahte"
        return json.dumps({"terms": terimler}), "sahte"
    return cagir


def test_on_tarama_adaylari_bekletilerek_ilk_bolumuyle_yazar():
    bolumler = _kitap()
    terimler = [
        {"source": "Iron Spear", "target": "Demir Mızrak", "tur": "nesne",
         "kanit": "Mira Vale had trained with the Iron Spear for years."},
        {"source": "Mira Vale", "target": "Mira Vale", "tur": "kisi",
         "kanit": "Mira Vale woke before dawn in chapter 2."},
        {"source": "Swift Step", "target": "Çevik Adım", "tur": "yetenek", "kanit": "[Skill acquired: Swift Step]"},
    ]
    sonuc = sozluk_tarama.on_tara(KITAP, bolumler, cagir=_terim_cagir(terimler, ele=["Swift Step"]))
    assert sonuc["yazilan"] == ["Iron Spear", "Mira Vale"]
    assert next(a for a in sonuc["adaylar"] if a["source"] == "Swift Step")["durum"] == "elendi"
    satirlar = {r["source"]: r for r in glossary.get_glossary_rows(KITAP)}
    assert satirlar["Iron Spear"]["target"] == "Demir Mızrak" and satirlar["Iron Spear"]["first_chapter"] == 1
    # ÖNCE BEKLEME: doğrulanmadan prompt'a girmez.
    assert {s: (r["durum"], r["origin"]) for s, r in satirlar.items()} == {
        "Iron Spear": (glossary.TUTULDU, "auto"), "Mira Vale": (glossary.TUTULDU, "auto")}
    assert "Swift Step" not in satirlar


def test_on_tarama_yazmadan_da_kosar_ve_ikinci_gecis_kapatilabilir():
    bolumler = _kitap()
    terimler = [{"source": "Iron Spear", "target": "Demir Mızrak", "tur": "nesne",
                 "kanit": "Mira Vale had trained with the Iron Spear for years."}]
    sonuc = sozluk_tarama.on_tara(KITAP, bolumler, ikinci_gecis=False, yaz=False,
                                  cagir=_terim_cagir(terimler, ele=["Iron Spear"]))
    assert sonuc["yazilan"] == [] and sonuc["adaylar"][0]["durum"] == "aday"
    assert glossary.get_glossary_rows(KITAP) == []


def test_cikar_on_taramayi_bayrakla_kosar(monkeypatch):
    _kitap()
    gorulen = []

    def cagir(user, system, api_key=""):
        gorulen.append(system)
        return json.dumps({} if system != pc.PROFIL_INSTRUCTION else YANIT), "sahte"

    pc.cikar(KITAP, cagir=cagir)
    assert gorulen == [pc.PROFIL_INSTRUCTION]  # SOZLUK_ON_TARAMA=0 (varsayılan)
    monkeypatch.setenv("SOZLUK_ON_TARAMA", "1")
    sonuc = pc.cikar(KITAP, cagir=cagir)
    assert gorulen[1:] == [pc.PROFIL_INSTRUCTION, sozluk_tarama.TARAMA_INSTRUCTION]
    assert sonuc["on_tarama"] == {"oneri": 0, "yazilan": [], "elenen": 0}


# ---------- uçlar ----------
@pytest.fixture
def istemci():
    import server

    return TestClient(server.app)


def test_uc_profil_karti_ve_karar(istemci, monkeypatch):
    _kitap()
    pc.profil_oner(KITAP, cagir=_cagir(YANIT))
    v = istemci.get(f"/api/book/{KITAP}/profil").json()
    alan = {a["alan"]: a for a in v["alanlar"]}
    assert v["profil_var"] is False and v["defter_acik"] is False
    assert alan["ana_karakter"]["model"]["durum"] == "aday" and alan["ana_karakter"]["etkin"] is None
    r = istemci.post(f"/api/book/{KITAP}/profil/karar", json={"alan": "ana_karakter", "karar": "onayla"})
    assert r.status_code == 200 and r.json()["profil_var"] is True and r.json()["defter_acik"] is True
    r = istemci.post(f"/api/book/{KITAP}/profil/karar", json={"alan": "sistem_sesi", "karar": "duzelt",
                                                               "deger": ["System", " "]})
    assert {a["alan"]: a for a in r.json()["alanlar"]}["sistem_sesi"]["etkin"] == ["System"]
    assert istemci.post(f"/api/book/{KITAP}/profil/karar",
                        json={"alan": "gercek_ad_sozcugu", "karar": "onayla"}).status_code == 404
    assert istemci.post(f"/api/book/{KITAP}/profil/karar",
                        json={"alan": "ana_karakter", "karar": "sil"}).status_code == 400
    baslayan = []
    monkeypatch.setattr(pc, "arka_planda", lambda slug, on_tarama=None: baslayan.append((slug, on_tarama)) or True)
    r = istemci.post(f"/api/book/{KITAP}/profil/oner", json={"on_tarama": True})
    assert r.json()["basladi"] is True and baslayan == [(KITAP, True)]
