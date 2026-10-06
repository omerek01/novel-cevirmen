"""Sözlüğün TAMAMINI yazma kapısının kurallarıyla geriye dönük denetle (bakım aracı).

Neden var: yazma kapısı (`core.sozluk_kapi`) yalnız BUNDAN SONRA eklenecek otomatik
adayları durdurur. Sözlükte zaten duran kayıtlar (Shadow Slave'de 1100) kapıdan
hiç geçmedi; ölçülen bozuklukların hepsi orada (`Weaver -> Weaver’s`, `Seven ->
Yediler`, `daemon -> Şeytan` = `Devil -> Şeytan`). Bu araç aynı kuralları her
kayda, ÖTEKİ kayıtlara karşı uygular; ayrıca kalıp (aile) tutarlılığını ve iyi
modellerin ısrarla uymadığı kayıtları (ihlal şüphesi, bütün bölümler yeniden
ölçülerek) raporlar.

API ÇAĞIRMAZ, kota yakmaz. Varsayılan KURU çalıştırmadır.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\sozluk_denetle.py --kitap shadow-slave
    ... --isaretle     # bulguları kayıtlara yaz (kayıt KURAL kalır, incelemeye düşer)
    ... --json rapor.json   # makine-okur rapor

`--isaretle` kaydın karşılığını DEĞİŞTİRMEZ ve onu prompt'tan ÇIKARMAZ: bugün
çeviride kullanılan bir terimi sessizce çekip almak kullanıcının bilmediği bir
davranış değişikliği olurdu. Kayıt inceleme listesine nedenleriyle düşer; karar
okuyucunun sözlük ekranında verilir.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import cache, glossary, library, sozluk_kapi, varlik_grafigi  # noqa: E402

ETIKET = {
    "bicim": "BİÇİM HATASI",
    "yasak_karsilik": "YASAK KARŞILIK",
    "karsilik_cakismasi": "İKİ KAVRAM, TEK KARŞILIK",
    "ihlal_suphesi": "İYİ MODELLER UYMUYOR",
    "sayi_uyumsuzlugu": "TEKİL / ÇOĞUL UYUMSUZ",
    "politika": "KATEGORİ POLİTİKASINA AYKIRI",
    "yakin_yazim": "AYNI ADIN YAZIMLARI",
    "kalip_tutarsizligi": "AİLE İÇİ YAZIM AYRIŞMASI",
    "sozcuk_karismasi": "BAŞKA SINIFIN SÖZCÜĞÜ (grafik)",
    "ad_tutarliligi": "AYNI KİŞİNİN ADLARI KARIŞIK (grafik)",
}


def denetle(slug: str) -> dict[str, list[dict]]:
    satirlar = glossary.get_glossary_rows(slug)
    _t, _k, korpus = cache.kaynak_kapsamasi(slug)
    sonuc = sozluk_kapi.sozlugu_denetle(
        satirlar, glossary.yasaklar(slug), glossary.politikalar(slug), korpus
    )
    for kaynak, n in sozluk_kapi.ihlal_supheleri(slug, {r["source"] for r in satirlar}, tam=True).items():
        sonuc.setdefault(kaynak, []).append(n)
    # Varlık grafiği varsa (`scripts/varlik_grafigi.py`) onun kuralları da.
    for kaynak, liste in varlik_grafigi.kalite_nedenleri(slug).items():
        sonuc.setdefault(kaynak, []).extend(liste)
    return sonuc


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", required=True, help="kitap slug'ı")
    ayristirici.add_argument("--isaretle", action="store_true",
                             help="bulguları kayıtlara yaz (incelemeye düşür)")
    ayristirici.add_argument("--json", help="raporu bu dosyaya JSON olarak da yaz")
    args = ayristirici.parse_args()

    slug = library.resolve_slug(args.kitap)
    satirlar = {r["source"]: r for r in glossary.get_glossary_rows(slug)}
    sonuc = denetle(slug)
    sayac = Counter(n["tur"] for liste in sonuc.values() for n in liste)
    print(f"=== {slug}: {len(satirlar)} kayıt, {len(sonuc)} kayıtta bulgu")
    for tur, adet in sayac.most_common():
        print(f"  {ETIKET.get(tur, tur):32} {adet}")
    for tur in ETIKET:
        bulgular = [(k, n) for k, liste in sonuc.items() for n in liste if n["tur"] == tur]
        if not bulgular:
            continue
        print(f"\n--- {ETIKET[tur]} ({len(bulgular)})")
        for kaynak, n in sorted(bulgular, key=lambda x: x[0].casefold()):
            hedef = (satirlar.get(kaynak) or {}).get("target")
            print(f"  {kaynak} -> {hedef}")
            print(f"      {n['aciklama']}")
    if args.json:
        Path(args.json).write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON rapor: {args.json}")
    if args.isaretle:
        n = glossary.kapi_isaretle(slug, sonuc)
        print(f"\n{n} kayıt işaretlendi (inceleme listesine düştü; karşılıklar değişmedi).")
    else:
        print("\nKURU çalıştırma — hiçbir şey yazılmadı. İnceleme listesine düşürmek için: --isaretle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
