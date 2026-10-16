"""Sayı/ölçek denetimi — kaynaktaki büyüklük çeviride korunmuş mu (2026-10-16, Faz A3).

Saf modül, API çağırmaz. Kör nokta taraması: belirlenimci denetimler yalnız İngilizce
sayı SÖZCÜĞÜ sızıntısına bakıyordu (`translate.SAYI_SOZCUKLERI`); "two thousand
sailors" -> "iki yüz denizci" gibi ölçek kayması yalnız LLM kalite katmanına
kalıyordu (gerçek vaka: 2026-10-13 cilalama binlik denizci sayısını kaybetti, yalnız
istemdeki örnekle tutuldu).

Ölçüt bilerek DAR — yalnız BÜYÜKLÜK taşıyan değerler:
* 10 ve üstü rakamlar (2,000 / 2.000 / 1.5 ayrımı dile göre çözülür),
* hundred/thousand/million/billion ya da dozen içeren sözcük ifadeleri,
* belirsiz çokluklar (hundreds/thousands of -> yüzlerce/binlerce).
Küçük sayılar DIŞARIDA: Türkçe onları doğal olarak düşürür ya da eke çevirir
("one of them" -> "biri", "two of us" -> "ikimiz"). Cümle ortasında büyük harfle
başlayan sayı sözcüğü özel adın parçasıdır (`Thousand Transformations`) ve sayılmaz
— `translate.SAYI_SOZCUKLERI` ölçümüyle aynı gözlem.
"""
from __future__ import annotations

import re

_EN_BIRLER = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "a": 1,
}
# "dozen" BİLEREK YOK (kalibrasyon, SS 147 bulgunun 52'si): Türkçede çoğunlukla yaklaşık
# ifadeye döner ("a dozen meters" -> "birkaç metre"), kesin sayı değildir.
_EN_CARPAN = {"hundred": 100, "thousand": 1000, "million": 10**6, "billion": 10**9}
_EN_BELIRSIZ = {"hundreds": 100, "thousands": 1000, "millions": 10**6, "billions": 10**9}

_TR_BIRLER = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8,
    "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
    "yetmiş": 70, "seksen": 80, "doksan": 90,
}
_TR_CARPAN = {"yüz": 100, "bin": 1000, "milyon": 10**6, "milyar": 10**9}
# "binbir" / "bin bir": "sayısız" anlamında kalıp ("binbir parçaya") — 1001 değil.
_TR_BELIRSIZ = {"yüzlerce": 100, "binlerce": 1000, "binbir": 1000, "milyonlarca": 10**6,
                "milyarlarca": 10**9}
# Sayı sözcüğünden sonra gelebilen ekler ("yüzden fazla", "bine yakın", "kırka").
# Liste DAR: sayı sözcükleri başka sözcüklerin başıdır (on -> onu/ona zamir, bin -> bina,
# altı -> altında). Ekli BİRLER yalnız dizinin İÇİNDE kabul edilir ("üç yüz kırka").
_TR_EKLER = frozenset("e a i ı ü u de da den dan te ta ten tan in ın ün un le la lik lık lük luk ce ca".split())

_SOZCUK = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)?|\d[\d.,]*\d|\d")
EN_ESIK = 10


def _tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def _rakam_en(t: str) -> float | None:
    t = t.rstrip(".,")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", t):
        return float(t.replace(",", ""))
    try:
        return float(t)
    except ValueError:
        return None


def _rakam_tr(t: str) -> list[float]:
    """Türkçe metindeki rakam. Model İngilizce ayırıcıyı da korur ("513,842"): ikisi de aday."""
    t = t.rstrip(".,")
    out = []
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        out.append(float(t.replace(".", "").replace(",", ".")))
    if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
        out.append(float(t.replace(",", "")))
    try:
        out.append(float(t.replace(",", ".")))
    except ValueError:
        pass
    return out


