"""Faz 2A v6: doğrulayıcı temsil gücü (zamir, ceset, çoğul True Names, rol), rün alt
satırları ve kapsama ipuçları — çevrimdışı, adlar KURGU. Her yetenek için olumsuzlar
olumlulardan fazladır: recall artarken hassasiyet kaybedilmemeli."""
from __future__ import annotations

import json

import pytest

from core import bilgi_delta as bd, bilgi_kanit as k, cache, glossary, kapsama_ipuclari as ki, varlik_grafigi as g


def rel(s, r, o, e, kaynak=None):
    return k.semantik_sonuc({"ozne": s, "iliski": r, "nesne": o, "kanit": e}, {}, (), kaynak)


def durum(ad, deger, e, kaynak=None):
    x = {"varlik": ad, "anahtar": "Yaşam", "makine_anahtari": "life_status", "deger": deger,
         "durum_bilgisi": "confirmed", "kanit": e}
    return k.state_kaniti(x, kaynak or e, {}, [])[0]


# ---------- sınırlı zamir çözümü ----------
def test_zamir_olumlu_durum():
    kaynak = "The gate opened at dawn. Mira stood by the wall. She was still alive."
    assert durum("Mira", "alive", "She was still alive.", kaynak)


def test_zamir_olumlu_oldurme():
    kaynak = "Arden reached the warrior. He killed Boran."
    assert rel("Arden", "oldurdu", "Boran", "He killed Boran.", kaynak)[0] == "verified"


@pytest.mark.parametrize("kaynak,kanit", [
    ("Arden spoke to Mira. She was still alive.", "She was still alive."),                 # iki aday
    ("Arden saw Mira while Lina approached. She was still alive.", "She was still alive."),  # üç aday
    ("Mira stood by the wall.\nShe was still alive.", "She was still alive."),               # paragraf sınırı
    ("Mira stood by the wall. The night was long. She was still alive.", "She was still alive."),  # 2 cümle geri
    ("She was still alive. Mira stood by the wall.", "She was still alive."),                # öncül yok
    ("Mira stood by the wall. Her heart was still alive.", "Her heart was still alive."),    # iyelik çözülmez
    ("Arden stood by the wall. She was still alive.", "She was still alive."),               # aday hedef değil
])
def test_zamir_olumsuz_durum(kaynak, kanit):
    assert not durum("Mira", "alive", kanit, kaynak)


@pytest.mark.parametrize("kaynak,kanit", [
    ("Arden and Mira reached Boran. He died.", "He died."),                # öldüren çıkarılmaz
    ("Arden reached the warrior. He attacked Boran.", "He attacked Boran."),  # açık öldürme yok
    ("Arden reached the warrior. He tried to kill Boran.", "He tried to kill Boran."),
    ("Arden met Lina. He killed Boran.", "He killed Boran."),               # iki aday
    ("Arden reached the warrior.\nHe killed Boran.", "He killed Boran."),   # paragraf sınırı
])
def test_zamir_olumsuz_oldurme(kaynak, kanit):
    assert rel("Arden", "oldurdu", "Boran", kanit, kaynak)[0] != "verified"


def test_zamir_kaynak_verilmezse_cozulmez():
    assert rel("Arden", "oldurdu", "Boran", "He killed Boran.")[0] != "verified"


