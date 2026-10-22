"""Defter kayıtları (`core.defter_kayit`): rün mesajlarından anı/efsun/nitelik/gölge/yankı/
yaratık/rün listesi ve kullanıcının elle düzeltmeleri — çevrimdışı.

Rün metinleri Shadow Slave'in mesaj BİÇİMİNİ taklit eden kısa yapay örneklerdir."""
from __future__ import annotations

import time

from core import cache, defter_kayit as dk, glossary

KITAP = "shadow-slave"  # rün profili bu slug'a bağlı

RUNLER = """He looked at the runes.

Name: Sunless.

True Name: Lost from Light.

Rank: Dreamer.

Memories: [Silver Bell], [Azure Blade].

Attributes: [Fated].

Aspect: [Shadow Slave].

Aspect Rank: Divine.

He smiled.

Memory: [Azure Blade].

Memory Rank: Awakened.

Memory Tier: I.

Memory Type: Weapon.

Memory Enchantments: [Sharp], [Doubtless].

Enchantment Description: [“The blade never dulls.”]

Enchantment Description: [Protects the wielder from mind attacks.]

Then the voice of the Spell came.

[You have slain an awakened monster, Rolling Stone..]

Shadow: [Stone Saint].

Shadow Rank: Awakened.

Shadow Class: Monster.

Shadow Attributes: [Stalwart]."""

SONRA = """Name: Sunless.

Rank: Awakened.

Memory: [Dark Wing].

Memory Rank: Awakened.

[You have slain an Ascended human, Hilde.]"""


def _bolum(no, kaynak):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"https://x/{no}", KITAP, no, "çeviri", kaynak, time.time()),
    )
    conn.commit()
    conn.close()


def _kitap():
    _bolum(16, RUNLER)
    _bolum(30, SONRA)
    return dk.cikar(KITAP)


def _bul(gorunum, tur, ad, sahip=None):
    for k in gorunum["kayitlar"][tur]:
        if k["ad"] == ad and (sahip is None or k["sahip"] == sahip):
            return k
    return None


def test_run_mesajlari_kayitlara_doner_sozlukte_olmasa_da():
    _kitap()
    g = dk.gorunum(KITAP, None)
    azure = _bul(g, "ani", "Azure Blade", "Sunny")
    assert azure and azure["ilk_bolum"] == 16
    assert azure["alanlar"] == {"rutbe": "Awakened", "kademe": "I", "tur": "Weapon"}
    assert _bul(g, "ani", "Silver Bell", "Sunny")
    assert _bul(g, "efsun", "Sharp", "Azure Blade")["alanlar"]["aciklama"] == "The blade never dulls."
    assert _bul(g, "efsun", "Doubtless", "Azure Blade")["alanlar"]["aciklama"] == "Protects the wielder from mind attacks."
    saint = _bul(g, "golge", "Stone Saint", "Sunny")
    assert saint["alanlar"]["rutbe"] == "Awakened" and saint["alanlar"]["sinif"] == "Monster"
    assert saint["alanlar"]["nitelikler"] == ["Stalwart"]
    tas = _bul(g, "yaratik", "Rolling Stone", "Sunny")
    assert tas["alanlar"] == {"rutbe": "awakened", "sinif": "monster"}
    assert _bul(g, "nitelik", "Fated", "Sunny")
    assert _bul(g, "alan", "gercek_adi", "Sunny")["deger"] == "Lost from Light"
    # İnsan öldürmek yaratık değildir; ayrı sınıfla tutulur ama yaratık listesine girmez.
    assert _bul(g, "yaratik", "Hilde") is None


def test_spoiler_konumdan_sonrasini_gizler_ve_rutbe_gecmisini_izler():
    _kitap()
    once = dk.gorunum(KITAP, 20)
    assert _bul(once, "alan", "rutbesi", "Sunny")["deger"] == "Dreamer"
    assert _bul(once, "ani", "Dark Wing") is None
    sonra = dk.gorunum(KITAP, 30)
    assert _bul(sonra, "alan", "rutbesi", "Sunny")["deger"] == "Awakened"
    assert _bul(sonra, "ani", "Dark Wing", "Sunny")


