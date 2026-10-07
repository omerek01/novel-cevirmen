"""Çift anlamlı adların ÇEVİRİ SONRASI denetimi — önbellekteki bölümler (API'siz).

Neden var (2026-10-07): koşullu sözlük kayıtları (`Saint -> Aziz [KOŞUL: yalnız rütbe]`)
uyum denetiminin DIŞINDADIR; gölgenin adı "Aziz" diye çevrildiğinde hiçbir sayıya
yansımıyordu. `anlam_ayirici` kesin sınıflanan paragrafları bulur, bu araç önbellekteki
hizalı çevirilerde beklenen karşılığın geçip geçmediğini sayar. Genel: tanımlar her
kitapta `varlik_grafigi.ceviri_anlamlari`'dan (sözlükte "bu bir ad" işaretli ek anlamlar).

Kullanım:
  python scripts/anlam_denetle.py --kitap shadow-slave            # özet (modele göre)
  python scripts/anlam_denetle.py --kitap shadow-slave --ayrinti  # bölüm listesi
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import anlam_ayirici, cache, library, varlik_grafigi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--ayrinti", action="store_true")
    args = ap.parse_args()
    slug = library.resolve_slug(args.kitap)
    anlamlar = varlik_grafigi.ceviri_anlamlari(slug)
    if not anlamlar:
        print("Bu kitapta 'ad' diye işaretlenmiş çift anlamlı kayıt yok.")
        return 0
    print("denetlenen kayıtlar:", ", ".join(a["kayit"] for a in anlamlar))
    model_bolum: Counter = Counter()
    model_ihlalli: Counter = Counter()
    sinif: Counter = Counter()
    ihlalli: list[tuple] = []
    olculemeyen = 0
    for b in cache.kaynak_bolumleri(slug):
        if not b.get("translation"):
            continue
        en = [p.strip() for p in (b["source"] or "").split("\n\n") if p.strip()]
        tr = [p.strip() for p in (b["translation"] or "").split("\n\n") if p.strip()]
        if len(en) != len(tr):
            olculemeyen += 1
            continue
        model = (cache.get_chapter(b["url"]) or {}).get("model") or "?"
        sonuc = anlam_ayirici.anlam_ihlalleri(en, tr, anlamlar, b["chapter_no"])
        isaretli = any(
            anlam_ayirici.paragraf_isaretleri(en, a["kayit"], b["chapter_no"], a["ayirici"]) for a in anlamlar
        )
        if not isaretli:
            continue
        model_bolum[model] += 1
        if sonuc:
            model_ihlalli[model] += 1
            n = sum(len(v) for v in sonuc.values())
            for v in sonuc.values():
                for x in v:
                    sinif[x["sinif"]] += 1
            ihlalli.append((b["chapter_no"], model, n))
    print(f"\nkesin sınıflanmış geçişi olan bölüm: {sum(model_bolum.values())}  "
          f"(hizasız, ölçülemeyen: {olculemeyen})")
    print(f"ihlalli bölüm: {len(ihlalli)}  ihlal türü: {dict(sinif)} "
          "(anlam = ad Türkçeleşmiş, taban = asıl karşılık yazılmamış)")
    print("\nmodele göre (ihlalli / denetlenen):")
    for m, n in model_bolum.most_common():
        print(f"  {model_ihlalli[m]:4} / {n:<4} {m}")
    if args.ayrinti:
        print("\nihlalli bölümler (bölüm, model, ihlalli paragraf):")
        for no, m, n in sorted(ihlalli):
            print(f"  #{no:<5} {n:3}  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
