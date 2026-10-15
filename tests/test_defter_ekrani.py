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
