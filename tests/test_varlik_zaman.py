"""Varlık grafiği: zaman ve bilgi durumu (Faz 1B–1G, 2026-10-07) — çevrimdışı.

İki saat ayrıdır: `ilk_bolum` = learned_at (SPOILER ölçütü), `gecerli_*` = hikâye
kronolojisi. Bilgi durumu (`durum_bilgisi`) iş akışı durumundan (`durum`) ayrıdır."""
from __future__ import annotations

from core import glossary, varlik_grafigi as vg

KITAP = "zaman-kitap"


def _k(*adlar):
    for ad in adlar:
        glossary.set_term(KITAP, ad, ad)
    return vg.DugumCozucu(KITAP).coz


def _bag(baglar, a, iliski, b):
    # SİMETRİK ilişki (yoldaş, düşman) kimliğe göre sıralanıp saklanır ve kimlikler
    # rastgeledir: iki yön de aranmalı, yoksa test rastgele düşer (ölçüldü: 5 koşuda 4).
    uclar = {(a, b), (b, a)} if vg.ILISKILER[iliski].get("simetrik") else {(a, b)}
    return next((x for x in baglar if x["iliski"] == iliski and (x["kaynak"], x["hedef"]) in uclar), None)


def test_geriye_donuk_aciklama_ogrenilmeden_gizli():
    # 800. bölüm: "X, 300'de Tarikat'a katılmıştı."
    k = _k("X", "Order")
    vg.bag_ekle(KITAP, k("X"), "grubu", k("Order"), 800, "x", "manual", 1.0, gecerli_baslangic=300)
    assert _bag(vg.baglar(KITAP, en_cok_bolum=500), "X", "grubu", "Order") is None
    gorunur = _bag(vg.baglar(KITAP, en_cok_bolum=850), "X", "grubu", "Order")
    assert gorunur["ilk_bolum"] == 800 and gorunur["gecerli_baslangic"] == 300


def test_gecerli_baslangic_varsayilmaz():
    # Bilinmeyen hikâye zamanı NULL kalır; ilk_bolum'a EŞİTLENMEZ.
    k = _k("A", "B")
    vg.bag_ekle(KITAP, k("A"), "ogretmeni", k("B"), 120, "x", "manual", 1.0)
    b = _bag(vg.baglar(KITAP), "A", "ogretmeni", "B")
    assert b["gecerli_baslangic"] is None and b["gecerli_bitis"] is None and b["aktif"] is True


def test_yanlis_inanc_gecmisi_korunur():
    k = _k("X")
    # 200: herkes X'in öldüğüne inanıyor. 250: X sağ çıkıyor.
    vg.deger_yaz(KITAP, k("X"), "Yaşam", "ölü", 200, "x", origin="model", durum_bilgisi="believed")
    vg.deger_yaz(KITAP, k("X"), "Yaşam", "sağ", 250, "y", origin="model", durum_bilgisi="confirmed")
    # 220'deki okur: ölü sanılıyor (çürütme henüz öğrenilmedi).
    assert vg.degerler(KITAP, 220)[k("X")]["Yaşam"] == {"deger": "ölü", "ilk_bolum": 200, "durum_bilgisi": "believed"}
    assert vg.deger_gecmisi(KITAP, k("X"), "Yaşam", 220) == [
        {"deger": "ölü", "ilk_bolum": 200, "durum_bilgisi": "believed"}]
    # Şimdi: sağ (doğrulandı); eski iddia SİLİNMEDİ, çürütüldü olarak görünür.
    assert vg.degerler(KITAP, 300)[k("X")]["Yaşam"]["deger"] == "sağ"
    assert vg.deger_gecmisi(KITAP, k("X"), "Yaşam", 300) == [
        {"deger": "ölü", "ilk_bolum": 200, "durum_bilgisi": "disproven"},
        {"deger": "sağ", "ilk_bolum": 250, "durum_bilgisi": "confirmed"},
    ]


def test_bag_iddiasi_curutulur_silinmez():
    k = _k("X", "Y")
    vg.bag_ekle(KITAP, k("X"), "oldurdu", k("Y"), 200, "x", "model", 0.9, durum="onaylandi", durum_bilgisi="rumor")
    vg.iddiayi_curut(KITAP, k("X"), "oldurdu", k("Y"), 250)
    assert _bag(vg.baglar(KITAP, en_cok_bolum=220), "X", "oldurdu", "Y")["durum_bilgisi"] == "rumor"
    assert _bag(vg.baglar(KITAP, en_cok_bolum=300), "X", "oldurdu", "Y")["durum_bilgisi"] == "disproven"


