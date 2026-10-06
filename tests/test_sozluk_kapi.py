"""Sözlük YAZMA KAPISI (`core.sozluk_kapi`) ve kapının sözlükle bağlantısı.

Her vaka Shadow Slave sözlüğünün 2026-10-06 incelemesinde ölçülmüş gerçek bir
kayıttır. Meşru kayıtlar için de test var: kapı her şeye uyarırsa görmezden
gelinir (projenin `ISLEV_SOZCUKLERI` dersi).
"""
from __future__ import annotations

import json

from core import cache, glossary, sozluk_kapi, translate

KITAP = "kapi-kitap"


def _satir(source, kitap=KITAP):
    return {r["source"]: r for r in glossary.get_glossary_rows(kitap)}.get(source)


def _neden_turleri(kaynak, hedef, mevcut=(), **kw):
    return [n["tur"] for n in sozluk_kapi.kapi_denetle(kaynak, hedef, list(mevcut), **kw)["nedenler"]]


def _m(kaynak, hedef):
    return {"source": kaynak, "target": hedef}


# ---------- biçim ----------
def test_bicim_ingilizce_iyelik_ve_yalin_olmayan_karsilik():
    assert sozluk_kapi.BICIM in _neden_turleri("Weaver", "Weaver’s")
    assert sozluk_kapi.BICIM in _neden_turleri("Weaver's Mask", "Weaver’s Maskesi")
    assert sozluk_kapi.BICIM in _neden_turleri("Terror of the Crimson Spire", "Kızıl Kule'nin Dehşet'i")
    assert sozluk_kapi.BICIM in _neden_turleri("Anvil of Valor", "Valor'un Anvil'i")
    assert sozluk_kapi.BICIM in _neden_turleri("What? No, wait", "What? No, wait!")


def test_bicim_mesru_kayitlara_dokunmaz():
    for kaynak, hedef in [
        ("Sunny", "Sunny"),  # İngilizce korunan
        ("PTVs", "PTV'ler"),  # kesmeli çoğul meşru
        ("Morgan’s Warbow", "Morgan'ın Savaş Yayı"),
        ("Sunny's Astonishing Emporium", "Sunny'nin Şaşırtıcı Çarşısı"),
        ("Call of the Nightmare", "Kabus'un Çağrısı"),
    ]:
        assert sozluk_kapi.BICIM not in _neden_turleri(kaynak, hedef), kaynak


# ---------- sayı ----------
def test_sayi_tekil_kaynak_cogul_karsilik_ve_tersi():
    for kaynak, hedef in [("Seven", "Yediler"), ("Lost", "Kayıplar"), ("Unknown", "Bilinmeyenler"),
                          ("Eyeless", "Gözsüzler"), ("Chained Island", "Zincirli Adalar"),
                          ("abominations", "ucube")]:
        assert sozluk_kapi.SAYI_UYUMSUZLUGU in _neden_turleri(kaynak, hedef), kaynak


def test_sayi_bas_sozcuge_ve_istisnalara_bakar():
    for kaynak, hedef in [
        ("Chains of Longing", "Özlem Zincirleri"),  # baş: Chains (çoğul)
        ("Lake of Bones", "Kemikler Gölü"),  # baş: Lake (tekil)
        ("Raised by Wolves", "Kurtlar Tarafından Büyütülen"),
        ("Northern Quadrant Corps", "Kuzey Çeyreği Kolordusu"),  # corps tekildir
        ("Doubtless", "Şüphesiz"),  # -ss çoğul değil
        ("Tenacious", "Azimli"),  # -ous
        ("Kuluçka", "Kuluçka"),
        ("Brood beasts", "Kuluçka Mahlukları"),  # iyelikli çoğul
    ]:
        assert sozluk_kapi.SAYI_UYUMSUZLUGU not in _neden_turleri(kaynak, hedef), kaynak


