"""Bilgi grafiği GEÇMİŞ DOLDURMA (1..946) ve canlı kuyruk işleme — Faz 2A aracı.

Çekirdek `core.bilgi_delta` (canlı okuma da AYNISINI kullanır). Kronolojik: bölüm N
ancak baş N-1 iken işlenir; N'nin bağlamı yalnız N-1'e kadar öğrenilen bilgidir.
Devam ettirilebilir: durum `bilgi_isleme` tablosunda; yeniden başlatma kopya üretmez.

Kullanım (varsayılan KURU — model çağrılmaz):
  --book shadow-slave --kapsam                     kapsama denetimi (API'siz)
  --book shadow-slave --adaylar                    doğrulama seti aday taraması (API'siz)
  --book shadow-slave --from 1 --to 100 --dry-run --adim 10   bağlam/token ölçümü
  --book shadow-slave --dogrulama 15,24,106 --model M --rapor r.json   YAZMADAN değerlendirme
  --book shadow-slave --from 1 --to 100 --model M --calistir           GERÇEK işleme
  --only-failed / --only-review / --chapter N / --limit K / --yeniden
Güvenlik durdurmaları: art arda başarısızlık, şema hatası oranı, bağ/inceleme patlaması,
bağlam bütçesi aşımı. Her 25 bölümde kontrol noktası (`bilgi_kontrol`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

from core import api_durum, bilgi_delta as bd, cache, glossary, library, translate, varlik_grafigi  # noqa: E402

KONTROL_ARALIGI = 25
DURDUR = {  # güvenlik eşikleri (bölüm başına / art arda)
    "ardisik_basarisiz": 3,
    "bolum_basina_yeni_bag": 40,
    "bolum_basina_inceleme": 15,
    "bolum_basina_yeni_varlik_onerisi": 25,
}


def kapsam(slug: str) -> None:
    conn = cache._connect()
    try:
        satir = conn.execute(
            "SELECT COUNT(*), SUM(source_text IS NOT NULL AND source_text != ''), "
            "SUM(translation IS NOT NULL AND translation != ''), MIN(chapter_no), MAX(chapter_no) "
            "FROM chapters WHERE book_slug = ?", (slug,)).fetchone()
        modeller = conn.execute(
            "SELECT COALESCE(model, '(yok)'), COUNT(*) FROM chapters WHERE book_slug = ? GROUP BY 1 ORDER BY 2 DESC",
            (slug,)).fetchall()
        nolar = [r[0] for r in conn.execute("SELECT chapter_no FROM chapters WHERE book_slug = ? AND chapter_no IS NOT NULL",
                                            (slug,))]
        kaynaksiz = [r[0] for r in conn.execute(
            "SELECT chapter_no FROM chapters WHERE book_slug = ? AND (source_text IS NULL OR source_text = '') "
            "ORDER BY chapter_no", (slug,))]
        cevirisiz = [r[0] for r in conn.execute(
            "SELECT chapter_no FROM chapters WHERE book_slug = ? AND (translation IS NULL OR translation = '') "
            "ORDER BY chapter_no", (slug,))]
    finally:
        conn.close()
    toplam, kaynakli, cevirili, en_az, en_cok = satir
    eksik = sorted(set(range(1, (en_cok or 0) + 1)) - set(nolar))
    print(f"== A. KAYNAK KAPSAMASI ({slug})")
    print(f"  bölüm satırı: {toplam}  numara aralığı: {en_az}..{en_cok}  önbellekte olmayan numara: {len(eksik)} {eksik[:20]}")
    print(f"  source_text olan: {kaynakli}  çevirisi olan: {cevirili}")
    print(f"  source_text EKSİK: {len(kaynaksiz)} {kaynaksiz[:30]}")
    print(f"  çeviri EKSİK: {len(cevirisiz)} {cevirisiz[:30]}")
    print("  çeviri modeli dağılımı:")
    for m, n in modeller:
        print(f"    {n:5} {m}")
    vg = varlik_grafigi._connect()
    try:
        print("== B. MEVCUT GRAFİK KAPSAMASI")
        for r in vg.execute("SELECT origin, durum, COALESCE(durum_bilgisi, 'NULL'), COUNT(*) FROM varlik_bag "
                            "WHERE book_slug = ? GROUP BY 1, 2, 3 ORDER BY 1, 2", (slug,)):
            print(f"    bağ  origin={r[0]:7} durum={r[1]:10} durum_bilgisi={r[2]:10} {r[3]}")
        ilis = vg.execute("SELECT iliski, COUNT(*) FROM varlik_bag WHERE book_slug = ? AND durum != 'reddedildi' "
                          "GROUP BY 1 ORDER BY 2 DESC", (slug,)).fetchall()
        print("    ilişki türü (reddedilmemiş):", ", ".join(f"{a}={n}" for a, n in ilis))
        print("    bağ kanıtı olan bölüm:", vg.execute(
            "SELECT COUNT(DISTINCT ilk_bolum) FROM varlik_bag WHERE book_slug = ? AND durum != 'reddedildi'",
            (slug,)).fetchone()[0])
        print("    değer kanıtı olan bölüm:", vg.execute(
            "SELECT COUNT(DISTINCT ilk_bolum) FROM varlik_deger WHERE book_slug = ?", (slug,)).fetchone()[0],
              " değer satırı:", dict(vg.execute("SELECT origin, COUNT(*) FROM varlik_deger WHERE book_slug = ? GROUP BY 1",
                                                (slug,)).fetchall()))
    finally:
        vg.close()
    satirlar = glossary.get_glossary_rows(slug)
    print("    sözlük kaydı:", len(satirlar), " ilk bölümü bilinen:", sum(r.get("first_chapter") is not None for r in satirlar),
          " tür:", dict(Counter(r.get("tur") or "?" for r in satirlar)))


ADAY_KALIPLARI = {
    "gercek_ad": r"bestowed a True Name|True Name:",
    "yanki_golge": r"received an Echo|created a Shadow|is evolving",
    "kimlik_aciga": r"\btrue identity\b|\bwas actually\b|\bturned out to be\b|\bin disguise\b|\bmasked\b",
    "yanlis_inanc": r"\b(?:thought|believed|assumed)\b[^.]{0,40}\bdead\b|\bstill alive\b|\bsurvived\b",
    "iliski_kirilma": r"\bbetray|\btraitor\b|\bturned against\b|\bno longer (?:a|an)? ?(?:ally|friend)",
    "unvan": r"\b(?:Lord|Lady|Saint|Master|Sovereign) of\b|\btitle\b",
    "rutbe_degisim": r"\bAscended\b|\bTranscendent\b|Rank:|Class:|Shadow Cores",
    "olum_savas": r"You have slain|\bkilled\b|\bslew\b",
}


def adaylar(slug: str) -> None:
    """Doğrulama seti için ADAY bölümler: her kalıp sınıfında en yoğun bölümler + varlık
    sayısı / diyalog oranı uç değerleri + mevcut model bağı yoğunluğu (metin basmaz)."""
    sozluk = glossary.ceviri_sozlugu(slug)
    vg = varlik_grafigi._connect()
    model_bag = Counter(dict(vg.execute(
        "SELECT ilk_bolum, COUNT(*) FROM varlik_bag WHERE book_slug = ? AND origin = 'model' GROUP BY 1", (slug,)).fetchall()))
    vg.close()
    ozet = []
    for b in cache.kaynak_bolumleri(slug):
        m = b["source"] or ""
        sayim = {ad: len(re.findall(desen, m)) for ad, desen in ADAY_KALIPLARI.items()}
        varlik = len(translate.metinde_gecen_terimler(sozluk, m))
        diyalog = m.count('"') + m.count("“")
        ozet.append({"no": b["chapter_no"], "varlik": varlik, "diyalog": diyalog / max(1, len(m) / 1000),
                     "model_bag": model_bag.get(b["chapter_no"], 0), **sayim})
    for ad in [*ADAY_KALIPLARI, "varlik", "diyalog", "model_bag"]:
        en = sorted(ozet, key=lambda x: -x[ad])[:6]
        print(f"  {ad:15} en yoğun: " + ", ".join(f"#{x['no']}({round(x[ad], 1)})" for x in en))
    az = sorted(ozet, key=lambda x: x["varlik"])[:6]
    print("  varlik (en az): " + ", ".join(f"#{x['no']}({x['varlik']})" for x in az))


def calistir(args, slug: str) -> int:
    model = args.model
    if args.chapter:
        bolumler = [args.chapter]
    elif args.only_failed or args.only_review:
        istenen = "failed" if args.only_failed else "needs_review"
        conn = bd._connect()
        bolumler = [r[0] for r in conn.execute(
            "SELECT bolum FROM bilgi_isleme WHERE book_slug = ? AND durum = ? ORDER BY bolum", (slug, istenen))]
        conn.close()
    else:
        bas = max(args.__dict__["from"] or (bd.bas_bolum(slug) + 1), 1)
        bolumler = list(range(bas, (args.to or bas + (args.limit or 1) - 1) + 1, args.adim or 1))
    if args.limit:
        bolumler = bolumler[: args.limit]
    if not args.calistir and not args.dry_run:
        print(f"KURU — {len(bolumler)} bölüm işlenecekti: {bolumler[:10]}{' …' if len(bolumler) > 10 else ''}. "
              "Ölçüm için --dry-run, gerçek işleme için --calistir --model M")
        return 0
    if args.calistir and not model:
        print("--calistir için --model gerekli")
        return 2
    toplam_giris, ardisik = [], 0
    with api_durum.islem("varlik_cikarim"):
        for i, n in enumerate(bolumler, 1):
            try:
                sonuc = bd.bolum_isle(slug, n, model or "kuru", kuru=args.dry_run,
                                      yeniden=args.yeniden or args.only_review)
            except bd.KronolojiHatasi as exc:
                print(f"DURDU (kronoloji): {exc}")
                return 3
            o = sonuc.get("olcum") or {}
            toplam_giris.append(o.get("toplam_giris_tahmini") or 0)
            print(f"  #{n}: {sonuc['durum']} kaynak={o.get('kaynak_tokeni')} bağlam={o.get('baglam_tokeni')} "
                  f"kesilen={o.get('kesilen_satir')} giriş≈{o.get('toplam_giris_tahmini')} "
                  f"{json.dumps(sonuc.get('sayac') or {}, ensure_ascii=False)}", flush=True)
            if args.dry_run:
                continue
            sayac = sonuc.get("sayac") or {}
            ardisik = ardisik + 1 if sonuc["durum"] == "failed" else 0
            sebep = None
            if ardisik >= DURDUR["ardisik_basarisiz"]:
                sebep = f"{ardisik} art arda başarısız (son hata: {sonuc.get('hata')})"
            elif sayac.get("yazilan_bag", 0) > DURDUR["bolum_basina_yeni_bag"]:
                sebep = f"bağ patlaması: {sayac['yazilan_bag']} yeni bağ"
            elif sayac.get("inceleme", 0) > DURDUR["bolum_basina_inceleme"]:
                sebep = f"inceleme sıçraması: {sayac['inceleme']}"
            elif o.get("baglam_tokeni", 0) > bd.BAGLAM_BUTCESI:
                sebep = "bağlam bütçesi aşıldı"
            if n % KONTROL_ARALIGI == 0 or i == len(bolumler) or sebep:
                print("  KONTROL NOKTASI", json.dumps(bd.kontrol_noktasi(slug, n), ensure_ascii=False))
            if sebep:
                print(f"DURDU (güvenlik): {sebep}")
                return 4
    if toplam_giris:
        print(f"ortalama giriş tahmini: {sum(toplam_giris) // len(toplam_giris)} token, toplam ≈ {sum(toplam_giris)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True)
    ap.add_argument("--from", type=int)
    ap.add_argument("--to", type=int)
    ap.add_argument("--chapter", type=int)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--adim", type=int, help="ölçümde her N. bölüm")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-failed", action="store_true")
    ap.add_argument("--only-review", action="store_true")
    ap.add_argument("--yeniden", action="store_true", help="işlenmiş bölümü yeniden işle (baş ilerlemez)")
    ap.add_argument("--calistir", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--kapsam", action="store_true")
    ap.add_argument("--adaylar", action="store_true")
    ap.add_argument("--dogrulama", help="virgüllü bölüm listesi: YAZMADAN değerlendir")
    ap.add_argument("--rapor")
    args = ap.parse_args()
    load_dotenv(KOK / ".env")
    slug = library.resolve_slug(args.book)
    if args.kapsam:
        kapsam(slug)
        return 0
    if args.adaylar:
        adaylar(slug)
        return 0
    if args.dogrulama:
        if not args.model:
            print("--dogrulama için --model gerekli")
            return 2
        sonuclar = []
        with api_durum.islem("varlik_cikarim"):
            for n in [int(x) for x in args.dogrulama.split(",")]:
                sonuclar.append(bd.bolum_degerlendir(slug, n, args.model))
                print(f"  #{n} tamam", flush=True)
        if args.rapor:
            Path(args.rapor).write_text(json.dumps(sonuclar, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return 0
    return calistir(args, slug)


if __name__ == "__main__":
    raise SystemExit(main())
