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

from core import glossary, library, translate  # noqa: E402


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


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", help="yalnız bu kitabın sözlüğü (slug)")
    ayristirici.add_argument("--uygula", action="store_true", help="önerileri DB'ye yaz")
    ayristirici.add_argument("--parti", type=int, default=40, help="çağrı başına ad sayısı")
    args = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
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
