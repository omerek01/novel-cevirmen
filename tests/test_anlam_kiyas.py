"""Anlam/bağlam kıyas aracının saf mantığı: madde seçimi, hakem doğrulama, istatistik.

Model çağrısı yoktur. Metinler uydurmadır.
"""
import pytest

import anlam_kiyas as ak


def kol(ceviri, kaynak="A one.\n\nB two.\n\nC three."):
    return {"translation": ceviri, "source": kaynak}


def test_yalniz_belirgin_farkli_paragraflar_hakeme_gider():
    a = kol("Bir.\n\nİki tane.\n\nÜç.")
    b = kol("Bir.\n\nİki tane!\n\nTamamen başka bir cümle.")
    maddeler = ak.maddeler(a, b, tohum=1)
    assert [m["p"] for m in maddeler] == [2]
    assert maddeler[0]["kaynak"] == "C three."
    assert maddeler[0]["onceki_kaynak"] == "B two."


def test_hizasi_tutmayan_bolum_atlanir():
    assert ak.maddeler(kol("Bir.\n\nİki.\n\nÜç."), kol("Tek blok."), tohum=1) == []
    assert ak.maddeler(kol("Bir.\n\nİki.\n\nÜç."), {"translation": "Bir.", "source": None}, tohum=1) == []


def test_xy_sirasi_tohumla_tekrarlanabilir_ve_iki_yonu_de_kullanir():
    kaynak = "\n\n".join(f"P{i}." for i in range(40))
    a = kol("\n\n".join(f"Birinci çeviri {i}." for i in range(40)), kaynak)
    b = kol("\n\n".join(f"Tamamen farklı cümle {i * 7}!" for i in range(40)), kaynak)
    m1 = ak.maddeler(a, b, tohum=7)
    assert m1 == ak.maddeler(a, b, tohum=7)
    yonler = {m["x_kol"] for m in m1}
    assert yonler == {"a", "b"}
    for m in m1:
        assert (m["X"], m["Y"]) == ((m["a"], m["b"]) if m["x_kol"] == "a" else (m["b"], m["a"]))


def test_hakem_karari_kola_cevrilir():
    maddeler = [{"p": 0, "x_kol": "a"}, {"p": 1, "x_kol": "b"}]
    yanit = {"kararlar": [
        {"id": 0, "anlam": "X", "akicilik": "esit", "tutarlilik": "Y", "not": "n1"},
        {"id": 1, "anlam": "X", "akicilik": "Y", "tutarlilik": "esit", "not": "n2"}]}
    kararlar = ak.kararlari_coz(yanit, maddeler)
    assert kararlar[0] == {"p": 0, "anlam": "a", "akicilik": "esit", "tutarlilik": "b", "not": "n1"}
    assert kararlar[1] == {"p": 1, "anlam": "b", "akicilik": "a", "tutarlilik": "esit", "not": "n2"}


@pytest.mark.parametrize("bozuk", [
    {"kararlar": [{"id": 0, "anlam": "X", "akicilik": "esit", "tutarlilik": "esit"}]},  # eksik madde
    {"kararlar": [{"id": 0, "anlam": "Z", "akicilik": "esit", "tutarlilik": "esit"},
                  {"id": 1, "anlam": "X", "akicilik": "esit", "tutarlilik": "esit"}]},
    {"yok": []},
])
def test_eksik_ya_da_gecersiz_hakem_yaniti_reddedilir(bozuk):
    with pytest.raises(ValueError):
        ak.kararlari_coz(bozuk, [{"p": 0, "x_kol": "a"}, {"p": 1, "x_kol": "b"}])


def test_isaret_testi_ve_ozet():
    assert ak.isaret_testi(0, 0) == 1.0
    assert ak.isaret_testi(5, 5) == pytest.approx(1.0)
    assert ak.isaret_testi(10, 0) == pytest.approx(2 * 0.5 ** 10)
    kararlar = [{"anlam": "a"}, {"anlam": "a"}, {"anlam": "b"}, {"anlam": "esit"}]
    o = ak.boyut_ozeti(kararlar, "anlam")
    assert (o["a"], o["b"], o["esit"]) == (2, 1, 1)
    assert 0 < o["p"] <= 1


def test_devam_yalniz_eksik_ve_hatali_isleri_doner():
    satirlar = [
        {"kol": "A", "bolum": 1, "translation": "x"},
        {"kol": "A", "bolum": 2, "hata_turu": "TranslateError"},
        {"kol": "B", "bolum": 1, "translation": "y"},
    ]
    assert ak.eksik_isler(satirlar, ["A", "B"], [1, 2]) == {"A": [2], "B": [2]}
    assert ak.eksik_isler(satirlar + [{"kol": "A", "bolum": 2, "translation": "z"}], ["A"], [1, 2]) == {}
