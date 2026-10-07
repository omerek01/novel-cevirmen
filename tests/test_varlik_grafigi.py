"""Varlık grafiği (`core.varlik_grafigi`) — çevrimdışı.

Rün metinleri Shadow Slave'in mesaj BİÇİMİNİ taklit eden kısa yapay örneklerdir
(roman metni değil). Gerçek veride ölçülen davranış: sunucu kopyasında 189 tekil
sistem bağı, kalite kurallarında 19 bulgu.
"""
from __future__ import annotations

from core import cache, glossary, library, varlik_grafigi as vg

KITAP = "shadow-slave"  # profil bu slug'a bağlı

RUNLER = """He looked at the runes.

Name: Sunless.

True Name: Lost from Light.

Rank: Dreamer.

Memories: [Silver Bell], [Azure Blade].

Attributes: [Fated].

He smiled.

Memory: [Azure Blade].

Memory Rank: Awakened.

Then the voice of the Spell came.

[You have slain an awakened monster, Rolling Stone.]

Shadow: [Stone Saint].

Shadow Rank: Awakened.

Shadow Class: Monster."""


def _sozluk():
    for k, v in {
        "Sunny": "Sunny", "Sunless": "Sunless", "Lost from Light": "Işıktan Mahrum",
        "Dreamer": "Rüyacı", "Silver Bell": "Gümüş Çan", "Azure Blade": "Gök Mavisi Bıçak",
        "Fated": "Yazgılı", "Awakened": "Uyanmış", "Monster": "Canavar", "Rolling Stone": "Yuvarlanan Taş",
        "Stone Saint": "Taş Aziz", "beast": "Mahluk", "Dormant": "Uykuda",
    }.items():
        glossary.set_term(KITAP, k, v)


def _bag_kumesi(**kw):
    return {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar(KITAP, **kw)}


def test_run_bloklari_dogru_ozneye_baglanir():
    bulunan = {(o, i, n) for o, i, n, _k in vg.sistem_baglarini_bul(RUNLER, "Sunny", ("Sunless",))}
    assert {
        ("Sunny", "gercek_adi", "Lost from Light"), ("Sunny", "rutbesi", "Dreamer"),
        ("Sunny", "anisi", "Silver Bell"), ("Sunny", "anisi", "Azure Blade"),
        ("Sunny", "niteligi", "Fated"), ("Azure Blade", "rutbesi", "Awakened"),
        ("Sunny", "oldurdu", "Rolling Stone"), ("Rolling Stone", "rutbesi", "awakened"),
        ("Rolling Stone", "sinifi", "monster"), ("Sunny", "golgesi", "Stone Saint"),
        ("Stone Saint", "rutbesi", "Awakened"), ("Stone Saint", "sinifi", "Monster"),
    } <= bulunan
    assert ("Sunny", "rutbesi", "Awakened") not in bulunan


def test_duz_paragraf_run_blogunu_kapatir():
    # Düz paragraftan sonra gelen rün biçimli satır önceki bloğun öznesine
    # bağlanmamalı (başka bir şeyin rünü ya da diyalog olabilir).
    metin = "Name: Sunless.\n\nRank: Dreamer.\n\nHe thought for a while.\n\nRank: Awakened."
    bulunan = {(o, i, n) for o, i, n, _k in vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))}
    assert bulunan == {("Sunny", "rutbesi", "Dreamer")}


def test_bolum_akisi_bag_yazar_ve_cozulemeyen_adi_atlar():
    _sozluk()
    assert vg.bolumden_sistem_baglari(KITAP, 16, RUNLER + "\n\nMemory: [Unknown Thing].") > 0
    baglar = _bag_kumesi()
    assert ("Sunny", "anisi", "Azure Blade") in baglar
    assert not any(b[2] == "Unknown Thing" for b in baglar)
    assert vg.bolumden_sistem_baglari("baska-kitap", 1, RUNLER) == 0  # profilsiz kitap