def test_iliski_evrimi_gecmis_bozulmaz():
    k = _k("A", "B")
    vg.bag_ekle(KITAP, k("A"), "yoldasi", k("B"), 100, "x", "manual", 1.0, gecerli_baslangic=100)
    vg.bag_ekle(KITAP, k("A"), "dusmani", k("B"), 301, "y", "manual", 1.0, gecerli_baslangic=301)
    once = vg.baglar(KITAP, en_cok_bolum=250)
    assert _bag(once, "A", "yoldasi", "B")["aktif"] is True          # bitiş henüz öğrenilmedi
    assert _bag(once, "A", "yoldasi", "B")["gecerli_bitis"] is None  # spoiler değil
    assert _bag(once, "A", "dusmani", "B") is None
    sonra = vg.baglar(KITAP, en_cok_bolum=350)
    yol = _bag(sonra, "A", "yoldasi", "B")
    assert (yol["aktif"], yol["gecerli_bitis"], yol["bitis_ogrenildigi"]) == (False, 300, 301)
    assert _bag(sonra, "A", "dusmani", "B")["aktif"] is True


def test_kapanma_yalniz_bildirilen_ve_onayli_bagla():
    k = _k("A", "B", "C")
    vg.bag_ekle(KITAP, k("A"), "yoldasi", k("B"), 100, "x", "manual", 1.0)
    vg.bag_ekle(KITAP, k("A"), "ogretmeni", k("B"), 200, "y", "manual", 1.0)  # birlikte var olabilir
    vg.bag_ekle(KITAP, k("A"), "dusmani", k("B"), 300, "z", "model", 0.9)       # aday: kapatmaz
    assert _bag(vg.baglar(KITAP), "A", "yoldasi", "B")["aktif"] is True
    # Aday onaylanınca kapatır.
    a, b = sorted((k("A"), k("B")))
    vg.bag_durumu(KITAP, a, "dusmani", b, "onaylandi")
    assert _bag(vg.baglar(KITAP), "A", "yoldasi", "B")["aktif"] is False
    # Tekil ilişki: yeni rütbe eskisini kapatır, başka öznenin rütbesine dokunmaz.
    vg.bag_ekle(KITAP, k("A"), "rutbesi", k("B"), 10, "r1", "sistem", 1.0)
    vg.bag_ekle(KITAP, k("C"), "rutbesi", k("B"), 10, "r3", "sistem", 1.0)
    vg.bag_ekle(KITAP, k("A"), "rutbesi", k("C"), 50, "r2", "sistem", 1.0)
    assert _bag(vg.baglar(KITAP), "A", "rutbesi", "B")["aktif"] is False
    assert _bag(vg.baglar(KITAP), "C", "rutbesi", "B")["aktif"] is True


def test_takma_ad_birlestirme_gecmis_bagi_korur():
    k = _k("Sunny", "Sunless", "Kai", "Dark City")
    vg.bag_ekle(KITAP, k("Sunny"), "takma_adi", k("Sunless"), 1, None, "manual", 1.0)
    vg.bag_ekle(KITAP, k("Sunless"), "bulundugu_yer", k("Dark City"), 120, "kanıt", "model", 0.9, durum="onaylandi")
    vg.takma_adlari_birlestir(KITAP)
    b = _bag(vg.baglar(KITAP), "Sunny", "bulundugu_yer", "Dark City")
    assert b is not None and (b["ilk_bolum"], b["kanit"]) == (120, "kanıt")
    # Takma ad düğümü ve kimlik bağı yerinde kalır (tarih kaybolmaz).
    assert _bag(vg.baglar(KITAP), "Sunny", "takma_adi", "Sunless") is not None


def test_benzer_adlar_kendiliginden_birlesmez():
    k = _k("Fire Keeper", "Fire Keepers", "House Night", "House of Night", "Chained Island", "Chained Isles")
    for a, b in (("Fire Keeper", "Fire Keepers"), ("House Night", "House of Night"),
                 ("Chained Island", "Chained Isles")):
        assert k(a) != k(b)
    vg.unvanli_adlari_bagla(KITAP)
    vg.takma_adlari_birlestir(KITAP)
    assert not [b for b in vg.baglar(KITAP) if b["iliski"] in ("takma_adi", "gercek_adi")]


def test_goc_eslemesi_model_bagini_dogrulanmis_saymaz():
    k = _k("A", "B")
    vg.bag_ekle(KITAP, k("A"), "yoldasi", k("B"), 5, "x", "model", 0.9, durum="onaylandi")
    vg.bag_ekle(KITAP, k("A"), "ogretmeni", k("B"), 6, "y", "sistem", 1.0)
    bag = {x["iliski"]: x for x in vg.baglar(KITAP)}
    assert bag["yoldasi"]["durum_bilgisi"] is None          # değerlendirilmemiş
    assert bag["ogretmeni"]["durum_bilgisi"] == "confirmed"


def test_bilinmeyen_durum_bilgisi_reddedilir():
    import pytest
    k = _k("A", "B")
    with pytest.raises(ValueError):
        vg.bag_ekle(KITAP, k("A"), "yoldasi", k("B"), 5, "x", "manual", 1.0, durum_bilgisi="dogru")
