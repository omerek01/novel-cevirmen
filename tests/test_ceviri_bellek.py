"""Bölümler arası tutarlılık belleği: önceki bölümlerden ilgili kaynak→çeviri çiftleri.

Ölçülen boşluk (2026-10-11, shadow-slave 850-967): `Captain` 64 yerde "Yüzbaşı",
5 yerde "Kaptan" çevrildi; sıradan sözcük olduğu için sözlükte yok, model her
bölümde yeniden karar veriyordu. Bellek ek model çağrısı yapmaz; yalnız önceki
bölümlerden seçilmiş örnekleri bağlam olarak verir. Metinler uydurmadır.
"""
from core import ceviri_bellek as b


def cift(bolum, en, tr):
    return {"bolum": bolum, "en": en, "tr": tr}


HAVUZ = [
    cift(40, '"Captain Velma, the gate is open," the guard said.', '"Yüzbaşı Velma, kapı açık," dedi muhafız.'),
    cift(41, "The rain fell over the quiet valley.", "Yağmur sessiz vadiye yağdı."),
    cift(42, '"Yes, sir," Orrin replied.', '"Evet, efendim," diye yanıtladı Orrin.'),
    cift(43, "A merchant sold apples at the market.", "Bir tüccar pazarda elma sattı."),
]


def test_ortak_ad_ve_hitap_tasiyan_ciftler_secilir():
    kaynak = ['Captain Velma looked at Orrin.', '"Sir, we must leave," Orrin said.']
    secilen = b.sec(HAVUZ, kaynak, en_fazla=2)
    assert [x["bolum"] for x in secilen] == [40, 42]


def test_ilgisiz_cift_secilmez():
    secilen = b.sec(HAVUZ, ["Captain Velma waited."], en_fazla=5)
    assert {x["bolum"] for x in secilen} == {40}


def test_ayni_anahtari_tekrar_eden_cift_yerine_yeni_anahtar_secilir():
    havuz = [
        cift(10, "Captain Velma ran.", "Yüzbaşı Velma koştu."),
        cift(11, "Captain Velma ran again.", "Yüzbaşı Velma yine koştu."),
        cift(12, '"Thank you, sir," Orrin said.', '"Teşekkürler efendim," dedi Orrin.'),
    ]
    secilen = b.sec(havuz, ["Captain Velma nodded.", '"Sir," Orrin said.'], en_fazla=2)
    assert 12 in {x["bolum"] for x in secilen}
    assert len({x["bolum"] for x in secilen} & {10, 11}) == 1


def test_uzun_bos_ve_isaretcili_cift_kullanilmaz():
    havuz = [
        cift(5, "Captain Velma " + "walked far " * 80, "Yüzbaşı Velma " + "çok yürüdü " * 80),
        cift(6, "Captain Velma smiled.", ""),
        cift(7, "[[3]] Captain Velma sat.", "[[3]] Yüzbaşı Velma oturdu."),
    ]
    secilen = b.sec(havuz, ["Captain Velma stood."], en_fazla=5)
    assert [x["bolum"] for x in secilen] == [7]
    assert "[[" not in secilen[0]["en"] and "[[" not in secilen[0]["tr"]


def test_sinir_asilmaz_ve_sira_kronolojik():
    havuz = [cift(i, f"Captain Velma{i} and Orrin{i} met.", f"Yüzbaşı Velma{i} ve Orrin{i} buluştu.")
             for i in range(20, 0, -1)]
    kaynak = [" ".join(f"Velma{i} Orrin{i}" for i in range(1, 21))]
    secilen = b.sec(havuz, kaynak, en_fazla=4)
    assert len(secilen) == 4
    assert [x["bolum"] for x in secilen] == sorted(x["bolum"] for x in secilen)


def test_kisa_vadeli_son_ciftler_yalniz_hizaliysa():
    en = "A one.\n\nB two.\n\nC three.\n\nD four."
    tr = "A bir.\n\nB iki.\n\nC üç.\n\nD dört."
    assert b.son_ciftler(en, tr, 2) == [{"en": "C three.", "tr": "C üç."}, {"en": "D four.", "tr": "D dört."}]
    assert b.son_ciftler(en, "Tek blok çeviri.", 2) == []
    assert b.son_ciftler("", "", 2) == []


def test_metin_bos_bellekte_bos_doner_dolu_bellekte_kural_ve_ornek_tasir():
    assert b.metin([], []) == ""
    m = b.metin([HAVUZ[0]], [{"en": "D four.", "tr": "D dört."}])
    assert "TUTARLILIK" in m
    assert "Yüzbaşı Velma" in m and "D dört." in m
    assert "[[" not in m


def test_havuz_satirlarindan_hizali_ciftler_kurulur():
    satirlar = [(8, "A.\n\nB.", "Bir.\n\nİki."), (9, "C.\n\nD.", "Tek blok."), (10, "E.", "Beş.")]
    havuz = b.havuz_kur(satirlar)
    assert {(x["bolum"], x["en"]) for x in havuz} == {(8, "A."), (8, "B."), (10, "E.")}


# ---------- çeviri akışına bağlantı ----------

import json
from types import SimpleNamespace

from core import ceviri_baglam, translate

KAYNAK = 'Captain Velma looked at Orrin.\n\n"Sir, we must leave," Orrin said.'


def _yanit(v):
    return SimpleNamespace(text=json.dumps(v, ensure_ascii=False),
                           candidates=[SimpleNamespace(finish_reason="STOP")])