# ---------- varyant ----------
def test_zararsiz_varyant_mevcut_kayda_baglanir():
    for yeni, mevcut, hedef in [
        ("Temple of the Chalice", "Temple of Chalice", "Kadeh Tapınağı"),
        ("The Lord of the Dead", "Lord of the Dead", "Ölülerin Efendisi"),
        ("Puppeteer Shroud", "Puppeteer's Shroud", "Kuklacının Örtüsü"),
    ]:
        sonuc = sozluk_kapi.kapi_denetle(yeni, "başka", [_m(mevcut, hedef)])
        assert sonuc["yazim_of"] == mevcut, yeni


def test_dizilis_varyanti_yalniz_ayni_karsilikta_baglanir():
    assert sozluk_kapi.kapi_denetle("clan Song", "Song klanı", [_m("Song clan", "Song klanı")])["yazim_of"] == "Song clan"
    sonuc = sozluk_kapi.kapi_denetle("Shadows Sense", "Gölge Hissi", [_m("Shadow Sense", "Gölge Duyusu")])
    assert sonuc["yazim_of"] is None
    assert sozluk_kapi.YAKIN_YAZIM in [n["tur"] for n in sonuc["nedenler"]]


def test_tekil_cogul_cifti_mesrudur():
    sonuc = sozluk_kapi.kapi_denetle("Seeds of Nightmare", "Kabus Tohumları", [_m("Seed of Nightmare", "Kabus Tohumu")])
    assert sonuc == {"yazim_of": None, "nedenler": []}


def test_tek_harf_yakinligi_kisa_adlarda_susar():
    assert _neden_turleri("Obel", "Obel", [_m("Abel", "Abel")]) == []
    assert _neden_turleri("Gale", "Gale", [_m("Dale", "Dale"), _m("Vale", "Vale")]) == []
    assert sozluk_kapi.YAKIN_YAZIM in _neden_turleri(
        "Locomotive Chiffonnier", "Hareketli Konsol", [_m("Locomotive Chiffonier", "Gezici Dolap")]
    )


# ---------- ters benzersizlik ----------
def test_iki_ayri_kavram_ayni_karsiligi_alamaz():
    assert sozluk_kapi.KARSILIK_CAKISMASI in _neden_turleri("daemon", "Şeytan", [_m("Devil", "Şeytan")])
    assert sozluk_kapi.KARSILIK_CAKISMASI in _neden_turleri(
        "God of Death", "Savaş Tanrısı", [_m("God of War", "Savaş Tanrısı")]
    )


def test_ingilizce_korunan_ve_varyant_cakisma_sayilmaz():
    assert _neden_turleri("Sunny", "Sunny", [_m("Sunless", "Sunny")]) == []
    assert _neden_turleri("War God", "Savaş Tanrısı", [_m("God of War", "Savaş Tanrısı")]) == []


def test_yasak_karsilik_ve_politika():
    assert sozluk_kapi.YASAK_KARSILIK in _neden_turleri(
        "Hollow", "Kovan", [], yasaklar={"Hollow Mountains": ["Kovan"]}
    )
    assert sozluk_kapi.POLITIKA in _neden_turleri(
        "Changing Star", "Değişen Yıldız", [], politikalar={"kisi": "ingilizce"}, tur="kisi"
    )
    assert _neden_turleri("Sunless", "Sunless", [], politikalar={"kisi": "ingilizce"}, tur="kisi") == []


# ---------- kalıp ----------
def test_kalip_tutarsizligi_azinlik_bicimi_isaretler():
    satirlar = [
        _m("Dormant", "Uykuda"), _m("Dormant Memory", "Uykuda Anı"),
        _m("Dormant Rank", "Uykuda Rütbesi"), _m("Dormant Ability", "Uykudaki Yetenek"),
        _m("Soul Beast", "Ruh Mahluku"), _m("Beast of Twilight", "Alacakaranlık Mahluku"),
        _m("Mirror Beast", "Ayna Mahluğu"),
        # Anlam farkı: ortak kökü yok, işaretlenmez.
        _m("Great Clan", "Büyük Klan"), _m("Great Devil", "Ulu Şeytan"), _m("Great Titan", "Ulu Titan"),
    ]
    sonuc = sozluk_kapi.kalip_tutarsizliklari(satirlar)
    assert set(sonuc) == {"Dormant Ability", "Mirror Beast"}


