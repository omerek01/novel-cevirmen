"""Kitap düzeyi örneklemeli terim taraması (bkz. app/core/sozluk_tarama.py).

  --tur N --cikti F : N tur (her tur farklı tohum = farklı parçalar, BİR model isteği) — KOTA HARCAR,
                      DB'ye yazmaz; adaylar F'ye
  --rapordan F --uygula : F'de `onay: true` işaretlenmiş adayları yazma kapısından geçirerek ekle
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from core import sozluk_tarama  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--kitap", required=True)
    a.add_argument("--tur", type=int, default=1)
    a.add_argument("--tohum", type=int, default=1)
    a.add_argument("--cikti")
    a.add_argument("--rapordan")
    a.add_argument("--uygula", action="store_true")
    args = a.parse_args()
    if args.rapordan:
        adaylar = [x for t in json.loads(Path(args.rapordan).read_text(encoding="utf-8"))["turlar"] for x in t["adaylar"]]
        if not args.uygula:
            print(f"{sum(1 for x in adaylar if x.get('onay') is True)} onaylı aday — KURU, uygulamak için --uygula")
            return 0
        print(json.dumps(sozluk_tarama.onaylananlari_ekle(args.kitap, adaylar), ensure_ascii=False, indent=1))
        return 0
    turlar, onceki = [], set()
    for i in range(args.tur):
        t = sozluk_tarama.tara(args.kitap, args.tohum + i)
        yeni = [x for x in t["adaylar"] if x["durum"] == "aday" and x["source"].casefold() not in onceki]
        onceki |= {x["source"].casefold() for x in t["adaylar"] if x["durum"] == "aday"}
        say = {}
        for x in t["adaylar"]:
            say[x["durum"]] = say.get(x["durum"], 0) + 1
        print(f"tur {i + 1} (tohum {t['tohum']}, {t['model']}): öneri {t['oneri']}, {say}, önceki turlarda olmayan aday {len(yeni)}")
        turlar.append(t)
    if args.cikti:
        Path(args.cikti).write_text(json.dumps(dict(kitap=args.kitap, turlar=turlar), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
