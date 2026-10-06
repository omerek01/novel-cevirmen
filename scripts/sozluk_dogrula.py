"""Sözlük kayıtlarını MODELLE doğrula (bakım aracı) — `core.sozluk_dogrulama`.

Deterministik denetim (`scripts/sozluk_denetle.py`) biçimi, sayıyı, çakışmayı ve
varyantı yakalar; ANLAMI yakalayamaz (`God of Death -> Savaş Tanrısı`,
`Corruption -> Yolsuzluk`). Bu araç her kaydı bağlam cümleleriyle ücretsiz
zincire sorar: tür, tanım, geri çeviri, uygunluk, sıradan sözcük mü.

KOTA HARCAR (ücretsiz zincir, parti başına bir istek; 1100 kayıt ≈ 45 istek).
Ücretli model ASLA kullanılmaz. Varsayılan KURU çalıştırmadır: kaç kayıt ve kaç
istek olacağını söyler, hiçbir şey çağırmaz.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\sozluk_dogrula.py --kitap shadow-slave
    ... --calistir --cikti dogrulama.json      # modele sor, sonucu dosyaya yaz
    ... --rapordan dogrulama.json --uygula     # dosyadaki sonuçları DB'ye işle
    ... --calistir --uygula                    # sor ve hemen işle
    ... --kapsam yeni                          # yalnız doğrulanmamış otomatik kayıtlar

Rapor dosyası ayrı tutulur: doğrulama bir yerde (anahtarlı makine) koşup sonucu
sunucudaki veritabanına KOTA HARCAMADAN uygulamak için.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

from core import api_durum, glossary, library, sozluk_dogrulama  # noqa: E402


def ozet(sonuclar: list[dict]) -> None:
    sayac = Counter(x["sonuc"] for x in sonuclar)
    print(f"\n{len(sonuclar)} kayıt: {sayac.get('gecti', 0)} geçti, {sayac.get('sorunlu', 0)} sorunlu")
    for x in sorted((x for x in sonuclar if x["sonuc"] == "sorunlu"), key=lambda x: x["source"].casefold()):
        n = x.get("not") or {}
        print(f"  {x['source']} -> {x.get('target')}")
        if n.get("geri_ceviri"):
            print(f"      geri çeviri: {n['geri_ceviri']}  (uyum {n.get('uyum')})")
        if n.get("sorun"):
            print(f"      sorun: {n['sorun']}")
        if n.get("oneri"):
            print(f"      öneri: {n['oneri']}")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", required=True)
    ayristirici.add_argument("--kapsam", choices=("hepsi", "yeni", "eksik"), default="hepsi",
                             help="eksik: hiç doğrulanmamış bütün kayıtlar (yarıda kalan koşuyu tamamlar)")
    ayristirici.add_argument("--model", help="tek model (ör. vertex/gemini-3.6-flash — ÜCRETLİ); yoksa ücretsiz zincir")
    ayristirici.add_argument("--calistir", action="store_true", help="modele sor (KOTA HARCAR)")
    ayristirici.add_argument("--cikti", help="sonuçları bu JSON dosyasına yaz")
    ayristirici.add_argument("--rapordan", help="model çağırmadan bu JSON dosyasındaki sonuçları kullan")
    ayristirici.add_argument("--uygula", action="store_true", help="sonuçları veritabanına işle")
    ayristirici.add_argument("--sinir", type=int, help="en çok bu kadar kayıt (deneme)")
    ayristirici.add_argument("--parti", type=int, default=sozluk_dogrulama.PARTI)
    args = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
    slug = library.resolve_slug(args.kitap)

    if args.rapordan:
        sonuclar = json.loads(Path(args.rapordan).read_text(encoding="utf-8"))
    elif args.calistir:
        with api_durum.islem("sozluk_dogrulama"):
            sonuclar = sozluk_dogrulama.kitabi_dogrula(
                slug, args.kapsam, parti=args.parti, sinir=args.sinir, yaz=False, ilerleme=print,
                models=(args.model,) if args.model else None,
            )
    else:
        satirlar = glossary.get_glossary_rows(slug)
        if args.kapsam == "yeni":
            satirlar = [r for r in satirlar if not r.get("dogrulama") and r.get("origin") == "auto"]
        elif args.kapsam == "eksik":
            satirlar = [r for r in satirlar if not r.get("dogrulama")]
        adet = min(len(satirlar), args.sinir or len(satirlar))
        print(f"{slug}: {adet} kayıt doğrulanacak, ~{-(-adet // args.parti)} istek "
              f"(zincir: {', '.join(sozluk_dogrulama.ucretsiz_zincir())}).")
        print("KURU çalıştırma — modele sormak için: --calistir")
        return 0

    ozet(sonuclar)
    if args.cikti:
        Path(args.cikti).write_text(json.dumps(sonuclar, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nRapor: {args.cikti}")
    if args.uygula:
        for x in sonuclar:
            sozluk_dogrulama.sonucu_yaz(slug, x)
        print(f"\n{len(sonuclar)} sonuç işlendi (sorunlular inceleme listesinde; karşılıklar değişmedi).")
    else:
        print("\nVeritabanına yazılmadı. İşlemek için: --uygula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
