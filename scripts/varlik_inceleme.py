"""Varlık grafiğinin MODEL bağlarını incele / kararları uygula (bakım aracı).

İş akışı (2026-10-07, kullanıcı: "bağları hepsini incele"):
  1. `--disa aday.json`   — inceleme bekleyen (aday) model bağlarını kanıtlarıyla dışa aktar.
  2. İnceleme (elle ya da Claude ile) bir karar dosyası üretir.
  3. `--uygula karar.json` — kararları yaz. Karar dosyası bağları KİMLİKLE tanımlar
     (`a_k`, `iliski`, `b_k`); sıra numarası kullanılmaz, çünkü çıkarım sürerken
     yeni bağ eklenir ve sıra kayardı.
  4. `--birlestir`        — onaylı takma ad / Gerçek Ad düğümlerindeki bağları asıl
     kişiye taşı (`varlik_grafigi.takma_adlari_birlestir`).

Karar türleri: `onay` (onaylandi) · `ret` (reddedildi — bir daha otomatik eklenmez)
· `duzelt` (ilişki türü yanlış: eski reddedilir, `yeni_iliski` ile elle eklenir) ·
`ters` (yön yanlış) · `ters_duzelt` (ikisi birden) · `belirsiz` (aday kalır).
Düzeltilen bağ kanıtını ve ilk bölümünü korur; kökeni `manual` olur (insan kararı).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import library, varlik_grafigi  # noqa: E402


def disa(slug: str, dosya: str) -> int:
    baglar = [
        b for b in varlik_grafigi.baglar(slug, durumlar=("aday",)) if b["origin"] == "model"
    ]
    Path(dosya).write_text(json.dumps([
        {"a_k": b["kaynak_kimlik"], "a": b["kaynak"], "iliski": b["iliski"], "b_k": b["hedef_kimlik"],
         "b": b["hedef"], "bolum": b["ilk_bolum"], "kanit": b["kanit"], "guven": b["guven"]}
        for b in baglar
    ], ensure_ascii=False), encoding="utf-8")
    return len(baglar)


def uygula(slug: str, kararlar: list[dict]) -> Counter:
    sayac: Counter = Counter()
    mevcut = {
        (b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"]): b
        for b in varlik_grafigi.baglar(slug, durumlar=("aday", "onaylandi", "reddedildi"))
    }
    for k in kararlar:
        anahtar = (k["a_k"], k["iliski"], k["b_k"])
        b = mevcut.get(anahtar)
        if b is None:
            sayac["bulunamadi"] += 1
            continue
        karar = k["karar"]
        if karar == "belirsiz":
            sayac["belirsiz"] += 1
            continue
        if karar == "onay":
            varlik_grafigi.bag_durumu(slug, *anahtar, "onaylandi")
        else:
            varlik_grafigi.bag_durumu(slug, *anahtar, "reddedildi")
        if karar in ("duzelt", "ters", "ters_duzelt"):
            iliski = k.get("yeni_iliski") or k["iliski"]
            a, n = (k["b_k"], k["a_k"]) if karar.startswith("ters") else (k["a_k"], k["b_k"])
            varlik_grafigi.bag_ekle(slug, a, iliski, n, b["ilk_bolum"], b["kanit"], "manual", 1.0)
        sayac[karar] += 1
    return sayac


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--disa", help="aday model bağlarını bu dosyaya yaz")
    ap.add_argument("--uygula", help="karar dosyasını uygula")
    ap.add_argument("--birlestir", action="store_true", help="takma ad düğümlerini asıl kişiye taşı")
    args = ap.parse_args()
    slug = library.resolve_slug(args.kitap)
    if args.disa:
        print(f"{disa(slug, args.disa)} aday model bağı -> {args.disa}")
    if args.uygula:
        sayac = uygula(slug, json.loads(Path(args.uygula).read_text(encoding="utf-8")))
        print("kararlar:", dict(sayac))
    if args.birlestir:
        print(f"{varlik_grafigi.takma_adlari_birlestir(slug)} bağ asıl kişiye taşındı")
    durum = Counter((b["origin"], b["durum"]) for b in varlik_grafigi.baglar(
        slug, durumlar=("aday", "onaylandi", "reddedildi")))
    print("grafik:", dict(durum))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
