"""Sunucu tarafı genel ayarlar (anahtar-değer).

Neden okuyucunun `localStorage`'ında DEĞİL: burada duran ayarlar ÇEVİRİYİ etkiliyor
ve çeviriyi yapan sunucu. Üç somut sonuç:
  * Telefon ve PC aynı seçimi görür (kütüphane ve okuma konumu gibi).
  * Arka plan işleri (prefetch, toplu çeviri, gece işi) istemci olmadan koşuyor;
    istemci-taraflı bir ayarı okuyamazlardı ve okumanın GÖVDESİ prefetch'ten gelir.
  * Ayar sunucu yeniden başlayınca kaybolmaz.

Tablo tembel oluşturulur (projenin geri kalanıyla aynı desen); merkezi şema dosyası
yok.
"""
from __future__ import annotations

import sqlite3

from . import db


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    return conn


def get(key: str, default: str = "") -> str:
    conn = _connect()
    try:
        satir = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    finally:
        conn.close()
    if satir is None or satir[0] is None:
        return default
    return str(satir[0])


def set(key: str, value: str) -> None:  # noqa: A001 - modül içi ad, çakışma yok
    """Ayarı yaz (E-16 gereği ON CONFLICT, REPLACE değil).

    `INSERT OR REPLACE` satırı SİLİP yeniden yazar; bu tabloda bugün tek sütun var
    ama ileride ikinci bir sütun eklenirse (ör. `updated_at`) REPLACE onu sessizce
    sıfırlardı. `chapters` tablosunda tam olarak bu sınıf hata yaşandı.
    """
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()