def _kur(monkeypatch, bellek):
    monkeypatch.setenv("CEVIRI_BELLEK", bellek)
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    istemler = []
    def uret(factory, models, user, **kw):
        istemler.append((kw.get("system"), user))
        return _yanit({"translation": "[[1]] Yüzbaşı Velma, Orrin'e baktı.\n\n[[2]] \"Efendim, gitmeliyiz,\" dedi Orrin.",
                       "detected_names": [], "detected_terms": {}}), "model"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    return istemler


def _cevir(**ek):
    return translate.translate_chapter(KAYNAK, "test", models=("model",), book_slug="kitap",
                                       bolum_url="test://k/50", bolum_no=50, **ek)


def test_bellek_kapaliyken_istem_bayt_bayt_ayni(monkeypatch):
    istemler = _kur(monkeypatch, "0")
    _cevir(bellek_havuzu=HAVUZ)
    istemler_eski = list(istemler); istemler.clear()
    _cevir()
    assert istemler == istemler_eski
    assert "TUTARLILIK" not in istemler[0][1]


def test_bellek_acikken_ilgili_ornek_ve_onceki_bolum_sonu_isteme_girer(monkeypatch):
    istemler = _kur(monkeypatch, "1")
    onceki = {"url": "test://k/49", "book_slug": "kitap", "chapter_no": 49,
              "source": "One.\n\nTwo.", "translation": "Bir.\n\nİki."}
    _cevir(bellek_havuzu=HAVUZ, onceki_bolum=onceki)
    system, user = istemler[0]
    assert system is None  # analiz kapalı: eski sistem talimatı ve çıktı şeması korunur
    assert "TUTARLILIK BELLEĞİ" in user and "Yüzbaşı Velma, kapı açık" in user
    assert "Yağmur sessiz vadiye" not in user  # ilgisiz çift girmez
    assert "TR: İki." in user
    assert user.index("TUTARLILIK BELLEĞİ") < user.index("ÇEVRİLECEK METİN")


def test_gelecek_bolum_bellege_giremez(monkeypatch):
    istemler = _kur(monkeypatch, "1")
    gelecek = [cift(60, "Captain Velma later became queen.", "Yüzbaşı Velma sonra kraliçe oldu.")]
    _cevir(bellek_havuzu=gelecek)
    assert "kraliçe" not in istemler[0][1]
    assert "TUTARLILIK" not in istemler[0][1]


def test_onceki_bolum_baska_kitapsa_son_paragraflar_girmez(monkeypatch):
    istemler = _kur(monkeypatch, "1")
    onceki = {"url": "x", "book_slug": "baska", "chapter_no": 49,
              "source": "One.", "translation": "Yabancı kitap."}
    _cevir(onceki_bolum=onceki)
    assert "Yabancı kitap." not in istemler[0][1]


def test_stil_kapaliyken_baglam_metni_ustup_talimatini_tasimaz(monkeypatch):
    analiz = {"ozet": [{"metin": "Özet.", "paragraf": 0, "alinti": "x"}]}
    monkeypatch.setenv("CEVIRI_STIL", "1")
    assert ceviri_baglam.STIL_TALIMATI in ceviri_baglam.baglam_metni(analiz, None)
    monkeypatch.setenv("CEVIRI_STIL", "0")
    m = ceviri_baglam.baglam_metni(analiz, None)
    assert ceviri_baglam.STIL_TALIMATI not in m and "Özet." in m


# ---------- önbellek ve boru hattı ----------

from core import cache, pipeline


def _bolum(no, en, tr, kitap="kitap", tur=None):
    cache.save_chapter(f"test://{kitap}/{no}", {
        "book_slug": kitap, "book_title": "K", "title": f"B{no}", "chapter_no": no,
        "translation": tr, "source": en, "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1, **({"content_type": tur} if tur else {})})


def test_havuz_yalniz_onceki_ve_hizali_bolumlerden_kurulur():
    _bolum(48, "Captain Velma ran.\n\nOrrin followed.", "Yüzbaşı Velma koştu.\n\nOrrin izledi.")
    _bolum(49, "Two paragraphs.\n\nHere.", "Tek paragraf.")           # hizasız
    _bolum(50, "Captain Velma now.", "Yüzbaşı Velma şimdi.")           # mevcut bölüm
    _bolum(51, "Captain Velma later.", "Yüzbaşı Velma sonra.")         # gelecek
    _bolum(47, "Captain Velma elsewhere.", "Başka kitap.", kitap="baska")
    havuz = cache.bellek_havuzu("kitap", 50)
    assert {x["bolum"] for x in havuz} == {48}
    assert len(havuz) == 2


def test_onceki_kaynak_hizali_kaynagi_da_tasir():
    _bolum(49, "One.\n\nTwo.", "Bir.\n\nİki.")
    onceki = cache.onceki_kaynak("kitap", "test://kitap/49", 50)
    assert onceki["hizali_kaynak"] == "One.\n\nTwo."


def test_boru_hatti_bellegi_yalniz_bayrakla_gonderir(monkeypatch):
    _bolum(49, "Captain Velma ran.", "Yüzbaşı Velma koştu.")
    monkeypatch.setenv("CEVIRI_BELLEK", "0")
    assert pipeline._roman_baglami("kitap", "test://kitap/50", "test://kitap/49", 50) == {}
    monkeypatch.setenv("CEVIRI_BELLEK", "1")
    ek = pipeline._roman_baglami("kitap", "test://kitap/50", "test://kitap/49", 50)
    assert ek["bellek_havuzu"][0]["tr"] == "Yüzbaşı Velma koştu."
    assert ek["onceki_bolum"]["chapter_no"] == 49
