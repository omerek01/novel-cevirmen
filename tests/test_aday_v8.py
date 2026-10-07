"""Faz 2A v8: aday-öncelikli çıkarım + span kimlikli kanıt — çevrimdışı, model SAHTE, adlar KURGU."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from core import bilgi_aday as ba, bilgi_delta as bd, cache, db, glossary, varlik_grafigi as g

K = "v8-kitap"


def kur(no, metin, *adlar):
    for a in adlar:
        glossary.set_term(K, a, a)
    cache.save_chapter(f"https://x/{K}/{no}", {"book_slug": K, "book_title": "V8", "title": f"B{no}",
                                               "chapter_no": no, "translation": "Ç.", "source": metin})


def calis(no, karar, serbest=()):
    veri = {"candidate_decisions": list(karar), "free_discoveries": list(serbest)}
    return ba.aday_degerlendir(K, no, bd.CIKARICI_MODELI, cagri=lambda u, s: (json.dumps(veri), {}))


def kd(cid, s, r, o, ids, decision="accept", kt="relationship", epi="confirmed", **ek):
    return {"candidate_id": cid, "decision": decision, "knowledge_type": kt, "subject": s, "relation_or_state": r,
            "object_or_value": o, "epistemic": epi, "evidence_span_ids": ids, **ek}


def kabul(sonuc):
    return [(o["veri"].get("ozne") or o["veri"].get("varlik"), o["veri"].get("iliski") or o["veri"].get("anahtar"),
             o["veri"].get("nesne") or o["veri"].get("deger")) for o in sonuc["degerlendirme"]["oneriler"] if o["karar"] == "işle"]


def aday_bul(sonuc, kelime):
    return next(c for c in sonuc["adaylar"] if kelime in c["snippet"])


# ---------- span'lar ----------
def test_span_kimlikleri_kararli_ve_ofsetler_birebir():
    metin = "Arden walked in. She... she smiled. \"Go!\" he said.\nMira stayed."
    a, b = ba.span_ayir(metin, 7), ba.span_ayir(metin, 7)
    assert a == b and [s["span_id"] for s in a] == ["ch7:p0:s0", "ch7:p0:s1", "ch7:p0:s2", "ch7:p1:s0"]
    assert all(metin[s["char_start"]:s["char_end"]] == s["text"] for s in a)
    assert a[1]["text"] == "She... she smiled."      # üç nokta + küçük harf cümleyi BÖLMEZ


def test_span_kimligi_baska_bolumu_reddeder():
    assert ba.span_kimligi("p0s1", 7) == "ch7:p0:s1" and ba.span_kimligi("ch7:p0:s1", 7) == "ch7:p0:s1"
    assert ba.span_kimligi("ch8:p0:s1", 7) == "" and ba.span_kimligi("hello", 7) == ""


# ---------- liderlik (etken/edilgen) + yerel epistemik ----------
def test_edilgen_ve_etken_liderlik_epistemik_yerellik():
    metin = ("The Iron Guard was led by a grim man named Torvan, who was perhaps the oldest soldier alive. "
             "Lysa leads the Hunters.")
    kur(1, metin, "Iron Guard", "Torvan", "Lysa", "Hunters")
    r = calis(1, [kd("C01", "Iron Guard", "lideri", "Torvan", ["p0s0"]), kd("C02", "Hunters", "lideri", "Lysa", ["p0s1"])])
    assert {("Iron Guard", "lideri", "Torvan"), ("Hunters", "lideri", "Lysa")} <= set(kabul(r))
    r = calis(1, [kd("C01", "Torvan", "lideri", "Iron Guard", ["p0s0"])])           # ters yön
    assert not kabul(r) and r["aday_kararlari"][0]["reason"] == "direction_reversed"


def test_aday_ureticisi_liderlik_ailesini_isaretler():
    kur(2, "The Iron Guard was led by Torvan. The Hunters were under the command of Lysa.", "Iron Guard", "Torvan", "Lysa", "Hunters")
    r = calis(2, [])
    assert all("leadership" in c["category"] for c in r["adaylar"]) and len(r["adaylar"]) == 2


# ---------- zamir: izinli öncül / belirsiz öncül ----------
def test_zamir_izinli_oncul_ve_yuksek_etki():
    kur(3, "Mira drew her blade. She killed Boran.", "Mira", "Boran")
    r = calis(3, [])
    c = aday_bul(r, "killed")
    assert [a["entity"] for a in c["antecedent_candidates"]] == ["Mira"]
    r = calis(3, [kd(c["candidate_id"], "Mira", "oldurdu", "Boran", ["p0s1"])])
    assert ("Mira", "oldurdu", "Boran") in kabul(r)
    r = calis(3, [kd(c["candidate_id"], "Arden", "oldurdu", "Boran", ["p0s1"])])  # öncül değil
    assert not kabul(r) and r["aday_kararlari"][0]["reason"] == "entity_not_allowed"


def test_belirsiz_oncul_incelemeye_duser():
    kur(4, "Mira spoke to Lina. She killed Boran.", "Mira", "Lina", "Boran")
    r = calis(4, [])
    c = aday_bul(r, "killed")
    r = calis(4, [kd(c["candidate_id"], "Mira", "oldurdu", "Boran", ["p0s1"])])
    assert not kabul(r) and r["aday_kararlari"][0]["outcome"] == "review"


def test_capraz_paragraf_oncul_otomatik_kabul_degil():
    kur(5, "Mira drew her blade.\nShe killed Boran.", "Mira", "Boran")
    r = calis(5, [])
    c = aday_bul(r, "killed")
    assert c["antecedent_candidates"][0]["cross_paragraph"]
    r = calis(5, [kd(c["candidate_id"], "Mira", "oldurdu", "Boran", ["p1s0"])])
    assert not kabul(r) and r["aday_kararlari"][0]["outcome"] == "review"


# ---------- span kuralları ----------
@pytest.mark.parametrize("ids,sebep", [(["p0s0", "p0s2"], "non_contiguous_span"), (["p0s1", "p0s0"], "non_contiguous_span"),
                                       (["p0s0", "p1s0"], "cross_paragraph_span"), (["p9s9"], "invalid_span_id"),
                                       (["ch99:p0:s0"], "invalid_span_id"), (["p0s0", "p0s1", "p0s2", "p0s3"], "invalid_span_id")])
def test_gecersiz_spanlar(ids, sebep):
    kur(6, "Torvan led the Iron Guard. One. Two. Three.\nNext.", "Iron Guard", "Torvan")
    r = calis(6, [], [kd(None, "Iron Guard", "lideri", "Torvan", ids)])
    assert not kabul(r) and r["aday_kararlari"][0]["reason"] == sebep


def test_cok_cumleli_bitisik_span_kanit_kaynaktan_alinir():
    kur(7, "Torvan rose. The Iron Guard was led by him since winter.", "Iron Guard", "Torvan")
    r = calis(7, [], [kd(None, "Iron Guard", "lideri", "Torvan", ["p0s0", "p0s1"])])
    k = r["aday_kararlari"][0]
    assert k["evidence"] == "Torvan rose. The Iron Guard was led by him since winter."


# ---------- ölüm ----------
@pytest.mark.parametrize("metin", ["They buried Arden. Everyone mourned Arden's death.",
                                   "They stared at the corpse of Arden."])
def test_adlastirilmis_ve_ceset_olumu(metin):
    kur(8, metin, "Arden")
    sid = [s["span_id"] for s in ba.span_ayir(metin, 8)][-1]
    r = calis(8, [], [kd(None, "Arden", "life_status", "dead", [sid], kt="state")])
    assert ("Arden", "Yaşam", "dead") in kabul(r)


def test_tanimlayici_olum_baglanamazsa_inceleme():
    metin = "He spent months with Arden, and then came the young man's death."
    kur(9, metin, "Arden")
    r = calis(9, [], [kd(None, "Arden", "life_status", "dead", ["p0s0"], kt="state")])
    assert not kabul(r) and r["aday_kararlari"][0]["outcome"] == "review"


def test_parazit_olumu_konak_olumu_degil_v8():
    metin = "It cut the parasite inside the Bone Tyrant in half. Then the mountain of bones crumbled."
    kur(10, metin, "Bone Tyrant")
    r = calis(10, [], [kd(None, "Bone Tyrant", "life_status", "dead", ["p0s0", "p0s1"], kt="state")])
    assert not kabul(r)


# ---------- True Name / rol / soy / kimlik ----------
def test_gercek_ad_tekil_cogul_ve_belirsiz():
    kur(11, "Arden's True Names include Dawn. Arden and Mira revealed their True Names: Dawn and Dusk.", "Arden", "Mira", "Dawn", "Dusk")
    r = calis(11, [], [kd(None, "Arden", "gercek_adi", "Dawn", ["p0s0"], kt="identity")])
    assert ("Arden", "gercek_adi", "Dawn") in kabul(r)
    r = calis(11, [], [kd(None, "Arden", "gercek_adi", "Dawn", ["p0s1"], kt="identity")])
    assert not kabul(r)


def test_rol_durumu():
    kur(12, "Torvan served as the scout of the band.", "Torvan")
    r = calis(12, [], [kd(None, "Torvan", "role", "scout", ["p0s0"], kt="state")])
    assert ("Torvan", "Görev", "scout") in kabul(r)


def test_soy_kapasite_boslugu_basaridir_iliski_yazmaz():
    kur(13, "Arden received the second part of the bloodline of the Weaver.", "Arden", "Weaver")
    r = calis(13, [], [kd(None, "Arden", "capability_gap", "Weaver", ["p0s0"], decision="capability_gap", gap_note="lineage")])
    assert not kabul(r) and any(i[0] == "relation_capability_gap" for i in r["degerlendirme"]["inceleme"])


def test_kimlik_aciga_cikmasi_inceleme_once_birlestirme_yok():
    kur(14, "So Mira was actually Lady Ash all along.", "Mira", "Lady Ash")
    r = calis(14, [], [kd(None, "Mira", "identity_revelation", "Lady Ash", ["p0s0"], decision="review", kt="identity")])
    assert any(i[0] == "identity_merge" for i in r["degerlendirme"]["inceleme"]) and not kabul(r)


# ---------- adaylar: tekilleştirme, sınır, rün ayrımı ----------
def test_aday_tekillestirme_ve_sinir():
    metin = " ".join(f"Arden{i} killed Boran{i}. Arden{i} killed Boran{i}." for i in range(30))
    kur(15, metin)
    r = calis(15, [])
    assert len(r["adaylar"]) <= ba.ADAY_SINIRI and len({c["span_ids"][0] for c in r["adaylar"]}) == len(r["adaylar"])
    assert r["olcum"]["aday_tokeni"] <= ba.ADAY_TOKEN_TAVANI


def test_run_satiri_aday_olmaz():
    kur(16, "Name: Arden.\nAttributes: [Steel Body].\nArden was dead by dawn.", "Arden")
    r = calis(16, [])
    assert all("Attributes" not in c["snippet"] for c in r["adaylar"])


def test_serbest_kesif_siniri_ve_gecerli_span():
    kur(17, "Torvan led the Iron Guard. Lysa led the Hunters. Kel led the Watch. Ana led the Wing.",
        "Torvan", "Iron Guard", "Lysa", "Hunters", "Kel", "Watch", "Ana", "Wing")
    s = [kd(None, g_, "lideri", l, [f"p0s{i}"]) for i, (l, g_) in enumerate(
        [("Torvan", "Iron Guard"), ("Lysa", "Hunters"), ("Kel", "Watch"), ("Ana", "Wing")])]
    r = calis(17, [], s)
    assert len(kabul(r)) == 3 and r["dogrulayici_sayac"]["free_over_cap"] == 1
    r = calis(17, [], [kd(None, "Iron Guard", "lideri", "Torvan", [])])
    assert not kabul(r)


def test_bilinmeyen_aday_kimligi_reddedilir():
    kur(18, "Torvan led the Iron Guard.", "Torvan", "Iron Guard")
    r = calis(18, [kd("C99", "Iron Guard", "lideri", "Torvan", ["p0s0"])])
    assert not kabul(r) and r["dogrulayici_sayac"]["unknown_candidate"] == 1


def test_istem_kanit_metni_istemez_span_ister():
    t = ba.ADAY_TALIMATI
    assert "never write quotes" in t and "evidence_span_ids" in t and "THESE ARE NOT FACTS" in ba.istem_kur(
        {"satirlar": [], "run_satirlari": [], "bilgi_siniri": 0}, "Arden ran.", 1, [])
    sema = ba.yanit_semasi()
    assert "evidence" not in sema["properties"]["candidate_decisions"]["items"]["properties"]
    assert ba.ADAY_SEMA_SURUMU == "delta-4-span-evidence"


def test_vertex_disi_model_reddedilir():
    with pytest.raises(bd.SaglayiciHatasi):
        ba.aday_degerlendir(K, 1, "gemini-3.8-flash")


# ---------- değiştirilemezlik ----------
def test_aday_dogrulama_kipi_yazmaz():
    kur(19, "Mira drew her blade. She killed Boran. The Iron Guard was led by Torvan.", "Mira", "Boran", "Iron Guard", "Torvan")
    bd._connect().close()

    def parmak():
        c = sqlite3.connect(db.db_path())
        try:
            return {t: hashlib.sha256(repr(c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()).encode()).hexdigest()
                    for t in ("varlik_bag", "varlik_deger", "glossary", "bilgi_isleme", "bilgi_oneri", "bilgi_inceleme", "bilgi_bas", "chapters")}
        finally:
            c.close()
    once = parmak()
    r = calis(19, [], [kd(None, "Iron Guard", "lideri", "Torvan", ["p0s2"]), kd(None, "Mira", "oldurdu", "Boran", ["p0s1"])])
    assert len(kabul(r)) == 2 and parmak() == once


def test_yuksek_etki_iddia_yerelligi():
    """Başka cümledeki olumsuzluk iddiayı reddettirmez; uçlar ayrı cümledeyse inceleme."""
    kur(20, "Mira struck. Mira killed Boran in the hall. Lina did not care.", "Mira", "Boran", "Lina")
    r = calis(20, [], [kd(None, "Mira", "oldurdu", "Boran", ["p0s1", "p0s2"])])
    assert ("Mira", "oldurdu", "Boran") in kabul(r)
    kur(21, "Boran fell. It was Mira who struck, and she did not care.", "Mira", "Boran")
    r = calis(21, [], [kd(None, "Mira", "oldurdu", "Boran", ["p0s0", "p0s1"])])
    assert not kabul(r) and r["aday_kararlari"][0]["outcome"] == "review"
    kur(22, "Mira tried to kill Boran.", "Mira", "Boran")   # aynı cümlede olumsuzlayıcı -> ret korunur
    r = calis(22, [], [kd(None, "Mira", "oldurdu", "Boran", ["p0s0"])])
    assert not kabul(r) and r["aday_kararlari"][0]["outcome"] == "rejected"