def test_zamir_kanit_birebir_kalir():
    terim = ("Mira",)
    glossary.set_term("v6-kitap", terim[0], terim[0])
    kaynak = "The gate opened. Mira stood by the wall. She was still alive."
    x = {"varlik": "Mira", "anahtar": "life_status", "deger": "alive", "kanit": "She was still alive.",
         "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir("v6-kitap", 5, {**{a: [] for a in bd.DELTA_SEMASI}, "state_changes": [x]}, kaynak)
    kabul = [o for o in sonuc["oneriler"] if o["karar"] == "işle"]
    assert kabul and kabul[0]["veri"]["kanit"] == "She was still alive."   # model alıntısı değişmedi
    # Kaynakta olmayan bir alıntı zamirle kurtarılmaz.
    x["kanit"] = "She was alive."
    sonuc = bd.delta_degerlendir("v6-kitap", 5, {**{a: [] for a in bd.DELTA_SEMASI}, "state_changes": [x]}, kaynak)
    assert not [o for o in sonuc["oneriler"] if o["karar"] == "işle"]


# ---------- ceset ----------
@pytest.mark.parametrize("e", ["They stared at the corpse of the Bone Tyrant.", "Bone Tyrant's corpse lay in the mud.",
                               "He found the body of the dead Bone Tyrant."])
def test_ceset_olum_durumu(e):
    assert durum("Bone Tyrant", "dead", e)


@pytest.mark.parametrize("e", ["The statue was shaped like a corpse of the Bone Tyrant.",
                               "The Bone Tyrant looked corpse-like.",
                               "The Bone Tyrant's corpse puppet moved.",
                               "The Bone Tyrant's corpse eater feasted.",
                               "It lay there like the corpse of the Bone Tyrant.",
                               "They found the corpse of an unknown person near the Bone Tyrant."])
def test_ceset_olumsuz(e):
    assert not durum("Bone Tyrant", "dead", e)


def test_ceset_oldurme_iliskisi_uretmez():
    e = "Ilsa stared at the corpse of the Bone Tyrant."
    assert rel("Ilsa", "oldurdu", "Bone Tyrant", e)[0] != "verified"


# ---------- True Name tekil/çoğul ----------
def test_gercek_ad_tekil_ve_cogul():
    assert rel("Arden", "gercek_adi", "Dawn", "Arden's True Name was Dawn.")[0] == "verified"
    assert rel("Arden", "gercek_adi", "Dawn", "Arden's True Names include Dawn.")[0] == "verified"


@pytest.mark.parametrize("e", ["Arden and Mira revealed their True Names: Dawn and Dusk.",
                               "Arden spoke of True Names. Mira said Dawn.",
                               "Arden was called Dawn."])
def test_gercek_ad_olumsuz(e):
    assert rel("Arden", "gercek_adi", "Dawn", e)[0] != "verified"


# ---------- rol ----------
@pytest.mark.parametrize("e,v", [("Arden was the scout.", "scout"), ("Arden served as the commander.", "commander"),
                                 ("Finally, Instructor Arden took the stage.", "instructor")])
def test_rol_olumlu(e, v):
    x = {"varlik": "Arden", "anahtar": "Görev", "makine_anahtari": "role", "deger": v, "durum_bilgisi": "confirmed", "kanit": e}
    assert k.state_kaniti(x, e, {}, [])[0]


@pytest.mark.parametrize("e,v", [("Arden met the scout.", "scout"), ("Mira was the commander, not Arden.", "commander"),
                                 ("Arden wanted to become a great scout someday.", "scout")])
def test_rol_olumsuz(e, v):
    x = {"varlik": "Arden", "anahtar": "Görev", "makine_anahtari": "role", "deger": v, "durum_bilgisi": "confirmed", "kanit": e}
    assert not k.state_kaniti(x, e, {}, [])[0]


# ---------- rün alt satırları ----------
def test_run_alt_satiri_ozneyi_mirasla_alir():
    metin = ("Name: Arden.\nRank: Ascended.\nAttributes: [Steel Body].\nHe read on.\n"
             "[Iron Will] Attribute Description: \"Strong.\"\n[Shadow Step] Ability Description: \"Fast.\"")
    p = g.sistem_baglarini_bul(metin, "Hero")
    assert ("Arden", "niteligi", "Steel Body") in [x[:3] for x in p]
    assert ("Arden", "niteligi", "Iron Will") in [x[:3] for x in p]
    assert ("Arden", "yetenegi", "Shadow Step") in [x[:3] for x in p]


def test_yetenek_duyurusu_ve_uc_nokta():
    metin = "[Aspect Ability acquired.]\nHe held his breath.\n[...Aspect Ability Name: Glass Veil.]"
    assert ("Hero", "yetenegi", "Glass Veil") in [x[:3] for x in g.sistem_baglarini_bul(metin, "Hero")]
    metin = "Aspect Ability: [Glass Veil].\nShe smiled."
    assert not g.sistem_baglarini_bul(metin, "Hero")   # etkin blok yok -> özne yok


@pytest.mark.parametrize("metin", [
    "[Iron Will] Attribute Description: \"Strong.\"",                                         # blok yok
    "Name: Arden.\nRank: Ascended.\n" + "Narration.\n" * 13 + "[Iron Will] Attribute Description: \"x\"",  # pencere aşıldı
    "Memory: [Silver Bell].\nMemory Rank: Dormant.\n[Iron Will] Attribute Description: \"x\"",  # Anı bloğu
])
def test_run_ozne_sizintisi_yok(metin):
    assert not any(x[2] == "Iron Will" for x in g.sistem_baglarini_bul(metin, "Hero"))


def test_run_bloku_sonraki_duzyaziya_sizmaz():
    metin = "Name: Arden.\nRank: Ascended.\nArden seemed to possess an unusual ability called Shadow Step."
    assert not any(x[2] == "Shadow Step" for x in g.sistem_baglarini_bul(metin, "Hero"))


# ---------- kapsama ipuçları ----------
def test_ipucu_cikarimi_kategori_ve_span():
    kaynak = "Arden walked home. Mira was dead by dawn. Boran had taught Lina the spear. People believed the tower fell."
    c = ki.ipuclari(kaynak)
    assert {x["kategori"] for x in c} == {"death_life", "teaching", "epistemic"}
    assert all(x["span"] in kaynak for x in c)
    assert all(isinstance(x["konum"], int) for x in c)


def test_ipucu_tekillestirme_ve_sinir():
    kaynak = " ".join(f"Arden{i} was dead." for i in range(30)) + " Mira was dead. Mira was dead."
    c = ki.ipuclari(kaynak)
    assert len(c) <= ki.IPUCU_SINIRI and len({x["span"] for x in c}) == len(c)
    assert sum(x["kategori"] == "death_life" for x in c) <= ki.KATEGORI_SINIRI
    assert bd._tok(ki.ipucu_bolumu(c)) <= ki.IPUCU_TOKEN_BUTCESI


def test_ipucu_deterministik_plani_tekrarlamaz():
    kaynak = "Attributes: [Steel Body].\nMira was dead."
    assert [x["kategori"] for x in ki.ipuclari(kaynak, ("Attributes: [Steel Body].",))] == ["death_life"]


def test_ipucu_olgu_degildir():
    """İpucu doğrulayıcıyı ATLATMAZ: ipucu metni kanıt olarak verilse bile kural aynı."""
    glossary.set_term("v6-ipucu", "Mira", "Mira")
    glossary.set_term("v6-ipucu", "Arden", "Arden")
    kaynak = "Arden fought hard. Mira was wounded."
    cue = ki.ipuclari(kaynak)
    x = {"ozne": "Arden", "iliski": "oldurdu", "nesne": "Mira", "kanit": "Arden fought hard. Mira was wounded.",
         "durum_bilgisi": "confirmed"}
    sonuc = bd.delta_degerlendir("v6-ipucu", 3, {**{a: [] for a in bd.DELTA_SEMASI}, "new_relationships": [x]}, kaynak)
    assert not [o for o in sonuc["oneriler"] if o["karar"] == "işle"]
    assert all("COVERAGE" not in o.get("karar", "") for o in sonuc["oneriler"])
    assert isinstance(cue, list)


def test_ipucu_istemde_ayri_bolum_ve_sozlesme():
    t = bd.CIKARICI_TALIMATI
    assert "COVERAGE CUES CONTRACT" in t and "They are NOT facts and NOT evidence" in t
    baglam = {"bolum": 4, "bilgi_siniri": 3, "satirlar": [], "run_satirlari": [],
              "ipuclari": [{"kategori": "death_life", "span": "Mira was dead.", "konum": 0}]}
    istem = bd.istem_kur(baglam, "Mira was dead.")
    assert "COVERAGE CUES — THESE ARE NOT FACTS:\n[1] (death_life) Mira was dead." in istem
    assert istem.index("COVERAGE CUES") < istem.index("THIS CHAPTER'S TEXT")


def test_ipucu_baglam_butcesine_girmez():
    cache.save_chapter("https://x/v6-b/9", {"book_slug": "v6-b", "book_title": "B", "title": "B9", "chapter_no": 9,
                                            "translation": "Ç.", "source": "Mira was dead. Arden taught Lina."})
    b = bd.baglam_kur("v6-b", 9, "Mira was dead. Arden taught Lina.", butce=10)
    assert b["baglam_tokeni"] <= 10 and b["ipuclari"] and b["ipucu_tokeni"] > 0


# ---------- doğrulama kipi yazmaz (ipuçlu istemle) ----------
def test_ipuclu_dogrulama_kipi_yazmaz():
    import hashlib
    import sqlite3
    from core import db
    glossary.set_term("v6-sim", "Mira", "Mira")
    cache.save_chapter("https://x/v6-sim/2", {"book_slug": "v6-sim", "book_title": "S", "title": "B2", "chapter_no": 2,
                                              "translation": "Ç.", "source": "The gate opened. Mira stood there. She was still alive."})
    bd._connect().close()

    def parmak():
        c = sqlite3.connect(db.db_path())
        try:
            return {t: hashlib.sha256(repr(c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()).encode()).hexdigest()
                    for t in ("varlik_bag", "varlik_deger", "glossary", "bilgi_isleme", "bilgi_oneri", "bilgi_inceleme", "bilgi_bas", "chapters")}
        finally:
            c.close()
    once = parmak()
    veri = {**{a: [] for a in bd.DELTA_SEMASI}, "state_changes": [
        {"varlik": "Mira", "anahtar": "life_status", "deger": "alive", "kanit": "She was still alive.", "durum_bilgisi": "confirmed"}]}
    goruldu = []
    r = bd.bolum_degerlendir("v6-sim", 2, bd.CIKARICI_MODELI,
                             cagri=lambda u, s: (goruldu.append(u) or json.dumps(veri), {}))
    assert "COVERAGE CUES" in goruldu[0] and r["olcum"]["ipucu_sayisi"] >= 1
    assert [o for o in r["degerlendirme"]["oneriler"] if o["karar"] == "işle"]
    assert parmak() == once
