"""Sonraki bölümün önceden ısıtılması (prefetch) bağlantı hatasında vazgeçmez.

Vaka (2026-10-19, shadow-slave #1043): ısıtma sürerken sunucu yeniden başladı,
çeviri iş parçacığıyla birlikte öldü. Okuyucunun yoklaması ilk başarısız istekte
DURUYORDU; sunucu ~8 sn sonra ayağa kalktığında bölüm bir daha istenmedi ve
okur bölümü açınca çevirinin tamamını (6 dk) baştan bekledi. Telefonun bağlantısı
kısa süre koptuğunda da aynısı olur.
"""
from __future__ import annotations

import time

import tohum

HEDEF = "https://ornek.test/isitma-kitap/2"


def _yukle_ve_isit(sayfa, yanit):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    istekler = []

    def isle(route):
        istekler.append(route.request.post_data_json)
        yanit(route, len(istekler))
    sayfa.route("**/api/prefetch", isle)
    sayfa.evaluate(
        "async (u) => { const m = await import('/js/okuyucu.js'); m.isitVeKaydet(u, 3); }", HEDEF)
    return istekler


def _bekle(sayfa, kosul, sure=12):
    # `time.sleep` OLMAZ: senkron Playwright beklerken olay işlemez, route çağrılmaz.
    son = time.time() + sure
    while time.time() < son and not kosul():
        sayfa.wait_for_timeout(200)


def test_baglanti_hatasindan_sonra_isitmayi_yeniden_ister(sayfa):
    def yanit(route, n):
        if n == 1:
            route.abort()  # sunucu yeniden başlıyor / telefon bağlantısı koptu
        else:
            route.fulfill(json={"ok": True, "queued": True})
    istekler = _yukle_ve_isit(sayfa, yanit)
    _bekle(sayfa, lambda: len(istekler) >= 2)
    assert len(istekler) >= 2
    assert istekler[1] == {"url": HEDEF}


def test_hazir_olunca_yoklamayi_birakir(sayfa):
    istekler = _yukle_ve_isit(
        sayfa, lambda route, n: route.fulfill(json={"ok": True, "cached": True}))
    _bekle(sayfa, lambda: False, sure=6)  # bir yoklama aralığı (5 sn) geçsin
    assert len(istekler) == 1
