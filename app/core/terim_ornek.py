"""Terim kullanım örneği — DelTA tarzı (2026-10-17, plan Faz 4; deneysel, `CEVIRI_TERIM_ORNEK=1`).

DelTA (2024/25) özel ad kaydının yanında uzun süreli bellekten ilgili geçmiş cümle çiftlerini
ÖRNEK olarak getiriyor. Bizde sözlük kaydı zaten istemde; eksik olan, modelin bir terimi
kayıttan farklı çevirmeye devam ettiği yerde "bu kitapta bu terim böyle çevrildi" kanıtı.

Kapsam bilerek DAR (projenin dersi: yalnız hedefli, doğrulanmış bağlam; genel bellek ve özet
ölçümde kazanç vermedi):
  * Terim adayı = SON `GERI_BOLUM` hizalı bölümde kayıtlı karşılıktan SAPAN (`karsilik_sapmasi`)
    ya da İngilizce kalan (`sozluk_ihlali`) kayıt, VE bu bölümün kaynağında geçiyor.
  * Koşullu kayıt (`kosullar`) ve korunan ad (`X -> X`) ALINMAZ: koşullu terimin tek anlamlı
    örneği öteki anlamı yanlış yönlendirir (Saint A/B dersi); korunan adın örneğe ihtiyacı yok.
  * Örnek = önceki bölümlerden, kaynakta terimin ve çeviride KAYITLI karşılığın (Türkçe
    çekimleriyle) birlikte geçtiği EN YENİ kısa paragraf çifti. Yoksa terim atlanır.
  * En çok `EN_COK_TERIM` terim; parça başına yalnız o parçada geçenler. Yeni model çağrısı yok.
  * Gelecek bölüm hiçbir koşulda girmez (`cache.bellek_havuzu`, yalnız `chapter_no < N`).
Kapalıyken çeviri istemi bayt bayt aynıdır.
"""
from __future__ import annotations

import os
from collections import Counter

from . import cache, translate, turkce_eslesme

GERI_BOLUM = 30
EN_COK_TERIM = 5
ORNEK_UST_KARAKTER = 420  # örnek paragrafın İngilizce uzunluk sınırı (istem kısa kalsın)


def acik_mi() -> bool:
    return os.getenv("CEVIRI_TERIM_ORNEK", "0") == "1"


def sorunlu_terimler(havuz: list[dict], glossary: dict[str, str], kosullar: dict[str, str] | None) -> Counter:
    """Havuzdaki (önceki hizalı bölümler) sapma + ihlal sayısı, kaynak terime göre."""
    bolumler: dict[int, tuple[list[str], list[str]]] = {}
    for x in havuz:
        en, tr = bolumler.setdefault(x["bolum"], ([], []))
        en.append(x["en"])
        tr.append(x["tr"])
    sayac: Counter = Counter()
    for en, tr in bolumler.values():
        for bulgu in (translate.karsilik_sapmasi_paragraflari(glossary, tr, en, kosullar),
                      translate.sozluk_ihlali_paragraflari(glossary, tr, en, kosullar)):
            for terimler in bulgu.values():
                sayac.update(terimler.keys())
    return sayac


def ornek_bul(kaynak: str, karsilik: str, havuz: list[dict]) -> dict | None:
    """Terimin kayıtlı karşılıkla çevrildiği en yeni kısa paragraf çifti."""
    desen = translate._term_regex(kaynak)
    for x in sorted(havuz, key=lambda y: -y["bolum"]):
        if (len(x["en"]) <= ORNEK_UST_KARAKTER and desen.search(x["en"])
                and turkce_eslesme.karsilik_gecer(karsilik, x["tr"])):
            return {"bolum": x["bolum"], "en": x["en"], "tr": x["tr"]}
    return None


def secim(kaynak_metin: str, glossary: dict[str, str] | None, kosullar: dict[str, str] | None,
          havuz: list[dict]) -> list[dict]:
    """[{source, target, sapma, bolum, en, tr}] — sorunlu ve bu bölümde geçen terimler (saf)."""
    if not glossary or not kaynak_metin or not havuz:
        return []
    kosullu = {k.casefold() for k in (kosullar or {})}
    out = []
    for kaynak, sayi in sorunlu_terimler(havuz, glossary, kosullar).most_common():
        karsilik = glossary.get(kaynak)
        if (not karsilik or kaynak.casefold() in kosullu or kaynak.casefold() == karsilik.casefold()
                or not translate._term_regex(kaynak).search(kaynak_metin)):
            continue
        ornek = ornek_bul(kaynak, karsilik, havuz)
        if ornek:
            out.append({"source": kaynak, "target": karsilik, "sapma": sayi, **ornek})
        if len(out) >= EN_COK_TERIM:
            break
    return out


def hazirla(book_slug: str, bolum_no, kaynak_metin: str, glossary, kosullar) -> list[dict] | None:
    """Pipeline girişi: bayrak kapalıysa ya da seçilecek terim yoksa None."""
    if not acik_mi() or not book_slug or type(bolum_no) is not int:
        return None
    return secim(kaynak_metin, glossary, kosullar, cache.bellek_havuzu(book_slug, bolum_no, GERI_BOLUM)) or None


def metin(ornekler: list[dict] | None, en_paras: list[str]) -> str:
    """Parçanın istemine eklenecek blok; parçada geçen terim yoksa boş."""
    parca = "\n\n".join(en_paras)
    secilen = [o for o in ornekler or () if translate._term_regex(o["source"]).search(parca)]
    if not secilen:
        return ""
    satirlar = ["TERİM KULLANIM ÖRNEKLERİ (bu kitabın önceki bölümlerinden, kabul edilmiş çeviri). "
                "Bu terimler son bölümlerde sözlükteki karşılıktan farklı çevrildi; sözlük karşılığını "
                "örnekteki gibi kullan. Örnekleri ÇEVİRME, yalnız terimin nasıl kullanıldığını gör."]
    for o in secilen:
        satirlar.append(f"- {o['source']} -> {o['target']} (bölüm {o['bolum']})\n  EN: {o['en']}\n  TR: {o['tr']}")
    return "\n".join(satirlar)
