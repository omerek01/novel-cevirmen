r"""Sözlük kayıtlarının KÖKEN CÜMLESİNİ geriye dönük doldurur (bakım aracı).

Köken cümlesi 2026-09-10'da eklendi ve ancak BUNDAN SONRA çevrilen bölümlerde
kendiliğinden doluyor. Kütüphanedeki kayıtların çoğu daha eski; bu araç onların
cümlesini ÖNBELLEKTEN çıkarır.

API ÇAĞIRMAZ ve siteye İNMEZ: kaydın `first_chapter` bölümü zaten çevrilmiş
hâlde önbellekte duruyor, cümle oradan `translate.cumle_bul` ile bulunuyor —
yani bedava ve tekrarlanabilir.

Mevcut cümleyi EZMEZ (`set_kaynak_cumle` yalnız boş olana yazar): köken "ilk
nerede gördük" sorusunun cevabıdır.

Kullanım (proje kökünden):
    .venv\Scripts\python.exe scripts\koken_cumle_doldur.py
    ... --uygula              # gerçekten yaz
    ... --slug shadow-slave   # yalnız bu kitap
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core import cache, glossary, library, translate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uygula", action="store_true", help="gerçekten yaz")
    ap.add_argument("--slug", help="yalnız bu kitap")
    a = ap.parse_args()

    kitaplar = [k["slug"] for k in library.list_books()]
    if a.slug:
        kitaplar = [s for s in kitaplar if s == a.slug]

    toplam_yazilan = toplam_aday = 0
    for slug in kitaplar:
        kayitlar = [
            r for r in glossary.get_glossary_rows(slug)
            if r.get("first_chapter") and not (r.get("kaynak_cumle") or "").strip()
        ]
        if not kayitlar:
            continue
        # Bölüm no -> url (önbellekteki bölüm listesi tek kaynak).
        no_url = {}
        for c in cache.list_chapters(slug):
            if c.get("chapter_no") is not None and c.get("url"):
                no_url.setdefault(int(c["chapter_no"]), c["url"])

        yazilan = 0
        # Aynı bölümü tekrar tekrar okumamak için bölüm metnini bir kez al.
        metin_onbellek: dict[int, str] = {}
        for r in kayitlar:
            no = int(r["first_chapter"])
            if no not in metin_onbellek:
                url = no_url.get(no)
                bolum = cache.get_chapter(url) if url else None
                metin_onbellek[no] = (bolum or {}).get("translation") or ""
            metin = metin_onbellek[no]
            if not metin:
                continue
            cumle = translate.cumle_bul(metin, r.get("target") or r["source"])
            if not cumle:
                continue
            if a.uygula and glossary.set_kaynak_cumle(slug, r["source"], cumle):
                yazilan += 1
            elif not a.uygula:
                yazilan += 1
        toplam_aday += len(kayitlar)
        toplam_yazilan += yazilan
        print(f"  {slug[:40]:40} aday={len(kayitlar):4}  cümle bulundu={yazilan}")

    fiil = "yazıldı" if a.uygula else "bulunurdu (KURU çalıştırma)"
    print(f"\ntoplam aday {toplam_aday} · {toplam_yazilan} {fiil}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
