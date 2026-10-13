"""Türkçe cilalama turu (CEVIRI_CILALA): ağsız, sahte model çağrısıyla."""
import json

from core import ceviri_cilala as cc

EN = ["He was tired.", "She smiled at him suddenly.", "The Spell faded."]
TR = ["O yorgundu.", "Kadın ona aniden gülümsedi.", "Büyü söndü."]


class _Yanit:
    def __init__(self, metin):
        self.text = metin


def _uret(paragraflar):
    def uret(user, system, asama):
        assert asama == "cilalama" and "CİLALAMAK" in system
        veri = json.loads(user)
        assert [p["n"] for p in veri["paragraflar"]] == [0, 1, 2]
        return _Yanit(json.dumps({"paragraflar": paragraflar}, ensure_ascii=False)), "vertex/gemini-3.8-flash"
    return uret


def _temiz(_):
    return set()


def test_cilalanan_paragraflar_yerine_yazilir():
    tr = list(TR)
    m = cc.cilala(tr, EN, {"Spell": "Büyü"}, _uret([{"n": 0, "tr": "Yorgundu."}, {"n": 1, "tr": TR[1]}, {"n": 2, "tr": TR[2]}]), _temiz)
    assert tr == ["Yorgundu.", TR[1], TR[2]]
    assert m["durum"] == "cilalandi" and m["degisen"] == 1


def test_eksik_paragraf_ozgun_kalir():
    tr = list(TR)
    cc.cilala(tr, EN, {}, _uret([{"n": 0, "tr": "Yorgundu."}]), _temiz)
    assert tr[1:] == TR[1:]


def test_ihlal_getiren_paragraf_geri_alinir():
    tr = list(TR)

    def ihlaller(paras):
        return {2} if "Spell" in paras[2] else set()

    m = cc.cilala(tr, EN, {"Spell": "Büyü"}, _uret([{"n": 2, "tr": "Spell söndü."}, {"n": 0, "tr": "Yorgundu."}]), ihlaller)
    assert tr[2] == TR[2] and tr[0] == "Yorgundu."
    assert m["geri_alinan"] == [2]


def test_asiri_kisalan_paragraf_kabul_edilmez():
    tr = list(TR)
    cc.cilala(tr, EN, {}, _uret([{"n": 1, "tr": "Gülümsedi."}]), _temiz)
    assert tr[1] == TR[1]


def test_model_hatasi_ceviriyi_degistirmez():
    tr = list(TR)

    def bozuk(user, system, asama):
        raise RuntimeError("429")

    m = cc.cilala(tr, EN, {}, bozuk, _temiz)
    assert tr == TR and m["durum"] == "cilalanamadi"


def test_korunacak_terimler_yalniz_bolumde_gecenler():
    assert cc.korunacak_terimler({"Spell": "Büyü", "Aspect": "Görünüş", "Sunny": ""}, ["The Spell faded, Sunny said."]) == ["Büyü", "Sunny"]


# ------------------------------------------------ çeviri akışı (CEVIRI_CILALA bayrağı)
from types import SimpleNamespace

from core import translate


def _cevap(veri):
    return SimpleNamespace(text=json.dumps(veri, ensure_ascii=False),
                           candidates=[SimpleNamespace(finish_reason="STOP")])


def _akis(monkeypatch, bayrak):
    monkeypatch.setenv("CEVIRI_KALITE", "0")
    if bayrak is None:
        monkeypatch.delenv("CEVIRI_CILALA", raising=False)
    else:
        monkeypatch.setenv("CEVIRI_CILALA", bayrak)
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    asamalar = []

    def uret(*args, **kwargs):
        asama = translate.api_durum.mevcut_baglam().get("asama") or "ceviri"
        asamalar.append(asama)
        if asama == "cilalama":
            return _cevap({"paragraflar": [{"n": 0, "tr": "Sunny taş kıyıya sessizce çıktı."}]}), "gemini-3.6-flash"
        return _cevap({"translation": "[[1]] Sunny sessizce taş kıyıya çıktı.", "detected_names": [],
                       "detected_terms": {}}), "gemini-3.6-flash"

    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    sonuc = translate.translate_chapter("Sunny quietly reached the stone shore.", "test", models=("gemini-3.6-flash",))
    return sonuc, asamalar


def test_bayrak_kapaliyken_cilalama_cagrisi_yok(monkeypatch):
    sonuc, asamalar = _akis(monkeypatch, None)
    assert "cilalama" not in asamalar
    assert sonuc["translation"] == "Sunny sessizce taş kıyıya çıktı."


def test_bayrak_acikken_okur_cilali_metni_gorur(monkeypatch):
    sonuc, asamalar = _akis(monkeypatch, "1")
    assert asamalar.count("cilalama") == 1
    assert sonuc["translation"] == "Sunny taş kıyıya sessizce çıktı."
