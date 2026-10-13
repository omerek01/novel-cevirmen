"""Okuma Salonu yazı tipleri: yerel dosya + kabuk listesi.

PWA çevrimdışı açılır; `fonts.css`'teki bir dosya diskte ya da `sw.js` SHELL
listesinde yoksa çevrimdışıyken yazı sistem fontuna düşer.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def test_fonts_css_deki_her_dosya_var_ve_kabukta():
    css = (WEB / "fonts.css").read_text(encoding="utf-8")
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    dosyalar = re.findall(r"url\((fonts/[^)]+\.woff2)\)", css)
    assert dosyalar
    for d in dosyalar:
        assert (WEB / d).exists(), d
        assert f'"/{d}"' in sw, d


def test_inter_kalkti_yeni_aileler_var():
    css = (WEB / "fonts.css").read_text(encoding="utf-8")
    assert "'Inter'" not in css
    for aile in ("Libre Caslon Display", "Libre Caslon Text", "Alegreya Sans", "Alegreya Sans SC", "Literata"):
        assert f"font-family:'{aile}'" in css, aile
