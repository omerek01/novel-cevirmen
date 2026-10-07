"""Bilgi deltası çekirdeği (Faz 2A) — çevrimdışı, model SAHTE. Metinler yapay."""
from __future__ import annotations

import json

import pytest

from core import bilgi_delta as bd, cache, glossary, varlik_grafigi as vg

K = "delta-kitap"


def _bolum(no, metin):
    cache.save_chapter(f"https://x/{K}/{no}", {
        "book_slug": K, "book_title": "Delta", "title": f"B{no}", "chapter_no": no,
        "translation": "Çeviri.", "source": metin,
    })


def _terimler(*adlar):
    for ad in adlar:
        glossary.set_term(K, ad, ad)
    return vg.DugumCozucu(K).coz


def _cagri(veri):
    def f(user, system):
        f.istemler.append(user)
        return json.dumps(veri), {"giris_tokeni": 100, "cikis_tokeni": 20}
    f.istemler = []
    return f


BOS = {ad: [] for ad in bd.DELTA_SEMASI}


# ---------- şema ----------
def test_sema_dogrulayici_bilinmeyen_ve_eksik_alani_reddeder():
    assert bd.sema_dogrula(BOS) == []
    assert any("bilinmeyen bölüm" in h for h in bd.sema_dogrula({**BOS, "events": []}))
    hatali = {**BOS, "new_relationships": [{"ozne": "A", "iliski": "yoldasi", "nesne": "B"}]}
    assert any("kanit eksik" in h for h in bd.sema_dogrula(hatali))
    hatali = {**BOS, "new_relationships": [{"ozne": "A", "iliski": "uydurma", "nesne": "B", "kanit": "x"}]}
    assert any("iliski bilinmiyor" in h for h in bd.sema_dogrula(hatali))
    hatali = {**BOS, "state_changes": [{"varlik": "A", "anahtar": "Yaşam", "deger": "ölü", "kanit": "x",
                                        "durum_bilgisi": "kesin"}]}
    assert any("durum_bilgisi" in h for h in bd.sema_dogrula(hatali))
    hatali = {**BOS, "new_relationships": [{"ozne": "A", "iliski": "yoldasi", "nesne": "B", "kanit": "x",
                                            "gecerli_baslangic": "300"}]}
    assert any("tam sayı değil" in h for h in bd.sema_dogrula(hatali))


# ---------- GELECEK BİLGİ GÜVENCESİ ----------
def test_baglam_yalniz_onceki_bolumlerin_bilgisini_tasir():
    k = _terimler("Mask", "Kai", "Order")
    _bolum(100, "The Mask watched Kai from the Order hall.")
    vg.bag_ekle(K, k("Kai"), "grubu", k("Order"), 50, "erken", "manual", 1.0)            # geçmiş: görünür
    vg.bag_ekle(K, k("Kai"), "gercek_adi", k("Mask"), 700, "kimlik", "manual", 1.0)      # gelecek kimlik
    vg.bag_ekle(K, k("Mask"), "dusmani", k("Order"), 100, "aynı bölüm", "manual", 1.0)    # N'de öğrenilen
    vg.deger_yaz(K, k("Kai"), "Yaşam", "sağ", 80)                                          # geçmiş durum
    vg.deger_yaz(K, k("Kai"), "Yaşam", "ölü", 900)                                         # gelecek durum
    glossary.terimi_yaz(K, "Mask", "Mask", kosul="aslında Kai")
    glossary.alan_kokeni_yaz(K, "Mask", "kosul", 700)                                       # gelecek açıklama
    glossary.tanim_yaz(K, "Mask", "kimliği gizli Kai")
    glossary.alan_kokeni_yaz(K, "Mask", "tanim", 700)                                       # gelecek tanım
    with glossary._connect() as c:
        c.execute("UPDATE glossary SET first_chapter = 700 WHERE book_slug = ? AND source = 'Mask'", (K,))
    metin = "\n".join(bd.baglam_kur(K, 100, bd.kaynak_metin(K, 100))["satirlar"])
    assert "Kai --grubu--> Order" in metin
    assert "Yaşam = sağ" in metin
    assert "gercek_adi" not in metin and "Mask (" not in metin.split("VARLIK")[0]
    assert "ölü" not in metin and "aslında Kai" not in metin and "kimliği gizli" not in metin
    assert "dusmani" not in metin  # N'de öğrenilen bağ N-1 bilgisi değildir
    # Bölümün KENDİ metnindeki ad bağlamda var (okur onu bu bölümde görüyor), açıklaması yok.
    assert "VARLIK Mask" in metin


