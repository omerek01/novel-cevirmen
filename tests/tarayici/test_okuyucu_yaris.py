"""Okuyucu: geç gelen ESKİ bölüm yanıtı yeni açılan bölümü ezmez.

Bölüm isteği çeviri yüzünden 30-60 sn sürebilir. Okur bu sırada başka bölüm açarsa
(Bölümler listesi, art arda Sonraki) eski yanıt sonradan gelip akışa yazılıyor,
ekranı eziyor ve okuma konumunu yanlış bölüme kaydediyordu.
"""
from __future__ import annotations

import tohum
from yardimci import js_bekle

MODUL = "import('/js/okuyucu.js')"


def test_gec_gelen_eski_bolum_yeni_bolumu_ezmez(sayfa):
    a = tohum.kitap("kitap-a", "Kitap A", bolum_sayisi=1)[0]
    b = tohum.kitap("kitap-b", "Kitap B", bolum_sayisi=1)[0]
    sayfa.goto(sayfa.taban + "/")
    bekleyen = []

    def tut(route):  # yanıtı bekletir: test sonra serbest bırakır
        bekleyen.append(route)

    sayfa.route(lambda u: "/api/chapter?" in u and "kitap-a" in u, tut)

    sayfa.evaluate(f"async (u) => {{ const m = await {MODUL}; m.loadChapter(u); }}", a)
    js_bekle(sayfa, "() => true")
    sayfa.wait_for_timeout(300)
    assert bekleyen, "A'nın isteği yakalanmadı"
    sayfa.evaluate(f"async (u) => {{ const m = await {MODUL}; await m.loadChapter(u); }}", b)
    bekleyen[0].continue_()  # A'nın yanıtı ŞİMDİ gelir: B açıldıktan sonra
    sayfa.wait_for_timeout(1000)

    durum = sayfa.evaluate(f"""async () => {{
        const m = await {MODUL};
        return {{ akis: m.stream.map((e) => e.url), aktif: m.activeUrl,
                  dom: [...document.querySelectorAll('#readerBody article[data-url]')]
                        .map((x) => x.dataset.url) }};
    }}""")
    assert durum["akis"] == [b], durum
    assert durum["dom"] == [b], durum
    assert durum["aktif"] in (b, None), durum
