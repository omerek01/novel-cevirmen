"""Sözlük karşılığı değişince eski çeviriyi YENİDEN ÇEVİRMEDEN güncelle (ölçüm aşaması).

Saf modül, API çağırmaz, veritabanına yazmaz. İki yol aynı makineyi kullanır:

* **Yerinde yazım** (`yeniden_yaz`): hizalı paragrafta eski karşılığın çekimli geçişini bul,
  eki `turkce_ek` ile soyut eklere ayır, yeni karşılığa göre yeniden kur.
* **Yer tutucu** (`sablon` / `doldur`): WTR-LAB'ın yaptığı gibi terimi metinde tutmak yerine
  ``⟦n|ekler|biçim⟧`` belirteci saklanır, okurken o anki sözlükten doldurulur. Türkçede
  belirteç EKİ DE taşır (soyut biçimde), çünkü ek köke göre değişir.

Bir geçiş yalnız şu koşullarda değiştirilir; aksi hâlde ``belirsiz`` sayılıp OLDUĞU GİBİ
bırakılır (yanlış değiştirmektense eski hâli bırakmak):

1. Hizalı İngilizce paragrafta kaynak terim geçiyor (aynı Türkçe sözcüğün sıradan anlamı
   değiştirilmesin) ve Türkçe geçiş sayısı İngilizce geçiş sayısını aşmıyor.
2. Ek tek anlamlı ayrışıyor ve yeni kökte tek yüzey veriyor (`turkce_ek.kur_tek`).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import turkce_ek
from .turkce_eslesme import _IYELIK, karsilik_deseni, tr_kucuk

BELIRTEC = re.compile(r"⟦(\d+)\|([^|⟧]*)\|([^⟧]*)⟧")


def kok(karsilik: str, kesmeli: bool = False) -> turkce_ek.Kok:
    """Karşılığın son sözcüğünden çekim kökü (iyelikli tamlama ayrımıyla)."""
    sozcukler = karsilik.split()
    son = tr_kucuk(sozcukler[-1].strip(turkce_ek.KESME))
    m = _IYELIK.search(son)
    iyelikli = len(sozcukler) > 1 and bool(m) and len(son) - len(m.group(1)) >= 2
    return turkce_ek.Kok(son, iyelikli=iyelikli, kesmeli=kesmeli)


def _tr_buyuk(metin: str) -> str:
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _bicim(yuzey: str, karsilik: str) -> str:
    """Harf biçimi: K = karşılığın kayıtlı yazımı, B = tamamı büyük, k = tamamı küçük,
    I = ilk harf büyük gerisi küçük (cümle başındaki küçük harfli kayıt)."""
    # Harflerin kendisine değil BÜYÜK/küçük kalıbına bakılır: kök yüzeyde değişmiş
    # olabilir (Kitap -> Kitabı, Yaratığı -> Yaratıkları). Son harf yumuşayabildiği için
    # karşılığın son harfi hariç.
    a, b = yuzey.replace(" ", ""), karsilik.replace(" ", "")
    n = max(1, len(b) - 1)
    if len(a) >= n and all(x.isupper() == y.isupper() for x, y in zip(a[:n], b[:n])):
        return "K"
    harfler = [c for c in yuzey if c.isalpha()]
    if len(harfler) > 1 and all(c.isupper() for c in harfler):
        return "B"
    if harfler and all(c.islower() for c in harfler):
        return "k"
    return "I"


def _kesme(yuzey: str) -> str:
    """Yüzeyde kullanılan kesme işareti ('' = kesmesiz). Düz/kıvrık ayrımı korunur."""
    son = re.split(r"\s+", yuzey)[-1]
    return next((k for k in turkce_ek.KESME if k in son), "")


def _uygula_bicim(metin: str, bicim: str) -> str:
    if bicim == "B":
        return _tr_buyuk(metin)
    if bicim == "k":
        return tr_kucuk(metin)
    if bicim == "I":
        k = tr_kucuk(metin)
        return _tr_buyuk(k[:1]) + k[1:]
    return metin


@dataclass
class Gecis:
    bas: int
    son: int
    yuzey: str
    ekler: tuple[tuple[str, ...], ...]   # ayrıştırma adayları (boş = ayrışmadı)
    kesmeli: bool


def gecisler(metin: str, karsilik: str) -> list[Gecis]:
    """Metindeki çekimli karşılık geçişleri ve eklerinin ayrıştırma adayları."""
    sonuc = []
    for m in karsilik_deseni(karsilik).finditer(metin):
        yuzey = m.group(0)
        son_sozcuk = re.split(r"\s+", yuzey)[-1]
        kesmeli = any(k in son_sozcuk for k in turkce_ek.KESME)
        adaylar = turkce_ek.ayristir(kok(karsilik, kesmeli), son_sozcuk)
        sonuc.append(Gecis(m.start(), m.end(), yuzey, adaylar, kesmeli))
    return sonuc


def _yeni_yuzey(g: Gecis, eski: str, yeni: str) -> str | None:
    son_sozcuk = re.split(r"\s+", g.yuzey)[-1]
    yeni_son = turkce_ek.kur_tek(kok(eski, g.kesmeli), son_sozcuk, kok(yeni, g.kesmeli))
    if yeni_son is None:
        return None
    return _yuzeye(yeni, yeni_son, _bicim(g.yuzey, eski), _kesme(g.yuzey))


def _yuzeye(karsilik: str, son_kucuk: str, bicim: str, kesme: str) -> str:
    """Küçük harfle kurulmuş son sözcüğü karşılığın yazımına ve yüzeyin biçimine oturt."""
    sozcukler = karsilik.split()
    # Kök küçük harfle kurulur; kayıtlı yazım (büyük harfi) geri konur.
    kok_yazim = sozcukler[-1].strip(turkce_ek.KESME)
    if son_kucuk.startswith(tr_kucuk(kok_yazim)):
        son_kucuk = kok_yazim + son_kucuk[len(kok_yazim):]
    if kesme:
        son_kucuk = son_kucuk.replace("'", kesme)
    return _uygula_bicim(" ".join(sozcukler[:-1] + [son_kucuk]), bicim)


@dataclass
class Sonuc:
    metin: str
    degisen: int = 0
    belirsiz: list[str] = field(default_factory=list)   # neden etiketleri
    ornekler: list[tuple[str, str]] = field(default_factory=list)  # (eski yüzey, yeni yüzey)


def yeniden_yaz(tr_paragraflar: list[str], en_paragraflar: list[str] | None, kaynak_desen,
                eski: str, yeni: str) -> tuple[list[str], Sonuc]:
    """Hizalı paragraflarda eski karşılığı yenisiyle değiştir. ``en_paragraflar`` None ise
    (hizasız bölüm) hiçbir şey değişmez, bütün geçişler belirsiz sayılır."""
    ozet = Sonuc("")
    cikti = list(tr_paragraflar)
    hizali = en_paragraflar is not None and len(en_paragraflar) == len(tr_paragraflar)
    for i, p in enumerate(tr_paragraflar):
        gs = gecisler(p, eski)
        if not gs:
            continue
        if not hizali:
            ozet.belirsiz += ["hizasiz"] * len(gs)
            continue
        en_sayi = len(kaynak_desen.findall(en_paragraflar[i]))
        if en_sayi == 0:
            ozet.belirsiz += ["kaynakta_yok"] * len(gs)
            continue
        if len(gs) > en_sayi:
            ozet.belirsiz += ["fazla_gecis"] * len(gs)
            continue
        parcalar, imlec = [], 0
        for g in gs:
            yeni_yuzey = _yeni_yuzey(g, eski, yeni) if g.ekler else None
            if yeni_yuzey is None:
                ozet.belirsiz.append("ayrismadi" if not g.ekler else "cok_anlamli")
                continue
            parcalar += [p[imlec:g.bas], yeni_yuzey]
            imlec = g.son
            ozet.degisen += 1
            ozet.ornekler.append((g.yuzey, yeni_yuzey))
        cikti[i] = "".join(parcalar) + p[imlec:]
    return cikti, ozet


def sablon_bolum(tr_paragraflar: list[str], en_paragraflar: list[str] | None,
                 kayitlar: dict[int, tuple[str, str]], desenler: dict[int, re.Pattern]
                 ) -> tuple[list[str], Counter]:
    """Bölümü paragraf paragraf şablona çevir. Kayıt yalnız hizalı İngilizce paragrafta
    kaynağı geçiyorsa aranır (karşılığı sıradan sözcük olan kayıt — "güçlü", "kara" —
    paragraftaki her "güçlü"yü belirtece çevirirdi) ve geçiş sayısı İngilizceyi aşamaz."""
    say: Counter = Counter()
    if en_paragraflar is None or len(en_paragraflar) != len(tr_paragraflar):
        say["hizasiz_bolum"] += 1
        return list(tr_paragraflar), say
    cikti = []
    for tr_p, en_p in zip(tr_paragraflar, en_paragraflar):
        aday = {}
        for kimlik, (kaynak, karsilik) in kayitlar.items():
            n = len(desenler[kimlik].findall(en_p))
            if n:
                aday[kimlik] = (karsilik, n)
        sab, n, kalan = sablon(tr_p, aday)
        say["belirtec"] += n
        say["cok_anlamli_kalan"] += kalan
        cikti.append(sab)
    return cikti, say


def sablon(metin: str, kayitlar: dict[int, tuple[str, int]]) -> tuple[str, int, int]:
    """Kayıtlı karşılık geçişlerini belirtece çevir: ``⟦kimlik|ek+ek|biçim⟧``.

    ``kayitlar``: kimlik -> (karşılık, en çok geçiş sayısı). Yalnız tek ayrıştırmalı geçiş
    belirteç olur (çok anlamlı ek, karşılık değişince hangi yüzeyi alacağını bilemez).
    Dönüş: (şablon, belirtece dönen, kalan)."""
    kapsanan: list[tuple[int, int, str]] = []
    kalan = 0
    for kimlik, (karsilik, ust) in sorted(kayitlar.items(), key=lambda kv: -len(kv[1][0])):
        gs = gecisler(metin, karsilik)
        if len(gs) > ust:
            kalan += len(gs)
            continue
        for g in gs:
            if any(not (g.son <= b or g.bas >= s) for b, s, _ in kapsanan):
                continue
            son_sozcuk = re.split(r"\s+", g.yuzey)[-1]
            tek = turkce_ek.soyut_tek(kok(karsilik, g.kesmeli), son_sozcuk)
            if tek is None:
                kalan += 1
                continue
            ek = "+".join(tek)
            bicim = _bicim(g.yuzey, karsilik) + _kesme(g.yuzey)
            kapsanan.append((g.bas, g.son, f"⟦{kimlik}|{ek}|{bicim}⟧"))
    kapsanan.sort()
    parcalar, imlec = [], 0
    for b, s, belirtec in kapsanan:
        parcalar += [metin[imlec:b], belirtec]
        imlec = s
    return "".join(parcalar) + metin[imlec:], len(kapsanan), kalan


def doldur(sablon_metin: str, kayitlar: dict[int, str]) -> str:
    """Belirteçleri o anki sözlükle doldur."""
    def _bir(m: re.Match) -> str:
        karsilik = kayitlar[int(m.group(1))]
        ekler = tuple(e for e in m.group(2).split("+") if e)
        bicim, kesme = m.group(3)[:1], m.group(3)[1:]
        son = turkce_ek.kur(kok(karsilik, bool(kesme)), ekler)
        return _yuzeye(karsilik, son, bicim, kesme)
    return BELIRTEC.sub(_bir, sablon_metin)
