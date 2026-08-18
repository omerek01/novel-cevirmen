"""Kitap başına sözlük (glossary) — terim tutarlılığı için kalıcı eşleme.

Eşleme: kaynak (İngilizce terim) -> karşılık (nasıl yazılsın). Karakter isimleri
çeviri sırasında otomatik eklenir; kullanıcı kendi terimlerini ekleyip düzenler.
chapters.db ile aynı dosyada ayrı bir tabloda tutulur.
"""
from __future__ import annotations

import re
import sqlite3

from . import db


def _connect() -> sqlite3.Connection:
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS glossary (
            book_slug TEXT,
            source TEXT,
            target TEXT,
            PRIMARY KEY (book_slug, source)
        )
        """
    )
    return conn


def get_glossary(book_slug: str) -> dict[str, str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT source, target FROM glossary WHERE book_slug = ? "
            "ORDER BY source COLLATE NOCASE",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: row[1] for row in rows}


def all_terms(book_slug: str | None = None) -> list[tuple[str, str, str]]:
    """Tüm kitapların (ya da tek kitabın) kayıtları: (slug, kaynak, karşılık).

    Bakım aracı için (`scripts/sozluk_gozden_gecir.py`): kitap-başına `get_glossary`
    slug listesini bilmeyi gerektirirdi, sözlükte ise kütüphanede artık olmayan
    slug'lar da bulunabiliyor.
    """
    conn = _connect()
    try:
        sorgu = "SELECT book_slug, source, target FROM glossary"
        parametre: tuple = ()
        if book_slug:
            sorgu += " WHERE book_slug = ?"
            parametre = (book_slug,)
        rows = conn.execute(sorgu + " ORDER BY book_slug, source", parametre).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def set_term(book_slug: str, source: str, target: str | None) -> None:
    source = (source or "").strip()
    if not source:
        return
    target = (target or "").strip() or source  # boş karşılık = aynen koru
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO glossary (book_slug, source, target) VALUES (?, ?, ?)",
            (book_slug, source, target),
        )
        conn.commit()
    finally:
        conn.close()


def delete_term(book_slug: str, source: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM glossary WHERE book_slug = ? AND source = ?",
            (book_slug, source),
        )
        conn.commit()
    finally:
        conn.close()


# Yazım varyantı ayırıcıları. Aynı özel ad metinde "Ore Empire", "OreEmpire",
# "Ore-Empire" diye geçebiliyor; bunlar TEK terimdir.
_FOLD_SEP_RE = re.compile(r"[\s\-_'’.·]+")


def fold_term(name: str) -> str:
    """Terimi yazım varyantından bağımsız KARŞILAŞTIRMA anahtarına indirger.

    ``Ore Empire`` · ``OreEmpire`` · ``ore-empire`` · ``ORE  EMPIRE`` → ``oreempire``.

    Yalnız karşılaştırma içindir; sözlükte SAKLANAN anahtar `normalize_source`
    çıktısıdır (kullanıcı ekranda okunaklı yazımı görmeli). Bu ayrım olmadan aynı
    ad iki satır olur ve karşılıkları ayrışır.
    """
    return _FOLD_SEP_RE.sub("", (name or "").strip()).casefold()


def normalize_source(name: str) -> str:
    """Terimi sözlük anahtarı hâline getir: çevresel noktalama + iyelik eki atılır.

    Model bazen ismi cümledeki çekimli hâliyle döndürüyor (``Sunny's``, ``"Nephis"``).
    Kök hâle indirgemezsek aynı karakter sözlükte iki satır olur ve karşılıkları
    ayrışır. Çeviri tarafı eki kendisi getirdiğinden anahtar kök olmalı.
    """
    term = (name or "").strip().strip("\"'“”‘’()[]{}.,;:!?")
    for suffix in ("'s", "’s", "s'", "s’"):
        if len(term) > len(suffix) + 1 and term.endswith(suffix):
            return term[: -len(suffix)].strip()
    return term


def merge_terms(book_slug: str, mapping: dict[str, str] | None) -> dict[str, str]:
    """Otomatik algılanan terimleri (kaynak -> karşılık) ekle.

    `INSERT OR IGNORE`: kullanıcının elle yazdığı karşılık ASLA ezilmez — sözlük
    kullanıcınındır, otomatik algılama yalnız BOŞLUĞU doldurur. Anahtar
    `normalize_source` ile kök hâline indirilir (çekim eki/noktalama atılır) ve
    "zaten kayıtlı mı" kararı `fold_term` ile verilir (yazım varyantı sayılmaz),
    yoksa aynı terim iki satır olur ve karşılıkları ayrışır.

    Döner: FİİLEN eklenenler (zaten kayıtlı olanlar hariç) — okuyucudaki bölüm
    künyesi bunu gösterir. Mevcut anahtarlar yazımdan ÖNCE aynı bağlantıda okunur;
    `executemany` + `rowcount` bu işe yaramaz (SQLite yalnız toplam sayı verir,
    hangi satırın eklendiğini değil).
    """
    if not mapping:
        return {}
    seen: dict[str, str] = {}
    gorulen: set[str] = set()
    for raw_kaynak, raw_hedef in mapping.items():
        term = normalize_source(raw_kaynak)
        hedef = (raw_hedef or "").strip() or term  # boş karşılık = aynen koru
        if not term:
            continue
        anahtar = fold_term(term)
        if anahtar not in gorulen:  # aynı yanıtta "Ore Empire" + "OreEmpire" gelebilir
            gorulen.add(anahtar)
            seen[term] = hedef
    if not seen:
        return {}
    conn = _connect()
    try:
        # Karşılaştırma `fold_term` üzerinden: kayıtlı terimin YAZIM VARYANTI yeni
        # satır açmamalı ("Ore Empire" varken "OreEmpire" ikinci kayıt olurdu ve
        # karşılıkları ayrışırdı).
        mevcut = {
            fold_term(r[0])
            for r in conn.execute(
                "SELECT source FROM glossary WHERE book_slug = ?", (book_slug,)
            )
        }
        eklenecek = {k: h for k, h in seen.items() if fold_term(k) not in mevcut}
        if eklenecek:
            conn.executemany(
                "INSERT OR IGNORE INTO glossary (book_slug, source, target) "
                "VALUES (?, ?, ?)",
                [(book_slug, k, h) for k, h in eklenecek.items()],
            )
            conn.commit()
        return eklenecek
    finally:
        conn.close()


def merge_names(book_slug: str, names: list[str] | None) -> dict[str, str]:
    """Otomatik algılanan İNGİLİZCE KALACAK adları ekle (yalnız KARAKTER adları).

    Lonca/yer gibi diğer özel adlar Türkçe'ye çevrilir ve `merge_terms` ile
    karşılığıyla yazılır — İngilizce kalan tek sınıf kişi adlarıdır.


    Karşılık = kaynağın kendisi (`X -> X`): çeviride İngilizce yazımıyla durur,
    yalnız Türkçe eki alır. Döner: fiilen eklenenler.
    """
    return merge_terms(book_slug, {ad: ad for ad in (names or []) if ad})