def test_ilk_bolum_yalniz_kuculur_ve_red_dirilmez():
    _sozluk()
    cozucu = vg.DugumCozucu(KITAP)
    a, b = cozucu.coz("Sunny"), cozucu.coz("Silver Bell")
    vg.bag_ekle(KITAP, a, "anisi", b, 50, "geç", "model", 0.6)
    vg.bag_ekle(KITAP, a, "anisi", b, 20, "erken", "model", 0.7)
    vg.bag_ekle(KITAP, a, "anisi", b, 90, "daha geç", "sistem", 1.0)
    bag = vg.baglar(KITAP)[0]
    assert bag["ilk_bolum"] == 20 and bag["kanit"] == "erken"
    assert bag["origin"] == "sistem" and bag["durum"] == "onaylandi"  # güçlü köken kazanır
    vg.bag_durumu(KITAP, a, "anisi", b, "reddedildi")
    assert vg.bag_ekle(KITAP, a, "anisi", b, 5, "x", "model") is False
    assert vg.baglar(KITAP) == []  # reddedilen varsayılan listede yok


def test_spoiler_suzgeci():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    assert _bag_kumesi(en_cok_bolum=10) == set()
    assert ("Sunny", "golgesi", "Stone Saint") in _bag_kumesi(en_cok_bolum=16)


def test_uc_spoiler_varsayilan_gizli():
    from fastapi.testclient import TestClient

    import server

    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    library.upsert_book(KITAP, "Shadow Slave", "https://x/ch-3", "B3", 3)
    c = TestClient(server.app)
    assert c.get(f"/api/book/{KITAP}/graph").json()["edges"] == []  # konum 3 < 16
    assert c.get(f"/api/book/{KITAP}/graph", params={"bolum": 16}).json()["edges"]
    tum = c.get(f"/api/book/{KITAP}/graph", params={"spoiler": "true"}).json()
    assert {e["relation"] for e in tum["edges"]} >= {"anisi", "golgesi", "gercek_adi"}


def test_sozluk_kaydi_silinince_baglari_gider():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    glossary.delete_term(KITAP, "Stone Saint")
    assert not any("Stone Saint" in (b[0], b[2]) for b in _bag_kumesi())


def test_kitap_birlestirmede_baglar_tasinir():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    glossary.set_term("hedef-kitap", "Sunny", "Sunny")  # hedefte zaten var, kimliği farklı
    conn = vg._connect()
    try:
        glossary.kitaba_tasi(conn, KITAP, "hedef-kitap")
        conn.commit()
    finally:
        conn.close()
    hedef = {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar("hedef-kitap")}
    assert ("Sunny", "anisi", "Silver Bell") in hedef
    assert vg.baglar(KITAP) == []


def test_sozcuk_karismasi_baska_sinifin_sozcugunu_yakalar():
    _sozluk()
    for k, v in {"Winter Beast": "Kış Canavarı", "Soul Beast": "Ruh Mahluku",
                 "Monster": "Canavar", "Awakened monsters": "Uyanmış canavarlar"}.items():
        glossary.set_term(KITAP, k, v)
    duzen = {"Monster": ["Canavar"], "beast": ["Mahluk"], "Awakened": ["Uyanmış"]}
    sonuc = vg.sozcuk_karismalari(KITAP, duzen)
    assert set(sonuc) == {"Winter Beast"}


def test_sozcuk_karismasi_kok_dusmani_yakalamaz():
    glossary.set_term(KITAP, "Vanquished Foes", "Alt Edilen Düşmanlar")
    assert vg.sozcuk_karismalari(KITAP, {"Fallen": ["Düşmüş"]}) == {}


def test_ayni_kisinin_adlari_karisik_politika():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    cozucu = vg.DugumCozucu(KITAP)
    vg.bag_ekle(KITAP, cozucu.coz("Sunny"), "takma_adi", cozucu.coz("Sunless"), 1, None, "manual")
    sonuc = vg.ad_tutarsizliklari(KITAP)
    assert set(sonuc) == {"Lost from Light"}
    assert "Sunless (İngilizce)" in sonuc["Lost from Light"]["aciklama"]


def test_inceleme_listesi_grafik_nedenlerini_gosterir():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    tur = {x["source"]: [n["tur"] for n in x["nedenler"]] for x in glossary.inceleme_listesi(KITAP)}
    assert vg.AD_TUTARLILIGI in tur["Lost from Light"]


