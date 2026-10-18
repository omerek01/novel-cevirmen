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

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from . import turkce_ek
from .turkce_eslesme import _IYELIK, karsilik_deseni, tr_kucuk

# ⟦kimlik|ekler|biçim+kesme|karşılık özeti|söyleniş ünlüsü⟧. Özet, belirteç yazılırken
# geçerli olan karşılığın kısaltılmış SHA-1'i: aynı karşılıkla doldurulursa özgün yazım
# (kesme, biçim, ünlü) BİREBİR geri gelir; karşılık değiştiyse yeni karşılığın kuralları
# (özel ad kesmesi, söyleniş uyumu) uygulanır.
BELIRTEC = re.compile(r"⟦(\d+)\|([^|⟧]*)\|([^|⟧]*)\|([0-9a-f]*)\|([^⟧]*)⟧")
_UNLULER = "aeıioöuü"
_KESMELI_EK = re.compile(r"([^\W\d_]+)['’]([^\W\d_]+)")


def _ozet(karsilik: str) -> str:
    return hashlib.sha1(karsilik.encode("utf-8")).hexdigest()[:8]


class Uyum:
    """Kitabın kendi çevirilerinden öğrenilen söyleniş ünlüleri (yabancı adlar için).

    Model "Knight'ın", "Reaper'a" yazdıysa uyum oradan okunur: yazımdaki son ünlü
    (i, e) yanıltır. Kalınlık bütün ek ünlülerinden, yuvarlaklık yalnız I türü ünlülerden
    (ı i u ü) öğrenilir — "Fool'a" yuvarlaklık söylemez. En az iki tanık ve %70 çoğunluk."""

    def __init__(self, metinler: Iterable[str] = ()):
        self._kalin: dict[str, Counter] = {}
        self._yuvarlak: dict[str, Counter] = {}
        for metin in metinler:
            for m in _KESMELI_EK.finditer(metin or ""):
                kok_, ek = tr_kucuk(m.group(1)), tr_kucuk(m.group(2))
                u = next((c for c in ek if c in _UNLULER), None)
                if not u:
                    continue
                self._kalin.setdefault(kok_, Counter())[u in "aıou"] += 1
                if u in "ıiuü":
                    self._yuvarlak.setdefault(kok_, Counter())[u in "uü"] += 1

    @staticmethod
    def _karar(sayac: Counter | None) -> bool | None:
        if not sayac:
            return None
        deger, n = sayac.most_common(1)[0]
        return deger if n >= 2 and n >= 0.7 * sum(sayac.values()) else None

    def unlu(self, sozcuk: str) -> str | None:
        s = tr_kucuk(sozcuk)
        kalin = self._karar(self._kalin.get(s))
        if kalin is None:
            return None
        yuvarlak = self._karar(self._yuvarlak.get(s))
        if yuvarlak is None:
            son = next((c for c in reversed(s) if c in _UNLULER), "a")
            yuvarlak = son in "oöuü"
        return {(True, True): "u", (True, False): "ı",
                (False, True): "ü", (False, False): "i"}[(kalin, yuvarlak)]


_INGILIZCE_IZ = re.compile(r"w|x|q|th|gh|sh|ee|oo|ea|ck|[^aeıioöuü]y$")


def _yabanci_mi(sozcuk: str, kaynak: str | None) -> bool:
    """Sözcük İngilizce mi: kaynak terimde aynen geçiyor ya da Türkçede olmayan yazım izi var."""
    s = tr_kucuk(sozcuk)
    if kaynak and s in tr_kucuk(kaynak).split():
        return True
    return bool(_INGILIZCE_IZ.search(s))


def kok(karsilik: str, kesmeli: bool = False, unlu: str | None = None) -> turkce_ek.Kok:
    """Karşılığın son sözcüğünden çekim kökü (iyelikli tamlama ayrımıyla)."""
    sozcukler = karsilik.split()
    son = tr_kucuk(sozcukler[-1].strip(turkce_ek.KESME))
    m = _IYELIK.search(son)
    iyelikli = len(sozcukler) > 1 and bool(m) and len(son) - len(m.group(1)) >= 2
    return turkce_ek.Kok(son, iyelikli=iyelikli, kesmeli=kesmeli, unlu=unlu)


def _yeni_kok(yeni: str, kaynak: str | None, uyum: "Uyum | None") -> turkce_ek.Kok:
    """DEĞİŞEN karşılığın kökü: özel ad (büyük harfle kayıtlı) ek kesmeyle ayrılır
    (Knight'a, Titan'a, Kasvetli Gölge'yle); yabancı adın uyumu önce kitaptan, yoksa
    İngilizce söyleniş kurallarından okunur."""
    son = yeni.split()[-1].strip(turkce_ek.KESME)
    unlu = uyum.unlu(son) if uyum else None
    if unlu is None and _yabanci_mi(son, kaynak):
        unlu = turkce_ek.ingilizce_unlu(son)
    return kok(yeni, kesmeli=yeni[:1].isupper(), unlu=unlu)