def test_cikarim_tekrarlaninca_ayni_kalir():
    _kitap()
    ilk = dk.gorunum(KITAP, None)
    dk.cikar(KITAP)
    assert dk.gorunum(KITAP, None) == ilk


def test_tek_bolum_akisi_mevcut_kayitlarla_birlesir():
    _bolum(16, RUNLER)
    dk.bolumden(KITAP, 30, SONRA)
    dk.bolumden(KITAP, 16, RUNLER)
    g = dk.gorunum(KITAP, None)
    assert _bul(g, "ani", "Dark Wing", "Sunny")["ilk_bolum"] == 30
    assert _bul(g, "ani", "Azure Blade", "Sunny")["ilk_bolum"] == 16
    assert _bul(g, "alan", "rutbesi", "Sunny")["deger"] == "Awakened"


def test_sozluk_karsiligi_kayda_eklenir():
    glossary.set_term(KITAP, "Azure Blade", "Gök Mavisi Bıçak")
    _kitap()
    assert _bul(dk.gorunum(KITAP, None), "ani", "Azure Blade")["tr"] == "Gök Mavisi Bıçak"
    assert _bul(dk.gorunum(KITAP, None), "ani", "Silver Bell")["tr"] is None


def test_elle_kayit_eklenir_ve_cikarim_onu_degistirmez():
    _kitap()
    dk.elle_yaz(KITAP, {"tur": "ani", "sahip": "Sunny", "ad": "Endless Spring", "ilk_bolum": 18,
                        "alanlar": {"tur": "Tool"}})
    dk.cikar(KITAP)
    k = _bul(dk.gorunum(KITAP, None), "ani", "Endless Spring", "Sunny")
    assert k["origin"] == "elle" and k["alanlar"] == {"tur": "Tool"}
    assert _bul(dk.gorunum(KITAP, 17), "ani", "Endless Spring") is None


def test_sistem_kaydini_elle_duzeltmek_yerini_alir_ve_geri_gelmez():
    _kitap()
    eski = _bul(dk.gorunum(KITAP, None), "ani", "Azure Blade")
    dk.elle_yaz(KITAP, {"tur": "ani", "sahip": "Sunny", "ad": "Azure Blade",
                        "alanlar": {"rutbe": "Dormant", "tur": "Weapon"}}, yerine=eski["anahtar"])
    dk.cikar(KITAP)
    k = _bul(dk.gorunum(KITAP, None), "ani", "Azure Blade")
    assert k["origin"] == "elle" and k["alanlar"]["rutbe"] == "Dormant"
    assert k["ilk_bolum"] == 16  # bölüm verilmezse eski kaydınki korunur
    # Ad değişirse eski ad bir daha görünmez.
    dk.elle_yaz(KITAP, {"tur": "ani", "sahip": "Sunny", "ad": "Azure Sword"}, yerine=k["anahtar"])
    dk.cikar(KITAP)
    g = dk.gorunum(KITAP, None)
    assert _bul(g, "ani", "Azure Blade") is None and _bul(g, "ani", "Azure Sword")


def test_kaldirilan_sistem_kaydi_cikarimla_dirilmez_geri_alinabilir():
    _kitap()
    k = _bul(dk.gorunum(KITAP, None), "ani", "Silver Bell")
    dk.kaldir(KITAP, k["anahtar"])
    dk.cikar(KITAP)
    assert _bul(dk.gorunum(KITAP, None), "ani", "Silver Bell") is None
    dk.geri_al(KITAP, k["anahtar"])
    assert _bul(dk.gorunum(KITAP, None), "ani", "Silver Bell")["origin"] == "sistem"


