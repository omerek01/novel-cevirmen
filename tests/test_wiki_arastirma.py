"""Wiki araştırması (`core.wiki_arastirma`): wikiyi bulma, dipnotlu cümleleri ayıklama, spoiler
süzgeci ve defterde olmayan adlar — çevrimdışı, sahte `getir`.

Wikitext örnekleri Shadow Slave Wiki'nin (Fandom) ölçülen biçimini taklit eder."""
from __future__ import annotations

import time

from core import cache, db, glossary, wiki_arastirma as w

KITAP = "shadow-slave"

RUNES = """{{TabViews}}
== Runes ==
'''[[Awakened Rank|Rank]]:''' Dreamer.<ref name=":15">Chapter 15 Shadow Slave</ref><br>
'''[[Shadow Core|Shadow Cores]]:''' <span class="x"><s>[2/7]<ref name=":352">Chapter 352 Monster Core</ref></s> → <s>[3/7]<ref>Chapter 526 Demon</ref></s> → </span>[5/7].<ref name=":1090">Chapter 1090 Tyrant</ref><br>
'''{{Color|#E3BE00|Memory}}:''' [ [[Shadow Lantern]] ].<ref name=":653">Chapter 653 Cute Little Snake</ref>
He became a Saint later.
Sunny lost the [Azure Blade] in a fight.<ref name=":15" /> He found [Feather of Truth].<ref>Chapter 1500 Spoiler</ref>
[You cannot lie.]<ref name=":15" />
"""


def _sahte(sayfalar=("Sunny", "Sunny/Runes", "Nephis", "Main Page"), site="Shadow Slave Wiki", alt="shadowslave"):
    cagrilar = []

    def getir(adres, params):
        cagrilar.append((adres, params))
        if not adres.startswith(f"https://{alt}.fandom.com"):
            return None
        if params.get("meta") == "siteinfo":
            return {"query": {"general": {"sitename": site, "server": f"https://{alt}.fandom.com",
                                          "scriptpath": ""}}}
        if params.get("list") == "allpages":
            return {"query": {"allpages": [{"title": t} for t in sayfalar]}}
        if params.get("action") == "parse":
            return {"parse": {"wikitext": {"*": RUNES if params["page"].endswith("/Runes") else ""}}}
        return None

    getir.cagrilar = cagrilar
    return getir


def _bolum(no):
    conn = cache._connect()
    conn.execute("INSERT INTO chapters (url, book_slug, book_title, chapter_no, translation, source_text, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", (f"https://x/{no}", KITAP, "Shadow Slave", no, "x", "x", time.time()))
    conn.commit()
    conn.close()


def _kisi(ad):
    glossary.set_term(KITAP, ad, ad)
    conn = db.connect()
    conn.execute("UPDATE glossary SET tur = 'kisi' WHERE book_slug = ? AND source = ?", (KITAP, ad))
    conn.commit()
    conn.close()


def test_aday_alt_alanlar_kitap_adindan():
    assert w.aday_alt_alanlar("Shadow Slave", "shadow-slave")[:2] == ["shadowslave", "shadow-slave"]
    assert "rotssg" in w.aday_alt_alanlar("Reincarnation of the Strongest Sword God", "rotssg-x")


def test_wiki_bul_site_adi_kitapla_uyusmali():
    assert w.wiki_bul("Shadow Slave", "shadow-slave", _sahte())["adres"] == "https://shadowslave.fandom.com/api.php"
    # Aynı alt alanda başka bir wiki (ad uyuşmuyor) kabul edilmez.
    assert w.wiki_bul("Shadow Slave", "shadow-slave", _sahte(site="Cooking Recipes Wiki")) is None


def test_ayikla_yalniz_dipnotlu_cumleleri_bolumleriyle_alir():
    c = dict(w.ayikla(RUNES))
    assert c["Rank: Dreamer."] == [15]
    assert c["Shadow Cores: [2/7]"] == [352] and c["Shadow Cores: [3/7]"] == [526]
    assert c["Shadow Cores: [5/7]."] == [1090]
    assert c["Memory: [Shadow Lantern]."] == [653]
    assert c["Sunny lost the [Azure Blade] in a fight."] == [15]  # adlı dipnot yeniden kullanımı
    assert not any("Saint" in m for m in c)  # dipnotsuz cümle: ne zaman olduğu bilinmez


def test_arastir_karakter_sayfalarini_ceker_notlar_konuma_gore_suzulur():
    _bolum(1)
    _kisi("Sunny")
    sonuc = w.arastir(KITAP, _sahte(), bekleme=0)
    assert sonuc["durum"] == "bulundu" and sonuc["sayfa"] == 2  # Sunny + Sunny/Runes; Nephis kişi değil
    notlar = w.notlar(KITAP, ["Sunny"], 700)
    assert notlar["durum"] == "hazir"
    metinler = [n["metin"] for n in notlar["notlar"]]
    assert "Memory: [Shadow Lantern]." in metinler
    assert not any("5/7" in m or "Feather" in m for m in metinler)  # 1090 ve 1500: spoiler
    assert any("5/7" in n["metin"] for n in w.notlar(KITAP, ["Sunny"], 1099)["notlar"])


def test_eksik_adlar_defterde_olmayan_basliklari_verir():
    notlar = [{"metin": "Memory: [Shadow Lantern]. [You cannot lie.] [Azure Blade]", "bolum": 653}]
    eksik = w.eksik_adlar(notlar, {glossary.fold_term("Azure Blade")})
    assert [e["ad"] for e in eksik] == ["Shadow Lantern"]  # rün cümlesi ad değil


def test_bulunamayan_wiki_kaydedilir_ve_bir_gun_yeniden_aranmaz(monkeypatch):
    _bolum(1)
    assert w.arastir(KITAP, _sahte(alt="baska"), bekleme=0)["durum"] == "yok"
    monkeypatch.setenv("WIKI_ARASTIRMA", "1")
    monkeypatch.setattr(w, "_arka_planda", lambda slug, is_: True)
    assert w.gerekirse_baslat(KITAP) is False
    monkeypatch.setenv("WIKI_ARASTIRMA", "0")
    assert w.gerekirse_baslat("yeni-kitap") is False  # bayrak kapalı: ağ yok


def test_elle_adres_tahminin_onune_gecer():
    _bolum(1)
    _kisi("Sunny")
    w.adres_yaz(KITAP, "https://shadowslave.fandom.com")
    getir = _sahte()
    w.arastir(KITAP, getir, bekleme=0)
    assert not any(p.get("meta") == "siteinfo" for _a, p in getir.cagrilar)
    assert w.kaynak(KITAP)["durum"] == "bulundu"


def test_yonlendirme_sayfasinin_tekrari_notlarda_bir_kez_cikar():
    _bolum(1)
    _kisi("Sunny")
    _kisi("Sunless")  # "Sunless" sayfası "Sunny"ye yönlendirir: aynı wikitext
    w.arastir(KITAP, _sahte(sayfalar=("Sunny/Runes", "Sunless/Runes")), bekleme=0)
    metinler = [n["metin"] for n in w.notlar(KITAP, ["Sunny", "Sunless"], 700)["notlar"]]
    assert len(metinler) == len(set(metinler))
