"""Defter ekranı (`core.defter_ekrani`) ve uçları: kişi listesi, karakter kartı, elle düzenleme,
spoiler süzgeci — çevrimdışı, sahte model."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from core import cache, db, defter_ekrani as de, defter_kayit as dk, glossary, karakter_defteri as kd, library
from core import varlik_grafigi as vg

KITAP = "shadow-slave"


def _bolum(no, en, tr):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"https://x/{no}", KITAP, no, "\n\n".join(tr), "\n\n".join(en), time.time()),
    )
    conn.commit()
    conn.close()


def _hitap(no, bicim="sen"):
    tr = "dinle" if bicim == "sen" else "dinleyin"
    return {"v": [{"ad": "Nephis", "tr": "Nephis", "t": "kisi", "p": 1, "a": "Sunny, listen"}],
            "g": [], "b": [{"o": "Sunny", "r": "yoldasi", "n": "Nephis", "p": 1, "a": "Sunny, listen", "s": "anlatici"}],
            "h": [{"p": 1, "ko": "Nephis", "mu": "Sunny", "f": bicim, "tra": tr}]}


@pytest.fixture
def kitap():
    for kaynak, hedef, tur in (("Sunny", "Sunny", "kisi"), ("Nephis", "Nephis", "kisi"),
                               ("Changing Star", "Değişen Yıldız", "kisi"), ("Immortal Flame", "Ölümsüz Alev", "orgut"),
                               ("Mirror Beast", "Ayna Mahluğu", "Canavar")):
        glossary.set_term(KITAP, kaynak, hedef)
        conn = db.connect()
        conn.execute("UPDATE glossary SET tur = ? WHERE book_slug = ? AND source = ?", (tur, KITAP, kaynak))
        conn.commit()
        conn.close()
    yanitlar = {}
    for no in (10, 11, 12, 13, 40):
        _bolum(no, [f'"Sunny, listen," Nephis said. ({no})'], [f'"Sunny, dinle," dedi Nephis. ({no})'])
        yanitlar[no] = _hitap(no)

    def cagir(user, model):
        istem = json.loads(user)
        return json.dumps(yanitlar[istem["bolum"]]), {"model": model, "giris": 1, "cikis": 1, "dusunme": 0}

    for no in (10, 11, 12, 13, 40):
        kd.bolum_isle(KITAP, no, cagir=cagir)
    kd.uzlastir(KITAP)
    _bolum(15, ["Name: Sunless.", "Rank: Dreamer.", "Memory: [Azure Blade].", "Memory Rank: Awakened.",
                "[You have slain an awakened beast, Mirror Beast.]"], ["x"] * 5)
    _bolum(50, ["Name: Sunless.", "Rank: Awakened."], ["x", "x"])
    dk.cikar(KITAP)
    return KITAP


def _kimlik(ad):
    return {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(KITAP)}[ad]


def test_liste_kisileri_sayar_ve_spoiler_konumunu_uygular(kitap):
    once = de.liste(KITAP, 12)
    nephis = next(k for k in once["kisiler"] if k["ad"] == "Nephis")
    assert nephis["bolum_sayisi"] == 3  # 10, 11, 12 — 13 ve 40 konumdan sonra
    assert all(k["ad"] != "Immortal Flame" for k in once["kisiler"])
    sonra = de.liste(KITAP, None)
    assert next(k for k in sonra["kisiler"] if k["ad"] == "Nephis")["bolum_sayisi"] == 5
    assert [y["ad"] for y in de.liste(KITAP, 20)["yaratiklar"]] == ["Mirror Beast"]
    assert de.liste(KITAP, 14)["yaratiklar"] == [] or all(y.get("oldurulme") is None
                                                           for y in de.liste(KITAP, 14)["yaratiklar"])
    assert [a["ad"] for a in de.liste(KITAP, 20)["anilar"]] == ["Azure Blade"]


def test_kart_baglari_hitabi_ve_run_listesini_toplar(kitap):
    k = de.kart(KITAP, _kimlik("Sunny"), 20)
    assert k["ad"] == "Sunny"
    bag = next(b for b in k["baglar"] if b["iliski"] == "yoldasi")
    assert bag["diger_ad"] == "Nephis" and bag["destek"] == 4  # 10–13; 40 konumdan sonra
    hitap = next(h for h in k["hitaplar"] if h["konusan"] == "Nephis")
    assert (hitap["bicim"], hitap["kararli"]) == ("sen", True)
    run = {a["ad"]: a["deger"] for a in k["run"]}
    assert run["rutbesi"] == "Dreamer"  # 50'deki Awakened konumdan sonra
    assert [a["ad"] for a in k["anilar"]] == ["Azure Blade"]
    assert de.kart(KITAP, _kimlik("Sunny"), None)["run"] and \
        {a["ad"]: a["deger"] for a in de.kart(KITAP, _kimlik("Sunny"), None)["run"]}["rutbesi"] == "Awakened"


def test_kart_bilinmeyen_kimlikte_none(kitap):
    assert de.kart(KITAP, "yok-boyle-kimlik", None) is None


# ---------------------------------------------------------------- uçlar

@pytest.fixture
def istemci(kitap):
    import server

    return TestClient(server.app)


def test_uc_liste_ve_kart(istemci):
    r = istemci.get(f"/api/book/{KITAP}/defter", params={"konum": 12})
    assert r.status_code == 200 and r.json()["sinir"] == 12
    r = istemci.get(f"/api/book/{KITAP}/defter/kart", params={"kimlik": _kimlik("Sunny"), "spoiler": True})
    assert r.status_code == 200 and r.json()["ad"] == "Sunny"
    assert istemci.get(f"/api/book/{KITAP}/defter/kart", params={"kimlik": "yok"}).status_code == 404


def test_uc_elle_kayit_ekle_duzelt_kaldir(istemci):
    yol = f"/api/book/{KITAP}/defter/kayit"
    r = istemci.post(yol, json={"kayit": {"tur": "ani", "sahip": "Sunny", "ad": "Endless Spring", "ilk_bolum": 15}})
    assert r.status_code == 200
    a = r.json()["anahtar"]
    kart = istemci.get(f"/api/book/{KITAP}/defter/kart", params={"kimlik": _kimlik("Sunny"), "spoiler": True}).json()
    assert "Endless Spring" in [x["ad"] for x in kart["anilar"]]
    assert istemci.post(yol, json={"kayit": {"tur": "bilinmez", "ad": "X"}}).status_code == 400
    assert istemci.request("DELETE", yol, json={"anahtar": a}).status_code == 200
    kart = istemci.get(f"/api/book/{KITAP}/defter/kart", params={"kimlik": _kimlik("Sunny"), "spoiler": True}).json()
    assert "Endless Spring" not in [x["ad"] for x in kart["anilar"]]


def test_uc_elle_bag_ekle_ve_kaldir(istemci):
    yol = f"/api/book/{KITAP}/defter/bag"
    govde = {"kaynak": _kimlik("Nephis"), "iliski": "klani", "hedef": _kimlik("Immortal Flame"), "ilk_bolum": 11}
    assert istemci.post(yol, json=govde).status_code == 200
    b = [x for x in vg.baglar(KITAP) if x["iliski"] == "klani"][0]
    assert (b["origin"], b["durum"]) == ("manual", "onaylandi")
    assert istemci.post(yol, json={**govde, "iliski": "uydurma"}).status_code == 400
    assert istemci.post(yol, json={**govde, "hedef": "yok"}).status_code == 404
    assert istemci.request("DELETE", yol, json=govde).status_code == 200
    assert not [x for x in vg.baglar(KITAP) if x["iliski"] == "klani"]


def test_uc_hitap_karari(istemci):
    yol = f"/api/book/{KITAP}/defter/hitap"
    govde = {"konusan": _kimlik("Nephis"), "muhatap": _kimlik("Sunny"), "hitap": "siz", "ilk_bolum": 1}
    assert istemci.post(yol, json=govde).status_code == 200
    kart = istemci.get(f"/api/book/{KITAP}/defter/kart", params={"kimlik": _kimlik("Sunny"), "spoiler": True}).json()
    h = next(h for h in kart["hitaplar"] if h["konusan"] == "Nephis")
    assert (h["bicim"], h["elle"]) == ("siz", True)
    assert istemci.post(yol, json={**govde, "hitap": "biz"}).status_code == 400


def test_yonlu_bag_destegi_ters_yonle_karismaz_ve_rutbe_ayri_gelir(kitap):
    from core import varlik_grafigi as vg2

    glossary.set_term(KITAP, "Julius", "Julius")
    glossary.set_term(KITAP, "Dreamer", "Rüyacı")
    s, j, d = _kimlik("Sunny"), _kimlik("Julius"), _kimlik("Dreamer")
    vg2.bag_ekle(KITAP, s, "ogretmeni", j, 10, None, "model", 1.0, durum="onaylandi")
    vg2.bag_ekle(KITAP, j, "ogretmeni", s, 11, None, "model", 0.5)
    vg2.bag_ekle(KITAP, s, "rutbesi", d, 12, None, "model", 1.0, durum="onaylandi")
    conn = kd._connect()
    for b in (10, 11, 12):
        conn.execute("INSERT INTO defter_iddia (book_slug, bolum, tur, ozne_ad, ozne_kimlik, iliski, nesne_ad, "
                     "nesne_kimlik, gecerli, created_at) VALUES (?, ?, 'bag', 'Sunny', ?, 'ogretmeni', 'Julius', ?, 1, 0)",
                     (KITAP, b, s, j))
    conn.commit()
    conn.close()
    k = de.kart(KITAP, s, None)
    ogretmen = {(b["yon"], b["destek"]) for b in k["baglar"] if b["iliski"] == "ogretmeni"}
    assert ogretmen == {("giden", 3), ("gelen", 0)}
    assert all(b["iliski"] != "rutbesi" for b in k["baglar"])
    assert [r["ad"] for r in k["rutbeler"]] == ["Dreamer"]


def test_takma_ad_olan_kisi_ayri_listelenmez_unvanli_sozluksuz_ad_elenir(kitap):
    from core import varlik_grafigi as vg2

    s, n, cs = _kimlik("Sunny"), _kimlik("Nephis"), _kimlik("Changing Star")
    vg2.bag_ekle(KITAP, n, "takma_adi", cs, 10, None, "model", 1.0, durum="onaylandi")
    vg2.bag_ekle(KITAP, cs, "takma_adi", n, 10, None, "model", 1.0, durum="onaylandi")
    conn = kd._connect()
    for b, ad in ((10, "Changing Star"), (11, "Lady Nephis"), (12, "Lady Nephis"), (13, "Lady Nephis"),
                  (10, "Knight"), (11, "Knight"), (12, "Knight"), (10, "Mordret"), (11, "Mordret"), (12, "Mordret")):
        kim = cs if ad == "Changing Star" else None
        conn.execute("INSERT INTO defter_iddia (book_slug, bolum, tur, ozne_ad, ozne_kimlik, deger, gecerli, created_at) "
                     "VALUES (?, ?, 'varlik', ?, ?, '{\"t\": \"kisi\"}', 1, 0)", (KITAP, b, ad, kim))
    conn.commit()
    conn.close()
    adlar = [k["ad"] for k in de.liste(KITAP, None)["kisiler"]]
    assert "Nephis" in adlar and "Changing Star" not in adlar
    assert "Lady Nephis" not in adlar and "Knight" not in adlar
    assert "Mordret" in adlar
    kart = de.kart(KITAP, n, None)
    assert [a["ad"] for a in kart["adlar"]] == ["Changing Star"]


def test_run_degerlerinin_sozluk_karsiliklari_gelir(kitap):
    glossary.set_term(KITAP, "Dreamer", "Rüyacı")
    k = de.kart(KITAP, _kimlik("Sunny"), 20)
    assert k["karsiliklar"]["Dreamer"] == "Rüyacı"
    assert "Awakened" not in k["karsiliklar"]  # sözlükte yok
    glossary.set_term(KITAP, "Awakened", "Uyanmış")
    assert de.liste(KITAP, 20)["karsiliklar"]["Awakened"] == "Uyanmış"  # anının rütbesi


def test_takma_adla_gelen_tekil_run_alani_tek_deger_gosterir(kitap):
    # 353'te "Name: Nephis." Demon; 524'te efendi kümesi "Master: Changing Star." Devil.
    n, cs = _kimlik("Nephis"), _kimlik("Changing Star")
    vg.bag_ekle(KITAP, n, "takma_adi", cs, 10, None, "model", 1.0, durum="onaylandi")
    _bolum(353, ["Name: Nephis.", "Class: Demon."], ["x", "x"])
    _bolum(524, ["He looked lower.", "Master: Changing Star.", "Class: Devil."], ["x", "x", "x"])
    dk.cikar(KITAP)
    sinif = [a for a in de.kart(KITAP, n, None)["run"] if a["ad"] == "sinifi"]
    assert [a["deger"] for a in sinif] == ["Devil"]
    assert [a["deger"] for a in de.kart(KITAP, n, 400)["run"] if a["ad"] == "sinifi"] == ["Demon"]


def test_rutbe_gecmisi_sinif_ve_geri_giden_rutbe_tasimaz(kitap):
    # Canlı kart (2026-10-15): Sunny "… Awakened → Devil → Ascended", Nephis "Dormant → Saint (98)
    # → Dreamer (352)". Sınıf rütbe değildir; rütbe geri gitmez — sonra daha düşüğü gelen yanlıştır.
    for ad in ("Dreamer", "Awakened", "Devil", "Ascended", "Master", "Saint"):
        glossary.set_term(KITAP, ad, ad)
    s = _kimlik("Sunny")
    for ad, bolum in (("Dreamer", 15), ("Saint", 98), ("Dreamer", 352), ("Awakened", 400), ("Devil", 703),
                      ("Ascended", 744), ("Master", 745)):
        vg.bag_ekle(KITAP, s, "rutbesi", _kimlik(ad), bolum, None, "model", 1.0, durum="onaylandi")
    assert [r["ad"] for r in de.kart(KITAP, s, None)["rutbeler"]] == ["Dreamer", "Awakened", "Ascended", "Master"]


# ---------- Sistem mesajları sekmesi (rün biçimi olmayan kitap; plan Faz 2) ----------
YENI = "deneme-kitap"


def _yeni_bolum(no, en, tr, zaman=None, url=None):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (url or f"https://y/{no}", YENI, no, "\n\n".join(tr) if tr else None, "\n\n".join(en), zaman or time.time()),
    )
    conn.commit()
    conn.close()


def test_sistem_mesajlari_hizaliysa_turkce_degilse_ingilizce_ve_spoiler_sinirli():
    _yeni_bolum(3, ["He walked on.", "[Quest accepted: Clear the Ruins.]", "Reward: 200 Gold"],
                ["Yürüdü.", "[Görev kabul edildi: Harabeleri Temizle.]", "Ödül: 200 Altın"])
    _yeni_bolum(7, ["Rain fell.", "[Level up!]"], ["Yağmur yağdı. [Seviye atladın!]"])  # hizasız
    _yeni_bolum(9, ["[Hidden quest found.]"], ["[Gizli görev bulundu.]"])

    assert de.liste(YENI, None)["sistem_sekmesi"] is True
    v = de.sistem_mesajlari(YENI, 8)
    assert v["sinir"] == 8 and [m["bolum"] for m in v["mesajlar"]] == [3, 3, 7]
    ilk, odul, hizasiz = v["mesajlar"]
    # Köşeli satır ile ardındaki anahtar satırı ayrı paragraf: her paragraf ayrı kayıt, anlatım alınmaz.
    assert ilk["turkce"] is True and ilk["metin"] == "[Görev kabul edildi: Harabeleri Temizle.]"
    assert odul["tur"] == "anahtar" and odul["anahtarlar"] == ["Reward"] and odul["metin"] == "Ödül: 200 Altın"
    assert hizasiz["turkce"] is False and hizasiz["metin"] == "[Level up!]" == hizasiz["en"]
    assert [m["bolum"] for m in de.sistem_mesajlari(YENI, None)["mesajlar"]] == [3, 3, 7, 9]
    assert v["anahtarlar"] == {"Reward": 1}


def test_sistem_mesajlari_bolumun_yalniz_en_yeni_kaydini_okur():
    _yeni_bolum(4, ["[Old message.]"], ["[Eski.]"], zaman=1.0, url="https://y/4-eski")
    _yeni_bolum(4, ["[New message.]"], ["[Yeni.]"], zaman=2.0, url="https://y/4-yeni")
    assert [m["en"] for m in de.sistem_mesajlari(YENI, None)["mesajlar"]] == ["[New message.]"]


def test_sistem_mesajlari_profildeki_sistem_sesini_ve_anahtarlari_kullanir():
    from core import kitap_profili

    metin = ["System: You gained a new title.", "Cooldown: 5 minutes"]
    _yeni_bolum(2, metin, ["Sistem: Yeni bir unvan kazandın.", "Bekleme: 5 dakika"])
    assert de.sistem_mesajlari(YENI, None)["mesajlar"] == []  # ses bilinmiyor, köşeli satır yok
    kitap_profili.yaz(YENI, "sistem_sesi", ["System"])
    v = de.sistem_mesajlari(YENI, None)
    assert [(m["tur"], m["metin"]) for m in v["mesajlar"]] == [
        ("ses", "Sistem: Yeni bir unvan kazandın."), ("anahtar", "Bekleme: 5 dakika")]
    assert v["anahtarlar"] == {"System": 1, "Cooldown": 1}


def test_run_bicimi_olan_kitapta_sistem_sekmesi_yok(kitap):
    assert de.liste(KITAP, None)["sistem_sekmesi"] is False
    assert de.sistem_mesajlari(KITAP, None)["mesajlar"] == []


def test_uc_sistem_mesajlari(istemci):
    _yeni_bolum(1, ["[Welcome.]"], ["[Hoş geldin.]"])
    r = istemci.get(f"/api/book/{YENI}/defter/sistem", params={"spoiler": True})
    assert r.status_code == 200 and r.json()["mesajlar"][0]["metin"] == "[Hoş geldin.]"


def test_baglar_sozluge_kimlik_indeksiyle_katilir(kitap):
    # İndeks yokken her bağ için kitabın tüm sözlüğü taranıyordu: canlıda Defter listesi
    # 5,4 sn sürdü, servis çalışanının 4 sn sınırına takıldı ve telefonda eski kopya
    # kaldı (2026-10-22, "1003'te kalmış").
    glossary.semayi_hazirla()
    vg.baglar(KITAP)  # tabloyu açar
    conn = db.connect()
    try:
        plan = " ".join(r[3] for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT b.kaynak_kimlik FROM varlik_bag b "
            "JOIN glossary k ON k.book_slug = b.book_slug AND k.kimlik = b.kaynak_kimlik WHERE b.book_slug = ?",
            (KITAP,)))
    finally:
        conn.close()
    assert "glossary_kimlik" in plan


def test_defter_uclari_service_worker_onbelleginden_gecmez():
    from pathlib import Path
    sw = (Path(__file__).resolve().parents[1] / "app" / "web" / "sw.js").read_text(encoding="utf-8")
    assert sw.index("DEFTER_YOLU.test(url.pathname)) return;") < sw.index("networkFirst(request)); // /api/books")


# ---------- Anlatımla gelen sınıf (canlı, 2026-10-22: Sunny 1090'da Tiran, kart "Şeytan") ----------
def _sunny_runleri():
    # 702: dördüncü çekirdek; 1047: başlıklı küme içinde parça sayacı. Sonra rün yok (1090 anlatım).
    _bolum(702, ["Name: Sunless.", "Class: Devil.", "Shadow Cores: [4/7].", "Shadow Fragments: [0/4000]."],
           ["x"] * 4)
    _bolum(1047, ["Name: Sunless.", "Shadow Fragments: [3857/4000]."], ["x", "x"])
    dk.cikar(KITAP)


def _run(kart):
    return {a["ad"]: a for a in kart["run"]}


def test_uzlastir_yaratik_sinifini_rutbe_degil_sinif_yazar(kitap):
    # "Does she know that I'm a Tyrant now, too?" modelde `Sunny rutbesi Tyrant` olarak geliyordu;
    # sınıf rütbe geçmişinde süzülüyor, rün listesine de hiç ulaşmıyordu.
    glossary.set_term(KITAP, "Tyrant", "Tiran")
    s, t = _kimlik("Sunny"), _kimlik("Tyrant")
    vg.bag_ekle(KITAP, s, "rutbesi", t, 703, None, "model", 1.0, durum="aday")  # eski yanlış etiket
    _bolum(1098, ["Sunny frowned. Does she know that I'm a Tyrant now, too?"], ["x"])
    kd.bolum_isle(KITAP, 1098, cagir=lambda user, model: (json.dumps(
        {"v": [], "g": [], "h": [], "b": [{"o": "Sunny", "r": "rutbesi", "n": "Tyrant", "p": 1,
                                           "a": "Does she know that I'm a Tyrant now", "s": "konusma"}]}),
        {"model": model, "giris": 1, "cikis": 1, "dusunme": 0}))
    kd.uzlastir(KITAP)
    baglar = {(b["iliski"], b["hedef"]): b for b in vg.baglar(KITAP, kimlik=s)}
    assert baglar[("sinifi", "Tyrant")]["ilk_bolum"] == 1098
    assert ("rutbesi", "Tyrant") not in baglar


def test_kart_anlatimdaki_ust_sinifi_ve_turetilen_cekirdegi_gosterir(kitap):
    _sunny_runleri()
    glossary.set_term(KITAP, "Tyrant", "Tiran")
    s = _kimlik("Sunny")
    vg.bag_ekle(KITAP, s, "sinifi", _kimlik("Tyrant"), 1098, "Does she know that I'm a Tyrant now, too?",
                "model", 0.5, durum="aday")
    run = _run(de.kart(KITAP, s, 1099))
    assert (run["sinifi"]["deger"], run["sinifi"]["origin"], run["sinifi"]["ilk_bolum"]) == ("Tyrant", "anlatim", 1098)
    assert run["Shadow Cores"]["deger"] == "5/7" and run["Shadow Cores"]["origin"] == "anlatim"
    # Yeni çekirdekte sayaç yeni eşikten (1000 x çekirdek) başlar; güncel sayı rünlerde görünmedi.
    assert run["Shadow Fragments"]["deger"] == "?/5000"
    # Spoiler: konum anlatımdan önceyse rün değerleri kalır.
    once = _run(de.kart(KITAP, s, 1050))
    assert (once["sinifi"]["deger"], once["Shadow Cores"]["deger"], once["Shadow Fragments"]["deger"]) == \
        ("Devil", "4/7", "3857/4000")


def test_kart_runden_dusuk_ya_da_eski_anlatim_sinifini_almaz(kitap):
    _sunny_runleri()
    for ad in ("Demon", "Tyrant"):
        glossary.set_term(KITAP, ad, ad)
    s = _kimlik("Sunny")
    vg.bag_ekle(KITAP, s, "sinifi", _kimlik("Demon"), 1098, None, "model", 1.0, durum="aday")  # geri gidemez
    vg.bag_ekle(KITAP, s, "sinifi", _kimlik("Tyrant"), 600, None, "model", 1.0, durum="aday")  # rün 702 daha yeni
    run = _run(de.kart(KITAP, s, None))
    assert (run["sinifi"]["deger"], run["sinifi"]["origin"]) == ("Devil", "sistem")
    assert run["Shadow Cores"]["deger"] == "4/7"


def test_kart_kitap_kurallariyla_celisen_degeri_uyarir(kitap):
    # Sınıf rünlerden Tyrant ama çekirdek 4/7: biri eski. Parça eşiği çekirdekle uyuşmalı.
    _bolum(702, ["Name: Sunless.", "Class: Tyrant.", "Shadow Cores: [4/7].", "Shadow Fragments: [10/3000]."],
           ["x"] * 4)
    dk.cikar(KITAP)
    uyarilar = de.kart(KITAP, _kimlik("Sunny"), None)["uyarilar"]
    assert any("Tyrant" in u and "4" in u for u in uyarilar)
    assert any("3000" in u and "4000" in u for u in uyarilar)


def test_kart_tutarli_degerde_uyari_yok_ve_eski_golge_sayilmaz(kitap):
    # 200'deki tam liste Stone Saint'i düşürür (evrim): tek çekirdekte tek GÜNCEL gölge, uyarı yok.
    _bolum(100, ["Name: Sunless.", "Shadow Cores: [1/7].", "Shadows: [Stone Saint]."], ["x"] * 3)
    _bolum(200, ["Name: Sunless.", "Shadows: [Marble Saint]."], ["x", "x"])
    dk.cikar(KITAP)
    assert de.kart(KITAP, _kimlik("Sunny"), None)["uyarilar"] == []
    _bolum(300, ["Name: Sunless.", "Shadows: [Marble Saint], [Soul Serpent]."], ["x", "x"])
    dk.cikar(KITAP)
    assert any("2 gölge" in u for u in de.kart(KITAP, _kimlik("Sunny"), None)["uyarilar"])


# ---------- Anlatımdaki durum değişimleri (`d`, istem defter-v3) ----------
def _durum_isle(no, en, d):
    _bolum(no, en, ["x"] * len(en))
    sonuc = kd.bolum_isle(KITAP, no, cagir=lambda user, model: (
        json.dumps({"v": [], "g": [], "b": [], "h": [], "d": d}), {"model": model, "giris": 1, "cikis": 1, "dusunme": 0}))
    assert sonuc["durum"] == "completed", sonuc


def _durum_iddialari(no):
    conn = db.connect()
    try:
        return conn.execute("SELECT ozne_ad, iliski, nesne_ad, gecerli, red_nedeni FROM defter_iddia "
                            "WHERE book_slug = ? AND bolum = ? AND tur = 'durum' ORDER BY id", (KITAP, no)).fetchall()
    finally:
        conn.close()


def test_durum_iddiasi_ana_karakterde_zamirle_kabul_baskasinda_ret(kitap):
    # 1090: "Sunny" adı paragraftan çok önce; çekirdek sözcüğü bir önceki paragrafta.
    en = ["Sunny did not have to summon the runes."] + [f"Filler {i}." for i in range(8)] + [
        "The soul was ready to form a new Shadow Core.", "His fifth one. He was about to become a Tyrant.",
        "And... he was a Tyrant."]
    _durum_isle(1090, en, [
        {"o": "Sunny", "k": "cekirdek", "i": "oldu", "n": "fifth", "p": 11, "a": "His fifth one."},
        {"o": "Sunny", "k": "sinif", "i": "oldu", "n": "Tyrant", "p": 12, "a": "And... he was a Tyrant"},
        {"o": "Nephis", "k": "sinif", "i": "oldu", "n": "Tyrant", "p": 12, "a": "And... he was a Tyrant"},
        {"o": "Sunny", "k": "sinif", "i": "oldu", "n": "Archer", "p": 12, "a": "And... he was a Tyrant"},
        {"o": "Sunny", "k": "uçak", "i": "oldu", "n": "x", "p": 12, "a": "And... he was a Tyrant"},
    ])
    assert _durum_iddialari(1090) == [
        ("Sunny", "cekirdek", "5", 1, None), ("Sunny", "sinif", "Tyrant", 1, None),
        ("Nephis", "sinif", "Tyrant", 0, "ad_yok"), ("Sunny", "sinif", "Archer", 0, "rutbe_degil"),
        ("Sunny", "uçak", "x", 0, "durum_yok")]


def test_kart_anlatimdaki_cekirdek_ve_esya_degisimlerini_isler(kitap):
    _sunny_runleri()
    _bolum(700, ["Name: Sunless.", "Memories: [Azure Blade], [Silver Bell]."], ["x", "x"])
    dk.cikar(KITAP)
    _durum_isle(800, ["Sunny watched the Azure Blade shatter into sparks."], [
        {"o": "Sunny", "k": "ani", "i": "kaybetti", "n": "Azure Blade", "p": 1, "a": "the Azure Blade shatter"}])
    _durum_isle(900, ["Sunny received the Shadow Lantern."], [
        {"o": "Sunny", "k": "ani", "i": "kazandi", "n": "Shadow Lantern", "p": 1, "a": "received the Shadow Lantern"}])
    _durum_isle(1090, ["Sunny felt his soul form a new Shadow Core.", "His fifth one."], [
        {"o": "Sunny", "k": "cekirdek", "i": "oldu", "n": "5", "p": 2, "a": "His fifth one."}])
    s = _kimlik("Sunny")
    k = de.kart(KITAP, s, 1099)
    run = _run(k)
    assert (run["sinifi"]["deger"], run["Shadow Cores"]["deger"], run["Shadow Fragments"]["deger"]) == \
        ("Tyrant", "5/7", "?/5000")
    anilar = {a["ad"]: a for a in k["anilar"]}
    assert anilar["Azure Blade"]["alanlar"]["elde"] == "yok" and anilar["Azure Blade"]["elde_bolum"] == 800
    assert anilar["Shadow Lantern"]["origin"] == "anlatim" and "elde" not in anilar["Silver Bell"]["alanlar"]
    once = {a["ad"]: a for a in de.kart(KITAP, s, 799)["anilar"]}
    assert "elde" not in once["Azure Blade"]["alanlar"] and "Shadow Lantern" not in once
    # Rün kanıtı üstün: sonraki tam liste Azure Blade'i yine gösterirse anlatımdaki kayıp uygulanmaz.
    _bolum(950, ["Name: Sunless.", "Memories: [Azure Blade], [Silver Bell], [Shadow Lantern]."], ["x", "x"])
    dk.cikar(KITAP)
    assert {a["ad"]: a for a in de.kart(KITAP, s, 1099)["anilar"]}["Azure Blade"]["alanlar"].get("elde") != "yok"


def test_durum_iddiasi_kayitli_kimligi_cozer_cins_adi_reddeder(kitap):
    # Vertex ölçümü: model kayıtlı öğeye id yazdı ("e12" = Devil) — 8 doğru iddia eleniyordu;
    # "the fifth shadow" gölge adı sanıldı.
    glossary.set_term(KITAP, "Devil", "Şeytan")
    en = ["Name: Sunless.", "Class: Devil.", "Sunny was now in possession of the fifth shadow."]

    def cagir(user, model):
        idler = {k["ad"]: k["id"] for k in json.loads(user)["kayitli"]}
        return json.dumps({"v": [], "g": [], "b": [], "h": [], "d": [
            {"o": idler["Sunny"], "k": "sinif", "i": "oldu", "n": idler["Devil"], "p": 2, "a": "Class: Devil."},
            {"o": "Sunny", "k": "golge", "i": "kazandi", "n": "fifth shadow", "p": 3,
             "a": "in possession of the fifth shadow"}]}), {"model": model, "giris": 1, "cikis": 1, "dusunme": 0}

    _bolum(702, en, ["x"] * 3)
    kd.bolum_isle(KITAP, 702, cagir=cagir)
    assert _durum_iddialari(702) == [("Sunny", "sinif", "Devil", 1, None),
                                     ("Sunny", "golge", "fifth shadow", 0, "ad_kucuk")]


def test_durum_alintisi_iki_paragrafa_yayilabilir(kitap):
    # Vertex ölçümü (744): alıntı "[Child of Shadows] was gone. A new Attribute had replaced it." iki paragraf.
    _durum_isle(744, ["Sunny studied the runes.", "Instead... [Child of Shadows] was gone.",
                      "A new Attribute had replaced it.", "Attribute: [Master of Shadows]."], [
        {"o": "Sunny", "k": "nitelik", "i": "evrimlesti", "n": "Child of Shadows", "y": "Master of Shadows",
         "p": 2, "a": "Instead... [Child of Shadows] was gone. A new Attribute had replaced it."},
        {"o": "Sunny", "k": "nitelik", "i": "kaybetti", "n": "Child of Shadows", "p": 1,
         "a": "Sunny studied the runes. Instead... [Child of Shadows] was gone. A new Attribute"}])
    assert [r[3:] for r in _durum_iddialari(744)] == [(1, None), (0, "alinti_yok")]


# ---------- Wikiye göre (dış kontrol) ----------
def test_kart_wiki_notlarini_konuma_kadar_ve_defterde_olmayan_adlari_verir(kitap):
    from core import wiki_arastirma as w

    def getir(adres, params):
        if params.get("meta") == "siteinfo":
            return {"query": {"general": {"sitename": "Shadow Slave Wiki", "server": "https://shadowslave.fandom.com"}}}
        if params.get("list") == "allpages":
            return {"query": {"allpages": [{"title": "Sunny"}]}}
        return {"parse": {"wikitext": {"*": "'''Memory:''' [Azure Blade].<ref>Chapter 15 x</ref>\n"
                                             "He got [Shadow Lantern].<ref>Chapter 653 y</ref>\n"
                                             "He got [Feather of Truth].<ref>Chapter 1500 z</ref>"}}}

    w.arastir(KITAP, getir, bekleme=0)
    wiki = de.kart(KITAP, _kimlik("Sunny"), 700)["wiki"]
    assert wiki["durum"] == "hazir" and len(wiki["notlar"]) == 2  # 1500 konumdan sonra
    assert [e["ad"] for e in wiki["eksikler"]] == ["Shadow Lantern"]  # Azure Blade defterde var
    assert de.kart(KITAP, _kimlik("Nephis"), 700)["wiki"]["durum"] == "sayfa_yok"
    # "Deftere ekle": elle kayıt (kanıtı wiki cümlesi) eklenince ad eksik sayılmaz, anılarda görünür.
    dk.elle_yaz(KITAP, {"tur": "ani", "sahip": "Sunny", "ad": "Shadow Lantern", "ilk_bolum": 653,
                        "kanit": "Wiki (Shadow Slave Wiki): He got [Shadow Lantern]."})
    kart = de.kart(KITAP, _kimlik("Sunny"), 700)
    assert kart["wiki"]["eksikler"] == []
    lantern = next(a for a in kart["anilar"] if a["ad"] == "Shadow Lantern")
    assert lantern["origin"] == "elle" and lantern["kanit"].startswith("Wiki (Shadow Slave Wiki)")
