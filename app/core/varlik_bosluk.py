"""Varlık grafiğinde EKSİK bağları bul (kaçırma oranını düşürmek için).

Neden var (2026-10-07, kullanıcı: "eski bölümlerde hiçbir şeyin kaçmaması
gerekiyor"): bölüm başına çıkarım (`varlik_cikarim`) tek bölümün metnine bakar ve
ölçülen verimi bölüm başına 1-2 bağdır — kitapta söylenen her ilişkiyi yakalamaz.
Kullanıcı eski bölümleri yeniden okuyamaz; kaçanı sistem bulmalı.

İki deterministik aday üretici + hedefli soru:

  * **Ortak geçiş (co-occurrence):** iki varlık kitapta sık sık AYNI CÜMLEDE
    geçiyor ama aralarında hiç bağ yoksa, büyük olasılıkla kaçırılmış bir ilişki
    vardır. Kanıt tek bölümden değil kitabın TAMAMINDAN toplanır; bölüm başına
    çıkarımın göremediği, bölümlere dağılmış ilişkiyi bu görür.
  * **Şema tamlığı:** türü belli olan varlığın taşıması gereken bağ eksikse
    (her Anının bir sahibi, her Yankının bir efendisi olmalı) hedefli sorulur. Bu
    aynı zamanda ölçülebilir bir ilerleme ölçütüdür.

Hedefli soruda kanıt, VERİLEN cümlelerden biri olmak ZORUNDADIR (birebir); model
kitabın dışından bilgi getiremez. İlk bölüm o cümlenin bölümüdür (spoiler).

Bu modül API çağırmaz; soru `varlik_cikarim.cift_sor` ile yapılır.
"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache

from . import cache, glossary, translate, varlik_grafigi

_CUMLE = re.compile(r"(?<=[.!?…])\s+|\n+")
ORNEK_CUMLE_SINIRI = 6
EN_AZ_ORTAK = 3


@lru_cache(maxsize=4096)
def _desen(kaynak: str) -> re.Pattern:
    return translate._term_regex(kaynak)


def _asil_eslemesi(book_slug: str) -> dict[str, str]:
    """Takma ad / Gerçek Ad -> asıl kişi (yalnız güvenilir kaynaklı bağlar)."""
    asil: dict[str, str] = {}
    for b in varlik_grafigi.baglar(book_slug, durumlar=("onaylandi",)):
        if b["iliski"] in ("takma_adi", "gercek_adi"):
            asil[b["hedef_kimlik"]] = b["kaynak_kimlik"]
    return asil


def ortak_gecisler(book_slug: str, en_az: int = EN_AZ_ORTAK, korpus: str | None = None) -> list[dict]:
    """Bağı OLMAYAN ve en az `en_az` cümlede birlikte geçen varlık çiftleri.

    Döner (sıklığa göre azalan): [{"a", "b", "a_kimlik", "b_kimlik", "sayi",
    "ilk_bolum", "ornekler": [(bölüm, cümle), ...]}]. Örnekler EN ERKEN bölümlerden
    seçilir: soru sonucu yazılan bağın `ilk_bolum`u gerçek ilk kuruluşa yakın olsun.
    """
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    if korpus is None:
        _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    kategoriler = varlik_grafigi.kategori_kimlikleri(book_slug, cozucu, korpus)
    asil = _asil_eslemesi(book_slug)
    sozluk = glossary.ceviri_sozlugu(book_slug)
    var_olan = set()
    for b in varlik_grafigi.baglar(book_slug, durumlar=("aday", "onaylandi", "reddedildi")):
        x, y = asil.get(b["kaynak_kimlik"], b["kaynak_kimlik"]), asil.get(b["hedef_kimlik"], b["hedef_kimlik"])
        var_olan.add(frozenset((x, y)))
    sayac: dict[frozenset, int] = defaultdict(int)
    ornek: dict[frozenset, list] = defaultdict(list)
    ilk: dict[frozenset, int] = {}
    for bolum in sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0):
        metin = bolum["source"] or ""
        no = bolum["chapter_no"]
        gecen = []
        for ad in translate.metinde_gecen_terimler(sozluk, metin):
            kimlik = cozucu.coz(ad)
            if kimlik and kimlik not in kategoriler:
                gecen.append((ad, asil.get(kimlik, kimlik)))
        if len(gecen) < 2:
            continue
        for cumle in _CUMLE.split(metin):
            if len(cumle) < 12:
                continue
            # ANMA = eşleşen metin parçası. Parçaları ÇAKIŞAN iki varlık aynı anmadır
            # (ölçülen gürültü: "Master Jet" içinde `Jet`, "Stone Saint" içinde `Saint`,
            # `Fire Keeper` ~ "Fire Keepers"); yalnız AYRIK anmalar çift oluşturur.
            anmalar: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for ad, k in gecen:
                for m in _desen(ad).finditer(cumle):
                    anmalar[k].append(m.span())
            if len(anmalar) < 2:
                continue
            icinde_l = sorted(anmalar)
            for i, x in enumerate(icinde_l):
                for y in icinde_l[i + 1:]:
                    if not any(
                        a1 >= b2 or b1 >= a2
                        for a1, a2 in anmalar[x] for b1, b2 in anmalar[y]
                    ):
                        continue  # her anmaları çakışıyor: aynı söz
                    cift = frozenset((x, y))
                    if cift in var_olan:
                        continue
                    sayac[cift] += 1
                    ilk.setdefault(cift, no)
                    if len(ornek[cift]) < ORNEK_CUMLE_SINIRI:
                        ornek[cift].append((no, cumle.strip()[:400]))
    out = []
    for cift, n in sayac.items():
        if n < en_az:
            continue
        x, y = sorted(cift)
        out.append({
            "a": cozucu.kaynak(x), "b": cozucu.kaynak(y), "a_kimlik": x, "b_kimlik": y,
            "sayi": n, "ilk_bolum": ilk[cift], "ornekler": ornek[cift],
        })
    out.sort(key=lambda c: -c["sayi"])
    return out


# Şema: türü belirleyen bağ -> taşıması gereken GELEN bağ (sahiplik).
SEMA = {
    # "X turu Memory" olan X'in bir sahibi (anisi) olmalı.
    "Memory": "anisi", "Memories": "anisi",
    "Echo": "yanki", "Echoes": "yanki",
    "Attribute": "niteligi",
}


def sema_eksikleri(book_slug: str) -> list[dict]:
    """Türü belli olup sahiplik bağı OLMAYAN varlıklar: [{"kimlik", "kaynak", "beklenen"}].

    Ölçüt grafikten: `X -> turu -> Memory` varsa X'e gelen bir `anisi` bağı beklenir.
    Sahipsiz Anı, okurun "bu kimin?" sorusuna cevapsız kalır."""
    baglar = varlik_grafigi.baglar(book_slug)
    gelen: dict[str, set[str]] = defaultdict(set)
    for b in baglar:
        gelen[b["hedef_kimlik"]].add(b["iliski"])
    out, gorulen = [], set()
    for b in baglar:
        beklenen = SEMA.get(b["hedef"]) if b["iliski"] == "turu" else None
        if beklenen and beklenen not in gelen[b["kaynak_kimlik"]] and b["kaynak_kimlik"] not in gorulen:
            gorulen.add(b["kaynak_kimlik"])
            out.append({"kimlik": b["kaynak_kimlik"], "kaynak": b["kaynak"], "beklenen": beklenen})
    return out


def varlik_cumleleri(book_slug: str, kaynak: str, sinir: int = ORNEK_CUMLE_SINIRI) -> list[tuple[int, str]]:
    """Bir varlığın geçtiği EN ERKEN cümleler (şema sorusu için kanıt havuzu)."""
    out = []
    desen = _desen(kaynak)
    for bolum in sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0):
        for cumle in _CUMLE.split(bolum["source"] or ""):
            if len(cumle) >= 12 and desen.search(cumle):
                out.append((bolum["chapter_no"], cumle.strip()[:400]))
                if len(out) >= sinir:
                    return out
    return out