def test_elle_eklenen_kayit_kaldirilinca_tumden_silinir():
    dk.elle_yaz(KITAP, {"tur": "yanki", "sahip": "Sunny", "ad": "Blackie"})
    k = _bul(dk.gorunum(KITAP, None), "yanki", "Blackie")
    dk.kaldir(KITAP, k["anahtar"])
    assert _bul(dk.gorunum(KITAP, None), "yanki", "Blackie") is None


def test_gecersiz_elle_kayit_reddedilir():
    import pytest

    with pytest.raises(ValueError):
        dk.elle_yaz(KITAP, {"tur": "bilinmez", "ad": "X"})
    with pytest.raises(ValueError):
        dk.elle_yaz(KITAP, {"tur": "ani", "ad": "  "})


def test_gorunus_rutbesi_sahibine_baglanir_ad_ve_aciklama_temizlenir():
    _kitap()
    g = dk.gorunum(KITAP, None)
    assert _bul(g, "alan", "gorunusu", "Sunny")["deger"] == "Shadow Slave"
    assert _bul(g, "alan", "gorunus_rutbesi", "Sunny")["deger"] == "Divine"
    assert not [k for k in g["kayitlar"]["alan"] if k["sahip"] == "Shadow Slave"]
    assert _bul(g, "efsun", "Sharp")["alanlar"]["aciklama"] == "The blade never dulls."
    assert _bul(g, "yaratik", "Rolling Stone")


def test_ceviri_akisi_bolumun_runlerini_deftere_katar():
    from core import pipeline

    pipeline._sozluge_isle(KITAP, {"detected_names": [], "detected_terms": []}, 16, RUNLER)
    assert _bul(dk.gorunum(KITAP, None), "ani", "Azure Blade", "Sunny")


# ---------- başlıksız sayaçlar (2026-10-15, kullanıcı bildirimi: 848'den sonra güncellenmedi) ----------
BOLUM_848 = """Name: Sunless.

Shadow Fragments: [777/4000].

Shadow: [Marble Saint].

Shadow Fragments: [44/200].

Shadow Abilities: [Weapon Sage], [Underworld Armament]."""

BOLUM_989 = """As he walked, Sunny decided to check on his runes out of boredom.

Shadow Fragments: [2471/4000].

Next, Sunny checked on Saint.

Shadow Fragments: [146/200]."""


def _sayaclari_dogrula():
    g = dk.gorunum(KITAP, None)
    assert _bul(g, "alan", "Shadow Fragments", "Sunny")["deger"] == "2471/4000"
    saint = _bul(g, "golge", "Marble Saint", "Sunny")
    assert saint["alanlar"]["Shadow Fragments"] == "146/200"
    assert set(saint["alanlar"]["yetenekler"]) == {"Weapon Sage", "Underworld Armament"}
    # Spoiler: 900. bölümdeki okur sonraki sayıyı görmez.
    once = dk.gorunum(KITAP, 900)
    assert _bul(once, "alan", "Shadow Fragments", "Sunny")["deger"] == "777/4000"
    assert _bul(once, "golge", "Marble Saint", "Sunny")["alanlar"]["Shadow Fragments"] == "44/200"


def test_basliksiz_sayaclar_dogru_sahibe_yazilir_bastan_kurulumda():
    _bolum(848, BOLUM_848)
    _bolum(989, BOLUM_989)
    dk.cikar(KITAP)
    _sayaclari_dogrula()


def test_basliksiz_sayaclar_tek_bolum_akisinda_da_dogru_sahibe_yazilir():
    # Çeviri akışı bölümü tek başına görür; paydaların sahipleri defterden okunur.
    dk.bolumden(KITAP, 848, BOLUM_848)
    dk.bolumden(KITAP, 989, BOLUM_989)
    _sayaclari_dogrula()


# ---------- Tam liste (envanter): kaybedilen/evrimleşen öğe güncel sayılmaz ----------
ENVANTER_SONRA = """Name: Sunless.

Memories: [Silver Bell], [Dark Wing].

Shadows: [Marble Saint].

Attributes: [Fated], [Ember of Divinity].

Echoes: —"""


