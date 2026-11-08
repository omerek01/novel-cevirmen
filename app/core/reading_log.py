"""Okuma günlüğü — "bugün / toplam bölüm" istatistiğinin veri kaynağı.

Satırı İSTEMCİ yazar (okuyucuda bölüm başarıyla render edilince `POST
/api/reading-log`): SW cache-first GET'i sunucuya ulaştırmadığı için sunucu-yanı
loglama imkânsızdır; prefetch/arka plan istekleri de böylece hiç loglanmaz.
`day` istemcinin YEREL günüdür — "bugün" sayacı gece yarısı UTC'ye kaymaz.
Tekilleştirme UNIQUE indeksledir (aynı gün aynı bölüm ikinci kez sayılmaz).
Yazım best-effort: DB meşgulse kayıt düşer, okuma asla bozulmaz.
"""
from __future__ import annotations

import re
import sqlite3
import statistics

from . import db

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reading_log (
            day TEXT NOT NULL,
            slug TEXT NOT NULL,
            url TEXT NOT NULL,
            ts REAL,
            UNIQUE(day, slug, url)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reading_log_ts ON reading_log(ts)")
    return conn


def log_read(day: str, slug: str, url: str) -> bool:
    """Bir bölüm okumasını günlüğe yaz (günde bölüm başına bir kez).

    True = yeni satır yazıldı; False = tekrar/geçersiz girdi/DB meşgul (yutulur —
    istatistik 1 eksik kalır, kabul edilmiş maliyet).
    """
    day = (day or "").strip()
    if not _DAY_RE.match(day) or not slug or not url:
        return False
    import time

    try:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO reading_log (day, slug, url, ts) "
                "VALUES (?, ?, ?, ?)",
                (day, slug, url, time.time()),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False  # best-effort: kilitli DB okuma akışını asla bozmasın


def stats(day: str) -> dict:
    """`{"today": N, "total": M}` — tek sorgu (N+1 yok).

    today: verilen (yerel) günde okunan benzersiz bölüm sayısı.
    total: tüm zamanlarda okunan benzersiz bölüm sayısı (D-B11v2: 'toplam'
    tanımı = benzersiz okunmuş bölüm).
    """
    day = (day or "").strip()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT url), "
            "COUNT(DISTINCT CASE WHEN day = ? THEN url END) FROM reading_log",
            (day,),
        ).fetchone()
    finally:
        conn.close()
    return {"today": row[1] or 0, "total": row[0] or 0}


# ---------------------------------------------------------------------------
# Okuma hızı (hızlı okuma planı Adım A, 2026-11-08,
# docs/superpowers/plans/2026-11-08-hizli-okuma.md §1).
#
# Birim harf/dk'dır (boşluk dışı karakter): Türkçe eklemeli olduğu için sözcük/dk
# dilden dile adil karşılaştırılmaz (Brysbaert 2019). Satırı istemci yazar: bir
# bölüm OTURUMU (url + rastgele `oturum_id`) biter, yarım bırakılır ya da sekme
# gizlenir. Aynı oturumun her gönderimi tek satırı günceller; aynı bölümün ikinci
# okuması ayrı satırdır. Geçerliliği sunucu yeniden hesaplar: istemci "geçersiz"
# derse geçerli yapılmaz, "geçerli" derse sınırlar yine denetlenir.
# ---------------------------------------------------------------------------
_OTURUM_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
KIPLER = ("serbest", "tempo")
EN_AZ_HARF = 1500
EN_AZ_MS = 60_000
HIZ_ALT, HIZ_UST = 400, 5000  # harf/dk; dışı göz gezdirme ya da hata
GUNLUK_GUN = 30