def _tr_sayi(w: str, dizi_icinde: bool) -> str | None:
    """Türkçe sözcüğün sayı kökü (ekli hâller dahil); sayı değilse None."""
    if w in _TR_BIRLER or w in _TR_CARPAN:
        return w
    for kok in (*_TR_CARPAN, *(_TR_BIRLER if dizi_icinde else ())):
        if w.startswith(kok) and w[len(kok):] in _TR_EKLER:
            return kok
    # milyon/milyar her eki alabilir ("milyarımız"): bu köklerle başlayan başka Türkçe
    # sözcük yok — "milyoner" dışında.
    for kok in ("milyon", "milyar"):
        if w.startswith(kok) and not w.startswith("milyoner"):
            return kok
    return None


def _deger_topla(sozcukler: list[str], birler: dict, carpan: dict) -> int | None:
    toplam = simdiki = 0
    olcekli = False
    for w in sozcukler:
        if w in birler:
            simdiki += birler[w]
        elif w in carpan:
            olcekli = True
            k = carpan[w]
            if k == 100:
                simdiki = (simdiki or 1) * 100
            else:
                toplam += (simdiki or 1) * k
                simdiki = 0
    deger = toplam + simdiki
    return deger if olcekli else None


def _onluk(birler: dict, w: str) -> bool:
    return birler.get(w, 0) >= 10 and birler[w] % 10 == 0


def _birler_ekle(dizi: list[str], w: str, birler: dict, kapat) -> bool:
    """Diziye ekle. Art arda iki BASAMAK sayısı ("one one", "iki üç") ayrı sayılardır.
    Art arda iki ONLUK ("altmış yetmiş", "sixty-seventy") ARALIKTIR: True döner, çağıran
    aralığı ve arkasından gelen ölçek sözcüğünü ölçüm dışı bırakır (kesin değer değil)."""
    if dizi and dizi[-1] in birler and w in birler:
        if _onluk(birler, dizi[-1]) and _onluk(birler, w):
            dizi.clear()
            return True
        if 0 < birler[dizi[-1]] < 10 and 0 < birler[w] < 10:
            kapat()
    dizi.append(w)
    return False


def _sozcuk_degerleri(metin: str, birler, carpan, belirsiz, kucuk, ad_suzgeci: bool) -> tuple[set, set]:
    """(kesin değerler, belirsiz büyüklükler) — yalnız ölçek sözcüğü içeren diziler."""
    kesin, bel = set(), set()
    dizi: list[str] = []
    turkce = not ad_suzgeci

    def kapat():
        if dizi:
            if turkce and dizi[-2:] == ["bin", "bir"] and len(dizi) == 2:
                bel.add(1000)  # "bin bir": kalıp, "sayısız"
            else:
                v = _deger_topla(dizi, birler, carpan)
                if v is not None and dizi[-1] not in ("a",):
                    kesin.add(float(v))
            dizi.clear()

    onceki_bitis = 0
    onceki_rakam = False
    aralik = False
    for m in _SOZCUK.finditer(metin):
        ham = m.group(0)
        w = kucuk(ham)
        ara = metin[onceki_bitis:m.start()]
        rakamdan_sonra = onceki_rakam and not ara.strip()
        onceki_rakam = ham[:1].isdigit()
        if rakamdan_sonra:
            kapat()
            continue  # "130 milyon": ölçek rakamla birlikte `degerler`de çarpılır
        # Cümle başı: metnin başı ya da arada cümle sonu işareti. Orada büyük harf ad kanıtı değil.
        cumle_basi = onceki_bitis == 0 or bool(re.search(r"[.!?…]", ara))
        onceki_bitis = m.end()
        # Noktalama sayı dizisini böler ("ten, a hundred") — TEK istisna: binlik ölçekten
        # sonraki virgül ("two thousand, five hundred"; RSSG kalibrasyonu).
        binlik_virgul = (ara.strip() == "," and dizi and carpan.get(dizi[-1], 0) >= 1000)
        if any(c in ara for c in ",;:.!?…\"“”()[]") and not binlik_virgul:
            kapat()
        # Belirsiz çokluk ek alabilir ("yüzlercesi", "binlercesini"): önek yeter, çünkü
        # bu sözcüklerin başka bir sözcüğün başı olduğu Türkçe/İngilizce yazım yok.
        kok = next((k for k in belirsiz if w.startswith(k)), None)
        if kok:
            kapat()
            bel.add(belirsiz[kok])
            continue
        if ad_suzgeci and ham[:1].isupper() and not cumle_basi and (
                any(p in birler or p in carpan for p in w.split("-"))):
            kapat()  # cümle ortasında büyük harfli sayı sözcüğü: özel adın parçası
            continue
        parcalar = w.split("-")  # "thirty-two"
        if turkce:
            sayi = _tr_sayi(w, bool(dizi))
            parcalar = [sayi] if sayi else []
        elif not all(p in birler or p in carpan for p in parcalar):
            parcalar = []
        if parcalar:
            if aralik:
                continue  # aralığın ölçek sözcüğü: "altmış yetmiş MİLYON"
            for p in parcalar:
                if _birler_ekle(dizi, p, birler, kapat):
                    aralik = True
                    break
            if turkce and not aralik and parcalar[0] != w:
                kapat()  # ekli sözcük diziyi bitirir ("üç yüz kırka")
            continue
        aralik = False
        if w in ("and", "ve") and dizi:
            continue
        kapat()
    kapat()
    return kesin, bel