# ---------- sözlüğe bağlantı ----------
def test_kapiya_takilan_aday_tutulur_prompta_girmez():
    eklenen = glossary.merge_terms(KITAP, {"Weaver": "Weaver’s", "Abyss": "Uçurum"}, "auto", 5)
    assert eklenen == {"Abyss": "Uçurum"}  # künye yalnız etkili olanı yazar
    satir = _satir("Weaver")
    assert satir["durum"] == glossary.TUTULDU and satir["inceleme"] == "bekliyor"
    assert json.loads(satir["kapi"])[0]["tur"] == sozluk_kapi.BICIM
    assert "Weaver" not in glossary.ceviri_sozlugu(KITAP)
    assert "Abyss" in glossary.ceviri_sozlugu(KITAP)
    # Tutulan aday sonraki bölümde yeniden eklenmez / tutulmaz (satır duruyor).
    assert glossary.merge_terms(KITAP, {"Weaver": "Weaver’s"}, "auto", 6) == {}


def test_onay_tutulani_kurala_cevirir_ve_surumu_artirir():
    glossary.merge_terms(KITAP, {"Weaver": "Weaver’s"}, "auto", 5)
    once = glossary.kitap_surumu(KITAP)
    assert glossary.onayla(KITAP, "Weaver")
    satir = _satir("Weaver")
    assert satir["durum"] is None and satir["inceleme"] == "onaylandi"
    assert "Weaver" in glossary.ceviri_sozlugu(KITAP)
    assert glossary.kitap_surumu(KITAP) > once
    assert glossary.gecmis(KITAP, "Weaver")[0]["islem"] == "guncelle"


def test_elle_duzeltme_tutulani_serbest_birakir():
    glossary.merge_terms(KITAP, {"Weaver": "Weaver’s"}, "auto", 5)
    glossary.terimi_yaz(KITAP, "Weaver", "Weaver")
    satir = _satir("Weaver")
    assert satir["durum"] is None and satir["kapi"] is None
    assert glossary.ceviri_sozlugu(KITAP)["Weaver"] == "Weaver"


def test_varyant_aday_mevcut_kayda_yazim_olarak_baglanir():
    glossary.set_term(KITAP, "Temple of Chalice", "Kadeh Tapınağı")
    eklenen = glossary.merge_terms(KITAP, {"Temple of the Chalice": "Kadeh Mabedi"}, "auto", 7)
    assert eklenen == {}
    assert _satir("Temple of the Chalice") is None
    assert glossary.ekler(KITAP)["Temple of Chalice"]["yazimlar"] == ["Temple of the Chalice"]
    assert glossary.ceviri_sozlugu(KITAP)["Temple of the Chalice"] == "Kadeh Tapınağı"


def test_ayni_yanittaki_iki_aday_birbirini_gorur():
    glossary.merge_terms(KITAP, {"Devil": "Şeytan", "daemon": "Şeytan"}, "auto", 3)
    assert _satir("Devil")["durum"] is None
    assert _satir("daemon")["durum"] == glossary.TUTULDU


def test_elle_ve_ice_aktarma_kapidan_gecmez():
    glossary.merge_terms(KITAP, {"Weaver": "Weaver’s"}, "import")
    assert _satir("Weaver")["durum"] is None


def test_kisi_adi_kapidan_gecer():
    assert glossary.merge_names(KITAP, ["Nephis", "Cassie"], "auto", 2) == {"Nephis": "Nephis", "Cassie": "Cassie"}


