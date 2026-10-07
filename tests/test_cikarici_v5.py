"""Çıkarıcı v5 (kapsama taraması) sözleşmeleri — çevrimdışı, model SAHTE, adlar KURGU.

Gerçek bölüm adları yalnız regresyon fikstürlerinde; üretim kodunda olmadıklarını
`test_uretim_kodunda_bolume_ozel_ad_ve_numara_yok` tutar."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from core import bilgi_delta as bd, bilgi_kanit as k, cache, db, glossary, settings, translate, varlik_grafigi as g

K = "v5-kitap"
BOS = {ad: [] for ad in bd.DELTA_SEMASI}


def bos(**kw):
    return {**BOS, **kw}


def terimler(*adlar):
    for ad in adlar:
        glossary.set_term(K, ad, ad)
    return g.DugumCozucu(K).coz


def islenenler(sonuc, tur=None):
    return [o for o in sonuc["oneriler"] if o["karar"] == "işle" and (tur is None or o["tur"] == tur)]


# ---------- sağlayıcı: YALNIZ Vertex, çeviri yapılandırmasından ayrı ----------
@pytest.mark.parametrize("model", ["gemini-3.6-flash", "gemini-2.5-flash", "vertex/sahte",
                                   "claude-haiku-4-5", "z-ai/glm-5.3", ""])
def test_cikarici_vertex_disi_modeli_reddeder(model, monkeypatch):
    def cagrilmamali(*a, **kw):
        raise AssertionError("model çağrılmamalı")
    monkeypatch.setattr(translate, "_generate_with_fallback", cagrilmamali)
    with pytest.raises(bd.SaglayiciHatasi):
        bd._model_cagir(model)
    with pytest.raises(bd.SaglayiciHatasi):
        bd.bolum_degerlendir(K, 1, model)


def test_cikarici_tek_halka_vertex_ve_yedege_dusmez(monkeypatch):
    from types import SimpleNamespace
    gorulen = []

    def uret(fabrika, modeller, user, system, max_tokens):
        gorulen.append(tuple(modeller))
        return SimpleNamespace(text=json.dumps(BOS), usage_metadata=None), modeller[0]
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    metin, kullanim = bd._model_cagir(bd.CIKARICI_MODELI)("u", "s")
    assert gorulen == [("vertex/gemini-3.6-flash",)]
    assert kullanim["saglayici"] == "VERTEX" and kullanim["fiili_model"] == bd.CIKARICI_MODELI
    # Yanıtlayan başka bir modelse (ör. ücretsiz Gemini) sonuç KABUL edilmez.
    monkeypatch.setattr(translate, "_generate_with_fallback",
                        lambda *a, **kw: (SimpleNamespace(text="{}", usage_metadata=None), "gemini-3.6-flash"))
    with pytest.raises(bd.SaglayiciHatasi):
        bd._model_cagir(bd.CIKARICI_MODELI)("u", "s")


def test_cikarici_ayari_ceviri_ayarindan_bagimsiz(monkeypatch):
    assert bd.CIKARICI_MODELI == "vertex/gemini-3.6-flash" and bd.CIKARICI_SAGLAYICI == "VERTEX"
    assert translate.PRIMARY_TRANSLATION_MODEL == "gemini-3.6-flash"
    assert not any(translate._vertex_modeli(m) for m in translate.DEFAULT_MODELS)
    varsayilan = translate.secili_zincir()
    assert varsayilan == translate.DEFAULT_MODELS                     # çıkarıcı çeviri zincirini değiştirmedi
    settings.set(translate.MODEL_AYAR_ANAHTARI, "gemini-2.5-flash")   # okuyucu çeviri modeli seçti
    assert translate.secili_zincir()[0] == "gemini-2.5-flash"
    assert bd.CIKARICI_MODELI == "vertex/gemini-3.6-flash"            # çıkarıcı etkilenmez
    # Çıkarıcı çeviri ayarını OKUMAZ: secili_zincir çağrılırsa test düşer.
    monkeypatch.setattr(translate, "secili_zincir", lambda: (_ for _ in ()).throw(AssertionError("okunmamalı")))
    from types import SimpleNamespace
    monkeypatch.setattr(translate, "_generate_with_fallback",
                        lambda f, m, u, system, max_tokens: (SimpleNamespace(text="{}", usage_metadata=None), m[0]))
    assert bd._model_cagir(bd.CIKARICI_MODELI)("u", "s")[1]["fiili_model"] == "vertex/gemini-3.6-flash"


def test_saglayici_ihlali_provider_blocked_sayilmaz():
    dis = translate.TranslateError("x")
    dis.__cause__ = bd.SaglayiciHatasi("y")
    assert bd._hata_sinifi(dis) == "provider_policy_violation"


# ---------- kapsama taraması / boş delta sözleşmesi ----------
def test_istem_kapsama_taramasi_ve_bos_delta_sozlesmesi():
    t = bd.CIKARICI_TALIMATI
    for kategori in bd.KAPSAMA_KATEGORILERI:
        assert kategori in t
    for sinyal in bd.BOS_DELTA_ONCESI_SINYALLER:
        assert sinyal in t
    assert "STAGE A" in t and "STAGE B" in t and "CHECK != EMIT" in t
    assert "do NOT output it" in t  # tarama çıktısı/düşünce zinciri istenmez
    for anahtar in bd.DURUM_ANAHTARLARI:
        assert anahtar in t
    for durum in bd.LIFE_STATUS:
        assert durum in t
    # Şema değişmedi: boş delta hâlâ geçerli bir cevap.
    assert bd.SEMA_SURUMU == "delta-3-v4-final" and bd.sema_dogrula(BOS) == []
    assert (bd.CIKARICI_SURUMU, bd.ISTEM_SURUMU) == ("7", "6")


def test_istem_kanit_kopyalama_disiplini():
    t = bd.CIKARICI_TALIMATI
    assert "DO NOT reconstruct evidence from memory" in t
    assert "DO NOT paraphrase" in t and "WITHOUT adding a closing quote mark" in t


def test_uretim_kodunda_bolume_ozel_ad_ve_numara_yok():
    kok = Path(__file__).resolve().parent.parent / "app" / "core"
    yasak = re.compile(r"\b(?:Kido|Sunny|Effie|Nether|Hope|Cassie|Rain|Soul Serpent)\b|\b(?:313|360|670|691|848)\b")
    for ad in ("bilgi_delta.py", "bilgi_kanit.py"):
        assert not yasak.search((kok / ad).read_text(encoding="utf-8")), ad
    assert not yasak.search(bd.CIKARICI_TALIMATI)


# ---------- kanıt birebirliği ----------
def test_kanit_birebir_kopya_olmali():
    kaynak = ("’Huh... so the Warden of Tides was actually called Varn? I wonder which came first, "
              "the name or the title... was he actually the Herald of Ash?’")
    birebir = "so the Warden of Tides was actually called Varn?"
    assert k.span_gecerli(birebir, kaynak)
    # Kaynakta olmayan kapanış tırnağı eklenmiş, ortası kısaltılmış alıntı REDDEDİLİR.
    assert not k.span_gecerli("’Huh... so the Warden of Tides was actually called Varn? I wonder "
                              "which came first, the name or the title...’", kaynak)
    assert not k.span_gecerli("The Warden of Tides is called Varn.", kaynak)   # parafraz


# ---------- tamamlayıcı bilgi bastırılmaz ----------
def test_bastirma_siniflari():
    assert bd.bastirma_sinifi(("bag", "a", "oldurdu", "b"), ("bag", "a", "oldurdu", "b")) == bd.EXACT_DUPLICATE
    assert bd.bastirma_sinifi(("bag", "a", "yoldasi", "b"), ("bag", "b", "yoldasi", "a")) == bd.SEMANTIC_DUPLICATE
    assert bd.bastirma_sinifi(("deger", "b", "Yaşam", "dead"), ("bag", "a", "oldurdu", "b")) == bd.COMPLEMENTARY_KNOWLEDGE
    assert bd.bastirma_sinifi(("bag", "a", "unvani", "c"), ("bag", "a", "unvani", "d")) == bd.COMPLEMENTARY_KNOWLEDGE


def test_mevcut_olum_bagi_yasam_durumunu_bastirmaz():
    coz = terimler("Arden", "Mira", "Guild")
    g.bag_ekle(K, coz("Arden"), "oldurdu", coz("Mira"), 5, "Arden killed Mira.", "manual", 1.0, durum="onaylandi")
    e = "The charm had been made by Mira, who was now dead."
    x = {"varlik": "Mira", "anahtar": "life_status", "deger": "dead", "kanit": e, "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir(K, 9, bos(state_changes=[x]), "Arden was silent. " + e)
    assert len(islenenler(sonuc, "state_changes")) == 1
    # Aynı durum zaten varsa EXACT olarak atlanır.
    g.deger_yaz(K, coz("Mira"), "Yaşam", "dead", 7, "eski", origin="model", durum_bilgisi="confirmed")
    sonuc = bd.delta_degerlendir(K, 9, bos(state_changes=[x]), "Arden was silent. " + e)
    atla = [o for o in sonuc["oneriler"] if o["karar"].startswith("atla:")]
    assert atla and atla[0]["bastirma"] == bd.EXACT_DUPLICATE


def test_istem_tamamlayici_temsili_aciklar():
    t = bd.CIKARICI_TALIMATI
    assert "COMPLEMENTARY REPRESENTATIONS ARE NOT DUPLICATES" in t
    assert "does NOT make 'Mira.life_status = dead'" in t


# ---------- parazit ölümü konak ölümü değildir ----------
def test_parazit_olumu_konak_olumu_degil():
    coz = terimler("Bone Tyrant", "Ilsa")
    kaynak = ("Ilsa threw the shield. It cut the parasite in half and exited the body of the Bone Tyrant "
              "from the other side. The mountain of bones froze, then shuddered. And then, it crumbled.")
    durum = {"varlik": "Bone Tyrant", "anahtar": "life_status", "deger": "dead", "kanit": kaynak,
             "durum_bilgisi": "confirmed"}
    bag = {"ozne": "Ilsa", "iliski": "oldurdu", "nesne": "Bone Tyrant", "kanit": kaynak, "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir(K, 3, bos(state_changes=[durum], new_relationships=[bag]), kaynak)
    assert not islenenler(sonuc)
    assert coz("Bone Tyrant")
    assert "parasite" in bd.CIKARICI_TALIMATI and "host/owner dead" in bd.CIKARICI_TALIMATI


# ---------- öğretmen / öğrenci ----------
@pytest.mark.parametrize("kanit", [
    "Ayla taught Boran swordsmanship.",
    "Boran knew her skill well, since Ayla had taught him how to wield a spear.",
    "Ayla trained Boran for years.",
    "Boran learned from Ayla.",
    "Ayla was Boran's teacher.",
    "Ayla mentored Boran through the winter.",
])
def test_ogretmen_yonu_ogrenci_ogretmeni_ogretmen(kanit):
    assert k.semantik_sonuc({"ozne": "Boran", "iliski": "ogretmeni", "nesne": "Ayla", "kanit": kanit}, {})[0] == "verified"
    assert k.semantik_sonuc({"ozne": "Ayla", "iliski": "ogretmeni", "nesne": "Boran", "kanit": kanit}, {})[0] == "wrong"


def test_ogretmen_hatirlama_sozlesmesi():
    terimler("Ayla", "Boran")
    e = "Boran knew her skill well, since Ayla had taught him how to wield a spear."
    dogru = {"ozne": "Boran", "iliski": "ogretmeni", "nesne": "Ayla", "kanit": e, "durum_bilgisi": "confirmed"}
    ters = {**dogru, "ozne": "Ayla", "nesne": "Boran"}
    sonuc = bd.delta_degerlendir(K, 4, bos(new_relationships=[dogru, ters]), e)
    kabul = islenenler(sonuc)
    assert [(o["veri"]["ozne"], o["veri"]["nesne"]) for o in kabul] == [("Boran", "Ayla")]
    t = bd.CIKARICI_TALIMATI
    assert "Boran ogretmeni Ayla" in t and "NEVER output the reverse" in t and "mentored" in t


# ---------- unvan / ad / Gerçek Ad ----------
def test_unvan_ad_ve_gercek_ad_ayrimi():
    terimler("Varn", "Herald of Ash", "Warden of Tides", "Sela", "Lady of Embers")
    kaynak = ("Then there is the youngest, Varn — the Herald of Ash, who hid in the dark. "
              "So the Warden of Tides was actually called Varn? "
              "Then the Lady of Embers came to live among us, becoming known as Sela.")
    e1 = "Then there is the youngest, Varn — the Herald of Ash, who hid in the dark."
    e2 = "So the Warden of Tides was actually called Varn?"
    e3 = "Then the Lady of Embers came to live among us, becoming known as Sela."
    veri = bos(
        new_relationships=[{"ozne": "Varn", "iliski": "unvani", "nesne": "Herald of Ash", "kanit": e1, "durum_bilgisi": "confirmed"},
                           {"ozne": "Varn", "iliski": "unvani", "nesne": "Warden of Tides", "kanit": e2, "durum_bilgisi": "confirmed"}],
        new_aliases=[{"asil": "Sela", "ad": "Lady of Embers", "tur": "unvani", "kanit": e3, "durum_bilgisi": "confirmed"},
                     {"asil": "Varn", "ad": "Warden of Tides", "tur": "gercek_adi", "kanit": e2, "durum_bilgisi": "confirmed"}],
        identity_revelations=[{"ad_1": "Warden of Tides", "ad_2": "Varn", "kanit": e2}],
    )
    sonuc = bd.delta_degerlendir(K, 6, veri, kaynak)
    kabul = {(o["veri"]["ozne"], o["veri"]["iliski"], o["veri"]["nesne"]) for o in islenenler(sonuc)}
    assert kabul == {("Varn", "unvani", "Herald of Ash"), ("Varn", "unvani", "Warden of Tides"),
                     ("Sela", "unvani", "Lady of Embers")}
    assert not any(i[0] == "identity_merge" for i in sonuc["inceleme"])          # gereksiz kimlik incelemesi yok
    assert not any(r[1] == "gercek_adi" for r in kabul)                           # sıradan ad != True Name
    t = bd.CIKARICI_TALIMATI
    assert "ORDINARY NAME" in t and "TRUE NAME (gercek_adi)" in t and "IDENTITY REVELATION" in t


# ---------- aynı bölüm deterministik bilgi ----------
def test_ayni_bolum_deterministik_bastirilir_ama_duzyazi_olumu_bastirilmaz(monkeypatch):
    coz = terimler("Ilsa", "Grey Hound")
    run = "[You have slain Grey Hound.]"
    monkeypatch.setattr(bd, "deterministik_plan", lambda slug, kaynak: [("Ilsa", "oldurdu", "Grey Hound", run)])
    kaynak = run + "\nLater, Ilsa saw that the Grey Hound was dead."
    tekrar = {"ozne": "Ilsa", "iliski": "oldurdu", "nesne": "Grey Hound", "kanit": run, "durum_bilgisi": "confirmed"}
    durum = {"varlik": "Grey Hound", "anahtar": "life_status", "deger": "dead",
             "kanit": "Later, Ilsa saw that the Grey Hound was dead.", "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir(K, 8, bos(new_relationships=[tekrar], state_changes=[durum]), kaynak)
    atla = [o for o in sonuc["oneriler"] if o["tur"] == "new_relationships"]
    assert atla[0]["karar"].startswith("atla:") and atla[0]["bastirma"] == bd.EXACT_DUPLICATE
    assert len(islenenler(sonuc, "state_changes")) == 1
    baglam = {"bolum": 8, "bilgi_siniri": 7, "satirlar": [], "run_satirlari": ['{"x": 1}']}
    istem = bd.istem_kur(baglam, kaynak)
    assert "ALREADY EXTRACTED FROM THIS CHAPTER — DO NOT RE-EXTRACT" in istem
    assert coz("Grey Hound")


# ---------- temsil kapasitesi boşluğu ----------
def test_aktarim_kapasite_boslugu_iliski_yazmaz():
    terimler("Orion", "Nila", "Sentinel")
    e = "Orion entrusted Sentinel to Nila."
    gap = {"kategori": "relation_capability_gap", "ozne": "Nila", "nesne": "Sentinel", "kanit": e, "onem": "medium",
           "aciklama": "MISSING_RELATION_CAPABILITY: transfer/entrustment requires human representation decision"}
    sahte = {"ozne": "Nila", "iliski": "golgesi", "nesne": "Sentinel", "kanit": e, "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir(K, 2, bos(review_items=[gap], new_relationships=[sahte]), e)
    assert any(i[0] == "relation_capability_gap" and i[3]["capability_gap"] for i in sonuc["inceleme"])
    assert not islenenler(sonuc)
    assert "relation_capability_gap" not in g.ILISKILER


# ---------- doğrulama kipi grafiğe dokunmaz ----------
def _parmak():
    conn = sqlite3.connect(db.db_path())
    try:
        out = {}
        for t in ("varlik_bag", "varlik_deger", "glossary", "bilgi_isleme", "bilgi_oneri", "bilgi_inceleme", "bilgi_bas"):
            rows = conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            out[t] = hashlib.sha256(repr(rows).encode()).hexdigest()
        return out
    finally:
        conn.close()


def test_dogrulama_kipi_grafigi_degistirmez():
    coz = terimler("Ayla", "Boran", "Mira")
    e = "Boran knew her skill well, since Ayla had taught him how to wield a spear. Mira, who was now dead, smiled once."
    cache.save_chapter(f"https://x/{K}/12", {"book_slug": K, "book_title": "V5", "title": "B12", "chapter_no": 12,
                                             "translation": "Çeviri.", "source": e})
    g.bag_ekle(K, coz("Ayla"), "yoldasi", coz("Mira"), 3, "eski", "manual", 1.0, durum="onaylandi")
    bd._connect().close()
    once = _parmak()
    veri = bos(new_relationships=[{"ozne": "Boran", "iliski": "ogretmeni", "nesne": "Ayla",
                                   "kanit": "Boran knew her skill well, since Ayla had taught him how to wield a spear.",
                                   "durum_bilgisi": "confirmed"}],
               review_items=[{"kategori": "relationship_conflict", "ozne": "Ayla", "iliski": "yoldasi", "nesne": "Mira",
                              "kanit": "Mira, who was now dead, smiled once.", "onem": "high"}])
    sonuc = bd.bolum_degerlendir(K, 12, bd.CIKARICI_MODELI, cagri=lambda u, s: (json.dumps(veri), {}))
    assert sonuc["durum"] == "dogrulama" and islenenler(sonuc["degerlendirme"])
    assert _parmak() == once


# ---------- kıyas betiği (v5.1): yalnız Vertex ----------
def test_kiyas_betigi_yalniz_vertex_model_kabul_eder():
    from validation_v5 import model_sec
    assert model_sec(None) == bd.CIKARICI_MODELI
    assert model_sec("vertex/gemini-3.8-flash") == "vertex/gemini-3.8-flash"
    for ad in ("gemini-3.8-flash", "vertex/sahte", "claude-sonnet-5"):
        with pytest.raises(bd.SaglayiciHatasi):
            model_sec(ad)
