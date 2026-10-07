"""Çift anlamlı kaydın geçiş sınıflayıcısı (`core.anlam_ayirici`) — yapay cümleler."""
from __future__ import annotations

from core import anlam_ayirici as aa, varlik_grafigi as vg

KURAL = vg.KITAP_PROFILLERI["shadow-slave"]["anlam_dugumleri"]["Saint"]["ayirici"]


def _sinif(par, bolum=400):
    return [s for _b, s in aa.gecisleri_siniflandir(par, "Saint", bolum, KURAL)]


def test_rutbe_kaliplari():
    assert _sinif("She had become a Saint long ago.") == ["taban"]
    assert _sinif("A Saint... he had fought a Saint?") == ["taban", "taban"]
    assert _sinif("This clown was an actual Saint.") == ["taban"]
    assert _sinif("The Saints of the clan gathered.") == ["taban"]
    assert _sinif("Saint Tyris raised her hand.") == ["taban"]
    assert _sinif("Masters and Saints alike bowed.") == ["taban"]
    assert _sinif("He reached the rank of Saint.") == ["taban"]
    assert _sinif("Every Awakened, Master, and Saint felt it.") == ["taban"]
    assert _sinif("They would become Masters, maybe even Saint.") == ["taban"]


def test_golge_ve_belirsiz():
    assert _sinif("Then he summoned Saint and waited.") == ["anlam"]
    assert _sinif("Saint and Nightmare guarded the camp.") == ["anlam"]
    assert _sinif("He glanced at Saint. The night was cold.") == ["anlam"]
    assert _sinif("Saint's sword flashed.") == ["anlam"]
    # Virgül tek başına sayım değildir: önceki cümlenin sonu.
    assert _sinif("Ascended, Saint was now Ascended!") == ["anlam"]
    assert _sinif("The Saint sighed.") == ["belirsiz"]
    assert _sinif("The wounded Saint dissipated.") == ["belirsiz"]
    # Vertex A/B'de ölçülen iki sınıflayıcı hatası:
    assert _sinif("He reluctantly sent one to Saint.") == ["anlam"]             # 585: edat, artikel değil
    assert _sinif("Remember that handsome Saint who flirted?") == ["belirsiz"]  # 856: rütbeli kişi


def test_bicim_adi_ve_erken_bolum():
    assert _sinif("The Stone Saint stood still. Marble Saint too.") == []
    assert _sinif("Saint walked away.", bolum=50) == ["taban"]  # gölge henüz yok


def test_paragraf_isaretleri_belirsizi_atlar():
    paragraflar = ["He summoned Saint.", "The Saint sighed.", "She became a Saint.", "Nothing here."]
    assert aa.paragraf_isaretleri(paragraflar, "Saint", 400, KURAL) == {0: {"anlam"}, 2: {"taban"}}



def test_anlam_ipucu_paragraf_numarali_ve_bos_parcada_yok():
    from core import translate
    anlamlar = [{"kayit": "Saint", "taban_karsilik": "Aziz", "anlam_karsilik": "Saint",
                 "anlam_aciklama": "gölge", "ayirici": KURAL}]
    paras = ["He summoned Saint.", "The Saint sighed.", "She became a Saint."]
    ipucu = translate.anlam_ipucu(paras, anlamlar, 400)
    assert '[[1]] → gölge: "Saint" yaz' in ipucu and '[[3]] → asıl anlam: "Aziz" yaz' in ipucu
    assert "[[2]]" not in ipucu  # belirsiz paragraf yazılmaz
    assert translate.anlam_ipucu(["Nothing here."], anlamlar, 400) == ""
    assert translate.anlam_ipucu(paras, None, 400) == ""


def test_ipucu_yoksa_talimat_bayt_bayt_ayni():
    from core import translate
    paras = ["Sunny walked."]
    assert translate._build_user_prompt(paras, {}, "") == translate._build_user_prompt(paras, {}, "", None, "")
    ile = translate._build_user_prompt(paras, {}, "", None, "ÇİFT ANLAMLI ADLAR — x")
    assert "ÇİFT ANLAMLI ADLAR" in ile


def test_ceviri_anlamlari_rutbe_sozcuklerini_grafikten_alir():
    from core import glossary
    for k, v in {"Saint": "Aziz", "Tyris": "Tyris", "Paragon": "Örnek"}.items():
        glossary.set_term("shadow-slave", k, v)
    c = vg.DugumCozucu("shadow-slave").coz
    vg.bag_ekle("shadow-slave", c("Tyris"), "rutbesi", c("Paragon"), 10, "x", "manual", 1.0)
    a = next(x for x in vg.ceviri_anlamlari("shadow-slave") if x["kayit"] == "Saint")
    assert a["taban_karsilik"] == "Aziz" and a["anlam_karsilik"] == "Saint"
    assert "Paragon" in a["ayirici"]["taban_oncesi"]  # grafikteki rütbe, kodda yok
    assert [s for _b, s in aa.gecisleri_siniflandir("Every Paragon and Saint knelt.", "Saint", 400,
                                                  a["ayirici"])] == ["taban"]
