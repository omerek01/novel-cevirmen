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


def test_bicim_adi_ve_erken_bolum():
    assert _sinif("The Stone Saint stood still. Marble Saint too.") == []
    assert _sinif("Saint walked away.", bolum=50) == ["taban"]  # gölge henüz yok


def test_paragraf_isaretleri_belirsizi_atlar():
    paragraflar = ["He summoned Saint.", "The Saint sighed.", "She became a Saint.", "Nothing here."]
    assert aa.paragraf_isaretleri(paragraflar, "Saint", 400, KURAL) == {0: {"anlam"}, 2: {"taban"}}