def _tr_buyuk(metin: str) -> str:
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _bicim(yuzey: str, karsilik: str) -> str:
    """Harf biçimi: K = karşılığın kayıtlı yazımı, B = tamamı büyük, k = tamamı küçük,
    I = ilk harf büyük gerisi küçük (cümle başındaki küçük harfli kayıt), S01… = sözcük
    başına baş harf maskesi (model kaydın bir sözcüğünü küçük yazmış: "ilk Lord'a")."""
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
    sozcukler = yuzey.split()
    if len(sozcukler) > 1 and all(w[:1].isupper() for w in sozcukler):
        return "T"  # başlık biçimi: kayıt küçük harfli ama metinde ad gibi yazılmış
    maske = "".join("1" if w[:1].isupper() else "0" for w in sozcukler)
    return "I" if maske == "1" + "0" * (len(sozcukler) - 1) else "S" + maske


def _ayir_bicim(alan: str) -> tuple[str, str]:
    """Belirteçteki biçim alanını (biçim, kesme) diye ayır: "S01'" -> ("S01", "'")."""
    if alan[:1] == "S":
        n = 1 + len(alan[1:]) - len(alan[1:].lstrip("01"))
        return alan[:n], alan[n:]
    return alan[:1], alan[1:]


def _karsilik_bicimi(bicim: str, karsilik: str) -> str:
    """Karşılık değişince eski yüzeyin biçimi: özel ad kayıtlı yazımıyla gelir (K), ama
    sözcük maskesi yeni karşılığın sözcük sayısı tutuyorsa korunur."""
    if bicim.startswith("S") and len(bicim) - 1 == len(karsilik.split()):
        return bicim
    if karsilik[:1].isupper() and bicim != "B":
        return "K"
    return "K" if bicim.startswith("S") else bicim


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
    if bicim == "T":
        return " ".join(_tr_buyuk(w[:1]) + w[1:] for w in metin.split(" "))
    sozcukler = metin.split(" ")
    if bicim.startswith("S") and len(bicim) - 1 == len(sozcukler):
        return " ".join((_tr_buyuk(w[:1]) if b == "1" else tr_kucuk(w[:1])) + w[1:]
                        for w, b in zip(sozcukler, bicim[1:]))
    return metin


@dataclass
class Gecis:
    bas: int
    son: int
    yuzey: str
    ekler: tuple[tuple[str, ...], ...]   # ayrıştırma adayları (boş = ayrışmadı)
    kesmeli: bool
    kok: turkce_ek.Kok | None = None      # ayrıştırmayı veren kök (söyleniş ünlüsüyle)


def gecisler(metin: str, karsilik: str, uyum: Uyum | None = None) -> list[Gecis]:
    """Metindeki çekimli karşılık geçişleri ve eklerinin ayrıştırma adayları.

    Kesmeli geçişte önce kitaptan öğrenilen söyleniş ünlüsüyle, tutmazsa yazımla denenir:
    model yabancı adı bazen söylenişe, bazen yazıma göre çekmiş olabilir."""
    sonuc = []
    son_yazim = karsilik.split()[-1].strip(turkce_ek.KESME) if karsilik.split() else ""
    for m in karsilik_deseni(karsilik).finditer(metin):
        yuzey = m.group(0)
        son_sozcuk = re.split(r"\s+", yuzey)[-1]
        kesmeli = any(k in son_sozcuk for k in turkce_ek.KESME)
        unlu = uyum.unlu(son_yazim) if (uyum and kesmeli) else None
        k = kok(karsilik, kesmeli, unlu)
        adaylar = turkce_ek.ayristir(k, son_sozcuk)
        if not adaylar and unlu:
            k = kok(karsilik, kesmeli)
            adaylar = turkce_ek.ayristir(k, son_sozcuk)
        sonuc.append(Gecis(m.start(), m.end(), yuzey, adaylar, kesmeli, k))
    return sonuc


def _yeni_yuzey(g: Gecis, eski: str, yeni: str, kaynak: str | None = None,
                uyum: Uyum | None = None) -> str | None:
    son_sozcuk = re.split(r"\s+", g.yuzey)[-1]
    yeni_kok = _yeni_kok(yeni, kaynak, uyum)
    yeni_son = turkce_ek.kur_tek(g.kok or kok(eski, g.kesmeli), son_sozcuk, yeni_kok)
    if yeni_son is None:
        return None
    bicim = _karsilik_bicimi(_bicim(g.yuzey, eski), yeni)
    return _yuzeye(yeni, yeni_son, bicim, _kesme(g.yuzey) if yeni_kok.kesmeli else "")