def test_baglam_butcesi_asilmaz_ve_kesilen_sayilir():
    k = _terimler("Kai", *[f"Yer{i}" for i in range(80)])
    _bolum(200, "Kai " + " ".join(f"Yer{i}" for i in range(80)))
    for i in range(80):
        vg.bag_ekle(K, k("Kai"), "bulundugu_yer", k(f"Yer{i}"), 10 + i, "x", "manual", 1.0)
    b = bd.baglam_kur(K, 200, bd.kaynak_metin(K, 200), butce=300)
    assert b["baglam_tokeni"] <= 300 and b["kesilen_satir"] > 0
    assert any(s.startswith("VARLIK") for s in b["satirlar"])  # öncelik 1 önce girer


# ---------- sınıflandırma + işleme ----------
def _veri(**kw):
    return {**BOS, **kw}


def test_siniflandirma_ve_isleme(monkeypatch):
    k = _terimler("Kai", "Nephis", "Effie", "Order")
    _bolum(1, "Kai met Nephis.")
    bd._connect().execute("INSERT OR REPLACE INTO bilgi_bas VALUES (?, 0)", (K,)).connection.commit()
    _bolum(2, "Kai and Nephis were companions. Kai joined the Order. Effie was Kai's enemy.")
    vg.bag_ekle(K, k("Kai"), "dusmani", k("Effie"), 1, "eski", "manual", 1.0)  # elle bağ
    vg.bag_ekle(K, k("Kai"), "grubu", k("Order"), 50, "geç kanıt", "model", 0.9)  # sonradan kanıtlanmış aday
    veri = _veri(new_relationships=[
        {"ozne": "Kai", "iliski": "yoldasi", "nesne": "Nephis", "kanit": "Kai and Nephis were companions."},
        {"ozne": "Kai", "iliski": "grubu", "nesne": "Order", "kanit": "Kai joined the Order."},
        {"ozne": "Kai", "iliski": "yoldasi", "nesne": "Effie", "kanit": "Effie was Kai's enemy."},
        {"ozne": "Kai", "iliski": "dusmani", "nesne": "Nephis", "kanit": "Kai fought Nephis all day."},  # kanıt yok
    ], identity_revelations=[{"ad_1": "Kai", "ad_2": "Effie", "kanit": "Effie was Kai's enemy."}])
    sonuc = bd.bolum_isle(K, 1, "sahte", cagri=_cagri(BOS))
    assert sonuc["durum"] == "completed" and bd.bas_bolum(K) == 1
    sonuc = bd.bolum_isle(K, 2, "sahte", cagri=_cagri(veri))
    sinif = {(o["veri"].get("ozne"), o["veri"].get("iliski"), o["veri"].get("nesne")): o["sinif"]
             for o in sonuc["degerlendirme"]["oneriler"] if o["tur"] == "new_relationships"}
    assert sinif[("Kai", "yoldasi", "Nephis")] == "NEW"
    assert sinif[("Kai", "grubu", "Order")] == "UPDATES_EXISTING"     # daha erken kanıt
    assert sinif[("Kai", "yoldasi", "Effie")] == "CONFLICTS_WITH_EXISTING"  # elle 'dusmani' ile çelişir
    assert sinif[("Kai", "dusmani", "Nephis")] == "NEEDS_REVIEW"       # kanıt bu bölümde değil
    bag = {(b["kaynak"], b["iliski"], b["hedef"]): b for b in vg.baglar(K, durumlar=("aday", "onaylandi"))}
    yeni = bag.get(("Kai", "yoldasi", "Nephis")) or bag.get(("Nephis", "yoldasi", "Kai"))
    assert yeni["durum"] == "aday" and yeni["ilk_bolum"] == 2 and yeni["gecerli_baslangic"] is None
    assert bag[("Kai", "grubu", "Order")]["ilk_bolum"] == 2              # learned_at erkene çekildi
    assert bag[("Effie", "dusmani", "Kai")]["origin"] == "manual" if ("Effie", "dusmani", "Kai") in bag \
        else bag[("Kai", "dusmani", "Effie")]["origin"] == "manual"     # elle bağ korunur
    kategoriler = {i["kategori"] for i in bd.inceleme_listesi(K)}
    assert {"identity_merge", "relationship_conflict"} <= kategoriler
    assert sonuc["durum"] == "needs_review"                             # critical inceleme var
    # Kimlik açığa çıkması BİRLEŞTİRMEZ.
    assert not [b for b in vg.baglar(K) if b["iliski"] in ("takma_adi", "gercek_adi")]


