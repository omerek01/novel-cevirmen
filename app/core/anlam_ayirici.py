"""Çift anlamlı sözlük kaydının metindeki HER geçişini sınıfla (deterministik, API'siz).

Neden var (2026-10-07, kullanıcı bildirimi): "Sunny'nin gölgesi Saint ile Aziz rütbesi
olan Saint karışıyordu." Sözlükte tek kayıt var (`Saint -> Aziz [KOŞUL: yalnız rütbe]`)
ve ayrımı model her geçişte kendisi yapıyordu; uyum denetimi koşullu kayıtları
ÖLÇEMEDİĞİ için hata hiçbir sayıya yansımıyordu. Bu modül geçişi üç sınıftan birine
koyar:

  * `taban`    — kaydın asıl anlamı (rütbe: "a Saint", "Saints", "Saint Tyris"),
  * `anlam`    — ikinci anlam (gölgenin ADI: "summoned Saint", "Saint and Nightmare"),
  * `belirsiz` — kural karar veremiyor ("the Saint"); model ve künye bilgisine kalır.

Kurallar kitap profilindedir (`varlik_grafigi.KITAP_PROFILLERI[...]["anlam_dugumleri"]
[kayıt]["ayirici"]`) ve ölçülerek kondu: Saint kitapta 1.099 kez geçiyor; artikelsiz
yalın kullanım (505) 106. bölümden sonra rastgele 40 örnekte ~%88 gölge, belirsiz
artikelli kullanım rütbe; "the Saint" iki anlama da gidiyor.
"""
from __future__ import annotations

import re

# Büyük harfle başlayıp AD sayılmayacak sözcükler ("Saint. The..." değil, "Saint Tyris").
_AD_DEGIL = frozenset(("The", "He", "She", "It", "They", "But", "And", "Then", "His", "Her", "I", "A", "An"))
_BELIRSIZ_ARTIKEL = re.compile(r"\b(?:a|an|another|every|no|any|one)\s+(?:[A-Za-z]+\s+)?$", re.IGNORECASE)
_BELIRLI_ARTIKEL = re.compile(r"\bthe\s+(?:[a-z]+\s+)?$", re.IGNORECASE)
_SONRAKI_SOZCUK = re.compile(r"\s+([A-Z][a-z]+)")


def gecisleri_siniflandir(paragraf: str, kayit: str, bolum_no: int | None, kural: dict) -> list[tuple[int, str]]:
    """Paragraftaki `kayit` geçişlerinin (başlangıç, sınıf) listesi.

    `kural` (profil): {"baslangic_bolumu": ikinci anlamın ilk bölümü,
    "bicim_onekleri": ayrı kayıt olan bileşikler ("Stone" -> "Stone Saint" atlanır),
    "taban_oncesi": tabanı kesinleştiren önceki sözcükler (rank, Masters...)}."""
    desen = re.compile(rf"\b{re.escape(kayit)}(s)?\b")
    onekler = tuple(kural.get("bicim_onekleri", ()))
    taban_oncesi = re.compile(
        r"\b(?:" + "|".join(map(re.escape, kural.get("taban_oncesi", ()))) + r")\s+(?:of\s+|and\s+|or\s+)?(?:a\s+)?$",
        re.IGNORECASE,
    ) if kural.get("taban_oncesi") else None
    out: list[tuple[int, str]] = []
    for m in desen.finditer(paragraf):
        once, sonra = paragraf[:m.start()], paragraf[m.end():]
        if onekler and re.search(r"\b(?:" + "|".join(map(re.escape, onekler)) + r")\s+$", once):
            continue  # ayrı sözlük kaydının parçası (Stone Saint)
        if bolum_no is not None and bolum_no < kural.get("baslangic_bolumu", 0):
            out.append((m.start(), "taban"))
            continue
        if m.group(1) and not sonra.startswith(("'", "’")):
            out.append((m.start(), "taban"))  # çoğul: Saints
            continue
        sonraki = _SONRAKI_SOZCUK.match(sonra)
        if sonraki and sonraki.group(1) not in _AD_DEGIL:
            out.append((m.start(), "taban"))  # unvan + ad: Saint Tyris
            continue
        if _BELIRSIZ_ARTIKEL.search(once) or (taban_oncesi and taban_oncesi.search(once)):
            out.append((m.start(), "taban"))
            continue
        if _BELIRLI_ARTIKEL.search(once):
            out.append((m.start(), "belirsiz"))
            continue
        out.append((m.start(), "anlam"))  # artikelsiz yalın kullanım: ad
    return out


def paragraf_isaretleri(paragraflar: list[str], kayit: str, bolum_no: int | None, kural: dict) -> dict[int, set[str]]:
    """{paragraf sırası: {sınıflar}} — yalnız KESİN sınıflanan geçişi olan paragraflar."""
    out: dict[int, set[str]] = {}
    for i, par in enumerate(paragraflar):
        siniflar = {s for _b, s in gecisleri_siniflandir(par, kayit, bolum_no, kural) if s != "belirsiz"}
        if siniflar:
            out[i] = siniflar
    return out