def test_simetrik_iliski_tek_bagdir():
    _sozluk()
    glossary.set_term(KITAP, "Kai", "Kai")
    cozucu = vg.DugumCozucu(KITAP)
    s, k = cozucu.coz("Sunny"), cozucu.coz("Kai")
    assert vg.bag_ekle(KITAP, s, "yoldasi", k, 120, "a", "model", 0.9) is True
    assert vg.bag_ekle(KITAP, k, "yoldasi", s, 110, "b", "model", 0.9) is False
    baglar = [b for b in vg.baglar(KITAP) if b["iliski"] == "yoldasi"]
    assert len(baglar) == 1 and baglar[0]["ilk_bolum"] == 110


def test_takma_ad_dugumundeki_baglar_asil_kisiye_tasinir():
    _sozluk()
    for k in ("Nephis", "Neph", "Dawn Shard", "Changing Star", "Tessai"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Nephis"), "takma_adi", k("Neph"), 209, None, "model", durum="onaylandi")
    vg.bag_ekle(KITAP, k("Nephis"), "gercek_adi", k("Changing Star"), 28, None, "manual")
    vg.bag_ekle(KITAP, k("Neph"), "anisi", k("Dawn Shard"), 296, "x", "model", 0.9)
    vg.bag_ekle(KITAP, k("Changing Star"), "oldurdu", k("Tessai"), 313, "y", "model", 0.9)
    vg.bag_ekle(KITAP, k("Nephis"), "anisi", k("Dawn Shard"), 400, "z", "model", 0.9)
    assert vg.takma_adlari_birlestir(KITAP) == 2
    baglar = {(b["kaynak"], b["iliski"], b["hedef"]): b for b in vg.baglar(KITAP)}
    assert baglar[("Nephis", "anisi", "Dawn Shard")]["ilk_bolum"] == 296  # erken olan kalır
    assert ("Nephis", "oldurdu", "Tessai") in baglar
    assert ("Neph", "anisi", "Dawn Shard") not in baglar
    assert ("Nephis", "takma_adi", "Neph") in baglar  # kimlik bağı yerinde


def test_unvanli_ad_asil_kisiye_baglanir_kategori_baglanmaz():
    for k, v in {"Roan": "Roan", "Master Roan": "Master Roan", "Hope": "Umut", "Lady Hope": "Leydi Umut",
                 "Demon": "İblis", "Ascended Demon": "Yükselmiş İblis", "Dale": "Dale",
                 "Ascended Dale": "Ascended Dale", "Chained Isles": "Zincirli Adalar"}.items():
        glossary.set_term(KITAP, k, v)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Master Roan"), "bulundugu_yer", k("Chained Isles"), 381, "x", "model", 0.9)
    assert vg.unvanli_adlari_bagla(KITAP) == 3
    baglar = {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar(KITAP)}
    assert {("Roan", "takma_adi", "Master Roan"), ("Hope", "takma_adi", "Lady Hope"),
            ("Dale", "takma_adi", "Ascended Dale")} <= baglar
    assert ("Demon", "takma_adi", "Ascended Demon") not in baglar
    vg.takma_adlari_birlestir(KITAP)
    assert ("Roan", "bulundugu_yer", "Chained Isles") in {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar(KITAP)}


def test_evrim_ve_golge_alma_runleri():
    b1 = vg.sistem_baglarini_bul("[You have received an Echo: Stone Saint.]\n\n[You have created a Shadow Monster: Stone Saint.]",
                                 "Sunny", ("Sunless",))
    assert ("Sunny", "yanki", "Stone Saint") in [x[:3] for x in b1]
    assert ("Sunny", "golgesi", "Stone Saint") in [x[:3] for x in b1]
    # 106 gölge, 273 evrim işareti, 278 bir ANI bloğu (eşleşmemeli), 310 yeni gölge adı.
    durum: dict = {}
    vg.evrimleri_esle([("Sunny", "golgesi", "Stone Saint", "")], durum, 106)
    vg.evrimleri_esle(vg.sistem_baglarini_bul("[...The Stone Saint is evolving.]", "Sunny", ()), durum, 273)
    s278 = vg.evrimleri_esle([("Sunny", "anisi", "Weaver's Mask", "")], durum, 278)
    assert all(x[1] != "donustu" for x in s278)
    b310 = vg.sistem_baglarini_bul("Shadow: [Marble Saint].\n\nShadow Rank: Awakened.", "Sunny", ("Sunless",))
    s310 = vg.evrimleri_esle(b310, durum, 310)
    assert ("Stone Saint", "donustu", "Marble Saint") in [x[:3] for x in s310]
    # Eski gölgenin yeniden listelenmesi evrim sonucu sayılmaz.
    durum2: dict = {}
    vg.evrimleri_esle([("Sunny", "golgesi", "Soul Serpent", "")], durum2, 358)
    vg.evrimleri_esle(vg.sistem_baglarini_bul("[...Marble Saint is evolving.]", "Sunny", ()), durum2, 400)
    s = vg.evrimleri_esle([("Sunny", "golgesi", "Soul Serpent", "")], durum2, 401)
    assert all(x[1] != "donustu" for x in s)


def test_bilinmeyen_iliski_reddedilir():
    import pytest

    with pytest.raises(ValueError):
        vg.bag_ekle(KITAP, "a", "sevgilisi", "b", 1, None, "model")


def test_ani_blogu_efsun_ve_esya_turu_baglarini_kurar():
    # Yapay rün bloğu (roman metni değil): iki efsun, açıklamalar aynı sırada.
    metin = (
        "Memory: [Bitter Peak].\n\nMemory Rank: Ascended.\n\nMemory Tier: III.\n\n"
        "Memory Type: Armor.\n\nMemory Description: [Bir zamanlar.]\n\n"
        "Memory Enchantments: [Black Venom], [Unbroken].\n\n"
        "Enchantment Description: [Zehir açıklaması.]\n\n"
        "Enchantment Description: [Kırılmazlık açıklaması.]\n\n"
        "Sunny sighed."
    )
    b = vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))
    uclu = {x[:3]: x[3] for x in b}
    assert ("Sunny", "anisi", "Bitter Peak") in uclu
    assert ("Bitter Peak", "turu", "Memory") in uclu
    assert ("Bitter Peak", "rutbesi", "Ascended") in uclu
    assert ("Bitter Peak", "esya_turu", "Armor") in uclu
    # Efsunun ne yaptığı bağın kanıtıdır; sıra korunur.
    assert "Zehir" in uclu[("Bitter Peak", "efsunu", "Black Venom")]
    assert "Kırılmazlık" in uclu[("Bitter Peak", "efsunu", "Unbroken")]


