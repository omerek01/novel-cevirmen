"""Tarayıcı testleri için ALT SÜREÇTE koşan test sunucusu.

Kullanım: python sunucu.py PORT  (NOVEL_DB_PATH ortamdan gelir)

`.env` BİLEREK yüklenmez: gerçek API anahtarları test sunucusuna sızarsa bir
test hatası (önbellekte olmayan bir bölümü açmak) gerçek bir çeviri isteğine,
ücretli model seçiliyse PARAYA dönerdi. Anahtarsız sunucu aynı hatada
"API anahtarı yok" der ve test gürültülü biçimde düşer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOK / "app"))

import dotenv  # noqa: E402

# `server` modülü import anında `load_dotenv(...)` çağırır; `from dotenv import
# load_dotenv` bağlaması import SIRASINDA yapıldığı için yama ondan ÖNCE olmalı.
dotenv.load_dotenv = lambda *a, **k: False
for ad in list(os.environ):
    if "API_KEY" in ad.upper():
        del os.environ[ad]

import uvicorn  # noqa: E402

import server  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(server.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
