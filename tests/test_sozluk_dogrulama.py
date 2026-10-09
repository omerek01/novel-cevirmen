"""Sözlük MODEL doğrulaması (`core.sozluk_dogrulama`) — çevrimdışı.

Model çağrısı sahtelenir; sınanan şey karar kuralı, yazım kuralları ve para
emniyetidir (ücretli model ASLA kullanılmaz).
"""
from __future__ import annotations

import pytest
import inspect

from core import glossary, sozluk_dogrulama, translate

KITAP = "dogrulama-kitap"


def _satir(source):
    return {r["source"]: r for r in glossary.get_glossary_rows(KITAP)}.get(source)


def test_zincir_yalniz_ucretsiz_ve_kullanici_secimine_bakmaz():
    zincir = sozluk_dogrulama.ucretsiz_zincir()
    assert zincir and not any(translate._ucretli_modeli(m) for m in zincir)
    # Tel tuzağı: arka plan bakım işi kullanıcının seçtiği (ücretli olabilen)
    # zinciri ASLA okumamalı.
    # 2026-10-09 kullanıcı kararı: çeviri akışındaki kontrol SEÇİLİ zinciri kullanır (eski tel tuzağının
    # yerini aldı); bakım aracının varsayılanı hâlâ ücretsiz zincirdir.
    assert "secili_zincir(" in inspect.getsource(sozluk_dogrulama)


def test_geri_ceviri_uyumu_anlam_kaymasini_olcer():
    assert sozluk_dogrulama.geri_ceviri_uyumu("God of Death", "God of War") < 0.5
    assert sozluk_dogrulama.geri_ceviri_uyumu("Hollow", "Hive") == 0.0
    assert sozluk_dogrulama.geri_ceviri_uyumu("Nightmare Seeds", "seeds of the nightmare") == 1.0
    assert sozluk_dogrulama.geri_ceviri_uyumu("Hollow", "") is None


def test_geri_ceviri_karar_vermez_yalniz_bilgidir():
    # Ölçüm: geri çeviri örtüşmesi eş anlamlılarda sahte red üretiyordu
    # (adamantine chitin -> "adamantine shell") ve hiçbir ek hata yakalamadı.
    sonuc, not_ = sozluk_dogrulama.karar_ver(
        {"source": "adamantine chitin", "target": "adamantin kabuk"},
        {"uygun": True, "geri_ceviri": "adamantine shell"},
    )
    assert sonuc == "gecti" and not_["uyum"] < 0.5
    sonuc, not_ = sozluk_dogrulama.karar_ver(
        {"source": "God of Death", "target": "Savaş Tanrısı"},
        {"uygun": False, "geri_ceviri": "God of War", "oneri": "Ölüm Tanrısı"},
    )
    assert sonuc == "sorunlu" and not_["geri_ceviri"] == "God of War"


def test_genel_sozcuk_tek_basina_sorun_degil():
    # Ölçüm: `Echo -> Yankı` sıradan kullanımda da doğru; işaret gürültüydü.
    assert sozluk_dogrulama.karar_ver(
        {"source": "Echo", "target": "Yankı"},
        {"uygun": True, "geri_ceviri": "Echo", "genel_sozcuk": True},
    )[0] == "gecti"


def test_karar_genel_sozcuk_ve_uygun_degil():
    assert sozluk_dogrulama.karar_ver(
        {"source": "Seven", "target": "Yediler"},
        {"uygun": True, "geri_ceviri": "the Seven", "genel_sozcuk": True},
    )[0] == "sorunlu"
    # Geri çeviri birebir tutsa bile modelin "uygun değil" kararı geçerlidir.
    sonuc, not_ = sozluk_dogrulama.karar_ver(
        {"source": "Corruption", "target": "Yolsuzluk"},
        {"uygun": False, "geri_ceviri": "Corruption", "sorun": "Siyasi anlam", "oneri": "Yozlaşma"},
    )
    assert sonuc == "sorunlu" and not_["oneri"] == "Yozlaşma" and not_["uyum"] == 1.0


def test_karar_ingilizce_korunan_ad_gecer():
    assert sozluk_dogrulama.karar_ver(
        {"source": "Sunny", "target": "Sunny"},
        {"uygun": True, "geri_ceviri": "Sunny", "genel_sozcuk": False},
    )[0] == "gecti"