def test_sistemle_celisen_model_bagi_reddedilir_elle_kurulan_kalir():
    for k in ("Bitter Peak", "Black Venom", "Sunny", "Nephis"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Bitter Peak"), "niteligi", k("Black Venom"), 50, "x", "model", 0.9)
    vg.bag_ekle(KITAP, k("Bitter Peak"), "efsunu", k("Black Venom"), 40, "y", "sistem", 1.0)
    vg.bag_ekle(KITAP, k("Sunny"), "yoldasi", k("Nephis"), 10, "z", "manual", 1.0)
    vg.bag_ekle(KITAP, k("Sunny"), "dusmani", k("Nephis"), 11, "w", "sistem", 1.0)
    assert vg.sistemle_celisenleri_reddet(KITAP) == 1
    durum = {(b["kaynak"], b["iliski"], b["hedef"]): b["durum"]
             for b in vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi"))}
    assert durum[("Bitter Peak", "niteligi", "Black Venom")] == "reddedildi"
    assert durum[("Bitter Peak", "efsunu", "Black Venom")] == "onaylandi"
    # Elle kurulan bağ, sistem başka ilişki söylese de reddedilmez.
    assert [d for (a, i, b), d in durum.items() if i == "yoldasi"] == ["onaylandi"]


def test_anlatimla_bolunmus_ani_blogu_ve_efsun_bicimleri():
    # Yapay metin; yapı 923. bölümdeki gibi: rün satırları arasına anlatım giriyor.
    metin = "\n\n".join([
        "Memory: [Bitter Cusp].", "Memory Rank: Ascended.", "Memory Type: Tool.",
        "A tool, huh.", "He kept reading.",
        "Memory Description: [Kısa.]", "He looked at the enchantments.",
        "Enchantment: [Black Venom].", "Enchantment Description: [Zehir.]",
        "Then he looked at the second one.",
        "Memory: [Stifled Scream].", "Memory Type: Charm.", "Jackpot.",
        "Enchantments: [Echoing Silence], [Word of Power].",
        "[Echoing Silence] Enchantment Description: Sessizlik.",
        "He tilted his head.",
        "[Word of Power] Enchantment Description: Söz.",
    ])
    b = {x[:3]: x[3] for x in vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))}
    assert "Zehir" in b[("Bitter Cusp", "efsunu", "Black Venom")]
    assert ("Bitter Cusp", "esya_turu", "Tool") in b
    assert "Sessizlik" in b[("Stifled Scream", "efsunu", "Echoing Silence")]
    assert "Söz" in b[("Stifled Scream", "efsunu", "Word of Power")]
    # Efsunlar Anılar arasında karışmaz.
    assert ("Bitter Cusp", "efsunu", "Echoing Silence") not in b


