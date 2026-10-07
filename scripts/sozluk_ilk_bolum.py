"""`first_chapter`'ı BOŞ sözlük kayıtlarına kaynak metinden ilk geçiş bölümünü yaz.

Neden var (Faz 1A, 2026-10-07): sözlük ucu artık okuma konumundan SONRAKİ kayıtları
gizliyor (`glossary.gorunur_sozluk`), ama eski kayıtların çoğunda `first_chapter`
yok ve onlar "bilinmiyor" diye görünür kalıyor. Bu araç değeri UYDURMAZ, kaynaktan
TÜRETİR: kaydın (sözlükle aynı eşleşme kuralıyla) geçtiği en erken ÖNBELLEKLİ bölüm.

Güvenli yön: önbellekte boşluk varsa bulunan bölüm gerçek ilk geçişten GEÇ olabilir,
ERKEN olamaz — kayıt gerekenden uzun gizli kalır, spoiler sızmaz. Hiç geçmeyen kayıt
(elle eklenmiş, kaynakta yok) BOŞ bırakılır.

Kullanım: python scripts/sozluk_ilk_bolum.py --kitap X [--uygula]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import cache, glossary, library, translate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--uygula", action="store_true")
    args = ap.parse_args()
    slug = library.resolve_slug(args.kitap)
    bos = [r for r in glossary.get_glossary_rows(slug) if r.get("first_chapter") is None]
    bolumler = sorted(cache.kaynak_bolumleri(slug), key=lambda b: b["chapter_no"] or 0)
    sozluk = {r["source"]: r["target"] for r in bos}
    tekili = translate._tekili_kayitli_cogullar(glossary.get_glossary(slug))
    bulunan: dict[str, int] = {}
    for b in bolumler:
        if b["chapter_no"] is None or not b["source"]:
            continue
        kalan = {s: t for s, t in sozluk.items() if s not in bulunan}
        if not kalan:
            break
        for s, t in kalan.items():
            if translate._terim_metinde(s, t, b["source"], tekili):
                bulunan[s] = b["chapter_no"]
    print(f"{slug}: first_chapter boş {len(bos)} kayıt; kaynaktan türetilebilen {len(bulunan)}, "
          f"kaynakta hiç geçmeyen {len(bos) - len(bulunan)} (boş kalır)")
    for s, n in sorted(bulunan.items(), key=lambda x: x[1])[:15]:
        print(f"  {n:5}  {s}")
    if not args.uygula:
        print("KURU — yazmak için: --uygula")
        return 0
    conn = glossary._connect()
    try:
        for s, n in bulunan.items():
            conn.execute(
                "UPDATE glossary SET first_chapter = ? WHERE book_slug = ? AND source = ? AND first_chapter IS NULL",
                (n, slug, s),
            )
        conn.commit()
    finally:
        conn.close()
    print(f"{len(bulunan)} kayda yazıldı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
