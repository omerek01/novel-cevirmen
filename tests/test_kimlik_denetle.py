"""Kimlik denetim aracı (`scripts/kimlik_denetle.py`) — saf kısımlar, yapay metin."""
from __future__ import annotations

import kimlik_denetle as kd

from core import glossary

KITAP = "kimlik-kitap"


def test_kimlik_kaliplari_ayni_cumle_yetmez():
    k = kd.kimlik_kaliplari("Sunless", "Lord of Shadows")
    assert any(p.search("Sunless, the Lord of Shadows, raised his hand.") for p in k)
    assert any(p.search("The Lord of Shadows — Sunless — smiled.") for p in k)
    assert any(p.search("Sunless, also known as the Lord of Shadows, left.") for p in k)
    # Aynı cümlede geçmek KİMLİK kanıtı değildir.
    assert not any(p.search("Sunless bowed before the Lord of Shadows.") for p in k)


def test_yinelenen_adaylar_genel_kurallarla_bulunur_birlestirilmez():
    for s, t in {"Fire Keeper": "Ateş Bekçisi", "Fire Keepers": "Ateş Bekçileri", "House Night": "Gece Hanesi",
                 "House of Night": "Gece Hanesi", "Chained Island": "Zincirli Ada", "Chained Isles": "Zincirli Adalar",
                 "Dark City": "Karanlık Şehir", "Dark Wing": "Kara Kanat"}.items():
        glossary.set_term(KITAP, s, t)
    adaylar = {(a, b): n for n, a, _ta, b, _tb in kd.yinelenen_adaylar(KITAP)}
    assert adaylar[("Fire Keeper", "Fire Keepers")] == "tekil/çoğul"
    assert adaylar[("House Night", "House of Night")] == "araya giren 'of'"
    assert adaylar[("Chained Island", "Chained Isles")] == "son sözcük ortak kök"
    assert ("Dark City", "Dark Wing") not in adaylar  # ortak kök yok: aday değil
    assert len(glossary.get_glossary_rows(KITAP)) == 8  # hiçbir şey birleştirilmedi
