"""Terim ölçütü kıyası (`SOZLUK_TERIM_OLCUTU`): aynı bölümler eski ve yeni ölçütle çevrilir.

Tek değişken bayraktır: sözlük, koşullar ve model aynı; cilalama/kalite/özet/analiz kapalı
(yalnız çeviri istemi ölçülür), sonuç sözlüğe ve önbelleğe YAZILMAZ. Ölçülen:
  * yeni aday (sözlükte olmayan detected_terms) sayısı ve sınıfı: sıradan sözcük, küçük harf,
    parçalı ad, başka kapı nedeni, temiz;
  * sözlük ihlali (kayıtlı karşılığın uygulanmadığı terim) sayısı.
Ücretli: kol başına bir bölüm çevirisi (seçili model). Çıktı roman metni içermez.

  python scripts/terim_olcutu_kiyas.py --kitap shadow-slave --son 6 --cikti /tmp/olcut.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(KOK / ".env")  # anahtarlar sunucuyla aynı kaynaktan (server.py da böyle yükler)

from core import cache, ceviri_asamalari, glossary, sozluk_kapi, translate  # noqa: E402

KAPALI = {"cilalama", "kalite", "ozet", "analiz"}


def _bolumler(kitap: str, son: int, nolar: list[int] | None = None) -> list[dict]:
    conn = cache._connect()
    try:
        if nolar:
            satirlar = conn.execute(
                f"SELECT chapter_no, source_text FROM chapters WHERE book_slug = ? AND source_text IS NOT NULL "
                f"AND chapter_no IN ({','.join('?' * len(nolar))}) ORDER BY chapter_no", (kitap, *nolar)).fetchall()
            return [{"no": n, "metin": m} for n, m in satirlar]
        satirlar = conn.execute(
            "SELECT chapter_no, source_text FROM chapters WHERE book_slug = ? AND source_text IS NOT NULL "
            "AND chapter_no IS NOT NULL ORDER BY chapter_no DESC LIMIT ?", (kitap, son)).fetchall()
    finally:
        conn.close()
    return [{"no": n, "metin": m} for n, m in reversed(satirlar)]


def _o_anki(sozluk, kosullar, satirlar, no):
    """İLK KARŞILAŞMA kipi: o bölümde ve sonra eklenen kayıtlar yokmuş gibi.

    Son bölümlerde terimlerin hepsi zaten sözlükte olduğu için iki kol aynı (hiç) adayı
    üretir; ölçüt farkı ancak terimin ilk görüldüğü bölümde ölçülebilir.
    shortcut: alternatif yazım anahtarları süzülür (yalnız kayıt kaynağı tutulur).
    """
    eski = [r for r in satirlar if r.get("first_chapter") is None or r["first_chapter"] < no]
    izin = {glossary.fold_term(r["source"]) for r in eski}
    return ({k: v for k, v in sozluk.items() if glossary.fold_term(k) in izin},
            {k: v for k, v in kosullar.items() if glossary.fold_term(k) in izin}, eski, izin)


def _siniflandir(kitap: str, adaylar: dict[str, str], satirlar: list[dict]) -> dict[str, list[str]]:
    genel = sozluk_kapi.genel_sozcukler(kitap, adaylar)
    out: dict[str, list[str]] = {"genel_sozcuk": [], "kucuk_harf": [], "parcali_ad": [], "kapi": [], "temiz": []}
    for k, h in adaylar.items():
        if sozluk_kapi.parcali_ad(k, h, satirlar):
            out["parcali_ad"].append(k)
            continue
        nedenler = {n["tur"] for n in sozluk_kapi.kapi_denetle(k, h, satirlar, genel=genel.get(k))["nedenler"]}
        if sozluk_kapi.GENEL_SOZCUK in nedenler:
            out["genel_sozcuk"].append(k)
        elif sozluk_kapi.KUCUK_HARF in nedenler:
            out["kucuk_harf"].append(k)
        elif nedenler:
            out["kapi"].append(k)
        else:
            out["temiz"].append(k)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kitap", required=True)
    ap.add_argument("--son", type=int, default=6, help="son kaç kaynaklı bölüm")
    ap.add_argument("--bolumler", default="", help="virgüllü bölüm numaraları (--son yerine)")
    ap.add_argument("--o-anki", action="store_true", help="sözlüğü bölümden ÖNCEKİ hâline indir")
    ap.add_argument("--cikti", required=True)
    a = ap.parse_args()
    nolar = [int(x) for x in a.bolumler.split(",") if x.strip()]

    asil = ceviri_asamalari.acik
    ceviri_asamalari.acik = lambda ad, *x, **y: False if ad in KAPALI else asil(ad, *x, **y)
    tum_sozluk = glossary.ceviri_sozlugu(a.kitap)
    tum_kosullar = glossary.ceviri_kosullari(a.kitap)
    tum_satirlar = glossary.get_glossary_rows(a.kitap)
    sonuc = []
    for b in _bolumler(a.kitap, a.son, nolar):
        if a.o_anki:
            sozluk, kosullar, satirlar, kayitli = _o_anki(tum_sozluk, tum_kosullar, tum_satirlar, b["no"])
        else:
            sozluk, kosullar, satirlar = tum_sozluk, tum_kosullar, tum_satirlar
            kayitli = {glossary.fold_term(s) for s in sozluk}
        for kol, deger in (("eski", "0"), ("yeni", "1")):
            os.environ["SOZLUK_TERIM_OLCUTU"] = deger
            bas = time.time()
            try:
                r = translate.translate_chapter(b["metin"], api_key="", glossary=sozluk, kosullar=kosullar,
                                                bolum_no=b["no"], book_slug=a.kitap)
            except translate.TranslateError as exc:
                sonuc.append({"bolum": b["no"], "kol": kol, "hata": str(exc)[:200]})
                print(b["no"], kol, "HATA", exc, flush=True)
                continue
            adaylar = {k: v for k, v in (r.get("detected_terms") or {}).items()
                       if glossary.fold_term(k) not in kayitli}
            ihlal = translate.sozluk_ihlalleri(sozluk, b["metin"], r["translation"], kosullar)
            sinif = _siniflandir(a.kitap, adaylar, satirlar)
            sonuc.append({"bolum": b["no"], "kol": kol, "sure": round(time.time() - bas, 1),
                          "model": r.get("model"), "aday": len(adaylar), "sinif": sinif,
                          "ihlal": sorted(ihlal)})
            print(b["no"], kol, {k: len(v) for k, v in sinif.items()}, "ihlal", len(ihlal), flush=True)
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    for kol in ("eski", "yeni"):
        satir = [s for s in sonuc if s["kol"] == kol and "sinif" in s]
        toplam = {k: sum(len(s["sinif"][k]) for s in satir) for k in ("genel_sozcuk", "kucuk_harf",
                                                                       "parcali_ad", "kapi", "temiz")}
        print(f"{kol}: bölüm {len(satir)}, aday {sum(s['aday'] for s in satir)}, {toplam}, "
              f"ihlal {sum(len(s['ihlal']) for s in satir)}")


if __name__ == "__main__":
    main()