# ---------- yasak karşılık ----------
def test_isaret_glossary_ile_translate_ayni():
    assert glossary.YASAK_ISARETI == translate.YASAK_ISARETI


def test_yasak_prompta_cikar_ama_kaydi_kosullu_yapmaz():
    glossary.set_term(KITAP, "daemon", "daimon")
    assert glossary.yasaklari_yaz(KITAP, "daemon", ["Şeytan", "daimon"]) == ["Şeytan"]  # kendi karşılığı düşer
    kosullar = glossary.ceviri_kosullari(KITAP)
    assert translate._gercek_kosul(kosullar["daemon"]) == ""
    prompt = translate._build_user_prompt(["The daemon smiled."], glossary.ceviri_sozlugu(KITAP), "", kosullar)
    assert 'daemon -> daimon  [YASAK: "Şeytan"]' in prompt
    assert "ASLA yazılmaz" in prompt
    # Yasak taşıyan kayıt uyum denetiminde KALIR (koşullu sayılmaz).
    ihlal = translate.sozluk_ihlalleri(glossary.ceviri_sozlugu(KITAP), "The daemon smiled.",
                                       "The daemon gülümsedi.", kosullar)
    assert ihlal == {"daemon": "daimon"}


def test_yasak_yokken_prompt_bayt_bayt_ayni():
    glossary.set_term(KITAP, "Spell", "Büyü")
    sozluk = glossary.ceviri_sozlugu(KITAP)
    a = translate._build_user_prompt(["The Spell spoke."], sozluk, "", glossary.ceviri_kosullari(KITAP))
    b = translate._build_user_prompt(["The Spell spoke."], sozluk, "", {})
    assert a == b and "YASAK" not in a


def test_yasak_karsiligi_kapida_yeni_adaya_verilmez():
    glossary.set_term(KITAP, "Hollow Mountains", "Oyuk Dağlar")
    glossary.yasaklari_yaz(KITAP, "Hollow Mountains", ["Kovan Dağları"])
    glossary.merge_terms(KITAP, {"Hollow Range": "Kovan Dağları"}, "auto", 9)
    assert _satir("Hollow Range")["durum"] == glossary.TUTULDU


# ---------- politika ve inceleme ----------
def test_politika_yazimi_ve_dogrulamasi():
    assert glossary.politikalari_yaz(KITAP, {"kisi": "ingilizce"}) == {"kisi": "ingilizce"}
    assert glossary.politikalari_yaz(KITAP, {"kisi": None}) == {}
    import pytest
    with pytest.raises(ValueError):
        glossary.politikalari_yaz(KITAP, {"kisi": "almanca"})
    with pytest.raises(ValueError):
        glossary.politikalari_yaz(KITAP, {"uzayli": "turkce"})


def test_inceleme_listesi_kapi_dogrulama_politika_nedenlerini_gosterir():
    glossary.merge_terms(KITAP, {"Weaver": "Weaver’s"}, "auto", 5)
    glossary.set_term(KITAP, "God of Death", "Savaş Tanrısı")
    glossary.dogrulama_yaz(KITAP, "God of Death", "sorunlu",
                           {"geri_ceviri": "God of War", "sorun": "Anlam kaymış.", "oneri": "Ölüm Tanrısı"})
    glossary.terimi_yaz(KITAP, "Changing Star", "Değişen Yıldız", tur="kisi")
    glossary.politikalari_yaz(KITAP, {"kisi": "ingilizce"})
    liste = {x["source"]: [n["tur"] for n in x["nedenler"]] for x in glossary.inceleme_listesi(KITAP)}
    assert liste["Weaver"] == [sozluk_kapi.BICIM]
    assert sozluk_kapi.DOGRULAMA in liste["God of Death"]
    assert sozluk_kapi.POLITIKA in liste["Changing Star"]
    # Biçim hatası listenin başında.
    assert glossary.inceleme_listesi(KITAP)[0]["source"] == "Weaver"


