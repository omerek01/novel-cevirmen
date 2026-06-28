"""Gerçek Chrome'u CDP debug-portuyla başlatır — sert Cloudflare'i aşmak için.

NEDEN: Cloudflare bir makineyi sıkı-bloka aldığında Playwright'in başlattığı tarayıcı
(paket Chromium VEYA channel=chrome) otomasyon parmak izinden ele verir ve geçemez.
Kullanıcının ELLE başlattığı gerçek Chrome (otomasyon bayrakları yok) ise insan kabul
edilir; "Verify you are human" çıksa bile bir kez tıklayınca geçer ve cookie bu profile
yazılır. Backend (fetch.py) FETCH_CDP_URL ayarlıyken bu açık Chrome'a CDP ile bağlanır.

KULLANIM (proje kökünden):
    .venv/Scripts/python.exe scripts/start_chrome_cdp.py

1) Açılan Chrome penceresinde freewebnovel/novelfull gibi siteye gir; CF çıkarsa çöz.
2) Pencereyi AÇIK BIRAK.
3) Sunucuyu şu env ile çalıştır (veya .env'e ekle):
       FETCH_CDP_URL=http://127.0.0.1:9222
   Artık telefondan/PC'den gelen tüm çekimler bu gerçek Chrome üzerinden geçer.
   Chrome'u kapatırsan backend otomatik olarak normal (paket Chromium) akışına döner —
   yani bu opsiyonel; kapalıyken hiçbir şey bozulmaz.

NOT: Ana (günlük) Chrome'unla çakışmaması için ayrı bir profil dizini kullanılır
(cache/.chrome-cdp). Bu yüzden ana Chrome'un açık olsa da sorun çıkmaz.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Windows konsolu cp1252; Türkçe print'leri UnicodeEncodeError vermesin.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

PORT = 9222
PROFILE = Path(__file__).resolve().parent.parent / "cache" / ".chrome-cdp"
START_URL = "https://freewebnovel.com"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str | None:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return shutil.which("chrome") or shutil.which("chrome.exe")


def port_open(port: int) -> bool:
    """9222 zaten dinleniyorsa CDP Chrome zaten açık demektir (ikinci pencere açma)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    if port_open(PORT):
        print(f"CDP Chrome zaten açık (port {PORT}). Yeni pencere açılmıyor.")
        return 0
    chrome = find_chrome()
    if not chrome:
        print("HATA: chrome.exe bulunamadı. Google Chrome kurulu mu?")
        return 1
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        START_URL,
    ]
    print(f"Chrome   : {chrome}")
    print(f"Port     : {PORT}")
    print(f"Profil   : {PROFILE}")
    print("Pencere açılıyor… CF çıkarsa çöz, sonra pencereyi AÇIK BIRAK.")
    print(f"Sunucuyu şu env ile çalıştır:  FETCH_CDP_URL=http://127.0.0.1:{PORT}\n")
    # Detached: bu script'ten bağımsız yaşasın (script kapansa da Chrome açık kalsın).
    subprocess.Popen(args, close_fds=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
