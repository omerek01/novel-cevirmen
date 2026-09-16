"""Tarayıcı (Playwright) testleri — İSTEĞE BAĞLI.

Varsayılan `pytest` koşusu bunları TOPLAMAZ: çevrimdışı birim testleri ~20 sn'de
biter ve Chromium ister; bunlar gerçek bir sunucu süreci + tarayıcı açar.
Çalıştırmak için: NOVEL_TARAYICI_TEST=1 .venv/Scripts/python.exe -m pytest tests/tarayici

Neden var: okuyucu build adımı olmayan vanilla JS ve hiçbir JS testi yoktu.
Kuyruk yarışı, odak yönetimi, çevrimdışı durum gibi kabul ölçütleri ancak
gerçek bir tarayıcıda doğrulanabiliyor.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

if os.environ.get("NOVEL_TARAYICI_TEST") != "1":
    collect_ignore_glob = ["test_*.py"]

BURASI = Path(__file__).resolve().parent


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sunucu_baslat(db_yolu) -> tuple[subprocess.Popen, str]:
    port = _bos_port()
    ortam = dict(os.environ, NOVEL_DB_PATH=str(db_yolu), PYTHONIOENCODING="utf-8")
    surec = subprocess.Popen(
        [sys.executable, str(BURASI / "sunucu.py"), str(port)],
        env=ortam, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    taban = f"http://127.0.0.1:{port}"
    son = time.time() + 40
    while True:
        try:
            with urllib.request.urlopen(taban + "/api/books", timeout=2) as r:
                if r.status == 200:
                    return surec, taban
        except OSError:
            pass
        if surec.poll() is not None or time.time() > son:
            cikti = surec.stdout.read().decode("utf-8", "replace") if surec.stdout else ""
            surec.kill()
            raise RuntimeError("test sunucusu açılmadı:\n" + cikti)
        time.sleep(0.25)


def sunucu_durdur(surec: subprocess.Popen) -> None:
    if surec.poll() is not None:
        return
    surec.terminate()
    try:
        surec.wait(timeout=10)
    except subprocess.TimeoutExpired:
        surec.kill()


@pytest.fixture(scope="session")
def sunucu(tmp_path_factory):
    """Tek test sunucusu (oturum boyu). Her test kendi verisini `temiz_db` ile kurar."""
    db_yolu = tmp_path_factory.mktemp("tarayici") / "chapters.db"
    surec, taban = sunucu_baslat(db_yolu)
    yield {"taban": taban, "db": str(db_yolu)}
    sunucu_durdur(surec)


@pytest.fixture
def kapatilabilir_sunucu(tmp_path, monkeypatch):
    """Test içinde ÖLDÜRÜLEBİLEN ayrı sunucu — gerçek çevrimdışılık için.

    `context.set_offline(True)` service worker'ın KENDİ ağ isteklerini kesmiyor
    (Chromium/Playwright sınırı): SW önbellekte bulamadığı bir modülü sunucudan
    sessizce çekiyor ve çevrimdışı testi dişsiz kalıyordu (mutasyonla ölçüldü:
    SHELL'den bir modül çıkarıldığında test yine geçiyordu). Sunucuyu fiilen
    kapatmak, telefonun Tailscale'i koptuğunda yaşadığının aynısı.
    """
    db_yolu = tmp_path / "kapanan.db"
    monkeypatch.setenv("NOVEL_DB_PATH", str(db_yolu))
    surec, taban = sunucu_baslat(db_yolu)
    yield {"taban": taban, "db": str(db_yolu), "durdur": lambda: sunucu_durdur(surec)}
    sunucu_durdur(surec)


@pytest.fixture
def temiz_db(sunucu, monkeypatch):
    """Tohumlama sunucunun DB'sine yazsın; her test boş başlasın."""
    monkeypatch.setenv("NOVEL_DB_PATH", sunucu["db"])
    from tohum import temizle

    temizle()
    return sunucu


@pytest.fixture(scope="session")
def tarayici():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def sayfa(tarayici, temiz_db, request):
    """Telefon boyutunda sayfa. Yakalanmamış JS hatası testi DÜŞÜRÜR.

    Service worker varsayılan olarak ENGELLİ: önbellek davranışı testler arasında
    sızarsa bir testin sonucu öncekinin bıraktığı kopyaya bağlı olurdu. SW'yi
    özellikle sınayan test `sw_acik` işaretiyle açar.
    """
    sw = "allow" if request.node.get_closest_marker("sw_acik") else "block"
    boyut = getattr(request, "param", None) or {"width": 390, "height": 844}
    baglam = tarayici.new_context(viewport=boyut, service_workers=sw)
    pg = baglam.new_page()
    hatalar: list[str] = []
    pg.on("pageerror", lambda e: hatalar.append(str(e)))
    pg.taban = temiz_db["taban"]
    pg.js_hatalari = hatalar
    yield pg
    baglam.close()
    assert not hatalar, "Yakalanmamış JS hatası:\n" + "\n".join(hatalar)


def pytest_configure(config):
    config.addinivalue_line("markers", "sw_acik: bu testte service worker açık")