def test_dogrulama_onaylanmis_kaydi_yeniden_incelemeye_dusurmez():
    glossary.set_term(KITAP, "Fool", "Aptal")
    glossary.onayla(KITAP, "Fool")
    glossary.dogrulama_yaz(KITAP, "Fool", "sorunlu", {"sorun": "Sıradan sözcük"})
    assert _satir("Fool")["inceleme"] == "onaylandi"
    assert "Fool" not in {x["source"] for x in glossary.inceleme_listesi(KITAP)}


def test_tanim_yalniz_bossa_kullaniciyi_ezmez():
    glossary.set_term(KITAP, "Hollow", "Oyuk")
    glossary.tanim_yaz(KITAP, "Hollow", "Antarktika'daki dağ silsilesi", "yer")
    glossary.tanim_yaz(KITAP, "Hollow", "model tanımı", "nesne", yalniz_bossa=True)
    satir = _satir("Hollow")
    assert satir["tanim"] == "Antarktika'daki dağ silsilesi" and satir["tur"] == "yer"


def test_kapi_isaretle_kurali_prompttan_cikarmaz():
    glossary.set_term(KITAP, "Seven", "Yediler")
    glossary.kapi_isaretle(KITAP, {"Seven": [{"tur": "sayi_uyumsuzlugu", "aciklama": "x", "ilgili": []}]})
    satir = _satir("Seven")
    assert satir["durum"] is None and satir["inceleme"] == "bekliyor"
    assert "Seven" in glossary.ceviri_sozlugu(KITAP)


# ---------- ihlal şüphesi ----------
def test_ihlal_suphesi_bugunku_olcutle_yeniden_olcer():
    glossary.set_term(KITAP, "Fool", "Aptal")
    glossary.set_term(KITAP, "Saint", "Aziz")
    for no, model in ((1, "gemini-3.6-flash"), (2, "gemini-3.6-flash"), (3, "gemini-3.5-flash-lite")):
        cache.save_chapter(f"https://x/{no}", {
            "book_slug": KITAP, "book_title": "K", "title": f"B{no}", "chapter_no": no,
            "translation": "The Fool güldü.", "source": "The Fool laughed.", "model": model,
            # Saklı bayrak SAHTE bir ihlal de içeriyor: yeniden ölçümde düşmeli.
            "glossary_leaks": {"Fool": "Aptal", "Saint": "Aziz"},
        })
    sonuc = sozluk_kapi.ihlal_supheleri(KITAP)
    assert set(sonuc) == {"Fool"}  # lite kanıt sayılmaz, Saint bugün ihlal değil
    assert sonuc["Fool"]["bolumler"] == [1, 2]


def test_sozlugu_denetle_geriye_donuk_birlestirme_ve_bicim():
    satirlar = [_m("Fire", "Ateş"), _m("The Fire", "Ateş"), _m("Weaver", "Weaver’s"),
                _m("Devil", "Şeytan"), _m("daemon", "Şeytan")]
    sonuc = sozluk_kapi.sozlugu_denetle(satirlar)
    assert sozluk_kapi.YAKIN_YAZIM in [n["tur"] for n in sonuc["Fire"]]
    assert sozluk_kapi.BICIM in [n["tur"] for n in sonuc["Weaver"]]
    assert sozluk_kapi.KARSILIK_CAKISMASI in [n["tur"] for n in sonuc["daemon"]]


def test_genel_sozcuk_sikligi_kitabin_kaynagindan():
    korpus = "Seven days passed. The seven of them waited. Then the Seven arrived. " * 3
    kucuk, buyuk = sozluk_kapi.genel_sozcuk_sikligi("Seven", korpus)
    assert kucuk == 3 and buyuk == 3
    assert sozluk_kapi.genel_sozcuk_sikligi("Hollow Mountains", korpus) is None
