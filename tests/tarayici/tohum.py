"""Tarayıcı testleri için veri tohumlama (çekirdek modüllerle doğrudan SQLite).

Metinler UYDURMADIR ve kısadır: testler gerçek bir romanın metnine ihtiyaç
duymaz, yalnız yapıya (paragraf sayısı, hizalı kaynak, künye) ihtiyaç duyar.
"""
from __future__ import annotations

import sqlite3

from core import cache, db, glossary, library

TABLOLAR = (
    "chapters", "books", "aliases", "glossary", "reading_log", "settings",
    "jobs", "kullanim", "sozluk_gecmis", "sozluk_red", "sozluk_yazim",
    "ceviri_arsivi",
)

TR = [
    "Kaan fenerini yaktı ve dar geçidin sonundaki kapıya baktı; kapı yarı açıktı.",
    "Arkasından gelen Mira, taş duvarlardaki işaretleri parmağıyla izledi.",
    "Gümüş Kule'nin çanı uzaktan üç kez çaldı ve ikisi de olduğu yerde durdu.",
    "Kaan sessizce ilerledi; zemindeki tozun üstünde taze ayak izleri vardı.",
]
EN = [
    "Kaan lit his lantern and looked at the door at the end of the narrow passage; it was half open.",
    "Mira, walking behind him, traced the marks on the stone walls with her finger.",
    "The bell of the Silver Tower rang three times in the distance, and both of them froze.",
    "Kaan moved forward quietly; there were fresh footprints on the dust covering the floor.",
]


def temizle() -> None:
    """Sunucunun DB'sindeki bütün satırları sil (tablo yoksa atla)."""
    conn = sqlite3.connect(db.db_path(), timeout=10)
    try:
        for tablo in TABLOLAR:
            try:
                conn.execute(f"DELETE FROM {tablo}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def bolum_url(slug: str, no: int) -> str:
    return f"https://ornek.test/{slug}/chapter-{no}"


def kitap(
    slug: str = "gumus-kule",
    baslik: str = "Gumus Kule",
    bolum_sayisi: int = 2,
    konum: int | None = 1,
    kunye: bool = True,
    adlar: list[str] | None = None,
) -> list[str]:
    """Kitap + ardışık zincirli bölümler kur. Bölüm URL'lerini döndürür.

    `adlar` varsayılan BOŞ: önbellek isabeti `detected_names`'i sözlüğe yeniden
    işler (`pipeline._finalize_cached`) ve kütüphane açılınca otomatik
    çevrimdışı tarama bölümleri GET'lediği için sözlük testleri kendiliğinden
    satır kazanırdı.
    """
    urller = [bolum_url(slug, n) for n in range(1, bolum_sayisi + 1)]
    for i, url in enumerate(urller):
        no = i + 1
        cache.save_chapter(url, {
            "book_slug": slug,
            "book_title": baslik,
            "title": f"Chapter {no}",
            "chapter_no": no,
            "translation": "\n\n".join(TR),
            "source": "\n\n".join(EN),
            "next_url": urller[i + 1] if i + 1 < len(urller) else None,
            "prev_url": urller[i - 1] if i else None,
            "detected_names": list(adlar or []),
            "chunk_count": 1,
            "engine": "gemini" if kunye else None,
            "model": "gemini-3.6-flash" if kunye else None,
            "added_terms": {"Silver Tower": "Gümüş Kule"} if kunye and no == 1 else None,
            "glossary_leaks": {},
            "ingilizce_kalinti": {},
        })
    konum_url = urller[konum - 1] if konum else urller[0]
    library.upsert_book(slug, baslik, konum_url, f"Chapter {konum or 1}", konum or 1)
    return urller


def sozluk(slug: str, kayitlar: dict[str, str], kosullar: dict[str, str] | None = None) -> None:
    for kaynak, karsilik in kayitlar.items():
        glossary.set_term(slug, kaynak, karsilik)
    for kaynak, kosul in (kosullar or {}).items():
        glossary.set_kosul(slug, kaynak, kosul)
