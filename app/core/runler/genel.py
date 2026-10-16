"""Genel sistem mesajı algılayıcı — biçimi bilinmeyen kitap için (plan Faz 2).

Ayrıntılı ayrıştırma (`shadow_slave` gibi) kitaba özgüdür; bu modül yalnız HAM satır kümesi ve
anahtar sözlüğü üretir, bağ kurmaz. Üç satır türü:

  * `koseli` — tümü köşeli parantezde ("[...]", "【...】"),
  * `ses`    — profilin sistem sesiyle açılan satır ("System: ...", "System Announcement: ..."),
  * `anahtar` — "Anahtar: değer". Profilde `sistem_anahtarlari` varsa YALNIZ onlar; yoksa satır
    ancak bir sistem bloğunun içindeyse sayılır (köşeli/ses satırına bitişik ya da onlardan
    zincirle bağlı anahtar satırları).

Ölçülen gürültü (RSSG, 170 bölüm): "Translator:" 120, "Editor:" 17 satır — çevirmen künyesi;
`_KUNYE` hiçbir durumda sistem mesajı sayılmaz. Tırnak içeren satır diyalogdur, alınmaz.
"""
from __future__ import annotations

import re
from collections import Counter

# Tümü köşeli satır ya da köşeli BAŞLIK + parantezli ek ("[Ad] (Epic Rank, Level 30)": eşya kartı).
_KOSELI = re.compile(r"^(?:\[[^\[\]]+\]|【[^【】]+】)\s*(?:\([^()]{1,80}\))?[.!]?$")
# Değeri köşeli anahtar satırı ("Memory: [Ad]."): tek başına sistem satırıdır.
_KOSELI_DEGER = re.compile(r"^\[[^\[\]]+\](?:\s*,\s*\[[^\[\]]+\])*[.!]?$")
# Blok penceresi: anahtar satırı son sistem satırından en çok bu kadar satır sonra gelebilir
# (RSSG eşya kartında "Active Skill 1-" gibi başlık satırları araya giriyor).
BLOK_PENCERESI = 3
_ANAHTAR = re.compile(r"^([A-Z][A-Za-z' ]{0,30}[A-Za-z]):\s*(\S.*)$")
_TIRNAK = re.compile(r"[\"“”]")
# Web romanı sitelerinin künye satırları (kitaptan bağımsız).
_KUNYE = frozenset(("translator", "translators", "editor", "editors", "proofreader", "proofreaders",
                    "author", "tl", "ed", "pr", "tl note", "tl notes", "translated by", "edited by",
                    "source", "sponsored", "patreon", "discord"))
EN_UZUN_SATIR = 300


def _satirlar(metin: str):
    for i, paragraf in enumerate((metin or "").split("\n\n")):
        for satir in paragraf.split("\n"):
            t = satir.strip()
            if t:
                yield i, t


def _tur(t: str, sesler: tuple[str, ...]) -> tuple[str, str | None, str] | None:
    """(tür, anahtar, değer) ya da None. Bloğa bakmaz."""
    if len(t) > EN_UZUN_SATIR:
        return None
    if _KOSELI.match(t):
        return "koseli", None, t
    if _TIRNAK.search(t):
        return None
    m = _ANAHTAR.match(t)
    anahtar = m.group(1) if m else None
    if anahtar and anahtar.casefold() in _KUNYE:
        return None
    # Ses satırı iki noktalı anahtarla açılır ("System:", "System Announcement:"); yalnız
    # "System" sözcüğüyle başlayan anlatım cümlesi ses değildir.
    if anahtar and any(anahtar.casefold().startswith(ses.casefold()) for ses in sesler):
        return "ses", anahtar, m.group(2).strip()
    if m:
        deger = m.group(2).strip()
        return ("koseli_deger" if _KOSELI_DEGER.match(deger) else "anahtar"), anahtar, deger
    return None


def sistem_satirlari(metin: str, sesler=(), anahtarlar=()) -> list[dict]:
    """Bölüm metnindeki sistem mesajı satırları: [{"paragraf", "tur", "anahtar", "deger", "satir"}]."""
    sesler = tuple(s for s in sesler if s)
    izinli = {a.casefold() for a in anahtarlar if a}
    adaylar = [(i, t, _tur(t, sesler)) for i, t in _satirlar(metin)]
    guclu = ("koseli", "ses", "koseli_deger")
    out = []
    son_kabul = None  # son kabul edilen satırın sırası
    for j, (i, t, tur) in enumerate(adaylar):
        kabul = False
        if tur is not None:
            if tur[0] in guclu:
                kabul = True
            elif izinli:
                kabul = tur[1].casefold() in izinli
            else:
                # Profil anahtarı yok: blok içinde olmalı (son sistem satırının penceresinde ya da
                # hemen ardından güçlü bir sistem satırı geliyor).
                sonraki = adaylar[j + 1][2] if j + 1 < len(adaylar) else None
                kabul = ((son_kabul is not None and j - son_kabul <= BLOK_PENCERESI)
                         or (sonraki is not None and sonraki[0] in guclu))
        if kabul:
            out.append({"paragraf": i, "tur": "koseli" if tur[0] == "koseli_deger" else tur[0],
                        "anahtar": tur[1], "deger": tur[2], "satir": t})
            son_kabul = j
    return out


def anahtar_sozlugu(satirlar: list[dict]) -> Counter:
    """Anahtar -> geçiş sayısı (profil önerisi için: hangi anahtarlar bu kitabın sistem dili)."""
    return Counter(s["anahtar"] for s in satirlar if s["anahtar"])
