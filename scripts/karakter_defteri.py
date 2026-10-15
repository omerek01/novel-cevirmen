"""Karakter defteri: pilot, geriye dönük doldurma ve ölçüm aracı (`core.karakter_defteri`).

Bölümler birbirinden BAĞIMSIZ işlenir (N−1 zinciri yok), bu yüzden doldurma paralel
koşar; sabit bekleme yoktur. Devam ettirilebilir: aynı istem sürümüyle tamamlanan bölüm
atlanır (`--yeniden` hariç).

Kullanım (varsayılan hiçbir şey YAZMAZ, model ÇAĞIRMAZ):
  --kitap shadow-slave --kuru [--from 1 --to 984]          istem boyutu / maliyet tahmini
  --kitap shadow-slave --taban                             defter öncesi ölçüm (Captain, sen/siz)
  --kitap shadow-slave --pilot 20 --calistir --rapor r.json   pilot (yarısı rastgele, yarısı diyalog yoğun)
  --kitap shadow-slave --from 1 --to 984 --es 4 --calistir    doldurma
  --kitap shadow-slave --uzlastir                          bağları varlik_bag'e aday yaz (API'siz)
  --kitap shadow-slave --metrik                            özet
  --kitap shadow-slave --run-kayit                         rün kayıtlarını (anı, efsun, gölge, yaratık,
                                                           rün listesi) baştan kur (API'siz; elle kayıtlar korunur)
  --kitap shadow-slave --ornek varlik=50,hitap=50,bag=30 --cikti denetim.json   elle denetim örneği
  --env /yol/.env   (Vertex proje ayarı; değer basılmaz)
Güvenlik durdurmaları: art arda başarısızlık; son 10 bölümde geçersiz iddia oranı > %50.
ROMAN METNİ içeren çıktılar (--ornek) git'e girmez.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import api_durum, db, karakter_defteri as kd  # noqa: E402

DURDUR = {"ardisik_basarisiz": 3, "gecersiz_orani": 0.5, "pencere": 10}
ES_TAVAN = 8
VARSAYILAN_CIKIS = 1500  # kuru tahminde bölüm başına çıkış tokeni (pilotta ölçülür)
PARAGRAF = chr(10) * 2


def bolumler(kitap: str) -> list[int]:
    conn = db.connect()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT chapter_no FROM chapters WHERE book_slug = ? AND chapter_no IS NOT NULL "
            "AND source_text IS NOT NULL AND translation IS NOT NULL ORDER BY chapter_no", (kitap,))]
    finally:
        conn.close()


def secim(args) -> list[int]:
    hepsi = bolumler(args.kitap)
    if args.bolumler:
        istenen = {int(x) for x in args.bolumler.split(",") if x.strip()}
        return [b for b in hepsi if b in istenen]
    if args.pilot:
        return pilot_secimi(args.kitap, hepsi, args.pilot, args.tohum)
    return [b for b in hepsi if (args.from_ is None or b >= args.from_) and (args.to is None or b <= args.to)]


def pilot_secimi(kitap: str, hepsi: list[int], n: int, tohum: int) -> list[int]:
    """Yarısı rastgele, yarısı en çok hitap adayı taşıyan (diyalog yoğun) bölümler."""
    rnd = random.Random(tohum)
    rastgele = set(rnd.sample(hepsi, min(n - n // 2, len(hepsi))))
    yogunluk = []
    for b in hepsi:
        metin = kd.bolum_metni(kitap, b)
        if not isinstance(metin, str):
            yogunluk.append((len(kd.hitap_adaylari(*metin)), b))
    diyalog = [b for _, b in sorted(yogunluk, reverse=True) if b not in rastgele][: n // 2]
    return sorted(rastgele | set(diyalog))


def kuru(args, secilen: list[int]) -> dict:
    from core import kullanim

    sonuc = [kd.bolum_isle(args.kitap, b, kuru=True) for b in secilen]
    olcu = [s for s in sonuc if s["durum"] == "kuru"]
    giris = sum(s["tahmini_giris"] for s in olcu)
    model = kd.model_adi()
    return {
        "bolum": len(secilen), "islenebilir": len(olcu),
        "hizasiz": sum(1 for s in sonuc if s["durum"] == "hizasiz"),
        "yok": sum(1 for s in sonuc if s["durum"] == "yok"),
        "ort_giris_token": round(giris / len(olcu)) if olcu else 0,
        "ort_hitap_adayi": round(sum(s["hitap_adayi"] for s in olcu) / len(olcu), 1) if olcu else 0,
        "ort_kayitli": round(sum(s["kayitli"] for s in olcu) / len(olcu), 1) if olcu else 0,
        "tahmini_usd": round(kullanim._maliyet(model, giris, VARSAYILAN_CIKIS * len(olcu)), 2),
        "not": f"çıkış bölüm başına {VARSAYILAN_CIKIS} token varsayıldı; düşünme tokenları hariç",
    }


def calistir(args, secilen: list[int]) -> list[dict]:
    if not args.yeniden:
        conn = kd._connect()
        try:
            tamam = {r[0] for r in conn.execute(
                "SELECT bolum FROM defter_isleme WHERE book_slug = ? AND durum = 'completed' AND istem_surumu = ?",
                (args.kitap, kd.ISTEM_SURUMU))}
        finally:
            conn.close()
        secilen = [b for b in secilen if b not in tamam]
    print(f"işlenecek {len(secilen)} bölüm, model {kd.model_adi()}, düşünme {kd.dusunme_ayari()}", flush=True)
    es = max(1, args.es)
    sonuclar: list[dict] = []
    ardisik = basarili_seri = 0
    kalan = list(secilen)
    denenen: set[int] = set()
    baslangic = time.time()

    def is_(b):
        with api_durum.islem("karakter_defteri"):
            return kd.bolum_isle(args.kitap, b)

    while kalan:
        parti, kalan = kalan[:es], kalan[es:]
        with ThreadPoolExecutor(max_workers=len(parti)) as havuz:
            gelen = [f.result() for f in as_completed([havuz.submit(is_, b) for b in parti])]
        for s in sorted(gelen, key=lambda x: x["bolum"]):
            sonuclar.append(s)
            if s["durum"] == "completed":
                kd.hitap_denetle(args.kitap, s["bolum"])
                ardisik, basarili_seri = 0, basarili_seri + 1
                print(f"  {s['bolum']}: {s['iddia']} geçersiz {s['gecersiz']} "
                      f"{s['kullanim'].get('giris')}/{s['kullanim'].get('cikis')} tok {s['sure_sn']} sn", flush=True)
            elif s["durum"] == "hata":
                ardisik += 1
                basarili_seri = 0
                print(f"  {s['bolum']}: HATA {s['hata'][:160]}", flush=True)
            else:
                print(f"  {s['bolum']}: {s['durum']}", flush=True)
        if any(s["durum"] == "hata" for s in gelen):
            if es > 1:
                es = max(1, es // 2)
            time.sleep(args.bekleme)
            # Bölüm başına en çok bir yeniden deneme: sürekli bozuk tek bir bölüm döngü kurmasın.
            tekrar = [s["bolum"] for s in gelen if s["durum"] == "hata" and s["bolum"] not in denenen]
            denenen.update(tekrar)
            kalan = tekrar + kalan
        elif basarili_seri >= 10 and es < ES_TAVAN and args.es > 1:
            es, basarili_seri = es + 1, 0
        son = [s for s in sonuclar if s["durum"] == "completed"][-DURDUR["pencere"]:]
        oran = (sum(s["gecersiz"] for s in son) / max(1, sum(sum(s["iddia"].values()) for s in son))) if son else 0
        if ardisik >= DURDUR["ardisik_basarisiz"]:
            print("DURDURULDU: art arda başarısızlık", flush=True)
            break
        if len(son) >= DURDUR["pencere"] and oran > DURDUR["gecersiz_orani"] and not args.pilot:
            print(f"DURDURULDU: geçersiz iddia oranı {oran:.0%}", flush=True)
            break
    print(f"bitti: {time.time() - baslangic:.0f} sn", flush=True)
    return sonuclar


def hitap_kiyas(kitap: str, yol: str) -> dict:
    """Her kolun ve canlı çevirinin hitap uyumsuzluğu (`kd.hitap_uyumu`, API'siz)."""
    satirlar = [json.loads(s) for s in Path(yol).read_text(encoding="utf-8").splitlines() if s.strip()]
    toplam: dict[str, dict] = {}
    canli_bolumler = set()
    for s in satirlar:
        if not s.get("translation"):
            continue
        en_p = [p.strip() for p in (s.get("source") or "").split(PARAGRAF)]
        tr_p = [p.strip() for p in s["translation"].split(PARAGRAF)]
        u = kd.hitap_uyumu(kitap, s["bolum"], en_p, tr_p)
        t = toplam.setdefault(s["kol"], {"degerlendirilen": 0, "uyumsuz": 0, "bolum": 0})
        t["degerlendirilen"] += u["degerlendirilen"]
        t["uyumsuz"] += u["uyumsuz"]
        t["bolum"] += 1
        canli_bolumler.add(s["bolum"])
    canli = {"degerlendirilen": 0, "uyumsuz": 0, "bolum": 0}
    for b in canli_bolumler:
        metin = kd.bolum_metni(kitap, b)
        if not isinstance(metin, str):
            u = kd.hitap_uyumu(kitap, b, *metin)
            canli["degerlendirilen"] += u["degerlendirilen"]
            canli["uyumsuz"] += u["uyumsuz"]
            canli["bolum"] += 1
    toplam["canli"] = canli
    for t in toplam.values():
        t["oran"] = round(t["uyumsuz"] / t["degerlendirilen"], 3) if t["degerlendirilen"] else None
    return toplam


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kitap", default="shadow-slave")
    ap.add_argument("--from", dest="from_", type=int)
    ap.add_argument("--to", type=int)
    ap.add_argument("--bolumler")
    ap.add_argument("--pilot", type=int)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--es", type=int, default=1)
    ap.add_argument("--bekleme", type=float, default=30.0, help="hatalı partiden sonra bekleme (sn)")
    ap.add_argument("--kuru", action="store_true")
    ap.add_argument("--taban", action="store_true")
    ap.add_argument("--calistir", action="store_true")
    ap.add_argument("--yeniden", action="store_true")
    ap.add_argument("--uzlastir", action="store_true")
    ap.add_argument("--run-kayit", action="store_true", help="defter_kayit.cikar: rün kayıtlarını baştan kur")
    ap.add_argument("--metrik", action="store_true")
    ap.add_argument("--ornek")
    ap.add_argument("--cikti")
    ap.add_argument("--rapor")
    ap.add_argument("--hitap-kiyas", help="anlam_kiyas çıktısı (jsonl): kolların hitap uyumu")
    ap.add_argument("--env")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.env:
        from dotenv import load_dotenv

        load_dotenv(args.env)
    rapor: dict = {"kitap": args.kitap, "istem_surumu": kd.ISTEM_SURUMU, "model": kd.model_adi(),
                   "dusunme": kd.dusunme_ayari()}
    if args.taban:
        rapor["taban"] = kd.taban_olcumu(args.kitap)
        print(json.dumps(rapor["taban"], ensure_ascii=False, indent=1))
    if args.kuru or args.calistir:
        secilen = secim(args)
        rapor["secilen"] = secilen
        if args.kuru:
            rapor["kuru"] = kuru(args, secilen)
            print(json.dumps(rapor["kuru"], ensure_ascii=False, indent=1))
        if args.calistir:
            rapor["sonuclar"] = calistir(args, secilen)
    if args.uzlastir:
        rapor["uzlastir"] = kd.uzlastir(args.kitap)
        print("uzlaştırma:", rapor["uzlastir"])
    if args.run_kayit:
        from core import defter_kayit

        rapor["run_kayit"] = defter_kayit.cikar(args.kitap)
        print("rün kayıtları:", rapor["run_kayit"])
    if args.metrik:
        rapor["metrik"] = kd.metrik(args.kitap)
        print(json.dumps(rapor["metrik"], ensure_ascii=False, indent=1))
    if args.ornek:
        adet = {a: int(n) for a, n in (x.split("=") for x in args.ornek.split(","))}
        ornek = kd.denetim_ornegi(args.kitap, adet, args.tohum)
        Path(args.cikti or "defter-denetim.json").write_text(json.dumps(ornek, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
        print(f"denetim örneği: {len(ornek)} kayıt -> {args.cikti or 'defter-denetim.json'}")
    if args.hitap_kiyas:
        rapor["hitap_kiyas"] = hitap_kiyas(args.kitap, args.hitap_kiyas)
        print(json.dumps(rapor["hitap_kiyas"], ensure_ascii=False, indent=1))
    if args.rapor:
        Path(args.rapor).write_text(json.dumps(rapor, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
