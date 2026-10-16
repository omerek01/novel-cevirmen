"""Türkçe karşılık eşleştirici — sözlük karşılığının ÇEKİMLİ hâllerini metinde bulur.

Saf modül, API çağırmaz. Sözlükteki Türkçe karşılığın çeviride geçip geçmediğini soran
HER denetim bunu kullanır (`anlam_ayirici`, `karakter_defteri`, `translate` karşılık
sapması). Kural tek yerde durur: ayrı kopyalar bu projede defalarca ayrıştı (künye
alanları, yakın yazım sınırı) ve iki denetim aynı karşılığa farklı karar verdi.

Neden ayrı bir eşleştirici (2026-10-16, kör nokta taraması): eski desen
``\\b{karşılık}\\w*`` + ``re.IGNORECASE`` iki yerde yanılıyordu:

* **Büyük-küçük harf:** Python'un harf katlaması Türkçe değildir — ``I``'nın küçüğü
  ``i`` sayılır, ``ı`` değil; ``İ`` ise iki karakterlik ``i̇`` olur. "IŞIK" ile "ışık",
  "İZ" ile "iz" eşleşmiyordu.
* **Ünsüz yumuşaması:** p/ç/t/k ile biten sözcük ünlüyle başlayan ek alınca b/c/d/ğ
  olur (Kitap -> Kitabı, Ağaç -> Ağacı, Kanat -> Kanadı, Köpek -> Köpeği). Önek
  araması yumuşamış hâli kaçırır ve DOĞRU çeviri sahte "karşılık yok" bulgusu olurdu.
* **Tamlama çoğulu:** iyelik ekiyle biten tamlama (Oyuk Dağı) çoğulda iyeliği
  düşürür (Oyuk Dağları); "Dağı" öneki "Dağları"nı tutmaz.

Bilerek KAPSAM DIŞI: ünlü düşmesi (ağız -> ağzı, oğul -> oğlu). Özel ad
karşılıklarında seyrek; eklemek kısa sözcüklerde yanlış eşleşme riskini artırır.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Ünsüz yumuşaması: sözcük sonu -> ek önündeki hâli (yalnız ünlüyle başlayan ekte).
_YUMUSAMA = {"p": "b", "ç": "c", "t": "d", "k": "ğ"}
_SERTLESME = {v: k for k, v in _YUMUSAMA.items()}
# Tamlamada iyelik eki (3. tekil): -ı/-i/-u/-ü, ünlüden sonra -sı/-si/-su/-sü.
_IYELIK = re.compile(r"(s?[ıiuü])$")
_KESME = "'’`"
_ISARETSIZ = str.maketrans("ığüşöçâîû", "igusocaiu")


def tr_kucuk(metin: str) -> str:
    """Türkçe küçük harf: I -> ı, İ -> i, gerisi `str.lower` (uzunluk korunur)."""
    return (metin or "").replace("I", "ı").replace("İ", "i").lower()


def isaretsiz(metin: str) -> str:
    """Türkçe küçük harf + harf işaretleri düzlenmiş (model alıntıyı bazen işaretsiz yazar)."""
    return tr_kucuk(unicodedata.normalize("NFC", metin or "")).translate(_ISARETSIZ)


def _harf_sinifi(c: str, gevsek: bool) -> str:
    """Tek harfin Türkçe büyük/küçük (ve istenirse işaretsiz) bütün yazımları."""
    k = tr_kucuk(c)
    if not k.isalpha():
        return re.escape(c)
    secenek = {k, {"i": "İ", "ı": "I"}.get(k, k.upper())}
    if gevsek:
        duz = k.translate(_ISARETSIZ)
        secenek |= {duz, duz.upper()}
    secenek.discard("")
    return "[" + "".join(re.escape(s) for s in sorted(secenek)) + "]"


def _sozcuk(sozcuk: str, gevsek: bool) -> str:
    return "".join(_harf_sinifi(c, gevsek) for c in sozcuk)


@lru_cache(maxsize=4096)
def karsilik_deseni(karsilik: str, gevsek: bool = False) -> re.Pattern:
    """Karşılığın ekli/çekimli hâllerini ham metinde arayan desen.

    Son sözcük ek alabilir (kesmeli ya da kesmesiz); p/ç/t/k ile bitiyorsa yumuşamış
    hâli de kabul edilir; çok sözcüklü karşılıkta son sözcük iyelikle bitiyorsa
    iyeliksiz gövde + ``-ler/-lar`` (tamlama çoğulu) da kabul edilir. Önceki sözcükler
    olduğu gibi aranır, aralarındaki boşluk esnektir. ``gevsek``: harf işaretleri
    yok sayılır (Dag = Dağ).
    """
    sozcukler = (karsilik or "").split()
    if not sozcukler:
        return re.compile(r"(?!x)x")
    son = tr_kucuk(sozcukler[-1].strip(_KESME))
    govdeler = [_sozcuk(son, gevsek)]
    if len(son) >= 3 and son[-1] in _YUMUSAMA:
        govdeler.append(_sozcuk(son[:-1], gevsek) + _harf_sinifi(_YUMUSAMA[son[-1]], gevsek)
                        + r"(?=[aeıioöuüâîûAEIİOÖUÜÂÎÛ])")
    m = _IYELIK.search(son)
    if len(sozcukler) > 1 and m and len(son) - len(m.group(1)) >= 2:
        # İyelik düşünce yumuşama da geri döner: Kabus Yaratığı -> Kabus Yaratıkları
        # (kalibrasyonda 989 geçişin 567'si bu yüzden sahte "karşılık yok" çıkmıştı).
        govde = son[: m.start()]
        sert = _SERTLESME.get(govde[-1])
        govde_d = _sozcuk(govde, gevsek)
        if sert:
            govde_d = f"(?:{govde_d}|{_sozcuk(govde[:-1] + sert, gevsek)})"
        govdeler.append(govde_d + _harf_sinifi("l", gevsek)
                        + "[" + "".join(_harf_sinifi(c, gevsek)[1:-1] for c in "ae") + "]"
                        + _harf_sinifi("r", gevsek))
    onceki = [_sozcuk(tr_kucuk(s), gevsek) for s in sozcukler[:-1]]
    son_desen = "(?:" + "|".join(govdeler) + ")"
    tam = r"\s+".join(onceki + [son_desen])
    return re.compile(rf"(?<!\w){tam}(?:[{_KESME}]?\w*)")


def _sayi_sirasi_varyantlari(karsilik: str) -> list[str]:
    """Sayılı karşılığın Türkçe sıra-sayı dizilişi: "Kademe 2" -> "2. Kademe".

    Kalibrasyon (RSSG): kayıt "Kademe 2" iken çevirilerin bir kısmı doğru biçimde
    "2. Kademe" yazıyordu ve sahte sapma sayılıyordu."""
    sozcukler = karsilik.split()
    sayilar = [s for s in sozcukler if s.isdigit()]
    if len(sayilar) != 1 or len(sozcukler) < 2:
        return []
    geri = [s for s in sozcukler if not s.isdigit()]
    return [f"{sayilar[0]}. {' '.join(geri)}"]


def karsilik_gecer(karsilik: str, metin: str, gevsek: bool = False) -> bool:
    """Karşılık (çekimli hâlleri ve sayı sırası varyantı dahil) metinde geçiyor mu."""
    if not karsilik or not metin:
        return False
    return any(karsilik_deseni(k, gevsek).search(metin)
               for k in [karsilik, *_sayi_sirasi_varyantlari(karsilik)])


def ayni_karsilik(bicim: str, karsilik: str) -> bool:
    """Çeviride görülen biçim kayıtlı karşılığın (çekimli) bir hâli mi — harf işareti toleranslı.

    Kısaltılmış anma da aynı sayılır (biçim karşılığın başı: "Oyuk" ⊂ "Oyuk Dağı"):
    uzun adın kısa anılması bir sapma değildir. Boş taraf karar verdirmez (True)."""
    if not bicim or not karsilik:
        return True
    b, k = isaretsiz(bicim).strip(), isaretsiz(karsilik).strip()
    if b == k or k.startswith(b):
        return True
    m = karsilik_deseni(karsilik, gevsek=True).match(bicim.strip())
    return bool(m) and m.end() == len(bicim.strip())
