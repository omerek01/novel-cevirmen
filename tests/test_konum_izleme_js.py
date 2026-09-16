"""Okuyucu dışındaki bölüm GET'leri okuma konumunu İLERLETMEMELİ (track=0).

`GET /api/chapter` varsayılan olarak kitabın "kaldığın yer" konumunu o bölüme
taşır. Gerçek bulgu (2026-09-16): elle "çevrimdışı indir" bölümleri track'siz
çekiyordu ve okuma konumu listedeki SON indirilen bölüme kayıyordu; çift dokunuşla
İngilizce kaynağı getirmek de aynı şeyi yapıyordu. Konumu yalnız okuyucunun
kendi yolu (`fetchChapterData`, track parametresi açık) belirler.
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "app" / "web"


def test_sabit_bolum_getleri_track0_tasir():
    ihlaller = []
    for dosya in sorted((WEB / "js").glob("*.js")):
        metin = dosya.read_text(encoding="utf-8")
        for m in re.finditer(r"fetch\(\s*`/api/chapter\?url=[^`]*`(\s*,\s*\{[^}]*\})?", metin):
            parca = m.group(0)
            if "DELETE" in parca:
                continue
            if "track=0" not in parca:
                satir = metin.count("\n", 0, m.start()) + 1
                ihlaller.append(f"{dosya.name}:{satir}: {parca[:90]}")
    assert not ihlaller, "track=0 olmayan bölüm GET'i:\n" + "\n".join(ihlaller)


def test_okuyucu_yolu_track_parametresini_tasir():
    metin = (WEB / "js" / "okuyucu.js").read_text(encoding="utf-8")
    assert '(track ? "" : "&track=0")' in metin
