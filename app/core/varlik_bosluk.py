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
ADAY_CUMLE_SINIRI = 60  # örnek seçimi için çift başına saklanan en erken cümleler

# İki anma arasında yalnız bu bağlayıcı varsa ikisi TEK bir adın parçasıdır
# ("Mantle of the Underworld", "Maiden of War", "Sunny's Shadow" değil — iyelik
# bir kişiye bağlanınca ilişkidir, ama iki sözlük parçası arasındaki iyelik çoğunlukla
# bileşik addır). Ölçülen (2026-10-07): ilk 438 çiftin başı bu gürültüydü
# (`Underworld <-> Mantle` 108, `War <-> Maiden` 84) ve model haklı olarak boş döndü.
_BITISIK = re.compile(r"^\s*(?:of(?:\s+the)?|['’]s|the)?\s*$", re.IGNORECASE)
BILESIK_ORANI = 0.5  # ortak geçişlerin en az bu kadarı bitişikse çift bileşik addır

# İLİŞKİ söyleyen cümlelerin ipuçları. Örnekler eskiden yalnız EN ERKEN cümlelerdi
# ve bunlar çoğunlukla aynı sahnede geçmeyi gösterip ilişkiyi söylemiyordu (ölçülen:
# `Sunny | Jet` gibi bariz çiftlerde bile model "açıkça söylenmiyor" deyip boş döndü).
_IPUCU = re.compile(
    r"\b(?:teacher|mentor|student|disciple|apprentice|friend|companion|cohort|ally|allies|"
    r"enemy|enemies|rival|brother|sister|father|mother|son|daughter|uncle|aunt|cousin|"
    r"wife|husband|lover|clan|member|leader|led|lead|master|servant|slave|shadow|echo|"
    r"memory|attribute|aspect|ability|named|called|known as|true name|rank|killed|"
    r"slain|slew|belong(?:s|ed)?|lord|heir|legacy|team|guard|retainer|vassal|sovereign|"
    r"domain|citadel|home|ruler|ruled|owner|owned|summoned|created|form|evolved)\b",
    re.IGNORECASE,
)


def _bitisik_mi(cumle: str, x_spanlari: list, y_spanlari: list) -> bool:
    for a1, a2 in x_spanlari:
        for b1, b2 in y_spanlari:
            ara = cumle[a2:b1] if a2 <= b1 else cumle[b2:a1] if b2 <= a1 else None
            if ara is not None and _BITISIK.match(ara):
                return True
    return False


