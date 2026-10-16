"""Kitap profili — kitaba özel bilgi koddan VERİYE (2026-10-16, plan Faz 1).

Kitaba özel kurallar (rütbe dizileri, kategori terimleri, ana karakter, rün okuması,
çift anlamlı adlar, sabit bağlar) `varlik_grafigi.KITAP_PROFILLERI` içinde koda gömülüydü:
profili olmayan kitapta rün/anı/rütbe katmanları sessizce kapanıyor, yeni kitap için kod
yazmak gerekiyordu. Bu modül şemanın sahibidir: alan başına bir satır, JSON değer.

* **Okuma tek noktadan**: `varlik_grafigi.profil()` buraya delege eder; ikinci bir kaynak
  açılmaz (projenin "tek nokta" kuralı). Yalnız `durum='onayli'` satırlar profile girer —
  model önerisi (`aday`, Faz 3) kullanıcı onaylamadan hiçbir istem/denetime girmez.
* **Kod kaydı `sistem` katmanıdır ve DB'ye KOPYALANMAZ**: her okumada koddan alınır, DB'de
  yalnız `manual` ve `model` satırları durur ve onun üstüne biner (öncelik manual > model >
  kod). İki yanlış ölçülerek elendi: (1) "varsa ezme" tohumu, koddaki profil sonradan
  düzeltilince sunucudaki eski tohum kalır ve düzeltme sessizce uygulanmazdı; (2) okumada
  tohum YAZMAK, başka bir bağlantı yazma kilidi tutarken (sözlük yazma yolu kapıyı, kapı
  profili çağırıyor) "database is locked" verdi — testlerin 84'ü düştü. OKUMA HİÇ YAZMAZ.
* **Tür korunur**: JSON listesi tuple'a döner (kod kaydı tuple taşır; çağıranlar `in`,
  dilimleme ve hash kullanıyor). Ölçüt: SS profili DB'den okununca koddakiyle BİREBİR eşit
  (`tests/test_kitap_profili.py`).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from . import db

# `sistem` DB'ye yazılmaz (koddan okunur); yalnız bu iki köken saklanır.
ORIGINLER = ("model", "manual")
DURUMLAR = ("aday", "onayli", "reddedildi")

_KILIT = threading.Lock()
# {(db yolu, slug): profil | None} — profil her bölümde, kimi yolda paragraf başına okunur.
_ONBELLEK: dict[tuple[str, str], dict] = {}  # yalnız DB katmanı


def _connect():
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kitap_profili (
            book_slug TEXT NOT NULL,
            alan TEXT NOT NULL,
            deger TEXT NOT NULL,
            origin TEXT NOT NULL,
            durum TEXT NOT NULL,
            kanit TEXT,
            updated_at REAL NOT NULL,
            PRIMARY KEY (book_slug, alan, origin)
        )
        """
    )
    return conn


def _tuple_yap(v):
    if isinstance(v, list):
        return tuple(_tuple_yap(x) for x in v)
    if isinstance(v, dict):
        return {k: _tuple_yap(x) for k, x in v.items()}
    return v


def _anahtar(book_slug: str) -> tuple[str, str]:
    return (str(db.db_path()), book_slug)


def onbellegi_temizle() -> None:
    with _KILIT:
        _ONBELLEK.clear()


def profil(book_slug: str, kod_kayitlari: dict[str, dict] | None = None) -> dict | None:
    """Kitabın etkin profili: koddaki kayıt + DB'deki ONAYLI satırlar (manual > model > kod).

    Hiçbiri yoksa None. Okuma yazma YAPMAZ (tablo yoksa DB katmanı boş sayılır)."""
    anahtar = _anahtar(book_slug)
    with _KILIT:
        katman = _ONBELLEK.get(anahtar)
    if katman is None:
        katman = _db_katmani(book_slug)
        with _KILIT:
            _ONBELLEK[anahtar] = katman
    kod = (kod_kayitlari or {}).get(book_slug)
    if not katman:
        return kod  # yalnız kod: aynı nesne döner (bugünkü davranış birebir)
    return {**(kod or {}), **katman}


def _db_katmani(book_slug: str) -> dict:
    # SALT-OKUNUR ve pragmasız bağlantı: `db.connect()` her açılışta `journal_mode=WAL`
    # yazar ve çağıran (sözlük yazma yolu) yazma kilidi tutarken o pragma "database is
    # locked" verir. WAL kipinde salt okuyucu yazanı beklemez.
    try:
        conn = sqlite3.connect(f"file:{db.db_path().as_posix()}?mode=ro", uri=True)
    except sqlite3.OperationalError:  # dosya yok
        return {}
    try:
        satirlar = conn.execute(
            "SELECT alan, deger, origin FROM kitap_profili WHERE book_slug = ? AND durum = 'onayli' "
            "AND origin IN ('manual', 'model')", (book_slug,)).fetchall()
    except sqlite3.OperationalError:  # tablo yok: DB katmanı boş (okuma şema yaratmaz)
        return {}
    finally:
        conn.close()
    secilen: dict[str, tuple[int, object]] = {}
    sira = {"model": 1, "manual": 2}
    for alan, deger, origin in satirlar:
        if alan not in secilen or sira[origin] > secilen[alan][0]:
            secilen[alan] = (sira[origin], _tuple_yap(json.loads(deger)))
    return {alan: v for alan, (_o, v) in secilen.items()}


def yaz(book_slug: str, alan: str, deger, origin: str = "manual", durum: str = "onayli",
        kanit=None) -> None:
    """Profil alanını yaz (aynı köken satırını günceller)."""
    if origin not in ORIGINLER or durum not in DURUMLAR:
        raise ValueError(f"Geçersiz köken/durum: {origin!r}/{durum!r}")
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO kitap_profili (book_slug, alan, deger, origin, durum, kanit, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(book_slug, alan, origin) DO UPDATE SET "
            "deger = excluded.deger, durum = excluded.durum, kanit = excluded.kanit, "
            "updated_at = excluded.updated_at",
            (book_slug, alan, json.dumps(deger, ensure_ascii=False), origin, durum,
             json.dumps(kanit, ensure_ascii=False) if kanit is not None else None, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    with _KILIT:
        _ONBELLEK.pop(_anahtar(book_slug), None)


def satirlar(book_slug: str) -> list[dict]:
    """Bütün satırlar (aday ve reddedilenler dahil) — arayüz ve bakım için."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT alan, deger, origin, durum, kanit, updated_at FROM kitap_profili "
            "WHERE book_slug = ? ORDER BY alan, origin", (book_slug,)).fetchall()
    finally:
        conn.close()
    return [{"alan": r[0], "deger": json.loads(r[1]), "origin": r[2], "durum": r[3],
             "kanit": json.loads(r[4]) if r[4] else None, "updated_at": r[5]} for r in rows]


def durum_yaz(book_slug: str, alan: str, origin: str, durum: str) -> bool:
    """Bir satırın durumunu değiştir (aday -> onayli / reddedildi). Satır yoksa False."""
    if durum not in DURUMLAR:
        raise ValueError(f"Geçersiz durum: {durum!r}")
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE kitap_profili SET durum = ?, updated_at = ? WHERE book_slug = ? AND alan = ? "
            "AND origin = ?", (durum, time.time(), book_slug, alan, origin))
        conn.commit()
    finally:
        conn.close()
    with _KILIT:
        _ONBELLEK.pop(_anahtar(book_slug), None)
    return cur.rowcount > 0
