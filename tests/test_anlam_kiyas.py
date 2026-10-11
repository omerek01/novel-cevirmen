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


@pytest.mark.parametrize("sarmal", [
    lambda liste: liste,                    # çıplak liste
    lambda liste: {"decisions": liste},     # başka adlı tek anahtar
    lambda liste: [{"kararlar": liste}],    # tek elemanlı listeye sarılı (gerçek red, 600. bölüm)
])
def test_hakem_listesi_baska_sarmalda_gelse_de_cozulur(sarmal):
    maddeler = [{"p": 0, "x_kol": "a"}, {"p": 1, "x_kol": "b"}]
    liste = [{"id": 0, "anlam": "X", "akicilik": "esit", "tutarlilik": "esit"},
             {"id": 1, "anlam": "Y", "akicilik": "esit", "tutarlilik": "esit"}]
    kararlar = ak.kararlari_coz(sarmal(liste), maddeler)
    assert [k["anlam"] for k in kararlar] == ["a", "a"]


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


def test_uzak_cikti_akisi_parcali_gelse_de_satir_satir_ayrisir():
    satirlar, kalan, kod = ak.akisi_ayir(b'{"a": 1}\n{"b"')
    assert satirlar == [{"a": 1}] and kalan == b'{"b"' and kod is None
    satirlar, kalan, kod = ak.akisi_ayir(kalan + b': 2}\n### BITTI 0 ###\n')
    assert satirlar == [{"b": 2}] and kalan == b"" and kod == 0


def test_uzak_is_hata_koduyla_biterse_kod_doner():
    satirlar, kalan, kod = ak.akisi_ayir(b"### BITTI 137 ###\n")
    assert satirlar == [] and kod == 137


# ---------- bölüm düzeyi akış hakemi ----------

def test_bolum_isi_iki_yonlu_ve_hizasizda_yok():
    a = kol("Bir.\n\nİki.\n\nÜç."); b = kol("Bir!\n\nİki!\n\nÜç!")
    isler = ak.bolum_isleri(a, b)
    assert [i["x_kol"] for i in isler] == ["a", "b"]
    assert isler[0]["istem"]["X"][0]["metin"] == "Bir." and isler[1]["istem"]["X"][0]["metin"] == "Bir!"
    assert isler[0]["istem"]["kaynak"][2] == {"p": 2, "metin": "C three."}
    assert ak.bolum_isleri(a, kol("Tek blok.")) == []


def test_bolum_karari_kola_cevrilir_ve_dogrulanir():
    y = {"akis": "X", "anlam": "esit", "kopukluklar": {"X": [], "Y": [{"p": 1, "not": "geçiş kopuk"}]}}
    k = ak.bolum_karari_coz(y, "b", 3)
    assert k == {"akis": "b", "anlam": "esit", "kopukluk": {"b": [], "a": [{"p": 1, "not": "geçiş kopuk"}]}}
    with pytest.raises(ValueError):
        ak.bolum_karari_coz({"akis": "Z", "anlam": "X", "kopukluklar": {"X": [], "Y": []}}, "a", 3)
    with pytest.raises(ValueError):
        ak.bolum_karari_coz({"akis": "X", "anlam": "X", "kopukluklar": {"X": [{"p": 9}], "Y": []}}, "a", 3)


def test_iki_yon_uyusmazsa_esit_sayilir():
    k1 = {"akis": "a", "anlam": "a", "kopukluk": {"a": [], "b": [{"p": 0}]}}
    k2 = {"akis": "b", "anlam": "a", "kopukluk": {"a": [{"p": 2}], "b": [{"p": 0}, {"p": 1}]}}
    birlesik = ak.yonleri_birlestir([k1, k2])
    assert birlesik["akis"] == "esit" and birlesik["anlam"] == "a"
    assert birlesik["kopukluk_sayisi"] == {"a": 0.5, "b": 1.5}


def test_uzak_kodlarda_yer_tutucu_kalmaz():
    for kod in (ak._HAZIRLA, ak._CALISTIR, ak._YARGILA):
        sabit = ak._sabitle(kod)
        assert "UZAK_APP" not in sabit and "CANLI_DB" not in sabit


def test_bolum_karari_tek_elemanli_listeye_sarili_gelse_de_cozulur():
    yanit = [{"akis": "X", "anlam": "esit", "kopukluklar": {"X": [], "Y": [{"p": 1, "not": "n"}]}}]
    karar = ak.bolum_karari_coz(yanit, "b", 3)
    assert karar["akis"] == "b" and karar["kopukluk"]["a"] == [{"p": 1, "not": "n"}]


# ---------- kollar ----------

def test_her_kol_butun_bayraklari_acikca_verir_I_yalniz_ozet_zinciriyle_ayrisir():
    # Kollar aynı süreçte sırayla koşar: bir kolun açtığı bayrak sonrakine sızmasın.
    anahtarlar = {frozenset(b) for b in ak.KOLLAR.values()}
    assert len(anahtarlar) == 1 and "CEVIRI_OZET" in next(iter(anahtarlar))
    fark = {k for k in ak.KOLLAR["I"] if ak.KOLLAR["I"][k] != ak.KOLLAR["H"][k]}
    assert fark == {"CEVIRI_OZET"} and ak.KOLLAR["I"]["CEVIRI_OZET"] == "1"


def test_ozet_zinciri_uzak_kosuya_enjekte_edilir_ve_onceki_bolum_kolun_kendi_kaydidir():
    assert ak.ENJEKTE.index("ozet_zinciri") < ak.ENJEKTE.index("translate")
    # Her kolun özetleri url#kol altında saklanır; önceki bölüm aynı anahtarla aranmazsa
    # zincir deneyde hiç kurulmaz (eski analiz ölçümünde olduğu gibi).
    assert "onceki['url'] + '#' + kol" in ak._CALISTIR


def test_zincir_kolu_kaldigi_yerden_surerken_onceki_halka_ciktidan_tohumlanir():
    # Her koşu yeni geçici DB açar; yeniden koşan bölüm, önceki bölümün özetini ancak
    # önceki çıktıdan alırsa zincir kopmaz (canlıda bu, kayıtlı özettir).
    satirlar = [
        {"kol": "I", "bolum": 968, "translation": "x", "iz": {"ozet_zinciri": {"ozet": "968 özeti"}}},
        {"kol": "I", "bolum": 969, "translation": "y", "iz": {"ozet_zinciri": {"ozet": None}}},
        {"kol": "H", "bolum": 599, "translation": "z", "iz": {}},
        {"kol": "I", "bolum": 600, "hata_turu": "TranslateError"},
    ]
    isler = {"I": [969, 601], "H": [600]}
    assert ak.zincir_tohumlari(satirlar, isler) == {"I": {"969": "968 özeti"}}
    # Önceki bölüm de yeniden koşuyorsa eski halka tohumlanmaz (yenisinin üstüne yazılırdı).
    assert ak.zincir_tohumlari(satirlar, {"I": [968, 969]}) == {}
    assert "ozet_zinciri.yaz(onceki['url']" in ak._CALISTIR
