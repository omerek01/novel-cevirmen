"""Tarayıcı testi yardımcıları."""
from __future__ import annotations

import time


def js_bekle(sayfa, ifade: str, timeout: int = 10000, aralik: int = 100):
    """JS ifadesi (async olabilir) doğru dönene kadar bekle; dönen değeri ver.

    `page.wait_for_function` ASYNC yüklemi BEKLEMEZ: dönen Promise nesnesi truthy
    olduğu için anında geçer. Ölçüldü (2026-09-16): `wait_for_function("async () =>
    false")` 0,03 sn'de geçiyordu — sunucu durumunu fetch ile doğrulayan her iddia
    dişsizdi. `page.evaluate` Promise'i bekler; yoklama burada Python tarafında yapılır.
    """
    son = time.monotonic() + timeout / 1000
    while True:
        deger = sayfa.evaluate(ifade)
        if deger:
            return deger
        if time.monotonic() > son:
            raise AssertionError(
                f"JS koşulu {timeout} ms içinde sağlanmadı: {ifade[:200]} (son değer: {deger!r})"
            )
        sayfa.wait_for_timeout(aralik)