def test_ayristirici_yalniz_tam_listeyi_envanter_sayar():
    from core.runler import ENVANTER, shadow_slave as ss
    tam = ss.sistem_baglarini_bul("Name: Sunless.\n\nMemories: [Silver Bell], [M... Un...old].\n\nEchoes: —",
                                  "Sunny", ("Sunless",))
    envanter = {n.split("\t")[0]: n.split("\t")[1] for o, i, n, _k in tam if i == ENVANTER}
    assert envanter == {"ani": '["Silver Bell", "M... Un...old"]', "yanki": "[]"}
    kesik = ss.sistem_baglarini_bul("Name: Sunless.\n\nMemories: [Silver Bell], [Endless Spring]...",
                                    "Sunny", ("Sunless",))
    assert all(i != ENVANTER for _o, i, _n, _k in kesik)


def _elde(g, tur, ad):
    return (_bul(g, tur, ad) or {}).get("alanlar", {}).get("elde", "var")


def _envanter_dogrula():
    g = dk.gorunum(KITAP, None)
    # 16: Azure Blade; 40'taki tam listede yok -> kaybedildi. Silver Bell listede kalır.
    assert _elde(g, "ani", "Azure Blade") == "yok" and _elde(g, "ani", "Silver Bell") == "var"
    assert _elde(g, "golge", "Stone Saint") == "yok" and _elde(g, "golge", "Marble Saint") == "var"
    assert _elde(g, "nitelik", "Fated") == "var"
    # Spoiler: konum listeden önceyse kayıp henüz bilinmez.
    assert _elde(dk.gorunum(KITAP, 39), "ani", "Azure Blade") == "var"


def test_tam_liste_disindaki_oge_artik_yok_sayilir_bastan_kurulumda():
    _bolum(16, RUNLER)
    _bolum(40, ENVANTER_SONRA)
    dk.cikar(KITAP)
    _envanter_dogrula()


def test_tam_liste_tek_bolum_akisinda_da_uygulanir_ve_geri_donen_var_olur():
    _bolum(16, RUNLER)
    dk.cikar(KITAP)
    dk.bolumden(KITAP, 40, ENVANTER_SONRA)
    _envanter_dogrula()
    dk.bolumden(KITAP, 60, "Name: Sunless.\n\nMemories: [Silver Bell], [Azure Blade], [Dark Wing].")
    assert _elde(dk.gorunum(KITAP, None), "ani", "Azure Blade") == "var"
    assert _elde(dk.gorunum(KITAP, 50), "ani", "Azure Blade") == "yok"


def test_alan_son_goruldugu_bolumu_konuma_gore_tasir():
    # Canlı: kart "4/7 · bölüm 702" diyordu; 1026'da yeniden görüldüğü, sonra hiç görülmediği bilinmiyordu.
    _bolum(16, RUNLER)
    _bolum(30, "Name: Sunless.\n\nRank: Dreamer.")
    dk.cikar(KITAP)
    dk.bolumden(KITAP, 45, "Name: Sunless.\n\nRank: Dreamer.")
    rutbe = lambda konum: next(k for k in dk.gorunum(KITAP, konum)["kayitlar"]["alan"] if k["ad"] == "rutbesi")
    assert (rutbe(None)["ilk_bolum"], rutbe(None)["son_bolum"]) == (16, 45)
    assert rutbe(40)["son_bolum"] == 30  # 45 konumdan sonra: spoiler değil


def test_golgeye_donusen_yanki_artik_yanki_sayilmaz():
    _bolum(1047, "Name: Sunless.\n\nEchoes: [Ravenous Fiend].")
    _bolum(1080, "Name: Sunless.\n\nShadows: [Onyx Saint], [Ravenous Fiend].")
    dk.cikar(KITAP)
    assert _elde(dk.gorunum(KITAP, None), "yanki", "Ravenous Fiend") == "yok"
    assert _elde(dk.gorunum(KITAP, None), "golge", "Ravenous Fiend") == "var"
    assert _elde(dk.gorunum(KITAP, 1050), "yanki", "Ravenous Fiend") == "var"
