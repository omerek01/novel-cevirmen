"""Varlık grafiğindeki EKSİK bağları bul ve doldur (bakım aracı) — `core.varlik_bosluk`.

Ortak geçiş: kitapta sık birlikte geçen ama bağı olmayan çiftler (API'siz).
`--calistir` bu çiftleri, birlikte geçtikleri cümlelerle modele sorar (KOTA/KREDİ).
Varsayılan KURU: yalnız aday çiftleri listeler.

    .venv\\Scripts\\python.exe scripts\\varlik_bosluk.py --kitap shadow-slave
    ... --calistir --sinir 30 --rapor r.json              # örnek, yazmaz
    ... --calistir --uygula --model vertex/gemini-3.6-flash
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

from core import api_durum, cache, library, translate, varlik_bosluk, varlik_cikarim, varlik_grafigi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--en-az", type=int, default=varlik_bosluk.EN_AZ_ORTAK)
    ap.add_argument("--sinir", type=int, help="en çok bu kadar çift")
    ap.add_argument("--calistir", action="store_true")
    ap.add_argument("--uygula", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--rapor")
    args = ap.parse_args()
    load_dotenv(KOK / ".env")
    slug = library.resolve_slug(args.kitap)
    _t, _k, korpus = cache.kaynak_kapsamasi(slug)
    ciftler = varlik_bosluk.ortak_gecisler(slug, args.en_az, korpus)
    if args.sinir:
        ciftler = ciftler[:args.sinir]
    print(f"{slug}: bağı olmayan {len(ciftler)} sık çift (en az {args.en_az} ortak cümle)")
    for c in ciftler[:30]:
        print(f"  {c['sayi']:4}  ilk#{c['ilk_bolum']:<4} {c['a']} <-> {c['b']}")
    if not args.calistir:
        print(f"KURU — sormak için: --calistir (~{-(-len(ciftler) // varlik_cikarim.CIFT_PARTI)} istek)")
        return 0
    cozucu = varlik_grafigi.DugumCozucu(slug)
    kategoriler = varlik_grafigi.kategori_kimlikleri(slug, cozucu, korpus)
    models = (args.model,) if args.model else None
    gecerli, red, hata = [], [], 0
    parti_boyu = varlik_cikarim.CIFT_PARTI
    with api_durum.islem("varlik_cikarim"):
        for i in range(0, len(ciftler), parti_boyu):
            parti = ciftler[i:i + parti_boyu]
            sonuc = None
            for bekleme in (*varlik_cikarim.YENIDEN_DENEME_SN, None):
                try:
                    sonuc = varlik_cikarim.ciftleri_sor(slug, parti, models=models, cozucu=cozucu,
                                                        kategoriler=kategoriler)
                    break
                except translate.TranslateError:
                    if bekleme is None:
                        break
                    time.sleep(bekleme)
            if sonuc is None:
                hata += 1
                print(f"! parti {i // parti_boyu + 1} düştü")
                continue
            gecerli += sonuc["gecerli"]
            red += sonuc["red"]
            if args.uygula:
                conn = varlik_grafigi._connect()
                try:
                    for g in sonuc["gecerli"]:
                        varlik_grafigi.bag_ekle(slug, g["ozne_kimlik"], g["iliski"], g["nesne_kimlik"],
                                                g["bolum"], g.get("kanit"), "model",
                                                float(g.get("guven") or 0), conn=conn)
                    conn.commit()
                finally:
                    conn.close()
            print(f"  {min(i + parti_boyu, len(ciftler))}/{len(ciftler)} çift: "
                  f"{len(sonuc['gecerli'])} bağ, {len(sonuc['red'])} red")
    print(f"\n{len(gecerli)} geçerli bağ, {len(red)} red, {hata} düşen parti")
    print("ilişki:", dict(Counter(g["iliski"] for g in gecerli).most_common()))
    print("red:", dict(Counter(r["sebep"] for r in red).most_common()))
    if args.rapor:
        Path(args.rapor).write_text(json.dumps({"gecerli": gecerli, "red": red}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    if not args.uygula:
        print("Veritabanına yazılmadı. Yazmak için: --uygula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