def test_ani_blogu_pencere_disinda_yeniden_acilmaz():
    metin = "\n\n".join(["Memory: [Bitter Cusp].", "Memory Rank: Ascended."]
                          + [f"Anlatım {i}." for i in range(vg.ANI_ANLATIM_PENCERESI + 1)]
                          + ["Enchantment: [Black Venom]."])
    assert all(x[1] != "efsunu" for x in vg.sistem_baglarini_bul(metin, "Sunny", ()))


def test_aninin_niteligi_efsune_cevrilir():
    for k in ("Puppeteer's Shroud", "Doubtless", "Memory", "Nephis", "Fire"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Puppeteer's Shroud"), "turu", k("Memory"), 15, "x", "sistem", 1.0)
    vg.bag_ekle(KITAP, k("Puppeteer's Shroud"), "niteligi", k("Doubtless"), 143, "trait", "model", 0.9, durum="onaylandi")
    vg.bag_ekle(KITAP, k("Nephis"), "niteligi", k("Fire"), 50, "y", "model", 0.9, durum="onaylandi")
    assert vg.ani_niteliklerini_efsune_cevir(KITAP) == 1
    durum = {(b["kaynak"], b["iliski"], b["hedef"]): (b["durum"], b["ilk_bolum"])
             for b in vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi"))}
    assert durum[("Puppeteer's Shroud", "efsunu", "Doubtless")] == ("onaylandi", 143)
    assert durum[("Puppeteer's Shroud", "niteligi", "Doubtless")][0] == "reddedildi"
    assert durum[("Nephis", "niteligi", "Fire")][0] == "onaylandi"  # kişi niteliği kalır


def test_durum_blogu_anlatimdan_sonra_devam_eder_rank_etmez():
    # Yapay metin; yapı 848. bölümdeki gibi.
    metin = "\n\n".join([
        "Name: Sunless.", "Rank: Ascended.", "Class: Devil.", "Shadow Cores: 4/7.",
        "He frowned at the numbers.",
        "Attributes: [Fated], [Flame of Divinity].",
        "Aspect: [Shadow Slave].", "Aspect Rank: Divine.",
        "He sighed.",
        "Aspect Abilities: [Shadow Step].", "Aspect Legacy: [Shadow Dance].",
        "Flaw: [Clear Conscience].", "Dream Anchor: [Tower of Longing].",
        "Someone else spoke.", "Rank: Dreamer.",
    ])
    b = {x[:3] for x in vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))}
    assert {
        ("Sunny", "sinifi", "Devil"), ("Sunny", "niteligi", "Flame of Divinity"),
        ("Sunny", "gorunusu", "Shadow Slave"), ("Shadow Slave", "rutbesi", "Divine"),
        ("Sunny", "yetenegi", "Shadow Step"), ("Sunny", "yetenegi", "Shadow Dance"),
        ("Sunny", "kusuru", "Clear Conscience"), ("Sunny", "ruya_capasi", "Tower of Longing"),
    } <= b
    # Anlatımdan sonra tek başına "Rank:" yine bağlanmaz.
    assert ("Sunny", "rutbesi", "Dreamer") not in b


