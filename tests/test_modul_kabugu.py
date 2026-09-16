"""Okuyucunun ES modül kabuğu: statik tel tuzakları (tarayıcı gerekmez).

Build adımı yok; modüller tarayıcıda doğrudan yüklenir. Üç sessiz arıza sınıfı
burada tutulur, üçü de yalnız belirli bir durumda görünür hâle gelir:

* `sw.js` SHELL listesinde olmayan modül → çevrimiçi her şey çalışır, çevrimdışı
  açılışta o modül indirilemez ve uygulama HİÇ başlamaz.
* Var olmayan bir adı içe aktarmak → modül grafiği yüklenmez, beyaz ekran.
* Göreli yol hatası → aynı sonuç.
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "app" / "web"
IMPORT_RE = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";', re.M)
EXPORT_RE = re.compile(r"^export\s+(?:async\s+function|function|const|let)\s+([A-Za-z_$][\w$]*)", re.M)


def _moduller() -> list[Path]:
    return sorted((WEB / "js").glob("*.js"))


def _shell() -> set[str]:
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    blok = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    return set(re.findall(r'"(/[^"]*)"', blok))


def test_her_modul_sw_kabugunda():
    kabuk = _shell()
    eksik = [f"/js/{m.name}" for m in _moduller() if f"/js/{m.name}" not in kabuk]
    assert not eksik, f"sw.js SHELL listesinde olmayan modüller: {eksik}"


def test_kabuktaki_her_modul_diskte_var():
    for yol in _shell():
        if yol.startswith("/js/"):
            assert (WEB / yol.lstrip("/")).is_file(), f"SHELL'de var ama diskte yok: {yol}"


def test_iceri_aktarilan_her_ad_disari_aktariliyor():
    disa = {m.resolve(): set(EXPORT_RE.findall(m.read_text(encoding="utf-8"))) for m in _moduller()}
    for dosya in [WEB / "app.js", *_moduller()]:
        metin = dosya.read_text(encoding="utf-8")
        for adlar, yol in IMPORT_RE.findall(metin):
            hedef = (dosya.parent / yol).resolve()
            assert hedef in disa, f"{dosya.name}: çözülemeyen içe aktarma {yol}"
            for parca in adlar.split(","):
                ad = parca.strip().split(" as ")[0].strip()
                if ad:
                    assert ad in disa[hedef], f"{dosya.name}: {yol} '{ad}' dışa aktarmıyor"


def test_giris_noktasi_modul_olarak_yuklenir():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="/app.js"></script>' in html


def test_sunucu_js_mime_turunu_acikca_kaydeder():
    """Windows kayıt defteri `.js`i text/plain verebilir; modül betiği o türle reddedilir."""
    kaynak = (WEB.parent / "server.py").read_text(encoding="utf-8")
    assert 'mimetypes.add_type("text/javascript", ".js")' in kaynak
