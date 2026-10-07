"""Varlık PROFİLİ: tek tek varlıkların bağlarını kitabın tamamından doldur (bakım aracı).

Neden var (2026-10-07): çift sorusu (`varlik_bosluk.py`) ölçülen denemede 30 çiftten
1 bağ verdi — ilişki nadiren tek bir çiftin birkaç cümlesinde açıkça söyleniyor.
Profil, TEK varlığın kitap boyunca geçtiği ilişki ipuçlu cümlelerin hepsine bakar
(`varlik_bosluk.profil_cumleleri`) ve modelden yalnız o varlığa değen, kanıtı verilen
cümlelerden biri olan bağları ister (`varlik_cikarim.varlik_profili_sor`).

Kullanım:
  python scripts/varlik_profil.py --kitap shadow-slave --ad Belle --ad Dorn
      KURU: her varlık için kaç cümle sorulacağını gösterir (API'siz).
  ... --obek yaratik
      Bir öbeğin bütün düğümleri (`varlik_grafigi.obek_siniflari`).
  ... --calistir --model vertex/gemini-3.6-flash --rapor r.json
      Sorar, rapora yazar; veritabanına YAZMAZ.
  ... --uygula
      Geçerli bağları `aday` olarak yazar (inceleme `varlik_inceleme.py` ile).
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

from core import api_durum, library, translate, varlik_bosluk, varlik_cikarim, varlik_grafigi  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--ad", action="append", default=[], help="profili doldurulacak varlık (tekrarlanabilir)")
    ap.add_argument("--obek", help="bir öbeğin bütün düğümleri (kisi, yaratik, yer, ...)")
    ap.add_argument("--sinir", type=int, default=varlik_bosluk.PROFIL_CUMLE_SINIRI, help="varlık başına cümle")
    ap.add_argument("--calistir", action="store_true")
    ap.add_argument("--uygula", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--rapor")
    args = ap.parse_args()
    load_dotenv(KOK / ".env")
    slug = library.resolve_slug(args.kitap)
    cozucu = varlik_grafigi.DugumCozucu(slug)
    adlar = list(args.ad)
    if args.obek:
        obekler = varlik_grafigi.obek_siniflari(slug)
        adlar += sorted(cozucu.kaynak(k) for k, s in obekler.items() if s == args.obek)
    if not adlar:
        ap.error("--ad ya da --obek gerekli")
    sorular = []
    for ad in adlar:
        if not cozucu.coz(ad):
            print(f"  ! {ad}: sözlükte yok, atlandı")
            continue
        cumleler = varlik_bosluk.profil_cumleleri(slug, ad, args.sinir)
        print(f"  {ad:30} {len(cumleler):3} cümle")
        if cumleler:
            sorular.append((ad, cumleler))
    if not args.calistir:
        print(f"KURU — sormak için: --calistir (~{len(sorular)} istek)")
        return 0
    kategoriler = varlik_grafigi.kategori_kimlikleri(slug, cozucu)
    models = (args.model,) if args.model else None
    gecerli, red, degerler, hata = [], [], [], 0
    with api_durum.islem("varlik_cikarim"):
        for ad, cumleler in sorular:
            sonuc = None
            for bekleme in (*varlik_cikarim.YENIDEN_DENEME_SN, None):
                try:
                    sonuc = varlik_cikarim.varlik_profili_sor(slug, ad, cumleler, models=models,
                                                             cozucu=cozucu, kategoriler=kategoriler)
                    break
                except translate.TranslateError:
                    if bekleme is None:
                        break
                    time.sleep(bekleme)
            if sonuc is None:
                hata += 1
                print(f"  ! {ad}: soru düştü")
                continue
            for g in sonuc["gecerli"]:
                g["sorulan"] = ad
            gecerli += sonuc["gecerli"]
            red += sonuc["red"]
            degerler += sonuc["degerler"]
            print(f"  {ad:30} {len(sonuc['gecerli'])} bağ, {len(sonuc['degerler'])} değer, "
                  f"{len(sonuc['red'])} red")
            if args.uygula:
                conn = varlik_grafigi._connect()
                try:
                    for g in sonuc["gecerli"]:
                        varlik_grafigi.bag_ekle(slug, g["ozne_kimlik"], g["iliski"], g["nesne_kimlik"],
                                                g["bolum"], g.get("kanit"), "model",
                                                float(g.get("guven") or 0), conn=conn)
                    for d in sonuc["degerler"]:
                        varlik_grafigi.deger_yaz(slug, d["kimlik"], d["anahtar"], d["deger"], d["bolum"],
                                                 d.get("kanit"), conn=conn)
                    conn.commit()
                finally:
                    conn.close()
    print(f"\n{len(gecerli)} geçerli bağ, {len(degerler)} değer, {len(red)} red, {hata} düşen soru")
    print("ilişki:", dict(Counter(g["iliski"] for g in gecerli).most_common()))
    print("red:", dict(Counter(r["sebep"] for r in red).most_common()))
    if args.rapor:
        Path(args.rapor).write_text(json.dumps({"gecerli": gecerli, "red": red, "degerler": degerler},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.uygula:
        print("Veritabanına yazılmadı. Yazmak için: --uygula")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
