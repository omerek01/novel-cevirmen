"""Ö5: bir önceki paragrafın tekrarı gibi duran Türkçe paragraf künyede şüphe olur."""
from core import ceviri_kalite as ck

UZUN = "Kuzey kapısının önünde sabaha kadar bekledi, rüzgâr hiç dinmedi ve fener söndü."


def test_kaynakta_tekrar_yokken_ardisik_ayni_paragraf_supheli():
    tr = ["Giriş.", UZUN, UZUN + " "]
    en = ["Intro.", "He waited at the north gate.", "Then he left for the river."]
    b = ck.paragraf_tekrarlari(tr, en)
    assert [x["paragraf"] for x in b] == [2] and b[0]["tur"] == "tekrar"


def test_kaynakta_da_tekrar_varsa_sayilmaz():
    satir = "[You have received a Memory: Ring of the Northern Gate. It is bound to you.]"
    assert ck.paragraf_tekrarlari([UZUN, UZUN], [satir, satir]) == []


def test_kisa_ve_hizasiz_paragraflar_sayilmaz():
    assert ck.paragraf_tekrarlari(["Evet.", "Evet."], ["Yes.", "Sure."]) == []
    assert ck.paragraf_tekrarlari([UZUN, UZUN], ["a"]) == []
