"""Tarayıcı testlerinde ASYNC yüklemli `wait_for_function` YASAK.

Playwright `wait_for_function` dönen Promise'i beklemez; Promise nesnesi truthy
olduğu için yüklem anında "doğru" sayılır. Ölçüldü (2026-09-16):
`wait_for_function("async () => false")` 0,03 sn'de geçti — sunucu durumunu fetch
ile doğrulayan 13 iddia hiçbir şey doğrulamıyordu. Yerine `yardimci.js_bekle`.
"""
from __future__ import annotations

import re
from pathlib import Path

KLASOR = Path(__file__).resolve().parent / "tarayici"


def test_async_yuklemli_wait_for_function_yok():
    desen = re.compile(r"wait_for_function\(\s*f?[\"'](async|\(\s*async)")
    ihlaller = [
        f"{d.name}:{d.read_text(encoding='utf-8')[:m.start()].count(chr(10)) + 1}"
        for d in sorted([*KLASOR.glob("test_*.py"), KLASOR / "conftest.py"])
        for m in desen.finditer(d.read_text(encoding="utf-8"))
    ]
    assert not ihlaller, "async yüklemli wait_for_function (dişsiz bekleme): " + ", ".join(ihlaller)