@pytest.mark.skip(reason="Yerini aldı: onay artık kaynak alıntısı ister (sozluk_dogrulama, kaynak bağlı onay). Kapsayan testler: test_sozluk_api_guvenligi.py::test_gecerli_onay_ve_resume_yeniden_cagri_yapmaz, ::test_alintisiz_model_onayi_kural_olmaz")
def test_kitabi_dogrula_yazar_tanimi_bossa_doldurur(monkeypatch):
    glossary.merge_terms(KITAP, {"Corruption": "Yolsuzluk", "Abyss": "Uçurum"}, "auto", 4)
    glossary.tanim_yaz(KITAP, "Abyss", "Kullanıcı tanımı")
    monkeypatch.setattr(translate, "ceviri_anahtari_var_mi", lambda *_a, **_k: True)

    def sahte(kayitlar, api_key="", kitap_basligi="", models=None):
        assert models is None  # ücretsiz zincir varsayılanı kullanılır
        return {
            "Corruption": {"tur": "kavram?", "tanim": "Güç yolunun karanlık hâli", "uygun": False,
                           "geri_ceviri": "Corruption", "sorun": "Siyasi anlam", "oneri": "Yozlaşma"},
            "Abyss": {"tur": "yer", "tanim": "Model tanımı", "uygun": True, "geri_ceviri": "abyss"},
        }

    monkeypatch.setattr(sozluk_dogrulama, "dogrula_parti", sahte)
    sonuc = sozluk_dogrulama.kitabi_dogrula(KITAP, "yeni", api_key="x")
    assert {x["source"]: x["sonuc"] for x in sonuc} == {"Corruption": "sorunlu", "Abyss": "gecti"}
    c, a = _satir("Corruption"), _satir("Abyss")
    assert c["dogrulama"] == "sorunlu" and c["inceleme"] == "bekliyor"
    assert c["tanim"] == "Güç yolunun karanlık hâli" and c["tur"] is None  # tanınmayan tür düşer
    assert c["target"] == "Yolsuzluk"  # doğrulama kaydı DEĞİŞTİRMEZ
    assert a["tanim"] == "Kullanıcı tanımı" and a["tur"] == "yer"
    # İkinci "yeni" turu zaten doğrulananları yeniden sormaz.
    assert sozluk_dogrulama.kitabi_dogrula(KITAP, "yeni", api_key="x") == []


def test_kuru_calistirma_yazmaz(monkeypatch):
    glossary.merge_terms(KITAP, {"Abyss": "Uçurum"}, "auto", 4)
    monkeypatch.setattr(sozluk_dogrulama, "dogrula_parti",
                        lambda *a, **k: {"Abyss": {"uygun": True, "geri_ceviri": "abyss"}})
    assert sozluk_dogrulama.kitabi_dogrula(KITAP, "hepsi", api_key="x", yaz=False)
    assert _satir("Abyss")["dogrulama"] is None


def test_arka_plan_bayrakla_kapanir(monkeypatch):
    monkeypatch.setenv("SOZLUK_DOGRULAMA", "0")
    assert sozluk_dogrulama.arka_planda_dogrula(KITAP) is False


def test_uc_dogrulama_durumu_ve_kapsam_denetimi():
    from fastapi.testclient import TestClient

    import server

    c = TestClient(server.app)
    assert c.post(f"/api/book/{KITAP}/glossary/verify", json={"kapsam": "hepsi"}).json()["basladi"] is False
    assert c.post(f"/api/book/{KITAP}/glossary/verify", json={"kapsam": "her"}).status_code == 400
    assert c.get(f"/api/book/{KITAP}/glossary/verify").json()["acik"] is False


def test_uclar_yasak_tanim_politika():
    from fastapi.testclient import TestClient

    import server

    c = TestClient(server.app)
    c.post(f"/api/book/{KITAP}/glossary", json={"source": "daemon", "target": "daimon"})
    r = c.put(f"/api/book/{KITAP}/glossary/yasak", json={"source": "daemon", "yasaklar": ["Şeytan"]})
    assert r.json()["yasaklar"] == ["Şeytan"]
    assert c.put(f"/api/book/{KITAP}/glossary/yasak", json={"source": "yok", "yasaklar": []}).status_code == 404
    r = c.put(f"/api/book/{KITAP}/glossary/tanim", json={"source": "daemon", "tanim": "Küçük tanrı", "tur": "diger"})
    assert r.json()["kayit"]["tanim"] == "Küçük tanrı"
    assert c.put(f"/api/book/{KITAP}/glossary/politika", json={"politikalar": {"kisi": "ingilizce"}}).json() == {
        "politikalar": {"kisi": "ingilizce"}}
    assert c.put(f"/api/book/{KITAP}/glossary/politika", json={"politikalar": {"kisi": "x"}}).status_code == 400
    veri = c.get(f"/api/book/{KITAP}/glossary").json()
    assert veri["yasaklar"] == {"daemon": ["Şeytan"]} and veri["politikalar"] == {"kisi": "ingilizce"}
