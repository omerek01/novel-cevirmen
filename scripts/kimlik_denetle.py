"""Varlık KİMLİĞİ denetimi: takma ad kanıtı + yinelenen kayıt adayları (API'siz, YAZMAZ).

Neden var (Faz 1G, 2026-10-07): yanlış birleştirme, yinelenen düğümden DAHA
tehlikelidir — iki kişinin geçmişi geri dönülmez biçimde karışır. Bu yüzden bulanık
otomatik birleştirme YOK; bu araç insan incelemesi için kanıt toplar. Kitaba özel
bilgi (lore) kullanmaz, yalnız o kitabın sözlüğüne ve kaynak metnine bakar.

1) `--ad A --ad B ...`: verilen adların İKİLİ kimlik kanıtı. Aranan kalıplar metinde
   iki adın AYNI varlığı gösterdiğini söyleyenlerdir: açıklayıcı ek ("A, the B",
   "B, A"), "A, also known as B", "A was the B", "B — A". Yalnız aynı cümlede geçmek
   kanıt SAYILMAZ (birbirleriyle konuşan iki kişi de aynı cümlede geçer).
2) Yinelenen kayıt ADAYLARI (genel, kitaba özel değil): tekil/çoğul, araya giren
   "of (the)", son sözcüğün ortak kökü (Island/Isles). Çiftin Türkçe karşılıkları ve
   kaynakta kaç bölümde geçtikleri yanında yazılır.

Kullanım:
  python scripts/kimlik_denetle.py --kitap shadow-slave --ad Sunny --ad Sunless --ad "Lord of Shadows"
  python scripts/kimlik_denetle.py --kitap shadow-slave --yinelenen
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import cache, glossary, library, translate, varlik_grafigi  # noqa: E402

_CUMLE = re.compile(r"(?<=[.!?…])\s+|\n+")


def kimlik_kaliplari(a: str, b: str) -> list[re.Pattern]:
    """İki adın AYNI varlık olduğunu söyleyen kalıplar (iki yön)."""
    A, B = re.escape(a), re.escape(b)
    kaliplar = []
    for x, y in ((A, B), (B, A)):
        kaliplar += [
            re.compile(rf"\b{x}\b,\s+(?:the\s+)?{y}\b"),                       # "A, the B"
            re.compile(rf"\b{x}\b,?\s+(?:also\s+)?(?:known|called)\s+as\s+(?:the\s+)?{y}\b", re.I),
            re.compile(rf"\b{x}\b\s+(?:was|is|had been)\s+(?:the|also the)\s+{y}\b"),  # "A was the B"
            re.compile(rf"\b{x}\b\s*[—–-]\s*(?:the\s+)?{y}\b"),                # "A — the B"
        ]
    return kaliplar


def kimlik_kaniti(slug: str, adlar: list[str]) -> None:
    cozucu = varlik_grafigi.DugumCozucu(slug)
    bolumler = sorted(cache.kaynak_bolumleri(slug), key=lambda b: b["chapter_no"] or 0)
    gecis = Counter()
    ilk = {}
    for ad in adlar:
        d = translate._term_regex(ad)
        for b in bolumler:
            if d.search(b["source"] or ""):
                gecis[ad] += 1
                ilk.setdefault(ad, b["chapter_no"])
    print("== adlar (sözlükte mi, kaynakta kaç bölümde, ilk bölüm):")
    for ad in adlar:
        print(f"   {ad:22} sözlük={'evet' if cozucu.coz(ad) else 'YOK':4} bölüm={gecis[ad]:4} ilk={ilk.get(ad)}")
    print("== mevcut kimlik bağları:")
    kimlikler = {cozucu.coz(ad) for ad in adlar} - {None}
    for bg in varlik_grafigi.baglar(slug, durumlar=("aday", "onaylandi")):
        if bg["iliski"] in ("takma_adi", "gercek_adi", "unvani", "bicimi") and (
            bg["kaynak_kimlik"] in kimlikler or bg["hedef_kimlik"] in kimlikler
        ):
            print(f"   {bg['kaynak']} --{bg['iliski']}--> {bg['hedef']} @{bg['ilk_bolum']} ({bg['origin']}/{bg['durum']})")
    print("== ikili kimlik kanıtı (kalıp eşleşmesi; ilk bölüm, kaç cümle):")
    for a, b in itertools.combinations(adlar, 2):
        kaliplar = kimlik_kaliplari(a, b)
        sayi, ilk_kanit = 0, None
        for bl in bolumler:
            for cumle in _CUMLE.split(bl["source"] or ""):
                if any(k.search(cumle) for k in kaliplar):
                    sayi += 1
                    ilk_kanit = ilk_kanit or bl["chapter_no"]
        if sayi:
            print(f"   {a} <-> {b}: {sayi} cümle, ilk #{ilk_kanit}  -> İNCELENMELİ (birleştirme YAPILMADI)")
        else:
            print(f"   {a} <-> {b}: kalıp yok -> kanıt yetersiz, ilişkisiz bırakıldı")


def _tekil(s: str) -> str:
    s = s.casefold()
    return s[:-2] if s.endswith("es") and len(s) > 5 else s[:-1] if s.endswith("s") and len(s) > 3 else s


def yinelenen_adaylar(slug: str) -> list[tuple]:
    satirlar = glossary.get_glossary_rows(slug)
    kaynaklar = [r["source"] for r in satirlar]
    hedef = {r["source"]: r["target"] for r in satirlar}
    out = []
    for a, b in itertools.combinations(sorted(set(kaynaklar)), 2):
        ta, tb = a.split(), b.split()
        neden = None
        if len(ta) == len(tb) and ta[:-1] == tb[:-1] and _tekil(ta[-1]) == _tekil(tb[-1]) and ta[-1] != tb[-1]:
            neden = "tekil/çoğul"
        elif re.sub(r"\s+of(\s+the)?\s+", " ", a) == b or re.sub(r"\s+of(\s+the)?\s+", " ", b) == a:
            neden = "araya giren 'of'"
        elif (len(ta) == len(tb) >= 2 and ta[:-1] == tb[:-1] and ta[-1][:1].isupper() and tb[-1][:1].isupper()
              and ta[-1][:3].casefold() == tb[-1][:3].casefold() and ta[-1] != tb[-1]):
            neden = "son sözcük ortak kök"
        if neden:
            out.append((neden, a, hedef[a], b, hedef[b]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--ad", action="append", default=[])
    ap.add_argument("--yinelenen", action="store_true")
    args = ap.parse_args()
    slug = library.resolve_slug(args.kitap)
    if len(args.ad) >= 2:
        kimlik_kaniti(slug, args.ad)
    if args.yinelenen:
        adaylar = yinelenen_adaylar(slug)
        print(f"\n== yinelenen kayıt ADAYLARI ({len(adaylar)}) — hiçbiri birleştirilmedi:")
        for neden, a, ta, b, tb in adaylar:
            ayni = "aynı karşılık" if ta.casefold() == tb.casefold() else "FARKLI karşılık"
            print(f"   [{neden}] {a} -> {ta}  |  {b} -> {tb}   ({ayni})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