def _ornek_sec(adaylar: list[tuple[int, str]], sinir: int = ORNEK_CUMLE_SINIRI) -> list[tuple[int, str]]:
    """İpucu taşıyan cümleler önce (kronolojik), kalan yer en erkenlerle dolar."""
    ipuclu = [c for c in adaylar if _IPUCU.search(c[1])]
    secilen = ipuclu[:sinir]
    for c in adaylar:
        if len(secilen) >= sinir:
            break
        if c not in secilen:
            secilen.append(c)
    return sorted(secilen, key=lambda c: c[0] or 0)


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
    "ilk_bolum", "bilesik", "ornekler": [(bölüm, cümle), ...]}]. Örnekler önce İLİŞKİ
    İPUCU taşıyan cümlelerden, sonra en erkenlerden seçilir (`_ornek_sec`); bitişik
    anma cümleleri örnek olmaz. `bilesik` = ortak geçişlerin çoğunda iki ad tek bir
    adın parçası ("Mantle of the Underworld"): ilişki değil, EKSİK sözlük kaydıdır —
    soruya gitmez, ayrıca raporlanır.
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
    bitisik: dict[frozenset, int] = defaultdict(int)
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
            # BİLEŞİK AD İÇİNDEKİ anmalar ("Sanctuary of Noctis", "War Maiden") o
            # varlığı değil, bileşik adı anar; üçüncü bir varlıkla çift KURMAZ.
            # Ölçülen (2026-10-07): bileşik çift süzgecinden sonra bile listenin başı
            # `Sunny | Noctis` (75), `Sunny | Underworld`, `Sunny | War` idi — hepsi
            # Sunny'nin bileşik adın tamamıyla birlikte geçtiği cümleler.
            bilesik_anma: set[tuple[str, tuple[int, int]]] = set()
            for i, x in enumerate(icinde_l):
                for y in icinde_l[i + 1:]:
                    for sx in anmalar[x]:
                        for sy in anmalar[y]:
                            if _bitisik_mi(cumle, [sx], [sy]):
                                bilesik_anma.update(((x, sx), (y, sy)))
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
                    if _bitisik_mi(cumle, anmalar[x], anmalar[y]):
                        sayac[cift] += 1
                        ilk.setdefault(cift, no)
                        bitisik[cift] += 1
                        continue
                    serbest_x = [s for s in anmalar[x] if (x, s) not in bilesik_anma]
                    serbest_y = [s for s in anmalar[y] if (y, s) not in bilesik_anma]
                    if not serbest_x or not serbest_y:
                        continue  # biri yalnız bileşik adın parçası olarak geçiyor
                    sayac[cift] += 1
                    ilk.setdefault(cift, no)
                    if len(ornek[cift]) < ADAY_CUMLE_SINIRI:
                        ornek[cift].append((no, cumle.strip()[:400]))
    out = []
    for cift, n in sayac.items():
        if n < en_az:
            continue
        x, y = sorted(cift)
        out.append({
            "a": cozucu.kaynak(x), "b": cozucu.kaynak(y), "a_kimlik": x, "b_kimlik": y,
            "sayi": n, "ilk_bolum": ilk[cift], "bilesik": bitisik[cift] >= BILESIK_ORANI * n,
            "ornekler": _ornek_sec(ornek[cift]),
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


PROFIL_CUMLE_SINIRI = 40


def profil_cumleleri(book_slug: str, kaynak: str, sinir: int = PROFIL_CUMLE_SINIRI) -> list[tuple[int, str]]:
    """Bir varlığın PROFİL sorusu için cümleleri: ilişki İPUCU taşıyanlar önce, kitap
    boyunca kronolojik; yer kalırsa en erkenlerle dolar (`_ornek_sec`).

    Bileşik adın parçası olarak geçen anma sayılmaz ("Sanctuary of Noctis" içindeki
    `Noctis`): o cümle varlığın kendisini değil, başka bir adı anar."""
    desen = _desen(kaynak)
    sozluk = glossary.ceviri_sozlugu(book_slug)
    adaylar: list[tuple[int, str]] = []
    for bolum in sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0):
        metin = bolum["source"] or ""
        if not desen.search(metin):
            continue
        digerleri = [_desen(ad) for ad in translate.metinde_gecen_terimler(sozluk, metin)
                     if glossary.fold_term(ad) != glossary.fold_term(kaynak)]
        for cumle in _CUMLE.split(metin):
            if len(cumle) < 12:
                continue
            anmalar = [m.span() for m in desen.finditer(cumle)]
            if not anmalar:
                continue
            oteki = [m.span() for d in digerleri for m in d.finditer(cumle)]
            serbest = [s for s in anmalar
                       if not any(_bitisik_mi(cumle, [s], [o]) or (o[0] <= s[0] and s[1] <= o[1] and o != s)
                                  for o in oteki)]
            if serbest:
                adaylar.append((bolum["chapter_no"], cumle.strip()[:400]))
    # İpuçlu cümleler kitap boyunca EŞİT ARALIKLA seçilir: en erken 40'ı almak, uzun
    # süre geçen bir varlığın (Sunny) profilini ilk bölümlere hapsederdi.
    ipuclu = [c for c in adaylar if _IPUCU.search(c[1])]
    if len(ipuclu) > sinir:
        adim = len(ipuclu) / sinir
        return [ipuclu[int(i * adim)] for i in range(sinir)]
    return _ornek_sec(adaylar, sinir)
