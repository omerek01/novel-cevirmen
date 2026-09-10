"""Sözlükte İNGİLİZCE KORUNAN kayıtları gözden geçir (bakım aracı).

Neden var: sözlük kuralı "karakter adı İngilizce kalır, karakter dışı HER özel ad
Türkçeleşir" olsa da model karakter olmayan adları uzun süre `detected_names`
kutusuna sızdırdı ve bu adlar sözlüğe `X -> X` diye çakıldı (ölçüm: bir kitapta
201 kaydın 173'ü). Sözlük prompt'ta KURALdır — böyle bir kayıt duran bir ad, yeni
bölümlerde de asla Türkçeleşmez. Çeviri yolundaki süzgeç (`translate.ayikla_
karakter_adlari`) yalnız BUNDAN SONRASINI korur; eski kayıtları bu araç temizler.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\sozluk_gozden_gecir.py            # RAPOR (yazmaz)
    .venv\\Scripts\\python.exe scripts\\sozluk_gozden_gecir.py --uygula   # önerileri yaz
    ... --kitap shadow-slave        # tek kitap
    ... --parti 30                  # tek Gemini çağrısına giren ad sayısı

Varsayılan KURU çalıştırmadır: ne değişeceğini gösterir, DB'ye dokunmaz. Karar
modele bırakılır ama kural nettir ve model tereddütte "karakter" demeye zorlanır
(bkz. translate.CLASSIFY_INSTRUCTION) — yanlış Türkçeleştirme, karakterin adını
kitap boyunca bozacağı için İngilizce bırakmaktan daha pahalıdır.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

from core import cache, glossary, library, translate  # noqa: E402


# Kaynak metin kapsaması bu oranın ALTINDAysa 'ölü kayıt' raporu o kitabı
# ATLAR. Kapsama düşükken 'hiçbir bölümde geçmiyor' demek yanıltıcıdır ve
# meşru bir kaydı sildirir; sözlükten düşen ad her bölümde yeniden karar
# konusu olur — fazladan bir satırın bedelinden çok daha pahalı.
MIN_KAYNAK_KAPSAMA = 0.8


def ingilizce_kalanlar(kitap: str | None) -> dict[str, list[str]]:
    """Kitap slug'ı -> karşılığı kaynağın AYNISI olan kayıtların kaynakları.

    Yazım varyantı da aynı sayılır (`fold_term`): "Ore Empire -> OreEmpire" gibi bir
    kayıt da fiilen "İngilizce korunuyor" demektir.
    """
    out: dict[str, list[str]] = {}
    for slug, kaynak, hedef in glossary.all_terms(kitap):
        if glossary.fold_term(kaynak) == glossary.fold_term(hedef or ""):
            out.setdefault(slug, []).append(kaynak)
    return out


def partiler(adlar: list[str], boyut: int):
    for i in range(0, len(adlar), boyut):
        yield adlar[i : i + boyut]


def kitap_slaglari(kitap: str | None) -> list[str]:
    if kitap:
        return [kitap]
    return sorted({slug for slug, _kaynak, _hedef in glossary.all_terms()})


def baslik(slug: str) -> str:
    return (library.get_book(slug) or {}).get("title") or slug


def rapor_olu(kitap: str | None, uygula: bool) -> int:
    """Kaynağı kitabın HİÇBİR bölümünde geçmeyen satırlar (uydurma / eskimiş kayıt).

    Ölçülen vaka: bir kitabın sözlüğünde BAŞKA kitapların karakterleri vardı
    (`Kim Dokja`, `Sunny`) — modelin sistem talimatındaki örneklerden sızdırdığı,
    o kitapta hiç geçmeyen adlar.
    """
    toplam = 0
    for slug in kitap_slaglari(kitap):
        sozluk = glossary.get_glossary(slug)
        if not sozluk:
            continue
        bolum, kapsanan, metin = cache.kaynak_kapsamasi(slug)
        if not bolum or kapsanan / bolum < MIN_KAYNAK_KAPSAMA:
            print(f"\n=== {baslik(slug)} ({slug})")
            print(f"  ATLANDI — kaynak metin kapsaması düşük ({kapsanan}/{bolum} bölüm).")
            print("  Bu kitapta 'geçmiyor' demek yanıltıcı olur; meşru kayıt silinebilir.")
            continue
        olu = [k for k in sozluk if not translate._term_regex(k).search(metin)]
        print(f"\n=== {baslik(slug)} ({slug}) — {len(olu)}/{len(sozluk)} ölü "
              f"(kapsama {kapsanan}/{bolum} bölüm)")
        for k in sorted(olu):
            print(f"  {k}  ->  {sozluk[k]}")
            if uygula:
                glossary.delete_term(slug, k)
        toplam += len(olu)
    return toplam


def rapor_cakisan(kitap: str | None) -> int:
    """Aynı Türkçe karşılığa giden farklı kaynaklar. Otomatik eylem YOK."""
    toplam = 0
    for slug in kitap_slaglari(kitap):
        ciftler = glossary.karsilik_cakismalari(slug)
        if not ciftler:
            continue
        print(f"\n=== {baslik(slug)} ({slug})")
        sozluk = glossary.get_glossary(slug)
        for _anahtar, kaynaklar in ciftler:
            print(f"  {sozluk[kaynaklar[0]]!r}  <-  {', '.join(kaynaklar)}")
            toplam += 1
    print("\nKasıtlı olabilir (aynı varlığın iki yazımı) ya da iki ayrı şeyi")
    print("çeviride ayırt edilemez kılıyor olabilir. Karar senin.")
    return toplam


def rapor_kardes(kitap: str | None) -> int:
    """Ortak kelime taşıyan terimlerde büyük-harf stili ayrışması (tel tuzağı)."""
    toplam = 0
    for slug in kitap_slaglari(kitap):
        gruplar = glossary.kardes_tutarsizliklari(slug)
        if not gruplar:
            continue
        print(f"\n=== {baslik(slug)} ({slug})")
        for kelime, uyeler in gruplar:
            print(f"  ortak kelime: {kelime!r}")
            for kaynak, hedef in uyeler:
                print(f"      {kaynak}  ->  {hedef}")
            toplam += 1
    return toplam


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", help="yalnız bu kitabın sözlüğü (slug)")
    ayristirici.add_argument("--uygula", action="store_true", help="önerileri DB'ye yaz")
    ayristirici.add_argument("--parti", type=int, default=40, help="çağrı başına ad sayısı")
    # ÇEVRİMDIŞI rapor kipleri: model çağrısı yok, GEMINI_API_KEY gerekmez.
    ayristirici.add_argument("--olu", action="store_true",
                             help="kaynağı hiçbir bölümde geçmeyen kayıtlar (rapor)")
    ayristirici.add_argument("--cakisan", action="store_true",
                             help="aynı Türkçe karşılığa giden farklı kaynaklar (rapor)")
    ayristirici.add_argument("--kardes", action="store_true",
                             help="ortak kelimeli terimlerde yazım ayrışması (rapor)")
    args = ayristirici.parse_args()

    load_dotenv(KOK / ".env")

    # Rapor kipleri sınıflandırma yapmaz → anahtar istemez, erken döner.
    if args.olu or args.cakisan or args.kardes:
        n = 0
        if args.olu:
            n += rapor_olu(args.kitap, args.uygula)
        if args.cakisan:
            n += rapor_cakisan(args.kitap)
        if args.kardes:
            n += rapor_kardes(args.kitap)
        if not n:
            print("\nBulgu yok.")
        elif args.olu and args.uygula:
            print(f"\n{n} kayıt işlendi (ölü kayıtlar silindi).")
        else:
            print(f"\n{n} bulgu.")
            # Silme önerisi YALNIZ ölü kayıt kipinde: çakışan/kardeş bulguları
            # otomatik eylem istemiyor, karar kullanıcınındır.
            if args.olu:
                print("Ölü kayıtları silmek için: --olu --uygula")
        return 0
    anahtar = os.getenv("GEMINI_API_KEY", "")
    if not anahtar:
        print("GEMINI_API_KEY yok (.env). Sınıflandırma için gerekli.")
        return 1

    hedefler = ingilizce_kalanlar(args.kitap)
    if not hedefler:
        print("İngilizce korunan kayıt yok — sözlük temiz.")
        return 0

    toplam_degisecek = 0
    for slug, adlar in hedefler.items():
        kitap = library.get_book(slug) or {}
        baslik = kitap.get("title") or slug
        print(f"\n=== {baslik} ({slug}) — {len(adlar)} İngilizce kayıt")
        oneriler: dict[str, dict] = {}
        for parti in partiler(adlar, args.parti):
            try:
                oneriler.update(translate.classify_terms(parti, anahtar, book_title=baslik))
            except translate.TranslateError as hata:
                print(f"  ! sınıflandırma başarısız ({hata}) — bu parti atlandı")
        degisecek = [
            (kaynak, o["target"])
            for kaynak, o in oneriler.items()
            if not o["is_character"] and o["target"] != kaynak
        ]
        korunan = len(adlar) - len(degisecek)
        for kaynak, hedef in degisecek:
            print(f"  {kaynak}  ->  {hedef}")
            if args.uygula:
                glossary.set_term(slug, kaynak, hedef)
        print(f"  ({korunan} kayıt karakter sayıldı, İngilizce kalıyor)")
        toplam_degisecek += len(degisecek)

    if args.uygula:
        print(f"\n{toplam_degisecek} kayıt Türkçeleştirildi.")
        print("Not: YALNIZ bundan sonra çevrilecek bölümleri etkiler; eski bölümler")
        print("okuyucudaki 'Yeniden çevir' ile tazelenir.")
    else:
        print(f"\nKURU ÇALIŞTIRMA: {toplam_degisecek} kayıt değişecekti.")
        print("Yazmak için: --uygula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