def test_durum_degerleri_bag_degil_degisimle_saklanir():
    for k in ("Sunny", "Sunless", "Bitter Cusp", "Memory"):
        glossary.set_term(KITAP, k, k)
    # Köşeli değer ve satıra yapışan filigran (ölçülen biçim) temizlenir.
    metin = "\n\n".join(["Name: Sunless.", "Shadow Cores: [4/7].", "He frowned.",
                          "Shadow Fragments: [777/4000]. filigran.example", "Memory: [Bitter Cusp].",
                          "Memory Tier: I."])
    bulunan = vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))
    assert ("Sunny", vg.DEGER, "Shadow Fragments\t777/4000") in {x[:3] for x in bulunan}
    vg.bolumden_sistem_baglari(KITAP, 848, metin)
    vg.bolumden_sistem_baglari(KITAP, 900, metin)  # değişmedi: yeni satır yok
    vg.bolumden_sistem_baglari(KITAP, 950, metin.replace("4/7", "5/7"))
    k = vg.DugumCozucu(KITAP).coz
    assert vg.degerler(KITAP, 949)[k("Sunny")]["Shadow Cores"] == {"deger": "4/7", "ilk_bolum": 848}
    assert vg.degerler(KITAP)[k("Sunny")]["Shadow Cores"] == {"deger": "5/7", "ilk_bolum": 950}
    assert vg.degerler(KITAP)[k("Bitter Cusp")]["Memory Tier"]["deger"] == "I"
    assert vg.degerler(KITAP, 800) == {}  # spoiler: konumdan önce değer yok
    # Değer bir bağ değildir.
    assert all(b["iliski"] != vg.DEGER for b in vg.baglar(KITAP))
    # Kayıt silinince değerleri de gider.
    glossary.delete_term(KITAP, "Bitter Cusp")
    assert k("Bitter Cusp") not in vg.degerler(KITAP)


def test_sabit_baglar_ilk_gecisten_kurulur(monkeypatch):
    for k in ("Sunny", "Sunless", "happy shadow", "gloomy shadow"):
        glossary.set_term(KITAP, k, k)
    profil = dict(vg.KITAP_PROFILLERI[KITAP])
    profil["sabit_baglar"] = (("Sunny", "kendi_golgesi", "happy shadow"),
                              ("Sunny", "kendi_golgesi", "gloomy shadow"),
                              ("Sunny", "kendi_golgesi", "missing shadow"))
    monkeypatch.setitem(vg.KITAP_PROFILLERI, KITAP, profil)
    for no, metin in ((390, "Nothing here."), (394, "Sunny smiled. The happy shadow danced."),
                      (434, "The gloomy shadow sighed. The happy shadow too.")):
        cache.save_chapter(f"https://x/ch-{no}", {
            "book_slug": KITAP, "book_title": "Shadow Slave", "title": f"B{no}", "chapter_no": no,
            "translation": "Çeviri.", "source": metin,
        })
    sonuc = vg.sistem_baglarini_cikar(KITAP)
    bag = {(b["kaynak"], b["iliski"], b["hedef"]): b for b in vg.baglar(KITAP)}
    assert bag[("Sunny", "kendi_golgesi", "happy shadow")]["ilk_bolum"] == 394
    assert bag[("Sunny", "kendi_golgesi", "happy shadow")]["kanit"] == "The happy shadow danced."
    assert bag[("Sunny", "kendi_golgesi", "gloomy shadow")]["ilk_bolum"] == 434
    assert "missing shadow" in sonuc["cozulemeyen"]


