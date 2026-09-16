"""Okuyucunun saf JS mantığı için Node birim testleri (tests/js/*.test.mjs).

Node kurulu değilse (ör. bulut sunucusu) ATLANIR: bu testler tarayıcı
modüllerinin saf kısımlarını sınar ve çalışma zamanı değil geliştirme
güvencesidir. Geliştirme makinesinde Node var; orada koşmaları zorunlu.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent


def test_node_birim_testleri():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node yok")
    sonuc = subprocess.run(
        [node, "--test", "tests/js/*.test.mjs"],
        cwd=KOK, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert sonuc.returncode == 0, sonuc.stdout[-4000:] + sonuc.stderr[-2000:]
