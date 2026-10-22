"""Sistem mesajı (rün) okuyucuları — biçim seçimi ve ortak sözleşme (plan Faz 2).

Kitabın sistem mesajı BİÇİMİ kitaba özgüdür (Shadow Slave'de Spell rünleri). Biçim modülü
profilin `run_bicimi` alanıyla seçilir; biçimi olmayan kitapta ayrıntılı ayrıştırma ve
sistem bağları yoktur (genel algılayıcı yalnız ham satırları listeler: `genel`).

Biçim modülü arayüzü:
  * `sistem_baglarini_bul(metin, ana_karakter, ana_adlar=(), paydalar=None, anilar=None)`
    -> [(özne, ilişki, nesne, kanıt)]; değer satırı ilişki olarak `DEGER` taşır, TAM envanter
    listesi (`Memories: [..]`) ayrıca `ENVANTER` taşır (nesne: "tür\t[json adlar]"),
  * `evrimleri_esle(bulunan, durum, bolum_no)` -> dönüşüm bağlarıyla güncel liste,
  * isteğe bağlı `siniftan_turet(run, sinif, basamak)` ve `tutarlilik(run, golge_sayisi)`.
"""
from __future__ import annotations

import importlib
import re
from types import ModuleType

DEGER = "_deger"  # (özne, DEGER, "anahtar\tdeğer", kanıt)
# (özne, ENVANTER, "ani|golge|yanki|nitelik\t[json adlar]", kanıt): öznenin o anki TAM listesi.
# Bağ değildir; listede olmayan eski öğe "artık yok" sayılır (`defter_kayit`).
ENVANTER = "_envanter"
# Bilinen biçimler: profil değeri -> modül adı. Yeni kitap biçimi = yeni modül + kayıt.
BICIMLER = {"shadow_slave": "shadow_slave"}
_PAYDA = re.compile(r"^\s*\d+\s*/\s*(\d+)\s*$")


def payda(deger: str | None) -> int | None:
    """"870/4000" -> 4000; sayaç değilse None."""
    m = _PAYDA.match(deger or "")
    return int(m.group(1)) if m else None


def bicim(p: dict | None) -> ModuleType | None:
    """Profilin rün biçimi modülü; biçim yoksa ya da bilinmiyorsa None."""
    ad = BICIMLER.get((p or {}).get("run_bicimi") or "")
    return importlib.import_module(f"{__name__}.{ad}") if ad else None
