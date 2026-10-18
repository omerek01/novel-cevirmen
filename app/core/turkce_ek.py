"""Türkçe ad çekimi: yüzeydeki eki SOYUT eklere ayır, yeni köke göre yeniden kur.

Saf modül, API çağırmaz. Sözlükte bir karşılık değişince (Kovan -> Oyuk) eski bölümlerdeki
"Kovan'a" gibi biçimleri yeniden çeviri yapmadan "Oyuk'a" yapabilmek için (2026-10-18,
benzer sistemler araştırması Ö1). WTR-LAB terimi metne yazmıyor, yer tutucuya yazıp okurken
dolduruyor; Türkçede bu doğrudan çalışmaz çünkü ek köke göre değişir (ünlü uyumu, kaynaştırma
harfi, ünsüz benzeşmesi ve yumuşaması). Bu modül eki köke bağlı olmayan soyut biçimde
(``(y)A``, ``DA``, ``(n)In``…) tutar ve her kökte yeniden kurar.

Ayrıştırma KURALLA DEĞİL ÜRETİMLE yapılır: eski kökten olası ek dizileri üretilir, yüzeyle
birebir aynı çıkanlar seçilir. Bu yüzden seçilen dizi eski kökte HER ZAMAN aynı yüzeyi verir
(geri üretim kendiliğinden doğrulanır). Birden çok dizi aynı yüzeyi verebilir — "Kovanı"
belirtme (-(y)I) de olabilir iyelik (-(s)I) de; yeni kök ünlüyle bitiyorsa ikisi farklı
çıkar ("Kaleyi" / "Kalesi"). O durumda karar verilmez: ``kur_tek`` None döner, çağıran
geçişi belirsiz sayar.

Bilerek KAPSAM DIŞI: ünlü düşmesi (ağız -> ağzı), ünlü daralması (de- -> diyor), fiil
çekimi. Karşılıklar ad olduğu için seyrek; ayrıştırılamayan biçim belirsiz kalır.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from .turkce_eslesme import tr_kucuk

_UNLU = "aeıioöuüâîû"
_KALIN = set("aıouâû")
_YUVARLAK = set("oöuüû")
_SERT = set("fstkçşhp")
_YUMUSAMA = {"p": "b", "ç": "c", "t": "d", "k": "ğ"}
KESME = "'’"

# Son hecesi ince ek alan alıntılar (saat -> saati). Kısa ve bilerek sınırlı: karşılıklar
# çoğunlukla özel ad; liste dışındaki istisna yanlış kurulur, ölçüm bunu sayar.
_INCE_ISTISNA = {
    "saat", "hal", "kalp", "rol", "gol", "alkol", "kontrol", "hayal", "ihtimal", "misal",
    "petrol", "sembol", "protokol", "festival", "kemal", "cemal", "celal", "hilal", "kabul",
}
# Çok heceli olduğu hâlde yumuşamayan alıntılar (saat -> saati, millet -> milleti).
_YUMUSAMAZ = {"saat", "devlet", "millet", "cennet", "nefret", "hukuk", "sanat", "hakikat"}


def uyum_metni(sozcuk: str) -> str:
    """Ünlü uyumunun okunacağı biçim. Yabancı adda sondaki ünsüz + "y" /i/ okunur
    (Sunny -> Sunny'ye); yazım değişmez, yalnız uyum ve kaynaştırma buna bakar."""
    if len(sozcuk) >= 2 and sozcuk[-1] == "y" and sozcuk[-2] not in _UNLU:
        return sozcuk + "i"
    return sozcuk

# Soyut ekler. Büyük harf: A = a/e, I = ı/i/u/ü, D = d/t, C = c/ç. Ayraç içi kaynaştırma:
# yalnız ünlüden sonra (y, n, s) ya da yalnız ünsüzden sonra (I) yazılır.
_TUREM = ["lI", "sIz", "lIk", "CI"]
_COGUL = ["lAr"]
_IYELIK = ["(I)m", "(I)n", "(s)I", "(I)mIz", "(I)nIz"]
_DURUM = ["(y)I", "(y)A", "DA", "DAn", "(n)In", "(y)lA", "CA"]
_KI = ["ki"]
_EK_FIIL = ["(y)DI", "(y)mIş", "(y)sA", "DIr", "(y)Im", "(y)sIn", "(y)Iz", "lAr"]

IYELIK3 = "(s)I"
# 3. kişi iyelikten sonra durum eki "n" kaynaştırması alır (Dağı -> Dağına, Dağında).
_ZAMIRSEL_N = {"(y)I": "nI", "(y)A": "nA", "DA": "nDA", "DAn": "nDAn", "CA": "nCA"}


@dataclass(frozen=True)
class Kok:
    """Çekimin uygulanacağı kök: karşılığın SON sözcüğü (küçük harf).

    ``iyelikli``: çok sözcüklü tamlama ve son sözcük 3. kişi iyelikle bitiyor
    (Oyuk Dağı). Çoğulda iyelik düşer (Dağları), durum ekleri "n" alır (Dağına).
    ``kesmeli``: yüzeyde ek kesmeyle ayrılmış (özel ad) — yumuşama yazılmaz.
    ``unlu``: ünlü uyumunun söylenişe göre okunacağı ünlü (yabancı ad: Knight -> "ı",
    Reaper -> "ı"). None = yazımdaki son ünlü. Kaynaştırma harfi ve ünsüz benzeşmesi
    yine yazımın son harfine bakar.
    """

    sozcuk: str
    iyelikli: bool = False
    kesmeli: bool = False
    unlu: str | None = None


def _son_unlu(metin: str) -> str | None:
    for c in reversed(metin):
        if c in _UNLU:
            return c
    return None


def _kalin_mi(metin: str, kok_sozcuk: str | None = None) -> bool:
    if kok_sozcuk is not None and kok_sozcuk in _INCE_ISTISNA and metin == kok_sozcuk:
        return False
    u = _son_unlu(metin)
    return u in _KALIN if u else False


def _gerceklestir(soyut: str, onceki: str, kok_sozcuk: str, unlu: str | None = None) -> str:
    """Tek soyut eki, önceki metne (kök + önceki ekler) göre yüzeye çevirir.

    ``unlu``: önceki metinde henüz ek ünlüsü yoksa uyumun okunacağı ünlü (yabancı ad)."""
    out = ""
    i = 0
    while i < len(soyut):
        c = soyut[i]
        metin = uyum_metni(onceki) + out
        # Uyum kaynağı: ek ünlüsü çıkana dek söyleniş ünlüsü, sonra eklerin kendisi.
        uyum = (onceki + unlu) if unlu and not any(x in _UNLU for x in out) else metin
        son = metin[-1] if metin else ""
        if c == "(":
            j = soyut.index(")", i)
            harf = soyut[i + 1:j]
            unlu_sonra = son in _UNLU
            if harf == "I":
                if not unlu_sonra:
                    out += _gerceklestir("I", onceki + out, kok_sozcuk,
                                         unlu if not any(x in _UNLU for x in out) else None)
            elif unlu_sonra:
                out += harf
            i = j + 1
            continue
        if c == "A":
            out += "a" if _kalin_mi(uyum, kok_sozcuk) else "e"
        elif c == "I":
            kalin = _kalin_mi(uyum, kok_sozcuk)
            yuv = (_son_unlu(uyum) or "a") in _YUVARLAK
            out += ("u" if yuv else "ı") if kalin else ("ü" if yuv else "i")
        elif c == "D":
            out += "t" if son in _SERT else "d"
        elif c == "C":
            out += "ç" if son in _SERT else "c"
        else:
            out += c
        i += 1
    return out


def _yumusar(kok: Kok, ek_basi: str) -> bool:
    """Kök sonu p/ç/t/k ünlüyle başlayan ek önünde yumuşar mı (yazımda)."""
    s = kok.sozcuk
    if kok.kesmeli or not ek_basi or ek_basi[0] not in _UNLU or not s or s[-1] not in _YUMUSAMA:
        return False
    if s.endswith("nk"):
        return True  # renk -> rengi, ahenk -> ahengi
    if s in _YUMUSAMAZ:
        return False
    return _hece(s) >= 2


def _hece(sozcuk: str) -> int:
    return sum(1 for c in sozcuk if c in _UNLU)


def kur(kok: Kok, ekler: tuple[str, ...]) -> str:
    """Kök + soyut ek dizisi -> yüzey (kesme dahil, kök küçük harf)."""
    govde = kok.sozcuk
    ekler = list(ekler)
    if kok.iyelikli and ekler and ekler[0] == "lAr":
        # Tamlama çoğulu: iyelik düşer, çoğul + iyelik gelir (Dağı -> Dağları); düşen
        # iyelikle birlikte yumuşama da geri döner (Yaratığı -> Yaratıkları).
        govde = _iyeliksiz(govde)
        ekler = ["lAr", IYELIK3] + ekler[1:]
    # Bir önceki ek (ya da iyelikli kökün kendisi) 3. kişi iyelik mi: durum eki "n" alır.
    iyelik3_once = kok.iyelikli and govde == kok.sozcuk
    yuzey_ek = ""
    for k, e in enumerate(ekler):
        if iyelik3_once and e in _ZAMIRSEL_N:
            e = _ZAMIRSEL_N[e]
        unlu = kok.unlu if not any(x in _UNLU for x in yuzey_ek) else None
        parca = _gerceklestir(e, govde + yuzey_ek, kok.sozcuk, unlu)
        if k == 0 and _yumusar(Kok(govde, kesmeli=kok.kesmeli), parca):
            s = govde
            govde = s[:-2] + "ng" if s.endswith("nk") else s[:-1] + _YUMUSAMA[s[-1]]
        yuzey_ek += parca
        iyelik3_once = e == IYELIK3
    # Özel ada YAPIM eki ve ÇOKLUK eki (ardındakilerle) kesmesiz yazılır (TDK: Ankaralı,
    # Türkler, Ahmetlerden). Hakem ölçümünde (2026-10-18) yanlışların 13/19'u buydu
    # (İblis'ler, Titan'lar). Söylenişi yazımından ayrılan yabancı adda kesme okunuşu
    # gösterdiği için kalır (Knight'lar).
    cokluk = ekler and ekler[0] == "lAr" and not kok.unlu
    if kok.kesmeli and yuzey_ek and not (ekler and ekler[0] in _TUREM) and not cokluk:
        return govde + "'" + yuzey_ek
    return govde + yuzey_ek


# İngilizce adın son hecesinin Türkçe söylenişteki ünlüsü (yalnız yazımın yanılttığı
# kalıplar; gerisi yazımdaki son ünlüye bırakılır). Hakem ölçümünde (2026-10-18) yanlış
# çıkan biçimlerin çoğu bunlardı: Knight'ı, Reaper'a, Abomination'ı.
_INGILIZCE_SONLAR = (
    (("tion", "sion"), "ı"),
    (("ight", "ite", "ice", "ime", "ine", "ide", "ire"), "ı"),
    (("er", "or", "ar", "ur", "our", "ure"), "ı"),
    (("ee", "ea", "ey", "ie"), "i"),
    (("oo", "ue"), "u"),
)


def ingilizce_unlu(sozcuk: str) -> str | None:
    """Yazımın uyumu yanıltabileceği İngilizce sonlar için söyleniş ünlüsü; yoksa None."""
    s = tr_kucuk(sozcuk)
    if len(s) < 3:
        return None
    for sonlar, unlu in _INGILIZCE_SONLAR:
        if any(s.endswith(x) for x in sonlar):
            return unlu
    return None


def _iyeliksiz(sozcuk: str) -> str:
    """Oyuk Dağı -> Dağ, Kabus Yaratığı -> Yaratık (son -(s)I düşer, yumuşama geri döner)."""
    if len(sozcuk) > 3 and sozcuk[-2:] in {"sı", "si", "su", "sü"} and sozcuk[-3] in _UNLU:
        return sozcuk[:-2]
    if sozcuk and sozcuk[-1] in "ıiuü":
        g = sozcuk[:-1]
        ters = {"b": "p", "c": "ç", "d": "t", "ğ": "k"}
        # Yumuşama yalnız çok hecede olduğu için tek heceli gövde geri sertleşmez (Dağı -> dağ).
        if g and g[-1] in ters and _hece(g) >= 2:
            return g[:-1] + ters[g[-1]]
        return g
    return sozcuk


def _diziler() -> list[tuple[str, ...]]:
    """Sıralı yuva kurallarına uyan bütün ek dizileri (boş dizi dahil)."""
    yuvalar = [_TUREM, _COGUL, _IYELIK, _DURUM, _KI, _EK_FIIL]
    sonuc: list[tuple[str, ...]] = []
    for secim in product(*[[None] + y for y in yuvalar]):
        dizi = tuple(e for e in secim if e is not None)
        if len(dizi) > 4:
            continue
        if "ki" in dizi and not any(d in dizi for d in ("DA", "(n)In")):
            continue
        sonuc.append(dizi)
    return sonuc


_DIZILER = _diziler()


@lru_cache(maxsize=65536)
def ayristir(kok: Kok, yuzey: str) -> tuple[tuple[str, ...], ...]:
    """Yüzeyi (küçük harf, kesme dahil olabilir) veren bütün ek dizileri. Boş = ayrıştırılamadı."""
    hedef = tr_kucuk(yuzey).replace("’", "'")
    iyeliksiz = [d for d in _DIZILER if not (kok.iyelikli and set(d) & set(_IYELIK))]
    return tuple(d for d in iyeliksiz if kur(kok, d) == hedef)


# Eşdeğerlik sınaması için farklı türden kökler: kalın/ince, düz/yuvarlak, ünlü/ünsüz/sert
# sonlu, yumuşayan, iyelikli tamlama, kesmeli ad.
_DENEME_KOKLERI = (
    Kok("kale"), Kok("göl"), Kok("kitap"), Kok("ütü"), Kok("kuzu"), Kok("ağaç"),
    Kok("dağı", iyelikli=True), Kok("sunny", kesmeli=True), Kok("nephis", kesmeli=True),
)


def soyut_tek(kok: Kok, yuzey: str) -> tuple[str, ...] | None:
    """Yüzeyin tek soyut ek dizisi. Birden çok aday HER deneme kökünde aynı yüzeyi
    veriyorsa (çoğuldan sonra ilgi eki = 2. kişi iyelik: -ların) aralarında fark yoktur,
    ilki alınır. Ayrışmayan ya da gerçekten çok anlamlı yüzey None."""
    adaylar = ayristir(kok, yuzey)
    if not adaylar:
        return None
    if len(adaylar) == 1:
        return adaylar[0]
    iyelikli_aday = any(set(d) & set(_IYELIK) for d in adaylar)
    for deneme in _DENEME_KOKLERI:
        if deneme.iyelikli and iyelikli_aday:
            continue  # iyelikli köke ikinci iyelik gelmez; bu kökte karşılaştırma anlamsız
        if len({kur(deneme, d) for d in adaylar}) > 1:
            return None
    return adaylar[0]


def kur_tek(eski: Kok, yuzey: str, yeni: Kok) -> str | None:
    """Eski kökteki yüzeyi yeni köke taşı. Tek anlamlı değilse ya da ayrışmazsa None."""
    adaylar = ayristir(eski, yuzey)
    if not adaylar:
        return None
    sonuclar = {kur(yeni, d) for d in adaylar}
    return sonuclar.pop() if len(sonuclar) == 1 else None