def _hiz_connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reading_speed (
            oturum_id TEXT NOT NULL UNIQUE,
            day TEXT NOT NULL,
            book_slug TEXT NOT NULL,
            url TEXT NOT NULL,
            mode TEXT NOT NULL,
            chars INTEGER NOT NULL,
            words INTEGER NOT NULL,
            active_ms INTEGER NOT NULL,
            valid INTEGER NOT NULL,
            ts REAL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reading_speed_day ON reading_speed(day)")
    # Öbek modunda okunan oturumun öbek boyu (Adım C; 0 = öbeksiz): kişisel hıza
    # yalnız 0 girer, öbekli hız boya göre ayrı karşılaştırılır.
    db.ensure_column(conn, "reading_speed", "obek", "obek INTEGER NOT NULL DEFAULT 0")
    return conn


def _hdk(chars: int, active_ms: int) -> float:
    return chars * 60_000 / active_ms if active_ms > 0 else 0.0


def gecerli_mi(chars: int, active_ms: int, istemci_gecerli: bool) -> bool:
    if not istemci_gecerli or chars < EN_AZ_HARF or active_ms < EN_AZ_MS:
        return False
    return HIZ_ALT <= _hdk(chars, active_ms) <= HIZ_UST


def log_speed(oturum_id: str, day: str, book_slug: str, url: str, mode: str,
              chars: int, words: int, active_ms: int, istemci_gecerli: bool,
              obek: int = 0) -> dict | None:
    """Oturumu yaz ya da güncelle. Dönüş `{"gecerli": bool}`; geçersiz girdi/DB meşgul: None."""
    if (not _OTURUM_RE.match(oturum_id or "") or not _DAY_RE.match(day or "")
            or mode not in KIPLER or not book_slug or not url):
        return None
    valid = gecerli_mi(chars, active_ms, istemci_gecerli)
    import time

    try:
        conn = _hiz_connect()
        try:
            conn.execute(
                "INSERT INTO reading_speed (oturum_id, day, book_slug, url, mode, chars, words,"
                " active_ms, valid, ts, obek) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(oturum_id) DO UPDATE SET day=excluded.day, mode=excluded.mode,"
                " chars=excluded.chars, words=excluded.words, active_ms=excluded.active_ms,"
                " valid=excluded.valid, ts=excluded.ts, obek=excluded.obek",
                (oturum_id, day, book_slug, url, mode, chars, words, active_ms, int(valid),
                 time.time(), max(0, min(6, int(obek or 0)))),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None  # best-effort: okuma akışı bozulmasın
    return {"gecerli": valid}


def _ozet(satirlar: list) -> dict | None:
    """(chars, words, active_ms) satırlarından ortanca harf/dk ve aynı kümenin sözcük karşılığı."""
    if not satirlar:
        return None
    hdk = statistics.median(_hdk(c, ms) for c, _w, ms in satirlar)
    harf = sum(c for c, _w, _ms in satirlar)
    sozcuk = sum(w for _c, w, _ms in satirlar)
    return {"hdk": round(hdk), "sdk": round(hdk * sozcuk / harf) if harf and sozcuk else None}


def _suzgec(son: list) -> list:
    """Göz gezdirme süzgeci: n >= 3 ise ortancanın 2 katından hızlı oturum atılır."""
    if len(son) < 3:
        return son
    m = statistics.median(_hdk(c, ms) for c, _w, ms in son)
    return [s for s in son if _hdk(s[0], s[2]) <= 2 * m]


def _gun_ekle(day: str, gun: int) -> str:
    import datetime as dt

    return (dt.date.fromisoformat(day) + dt.timedelta(days=gun)).isoformat()


def speed_stats(day: str) -> dict:
    """Kişisel hız, başlangıç çizgisi, değişim, son 30 gün ve bugünkü pratik dakikası."""
    bos = {"kisisel_hiz": None, "ilk_hafta": None, "degisim": None,
           "gunluk": [], "bugun_dk": 0.0, "oturum_sayisi": 0, "obek_hizlari": {}}
    day = (day or "").strip()
    if not _DAY_RE.match(day):
        return bos
    conn = _hiz_connect()
    try:
        serbest = conn.execute(
            "SELECT chars, words, active_ms, day FROM reading_speed"
            " WHERE valid = 1 AND mode = 'serbest' AND obek = 0 ORDER BY ts").fetchall()
        obekli = conn.execute(
            "SELECT chars, words, active_ms, obek FROM reading_speed"
            " WHERE valid = 1 AND mode = 'serbest' AND obek > 0 ORDER BY ts").fetchall()
        bugun_ms = conn.execute(
            "SELECT COALESCE(SUM(active_ms), 0) FROM reading_speed WHERE day = ?",
            (day,)).fetchone()[0]
        bas = _gun_ekle(day, -(GUNLUK_GUN - 1))
        pencere = conn.execute(
            "SELECT day, mode, chars, words, active_ms FROM reading_speed"
            " WHERE valid = 1 AND obek = 0 AND day BETWEEN ? AND ? ORDER BY day",
            (bas, day)).fetchall()
    finally:
        conn.close()

    kisisel = _ozet(_suzgec([(c, w, ms) for c, w, ms, _d in serbest[-10:]]))
    boylar: dict[int, list] = {}
    for c, w, ms, boy in obekli:
        boylar.setdefault(boy, []).append((c, w, ms))
    obek_hizlari = {str(boy): {**_ozet(_suzgec(s[-10:])), "n": len(s)}
                    for boy, s in sorted(boylar.items())}

    ilk = None
    if len(serbest) >= 5:
        ilk = {**_ozet([(c, w, ms) for c, w, ms, _d in serbest[:5]]),
               "n": 5, "bas_gun": serbest[0][3]}
    degisim = None
    if ilk and kisisel and len(serbest) >= 10 and ilk["hdk"]:
        degisim = round(kisisel["hdk"] / ilk["hdk"] - 1, 3)

    gunler: dict[str, dict] = {}
    for d, mode, c, w, ms in pencere:
        gunler.setdefault(d, {"serbest": [], "tempo": []})[mode].append((c, w, ms))
    gunluk = []
    for d in sorted(gunler):
        s = _ozet(gunler[d]["serbest"])
        t = _ozet(gunler[d]["tempo"])
        gunluk.append({"gun": d, "hdk": s["hdk"] if s else None, "sdk": s["sdk"] if s else None,
                       "tempo_hdk": t["hdk"] if t else None})

    return {"kisisel_hiz": kisisel, "ilk_hafta": ilk, "degisim": degisim, "gunluk": gunluk,
            "bugun_dk": round(bugun_ms / 60_000, 1), "oturum_sayisi": len(serbest),
            "obek_hizlari": obek_hizlari}