def degerler(metin: str, dil: str) -> tuple[set, set]:
    """Paragraftaki ölçekli değerler: (kesin değerler, belirsiz büyüklükler)."""
    if dil == "en":
        kesin, bel = _sozcuk_degerleri(metin, _EN_BIRLER, _EN_CARPAN, _EN_BELIRSIZ,
                                       str.lower, ad_suzgeci=True)
        def rakam(t):
            v = _rakam_en(t)
            return [v] if v is not None else []
    else:
        kesin, bel = _sozcuk_degerleri(metin, _TR_BIRLER, _TR_CARPAN, _TR_BELIRSIZ,
                                       _tr_kucuk, ad_suzgeci=False)
        rakam = _rakam_tr
    # Önünde harf olabilir ("5x25"); yalnız rakam/ayırıcı sayının parçasıdır.
    olcek = _EN_CARPAN if dil == "en" else _TR_CARPAN
    kucuk = str.lower if dil == "en" else _tr_kucuk
    for m in re.finditer(r"(?<![\d.,])\d[\d.,]*\d|(?<![\d.,])\d", metin):
        carpim = 1
        sonraki = re.match(r"\s+([^\W\d_]+)", metin[m.end():])
        if sonraki:  # karışık yazım: "130 milyon", "2.5 million"
            w = kucuk(sonraki.group(1))
            kok = w if w in olcek else (_tr_sayi(w, False) if dil != "en" else None)
            carpim = olcek.get(kok, 1)
        for v in rakam(m.group(0)):
            if v * carpim >= EN_ESIK:
                kesin.add(v * carpim)
    return kesin, bel


def uyumsuzluk(en: str, tr: str) -> list[str]:
    """Kaynakta olup çeviride karşılığı bulunmayan ölçekli değerler (okunur etiketler)."""
    en_k, en_b = degerler(en, "en")
    tr_k, tr_b = degerler(tr, "tr")
    eksik = []
    for v in sorted(en_k):
        if v < EN_ESIK:
            continue
        if v in tr_k:
            continue
        # Abartı: "a thousand times" -> "binlerce kez" meşru (yalnız yalın taban değer).
        if v in _ETIKET and v in tr_b:
            continue
        eksik.append(f"{v:,.0f}".replace(",", ".") if v == int(v) else f"{v:g}")
    for b in sorted(en_b):
        # Belirsiz çokluk aynı belirsizlikle YA DA aynı ölçekte kesin bir değerle karşılanabilir.
        if b not in tr_b and not any(b <= v < b * 10 for v in tr_k):
            eksik.append(_ETIKET[b])
    return eksik


_ETIKET = {100: "yüzlerce", 1000: "binlerce", 10**6: "milyonlarca", 10**9: "milyarlarca"}


def paragraf_uyumsuzluklari(tr_paras: list[str], en_paras: list[str]) -> dict[int, list[str]]:
    """{paragraf: [eksik değerler]} — hizalı çeviride. Hizasızsa ölçülmez ({})."""
    if not tr_paras or len(tr_paras) != len(en_paras):
        return {}
    out = {}
    for i, (tr, en) in enumerate(zip(tr_paras, en_paras)):
        e = uyumsuzluk(en, tr)
        if e:
            out[i] = e
    return out
