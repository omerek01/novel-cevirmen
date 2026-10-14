"""NovelLink uygulama ikonunu üretir: `app/web/icon.svg` + PWA/iOS PNG'leri.

Okuma Salonu (2026-10-13) dilinde logo: ceviz zemin, üstten lamba ışığı, Libre
Caslon Text kalın "N" (kâğıt rengi) ve harfin çaprazının ARKASINDAN geçip altta
çentikle biten mühür kırmızısı kitap ayracı kurdelesi ("kaldığın yer").

Glif, `app/web/fonts/libre-caslon-text-700-latin.woff2` içinden fontTools ile
çıkarılmış yoldur (SIL OFL; gömmeye izin verir). Yol olarak gömülür ki ikon
tarayıcıdaki sistem yazı tipine (eski logodaki Georgia gibi) bağlı kalmasın.

PNG'ler projenin Playwright Chromium'uyla çizilir; SVG ile birebir aynı görünür.
Çalıştırma (kök dizinden):  .venv/Scripts/python.exe scripts/ikon_uret.py
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

WEB = pathlib.Path(__file__).resolve().parent.parent / "app" / "web"

# Libre Caslon Text Bold "N" (upm 1000, taban çizgisi y=0, yukarı +y).
N_YOLU = (
    "M689 -10 197 610V56L285 37V0H39V37L128 56V714L40 733V770H311L689 295"
    "V714L601 733V770H847V733L758 714V-10Z"
)
OLCEK = 0.32  # büyük harf yüksekliği ~246 px (512 tuvalde)
N_DONUSUM = (
    f"translate({256 - (39 + 847) / 2 * OLCEK:.2f} {128 + 770 * OLCEK:.2f}) "
    f"scale({OLCEK} {-OLCEK})"
)

# Renkler style.css gece temasından: zemin --bg, harf --ink, lamba --lamp;
# kurdele mühür kırmızısı (--stamp gündüz #a23a2a) çevresinde kumaş gölgesi.
ZEMIN = "#14110e"
MUREKKEP = "#ece3d1"
KOSE = 96  # yuvarlak köşe ("any" ikon ve favicon)

# Kurdele: tuvalin üst kenarından sarkar, N'nin üst serifleri arasından girer,
# çaprazın arkasından geçer, taban çizgisinin altında V çentikle biter. Maskeli
# (maskable) ikonun güvenli dairesi (yarıçap 205) içinde kalır.
KURDELE = "M228 0H284V452L256 424L228 452Z"


def svg(tam_tasma: bool = False) -> str:
    """`tam_tasma`: köşesiz, kenara kadar zemin (maskable PNG ve iOS için)."""
    if tam_tasma:
        kirp_tanim, kirp = "", ""
        zemin = f'<rect width="512" height="512" fill="{ZEMIN}"/>'
    else:
        kirp_tanim = f'<clipPath id="kose"><rect width="512" height="512" rx="{KOSE}"/></clipPath>'
        kirp = ' clip-path="url(#kose)"'
        zemin = f'<rect width="512" height="512" rx="{KOSE}" fill="{ZEMIN}"/>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <!-- NovelLink: Okuma Salonu logosu. Elle düzenleme; scripts/ikon_uret.py üretir. -->
  <defs>
    {kirp_tanim}
    <radialGradient id="lamba" cx="256" cy="-40" r="420" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffc478" stop-opacity=".2"/>
      <stop offset="1" stop-color="#ffc478" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="kurdele">
      <stop offset="0" stop-color="#8f2f22"/>
      <stop offset=".45" stop-color="#b8432f"/>
      <stop offset="1" stop-color="#8a2c20"/>
    </linearGradient>
    <!-- N'nin çevresinde ince boşluk: kurdele harfin arkasından geçiyor okunur -->
    <mask id="oyuk">
      <rect width="512" height="512" fill="#fff"/>
      <path transform="{N_DONUSUM}" d="{N_YOLU}" fill="#000" stroke="#000" stroke-width="30" stroke-linejoin="round"/>
    </mask>
  </defs>
  <g{kirp}>
    {zemin}
    <rect width="512" height="512" fill="url(#lamba)"/>
    <path mask="url(#oyuk)" fill="url(#kurdele)" d="{KURDELE}"/>
  </g>
  <path transform="{N_DONUSUM}" d="{N_YOLU}" fill="{MUREKKEP}"/>
</svg>
"""


# (dosya, piksel, tam_tasma): "any" ikonlar yuvarlak köşeli ve saydam; maskable
# ve iOS kenara kadar zemin ister (köşeyi işletim sistemi keser).
PNGLER = [
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-maskable-192.png", 192, True),
    ("icon-maskable-512.png", 512, True),
    ("apple-touch-icon.png", 180, True),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolu cp1252: "ı" basılamaz
    (WEB / "icon.svg").write_text(svg(), encoding="utf-8")
    with sync_playwright() as p:
        tarayici = p.chromium.launch()
        for ad, boyut, tam in PNGLER:
            sayfa = tarayici.new_page(viewport={"width": boyut, "height": boyut})
            icerik = svg(tam).replace("<svg ", f'<svg width="{boyut}" height="{boyut}" ', 1)
            sayfa.set_content(
                f'<html><body style="margin:0;background:transparent">{icerik}</body></html>'
            )
            sayfa.screenshot(path=str(WEB / ad), omit_background=not tam)
            sayfa.close()
        tarayici.close()
    print("yazıldı:", "icon.svg", *(ad for ad, _, _ in PNGLER))


if __name__ == "__main__":
    main()