def _yuzeye(karsilik: str, son_kucuk: str, bicim: str, kesme: str) -> str:
    """Küçük harfle kurulmuş son sözcüğü karşılığın yazımına ve yüzeyin biçimine oturt."""
    sozcukler = karsilik.split()
    # Kök küçük harfle kurulur; kayıtlı yazım (büyük harfi) geri konur.
    kok_yazim = sozcukler[-1].strip(turkce_ek.KESME)
    # Büyük/küçük kalıbı harf harf aktarılır: kök yüzeyde değişmiş olabilir
    # (Yaratığı -> Yaratıkları), önek karşılaştırması o zaman tutmazdı.
    son_kucuk = "".join(
        _tr_buyuk(c) if i < len(kok_yazim) and kok_yazim[i].isupper() else c
        for i, c in enumerate(son_kucuk))
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
                eski: str, yeni: str, *, kaynak: str | None = None,
                uyum: Uyum | None = None) -> tuple[list[str], Sonuc]:
    """Hizalı paragraflarda eski karşılığı yenisiyle değiştir. ``en_paragraflar`` None ise
    (hizasız bölüm) hiçbir şey değişmez, bütün geçişler belirsiz sayılır."""
    ozet = Sonuc("")
    cikti = list(tr_paragraflar)
    hizali = en_paragraflar is not None and len(en_paragraflar) == len(tr_paragraflar)
    for i, p in enumerate(tr_paragraflar):
        gs = gecisler(p, eski, uyum)
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
            yeni_yuzey = _yeni_yuzey(g, eski, yeni, kaynak, uyum) if g.ekler else None
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
                 kayitlar: dict[int, tuple[str, str]], desenler: dict[int, re.Pattern],
                 uyum: Uyum | None = None) -> tuple[list[str], Counter]:
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
        sab, n, kalan = sablon(tr_p, aday, uyum)
        say["belirtec"] += n
        say["cok_anlamli_kalan"] += kalan
        cikti.append(sab)
    return cikti, say


def sablon(metin: str, kayitlar: dict[int, tuple[str, int]],
           uyum: Uyum | None = None) -> tuple[str, int, int]:
    """Kayıtlı karşılık geçişlerini belirtece çevir (biçim için `BELIRTEC`).

    ``kayitlar``: kimlik -> (karşılık, en çok geçiş sayısı). Yalnız tek ayrıştırmalı geçiş
    belirteç olur (çok anlamlı ek, karşılık değişince hangi yüzeyi alacağını bilemez).
    Dönüş: (şablon, belirtece dönen, kalan)."""
    kapsanan: list[tuple[int, int, str]] = []
    kalan = 0
    for kimlik, (karsilik, ust) in sorted(kayitlar.items(), key=lambda kv: -len(kv[1][0])):
        gs = gecisler(metin, karsilik, uyum)
        if len(gs) > ust:
            kalan += len(gs)
            continue
        for g in gs:
            if any(not (g.son <= b or g.bas >= s) for b, s, _ in kapsanan):
                continue
            son_sozcuk = re.split(r"\s+", g.yuzey)[-1]
            tek = turkce_ek.soyut_tek(g.kok, son_sozcuk) if g.ekler else None
            if tek is None:
                kalan += 1
                continue
            ek = "+".join(tek)
            bicim = _bicim(g.yuzey, karsilik) + _kesme(g.yuzey)
            unlu = g.kok.unlu or ""
            belirtec = f"⟦{kimlik}|{ek}|{bicim}|{_ozet(karsilik)}|{unlu}⟧"
            # Geri doldurma özgünü birebir vermiyorsa (biçim sınıflarına sığmayan yazım:
            # "İLk Lord'a") geçiş metin kalır: şablon özgün metni asla bozmamalı.
            if doldur(belirtec, {kimlik: karsilik}) != g.yuzey:
                kalan += 1
                continue
            kapsanan.append((g.bas, g.son, belirtec))
    kapsanan.sort()
    parcalar, imlec = [], 0
    for b, s, belirtec in kapsanan:
        parcalar += [metin[imlec:b], belirtec]
        imlec = s
    return "".join(parcalar) + metin[imlec:], len(kapsanan), kalan


def doldur(sablon_metin: str, kayitlar: dict[int, str], kaynaklar: dict[int, str] | None = None,
           uyum: Uyum | None = None) -> str:
    """Belirteçleri o anki sözlükle doldur. Karşılık belirteç yazıldığından beri aynıysa
    özgün yazım birebir geri gelir; değiştiyse yeni karşılığın kuralları uygulanır."""
    def _bir(m: re.Match) -> str:
        kimlik = int(m.group(1))
        karsilik = kayitlar[kimlik]
        ekler = tuple(e for e in m.group(2).split("+") if e)
        bicim, kesme = _ayir_bicim(m.group(3))
        if m.group(4) == _ozet(karsilik):
            son = turkce_ek.kur(kok(karsilik, bool(kesme), m.group(5) or None), ekler)
            return _yuzeye(karsilik, son, bicim, kesme)
        yeni_kok = _yeni_kok(karsilik, (kaynaklar or {}).get(kimlik), uyum)
        son = turkce_ek.kur(yeni_kok, ekler)
        bicim = _karsilik_bicimi(bicim, karsilik)
        return _yuzeye(karsilik, son, bicim, (kesme or "'") if yeni_kok.kesmeli else "")
    return BELIRTEC.sub(_bir, sablon_metin)