def test_elle_bag_model_bagini_reddeder():
    for k in ("Sunny", "gloomy shadow"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Sunny"), "golgesi", k("gloomy shadow"), 781, "x", "model", 0.9, durum="onaylandi")
    vg.bag_ekle(KITAP, k("Sunny"), "kendi_golgesi", k("gloomy shadow"), 409, "y", "manual", 1.0)
    assert vg.sistemle_celisenleri_reddet(KITAP) == 1
    durum = {(b["iliski"]): b["durum"] for b in vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi"))}
    assert durum == {"golgesi": "reddedildi", "kendi_golgesi": "onaylandi"}


def test_obek_siniflari_bagdan_turer_sozluk_turunu_duzeltir():
    kayitlar = {
        "Sunny": "kisi", "Devil": "rutbe", "Saint": "diger", "Bitter Cusp": "nesne", "Black Venom": "yetenek",
        "gloomy shadow": "nesne", "Rolling Stone": "diger", "Monster": "rutbe", "Chained Isles": "yer",
        "First Irregular Company": "orgut", "Belle": "kisi", "Fated": "yetenek", "Shadow Slave": "diger",
        "Black Knight": "kisi", "Tower of Longing": "diger",
    }
    for k, tur in kayitlar.items():
        glossary.set_term(KITAP, k, k)
        glossary.tanim_yaz(KITAP, k, None, tur=tur)
    k = vg.DugumCozucu(KITAP).coz
    for a, i, b in [
        ("Sunny", "sinifi", "Devil"), ("Sunny", "anisi", "Bitter Cusp"), ("Bitter Cusp", "efsunu", "Black Venom"),
        ("Sunny", "golgesi", "Saint"), ("Sunny", "kendi_golgesi", "gloomy shadow"),
        ("Sunny", "oldurdu", "Rolling Stone"), ("Rolling Stone", "sinifi", "Monster"),
        ("Sunny", "niteligi", "Fated"), ("Sunny", "gorunusu", "Shadow Slave"),
        ("Belle", "grubu", "First Irregular Company"), ("First Irregular Company", "lideri", "Sunny"),
        ("Black Knight", "sinifi", "Devil"), ("Sunny", "ruya_capasi", "Tower of Longing"),
        ("Sunny", "bulundugu_yer", "Chained Isles"),
    ]:
        vg.bag_ekle(KITAP, k(a), i, k(b), 10, "x", "sistem", 1.0)
    o = {vg.DugumCozucu(KITAP).kaynak(x): s for x, s in vg.obek_siniflari(KITAP).items()}
    assert o["Sunny"] == "kisi"  # sınıfı Devil olduğu hâlde
    assert o["Bitter Cusp"] == "ani" and o["Black Venom"] == "efsun"
    assert o["Saint"] == "yaratik" and o["gloomy shadow"] == "golge"
    assert o["Rolling Stone"] == "yaratik" and o["Black Knight"] == "yaratik"
    assert o["Fated"] == "nitelik" and o["Shadow Slave"] == "gorunus"
    assert o["First Irregular Company"] == "grup" and o["Belle"] == "kisi"
    assert o["Chained Isles"] == "yer" and o["Tower of Longing"] == "yer"


def test_obek_kural_sirasi_olculen_hatalar():
    kayitlar = {"Sunny": "kisi", "Shadow Slave": "rutbe", "Beth": "kisi", "Obel": "kisi",
                "Abomination": "diger", "Black Knight": "kisi", "Flesh Reaver": "diger",
                "awakened beast": "diger", "Crimson Terror": "diger", "Lost from Light": "diger"}
    for k, tur in kayitlar.items():
        glossary.set_term(KITAP, k, k)
        glossary.tanim_yaz(KITAP, k, None, tur=tur)
    k = vg.DugumCozucu(KITAP).coz
    for a, i, b in [("Sunny", "gorunusu", "Shadow Slave"), ("Beth", "lideri", "Obel"),
                    ("Black Knight", "turu", "Abomination"), ("Flesh Reaver", "turu", "awakened beast"),
                    ("Sunny", "gercek_adi", "Lost from Light")]:
        vg.bag_ekle(KITAP, k(a), i, k(b), 10, "x", "model", 0.9, durum="onaylandi")
    vg.bag_ekle(KITAP, k("Crimson Terror"), "dusmani", k("Obel"), 10, "x", "model", 0.9, durum="onaylandi")
    o = {vg.DugumCozucu(KITAP).kaynak(x): s for x, s in vg.obek_siniflari(KITAP).items()}
    assert o["Shadow Slave"] == "gorunus"     # sözlükte "rutbe" türünde olsa da
    assert o["Beth"] == "kisi"                # kişiden kişiye "lideri" grup yapmaz
    assert o["Abomination"] == "kategori"     # bir şeyin türü
    assert o["Flesh Reaver"] == "yaratik"     # türü bir yaratık sınıfı içeriyor
    assert o["Crimson Terror"] == "yaratik"   # adı yaratık sınıfıyla bitiyor
    assert o["Lost from Light"] == "kisi"     # sahibinin öbeği
