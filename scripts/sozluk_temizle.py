"""Eski hatalı sözlük kayıtlarının temizliği (bkz. app/core/sozluk_temizlik.py).

  kuru (vars.)         : vakaları kur ve listele — API'siz, yazmaz
  --calistir --cikti F : ücretsiz zincire sor, önerileri F'ye yaz — KOTA HARCAR, DB'ye yazmaz
  --rapordan F --uygula: F'de `onay: true` işaretlenmiş önerileri uygula — DB'ye YAZAR

Sunucuda önce yedek: cp cache/chapters.db cache/chapters.db.yedek-<tarih> (WAL açıkken backup API).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from core import sozluk_temizlik  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--kitap", required=True)
    a.add_argument("--calistir", action="store_true")
    a.add_argument("--cikti")
    a.add_argument("--sinir", type=int, help="en çok bu kadar vaka (deneme)")
    a.add_argument("--rapordan")
    a.add_argument("--uygula", action="store_true")
    args = a.parse_args()
    if args.rapordan:
        oneriler = json.loads(Path(args.rapordan).read_text(encoding="utf-8"))["oneriler"]
        onayli = [x for x in oneriler if x.get("onay") is True]
        print(f"{len(onayli)} onaylı öneri / {len(oneriler)}")
        if not args.uygula:
            print("KURU — uygulamak için --uygula")
            return 0
        rapor = sozluk_temizlik.onerileri_uygula(args.kitap, oneriler)
        print(json.dumps([dict(source=r["source"], islem=r["islem"], uygulandi=r["uygulandi"],
                               neden=r.get("neden")) for r in rapor], ensure_ascii=False, indent=1))
        return 0
    vakalar = sozluk_temizlik.vakalari_kur(args.kitap)
    if args.sinir:
        vakalar = vakalar[:args.sinir]
    print(f"{len(vakalar)} vaka, {sum(len(v['kayitlar']) for v in vakalar)} kayıt")
    if not args.calistir:
        for v in vakalar[:40]:
            print(f"  {v['id']}: " + " | ".join(f"{k['source']} -> {k['target']}" for k in v["kayitlar"]))
        print("KURU — modele sormak için --calistir --cikti F")
        return 0
    oneriler = sozluk_temizlik.vakalari_sor(args.kitap, vakalar, ilerleme=print)
    if args.cikti:
        Path(args.cikti).write_text(json.dumps(dict(kitap=args.kitap, vakalar=vakalar, oneriler=oneriler),
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    sayim = {}
    for x in oneriler:
        k = (x.get("islem") or "-", x["durum"])
        sayim[k] = sayim.get(k, 0) + 1
    print(sayim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