def test_yeniden_isleme_kopya_uretmez_elle_karari_korur():
    k = _terimler("Kai", "Nephis")
    bd._connect().execute("INSERT OR REPLACE INTO bilgi_bas VALUES (?, 0)", (K,)).connection.commit()
    _bolum(1, "Kai and Nephis were companions.")
    veri = _veri(new_relationships=[
        {"ozne": "Kai", "iliski": "yoldasi", "nesne": "Nephis", "kanit": "Kai and Nephis were companions."}])
    bd.bolum_isle(K, 1, "sahte", cagri=_cagri(veri))
    a, b = sorted((k("Kai"), k("Nephis")))
    vg.bag_durumu(K, a, "yoldasi", b, "reddedildi")                       # elle karar: ret
    bd.bolum_isle(K, 1, "sahte", yeniden=True, cagri=_cagri(veri))
    bd.bolum_isle(K, 1, "sahte-v2", yeniden=True, cagri=_cagri(veri))
    satirlar = [x for x in vg.baglar(K, durumlar=("aday", "onaylandi", "reddedildi")) if x["iliski"] == "yoldasi"]
    assert len(satirlar) == 1 and satirlar[0]["durum"] == "reddedildi"  # diriltilmedi, kopya yok
    conn = bd._connect()
    cikarimlar = {r[0] for r in conn.execute("SELECT cikarim FROM bilgi_oneri WHERE book_slug = ?", (K,))}
    conn.close()
    assert len(cikarimlar) == 2  # v1 ve v2 önerileri ayırt edilir


def test_kronoloji_atlanamaz_ve_kuru_calistirma_yazmaz():
    _terimler("Kai")
    _bolum(5, "Kai slept.")
    with pytest.raises(bd.KronolojiHatasi):
        bd.bolum_isle(K, 5, "sahte", cagri=_cagri(BOS))   # baş 0, 5 işlenemez
    kuru = bd.bolum_isle(K, 5, "sahte", kuru=True)
    assert kuru["durum"] == "kuru" and kuru["olcum"]["kaynak_tokeni"] > 0
    assert bd.isleme_durumu(K, 5) is None and bd.bas_bolum(K) == 0


def test_bozuk_yanit_bolumu_failed_yapar_bas_ilerlemez():
    _terimler("Kai")
    _bolum(1, "Kai slept.")
    sonuc = bd.bolum_isle(K, 1, "sahte", cagri=lambda u, s: ("bu JSON değil", {}))
    assert sonuc["durum"] == "failed" and bd.bas_bolum(K) == 0
    d = bd.isleme_durumu(K, 1)
    assert d["durum"] == "failed" and d["deneme"] == 1 and d["cikarici_surumu"] == bd.CIKARICI_SURUMU


def test_durum_degisimi_iddia_gecmisi_ile_islenir():
    k = _terimler("Kai")
    bd._connect().execute("INSERT OR REPLACE INTO bilgi_bas VALUES (?, 0)", (K,)).connection.commit()
    _bolum(1, "Everyone believed Kai was dead.")
    _bolum(2, "Kai walked in, alive.")
    bd.bolum_isle(K, 1, "sahte", cagri=_cagri(_veri(state_changes=[
        {"varlik": "Kai", "anahtar": "Yaşam", "deger": "ölü", "kanit": "Everyone believed Kai was dead.",
         "durum_bilgisi": "believed"}])))
    bd.bolum_isle(K, 2, "sahte", cagri=_cagri(_veri(state_changes=[
        {"varlik": "Kai", "anahtar": "Yaşam", "deger": "sağ", "kanit": "Kai walked in, alive.",
         "durum_bilgisi": "confirmed"}])))
    assert vg.degerler(K, 1)[k("Kai")]["Yaşam"]["deger"] == "ölü"
    assert [x["durum_bilgisi"] for x in vg.deger_gecmisi(K, k("Kai"), "Yaşam", 2)] == ["disproven", "confirmed"]


def test_canli_kuyruk_okumayi_engellemez(monkeypatch):
    bd.canli_kuyruga_ekle(K, 947)
    assert bd.isleme_durumu(K, 947)["durum"] == "pending"
    monkeypatch.setattr(bd, "_connect", lambda: (_ for _ in ()).throw(__import__("sqlite3").Error("kilit")))
    bd.canli_kuyruga_ekle(K, 948)  # hata yutulur, istisna yükselmez


def test_dogrulama_kipi_hicbir_sey_yazmaz():
    k = _terimler("Kai", "Nephis")
    _bolum(300, "Kai and Nephis were companions.")
    veri = _veri(new_relationships=[
        {"ozne": "Kai", "iliski": "yoldasi", "nesne": "Nephis", "kanit": "Kai and Nephis were companions."}],
        identity_revelations=[{"ad_1": "Kai", "ad_2": "Nephis", "kanit": "Kai and Nephis were companions."}])
    sonuc = bd.bolum_degerlendir(K, 300, "sahte", cagri=_cagri(veri))
    assert sonuc["degerlendirme"]["oneriler"][0]["sinif"] == "NEW"
    assert vg.baglar(K, durumlar=("aday", "onaylandi", "reddedildi")) == []
    assert bd.inceleme_listesi(K) == [] and bd.isleme_durumu(K, 300) is None and bd.bas_bolum(K) == 0
