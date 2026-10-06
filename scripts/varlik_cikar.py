"""Varlık grafiğini MODEL çıkarımıyla doldur (bakım aracı) — `core.varlik_cikarim`.

KOTA / KREDİ HARCAR: bölüm başına bir istek. Varsayılan KURU çalıştırmadır.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\varlik_cikar.py --kitap shadow-slave
    ... --calistir --sinir 10 --rapor ornek.json        # ÖRNEK koşu, yazmaz
    ... --calistir --bolumler 100-110 --rapor r.json
    ... --calistir --uygula --model vertex/gemini-3.6-flash   # tüm kitap, yazar

`--model` verilmezse ücretsiz zincir kullanılır. Vertex ÜCRETLİDİR (Cloud
kredisinden); yalnız bu bayrakla, açıkça. Önce örnek koşunun raporunu oku: reddedilen
bağların sebepleri ve geçerli bağların kanıtları kesinliği ölçmenin yoludur.
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

from core import api_durum, cache, library, varlik_cikarim, varlik_grafigi  # noqa: E402


def _araliklar(metin: str) -> set[int]:
    out: set[int] = set()
    for parca in metin.split(","):
        if "-" in parca:
            a, b = parca.split("-")
            out |= set(range(int(a), int(b) + 1))
        elif parca.strip():
            out.add(int(parca))
    return out


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", required=True)
    ayristirici.add_argument("--calistir", action="store_true", help="modele sor (KOTA/KREDİ HARCAR)")
    ayristirici.add_argument("--uygula", action="store_true", help="geçerli bağları yaz")
    ayristirici.add_argument("--model", help="tek model (ör. vertex/gemini-3.6-flash); yoksa ücretsiz zincir")
    ayristirici.add_argument("--sinir", type=int, help="en çok bu kadar bölüm")
    ayristirici.add_argument("--bolumler", help="bölüm aralığı, ör. 100-110,250")
    ayristirici.add_argument("--rapor", help="sonucu JSON olarak yaz")
    args = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
    slug = library.resolve_slug(args.kitap)
    nolar = _araliklar(args.bolumler) if args.bolumler else None
    if not args.calistir:
        bolumler = [b for b in cache.kaynak_bolumleri(slug) if nolar is None or b["chapter_no"] in nolar]
        adet = min(len(bolumler), args.sinir or len(bolumler))
        print(f"{slug}: {adet} bölüm işlenecek = {adet} istek "
              f"({args.model or 'ücretsiz zincir'}). KURU — çalıştırmak için: --calistir")
        return 0
    models = (args.model,) if args.model else None
    with api_durum.islem("varlik_cikarim"):
        ozet = varlik_cikarim.kitabi_cikar(
            slug, models=models, bolum_nolari=nolar, sinir=args.sinir, yaz=args.uygula, ilerleme=print,
        )
    print(f"\n{ozet['bolum']} bölüm: {len(ozet['gecerli'])} geçerli bağ, {len(ozet['red'])} red, "
          f"{len(ozet['hata'])} hata")
    print("geçerli, ilişkiye göre:", dict(Counter(g["iliski"] for g in ozet["gecerli"]).most_common()))
    print("red sebepleri:", dict(Counter(r["sebep"] for r in ozet["red"]).most_common()))
    if ozet["yeni_adlar"]:
        print("sözlükte olmayan adlar:", sorted(ozet["yeni_adlar"].items(), key=lambda x: -x[1])[:30])
    if args.rapor:
        Path(args.rapor).write_text(json.dumps(ozet, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"rapor: {args.rapor}")
    if not args.uygula:
        print("Veritabanına yazılmadı. Yazmak için: --uygula")
    else:
        print(f"Grafikte toplam {len(varlik_grafigi.baglar(slug))} bağ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
