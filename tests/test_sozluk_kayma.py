"""Sözlük dışı kayma madenciliği (Faz A8). Cümleler uydurmadır."""
from core.sozluk_kayma import kaymalar, paragraf_atfi

SOZ = {"Iron Gate": "Demir Kapı"}


def test_tek_aday_tek_karsilik_atfedilir():
    assert paragraf_atfi("They saluted the Warden quietly.", "Sessizce Muhafız'ı selamladılar.", SOZ) \
        == ("Warden", "Muhafız")


def test_aynen_korunan_aday():
    assert paragraf_atfi("They saluted the Warden quietly.", "Sessizce Warden'ı selamladılar.", SOZ) \
        == ("Warden", "=")


def test_iki_aday_varsa_atif_yapilmaz():
    assert paragraf_atfi("The Warden met the Envoy.", "Muhafız Elçi ile buluştu.", SOZ) is None


def test_sozluk_kaydi_aday_sayilmaz_ve_karsiligi_aciklanir():
    # "Iron Gate" sözlükte: aday yalnız Warden, Türkçede "Demir Kapı" açıklanmış sayılır.
    assert paragraf_atfi("At the Iron Gate, the Warden waited.",
                         "Demir Kapı'da Muhafız bekliyordu.", SOZ) == ("Warden", "Muhafız")


def test_iki_karsiliga_bolunen_terim_kayma_sayilir():
    paragraflar = []
    for no in range(1, 9):
        tr = "Sessizce Muhafız'ı selamladılar." if no <= 5 else "Sessizce Gardiyan'ı selamladılar."
        paragraflar.append((no, "They saluted the Warden quietly.", tr))
    sonuc = kaymalar(paragraflar, lambda no: SOZ)
    assert sonuc and sonuc[0]["kaynak"] == "Warden"
    assert [k["karsilik"] for k in sonuc[0]["karsiliklar"]] == ["Muhafız", "Gardiyan"]


def test_tutarli_terim_kayma_sayilmaz():
    paragraflar = [(no, "They saluted the Warden quietly.", "Sessizce Muhafız'ı selamladılar.")
                   for no in range(1, 9)]
    assert kaymalar(paragraflar, lambda no: SOZ) == []


def test_cekim_farki_kayma_sayilmaz():
    # "Muhafız" / "Muhafızlar" / "Muhafızları" aynı köktür: kayma değil.
    trler = ["Sessizce Muhafız'ı selamladılar.", "Sessizce Muhafızlar'ı selamladılar.",
             "Sessizce Muhafızları selamladılar."]
    paragraflar = [(no, "They saluted the Warden quietly.", trler[no % 3]) for no in range(1, 10)]
    assert kaymalar(paragraflar, lambda no: SOZ) == []


def test_betik_onerileri_ingilizce_ve_kayitliyi_atlar():
    import sozluk_kayma as betik  # scripts/ (conftest yolu ekler)
    kaymalar_ = [
        {"kaynak": "Warden", "karsiliklar": [{"karsilik": "Muhafız", "sayi": 5}]},
        {"kaynak": "Knight", "karsiliklar": [{"karsilik": "(İngilizce)", "sayi": 5}]},
        {"kaynak": "Iron Gate", "karsiliklar": [{"karsilik": "Demir Geçit", "sayi": 5}]},
    ]
    assert betik.oneriler(kaymalar_, SOZ) == {"Warden": "Muhafız"}
