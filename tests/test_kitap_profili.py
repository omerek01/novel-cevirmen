"""Kitap profili koddan veriye (Faz 1): davranış değişmez, DB tek okuma noktası."""
from core import kitap_profili, sozluk_kapi
from core import varlik_grafigi as vg

SS = "shadow-slave"


def test_ss_profili_dbden_koddakiyle_birebir_ayni():
    assert vg.profil(SS) == vg.KITAP_PROFILLERI[SS]


def test_profilsiz_kitap_none():
    assert vg.profil("yeni-kitap") is None


def test_elle_duzeltme_sistemi_ezer_ve_kod_esitlemesi_onu_silmez(monkeypatch):
    vg.profil(SS)
    kitap_profili.yaz(SS, "ek_rutbeler", ["Deneme"], origin="manual")
    assert vg.profil(SS)["ek_rutbeler"] == ("Deneme",)
    # Kod kaydı değişti (geliştirici düzeltmesi): sistem satırı eşitlenir, elle satır kalır.
    yeni = dict(vg.KITAP_PROFILLERI[SS], ana_karakter="Baskasi")
    monkeypatch.setitem(vg.KITAP_PROFILLERI, SS, yeni)
    p = vg.profil(SS)
    assert p["ana_karakter"] == "Baskasi" and p["ek_rutbeler"] == ("Deneme",)


def test_koddan_kalkan_alan_dbden_de_kalkar(monkeypatch):
    vg.profil(SS)
    yeni = {k: v for k, v in vg.KITAP_PROFILLERI[SS].items() if k != "sabit_baglar"}
    monkeypatch.setitem(vg.KITAP_PROFILLERI, SS, yeni)
    assert "sabit_baglar" not in vg.profil(SS)


def test_aday_profile_girmez_onaylaninca_girer():
    kitap_profili.yaz("yeni-kitap", "ana_karakter", "Mara", origin="model", durum="aday")
    assert vg.profil("yeni-kitap") is None
    assert kitap_profili.durum_yaz("yeni-kitap", "ana_karakter", "model", "onayli")
    assert vg.profil("yeni-kitap") == {"ana_karakter": "Mara"}


def test_dbdeki_dizi_sozluk_kapisina_ulasir():
    """Kod kaydı OLMAYAN kitap: profil yalnız DB'deyken de rütbe+sınıf birleşimi tanınır."""
    mevcut = [{"source": "Novice", "target": "Acemi"}, {"source": "Wolf", "target": "Kurt"}]
    # Profil yokken birleşim tanınmaz (bugünkü davranış: profilsiz kitapta sessiz).
    assert not sozluk_kapi.rutbe_sinif_birlesimi("Novice Wolf", "Acemi Kurt", mevcut, "yeni-kitap")
    kitap_profili.yaz("yeni-kitap", "diziler", {"insan_rutbesi": ["Novice"], "yaratik_sinifi": ["Wolf"]})
    assert sozluk_kapi.rutbe_sinif_birlesimi("Novice Wolf", "Acemi Kurt", mevcut, "yeni-kitap")
    assert not sozluk_kapi.rutbe_sinif_birlesimi("Novice Wolf", "Acemi Ayı", mevcut, "yeni-kitap")


# Faz 1 öncesindeki sabit istemlerin (DEFTER_TALIMATI, CIKARIM_INSTRUCTION, CIFT_INSTRUCTION)
# sha256'sı. SS istemi profilden kurulunca bayt bayt aynı kalmalı; SS istemini BİLEREK
# değiştiren iş bu özetleri günceller (ve istem sürümünü düşünür).
_SS_ISTEM_OZETLERI = {
    "defter": "35d29a39c8e19be53a189a95138f2573efdefb45f6167f36eefa50adb10228a9",  # defter-v3: durum değişimleri (`d`)
    "cikarim": "65fd351d3f47f98bfac7b6aa31a13d0c90cb811cfb00276270020bc3e9a3e1fa",
    "cift": "b0a39c99a89ed7c39c1d8ec3fd5f9086a9784b2440b41b589424385bff38bdce",
}


def _istemler(slug):
    from core import karakter_defteri, varlik_cikarim

    return {"defter": karakter_defteri.defter_talimati(slug),
            "cikarim": varlik_cikarim.cikarim_talimati(slug),
            "cift": varlik_cikarim.cift_talimati(slug)}


def test_ss_istemleri_profilden_bayt_bayt_ayni():
    import hashlib

    ozet = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in _istemler(SS).items()}
    assert ozet == _SS_ISTEM_OZETLERI


def test_profilsiz_kitap_isteminde_ss_izi_yok():
    for ad, metin in _istemler("yeni-kitap").items():
        for iz in ("Sunny", "Nephis", "Spell", "True Name", "Saint", "$"):
            assert iz not in metin, (ad, iz)
    assert "gercek_adi KULLANMA" in _istemler("yeni-kitap")["defter"]


def test_istem_ornekleri_ve_iddialar_dbdeki_profilden():
    kitap_profili.yaz("yeni-kitap", "istem_ornekleri", {"defter_rutbe": "Novice, Adept…"})
    kitap_profili.yaz("yeni-kitap", "sistem_sesi", ["System"])
    kitap_profili.yaz("yeni-kitap", "gercek_ad_sozcugu", ["Soul Name"])
    ist = _istemler("yeni-kitap")
    assert "(Novice, Adept…)" in ist["defter"] and "Ada ogretmeni Marcus" in ist["defter"]  # eksik: nötr
    assert 'konuşan "System"' in ist["defter"] and 'metin "Soul Name" dediğinde' in ist["defter"]
    assert "Gerçek Adı (Soul Name)" in ist["cikarim"] and "metnin 'Soul Name' dediği ad" in ist["cikarim"]
    assert "gercek_adi yalnız metnin 'Soul Name' dediği addır" in ist["cift"]
