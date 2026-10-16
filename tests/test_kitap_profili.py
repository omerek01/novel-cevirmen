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
