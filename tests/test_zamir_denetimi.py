"""Zamir belirsizliği işaretleyicisi (Faz A7). Cümleler uydurmadır."""
from core.zamir_denetimi import belirsiz_mi, paragraf_isaretleri

EN = "When Mara reached the gate, Tomas handed her the key and she thanked him before he left."


def test_adlar_zamire_inince_isaretlenir():
    assert belirsiz_mi(EN, "Kapıya vardığında o, ona anahtarı verdi; o da ona teşekkür etti ve gitti.")


def test_adlar_korunursa_isaretlenmez():
    # İki zamir var ama iki ad da korunmuş: kimin ne yaptığı belli.
    assert not belirsiz_mi(EN, "Mara kapıya vardığında Tomas ona anahtarı verdi; Mara da ona teşekkür etti.")


def test_tek_cinsiyetli_paragraf_isaretlenmez():
    assert not belirsiz_mi("Tomas told Arto that he was tired.", "O, onun yorgun olduğunu söyledi; o da sustu.")


def test_tek_adli_paragraf_isaretlenmez():
    assert not belirsiz_mi("She looked at him, then he smiled at Mara.", "O ona baktı, o da gülümsedi.")


def test_hizasizda_olcmez():
    assert paragraf_isaretleri(["a"], [EN, "b"]) == []
    assert paragraf_isaretleri(["Kapıya vardığında o, ona anahtarı verdi; o da ona teşekkür etti."], [EN]) == [0]
