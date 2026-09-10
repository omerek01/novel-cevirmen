"""Bölüm SIRASI ve ADI denetimi — numara + zincir + okuma konumu.

Varsayılan KURU çalıştırma (hiçbir şey yazmaz); `--uygula` ile düzeltir.
`scripts/uyum_denetle.py` ile aynı desen.

Neden gerekti (ölçülen gerçek vaka, Shadow Slave 2026-09-02): `fetch_into_book`
sayfanın KENDİ bölüm numarasını yok sayıp kuyruk sayacı (`tail+1`) veriyordu.
Kuyruk 140'tayken eklenen `chapter-137` 141 numarasını, sonra eklenen `chapter-141`
142'yi aldı; üstelik her ekleme kuyruğun `next`'ini yeni bölüme çevirdiği için
zincir de koptu (140 -> 137 -> 141). Okuyucuda bölüm sırası ve adı kaydı.
Kök sebep düzeltildi; bu araç o dönemden kalan SATIRLARI onarır.

ÜÇ denetim, üçü de AYRI karar:

1. NUMARA — `chapter_no`, URL'deki ve başlıktaki numarayla uyuşmalı.
   Düzeltme YALNIZ URL ve BAŞLIK birbiriyle uyuşup ikisi birden `chapter_no`'dan
   ayrıldığında yapılır. Bu, "iki bağımsız kaynak aynı şeyi söylüyor" demektir;
   tek kaynağa dayanıp numara değiştirmek, doğru satırı bozma riski taşır
   (gerçek yanlış-pozitifler: manga sayfaları tek `chapter-0` URL'si altında,
   "Chapter 0" adlı ön sözler).

2. ZİNCİR — `prev_url`/`next_url`, düzeltilmiş numara sırasını izlemeli.
   Yalnız hedef bölüm AYNI kitapta önbellekte varsa düzeltilir. Son bölümün
   `next`'ine DOKUNULMAZ: o, henüz indirilmemiş bölümü gösteren "ileri okuma"
   işaretçisidir ve boş olmaması normaldir.

3. KONUM — `books.current_url` ile `current_title`/`chapter_no` aynı bölümü
   anlatmalı. Ölçüt URL'dir: "kaldığın yer" onu açar, ad ve numara türetilmiş
   alanlardır.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from core import cache, db, library  # noqa: E402

URL_NO = re.compile(r"chapter[-_/](\d+)")
BASLIK_NO = re.compile(r"chapter\s*0*(\d+)", re.I)


def _bolumler(slug: str) -> list[dict]:
    conn = db.connect()
    try:
        satirlar = conn.execute(
            "SELECT url, title, chapter_no, prev_url, next_url FROM chapters "
            "WHERE book_slug = ? ORDER BY chapter_no IS NULL, chapter_no",
            (slug,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"url": r[0], "title": r[1], "no": r[2], "prev": r[3], "next": r[4]}
        for r in satirlar
    ]


def _kitaplar() -> list[str]:
    conn = db.connect()
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT book_slug FROM chapters WHERE book_slug IS NOT NULL"
            )
        ]
    finally:
        conn.close()


def _numara_duzeltmeleri(bolumler: list[dict]) -> list[tuple[dict, int]]:
    """URL ve BAŞLIK aynı numarayı söylüyor ama `chapter_no` başka → düzelt."""
    out = []
    for b in bolumler:
        mu = URL_NO.search(b["url"] or "")
        mt = BASLIK_NO.search(b["title"] or "")
        if not mu or not mt:
            continue  # iki bağımsız kaynak yoksa karar verilemez, dokunma
        nu, nt = int(mu.group(1)), int(mt.group(1))
        if nu == nt and b["no"] != nu:
            out.append((b, nu))
    return out


def _zincir_duzeltmeleri(bolumler: list[dict]) -> list[tuple[dict, str | None, str | None]]:
    """Numara sırasına göre doğru prev/next; yalnız sapan satırlar döner."""
    sirali = sorted(
        (b for b in bolumler if b["no"] is not None), key=lambda b: b["no"]
    )
    # Önbellek BOŞLUKLU olabilir (gerçek veri: bir kitapta 1. bölümden sonra 1704
    # geliyor). Bu yüzden "sıradaki önbellekli bölüm" GERÇEK komşu demek değildir ve
    # her sapma bozukluk sayılamaz. Onarılan bozukluğun imzası dar: `fetch_into_book`
    # AYNI KİTAP içindeki bağlantıları yanlış satıra çeviriyordu.
    #
    # Ölçüt bu yüzden üç koşullu — mevcut değer (1) dolu, (2) bu kitapta ÖNBELLEKLİ
    # bir bölümü gösteriyor ve (3) sıraya göre yanlış bölüm. Boş bir `prev` ya da
    # önbellekte OLMAYAN bir bölümü gösteren bağlantı, komşunun henüz indirilmemiş
    # olduğunu söyler — bozukluk değildir ve silinmemelidir.
    kitaptaki = {b["url"] for b in bolumler}
    out = []
    for i, b in enumerate(sirali):
        dogru_prev = sirali[i - 1]["url"] if i > 0 else None
        dogru_next = sirali[i + 1]["url"] if i + 1 < len(sirali) else None

        def _karar(mevcut, dogru):
            if mevcut is None or mevcut not in kitaptaki or dogru is None:
                return mevcut  # karar verilemez: olduğu gibi bırak
            return dogru

        yeni_prev = _karar(b["prev"], dogru_prev)
        yeni_next = _karar(b["next"], dogru_next)
        if b["prev"] != yeni_prev or b["next"] != yeni_next:
            out.append((b, yeni_prev, yeni_next))
    return out


def _konum_duzeltmesi(slug: str, bolumler: list[dict]) -> tuple[str, int | None] | None:
    """`books` satırındaki ad/numara `current_url`'in bölümüyle uyuşuyor mu?"""
    kitap = library.get_book(slug)
    if not kitap or not kitap.get("current_url"):
        return None
    hedef = next((b for b in bolumler if b["url"] == kitap["current_url"]), None)
    if hedef is None:
        return None  # konum önbellekte olmayan bir bölümü gösteriyor: karar verilemez
    if kitap.get("current_title") == hedef["title"] and kitap.get("chapter_no") == hedef["no"]:
        return None
    return (hedef["title"] or "", hedef["no"])


def _kisa(u: str | None) -> str:
    return "-" if not u else "..." + u[-18:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug", nargs="?", help="tek kitap (boş = hepsi)")
    ap.add_argument("--uygula", action="store_true", help="düzeltmeleri YAZ")
    args = ap.parse_args()

    hedefler = [args.slug] if args.slug else _kitaplar()
    toplam = 0
    for slug in hedefler:
        bolumler = _bolumler(slug)
        numaralar = _numara_duzeltmeleri(bolumler)

        # Zincir denetimi DÜZELTİLMİŞ numaralar üzerinden yapılmalı: yanlış numarayla
        # kurulan sıra, doğru zinciri "bozuk" gösterirdi.
        duzeltilmis = [dict(b) for b in bolumler]
        yeni_no = {b["url"]: n for b, n in numaralar}
        for b in duzeltilmis:
            if b["url"] in yeni_no:
                b["no"] = yeni_no[b["url"]]
        zincirler = _zincir_duzeltmeleri(duzeltilmis)
        konum = _konum_duzeltmesi(slug, duzeltilmis)

        if not numaralar and not zincirler and not konum:
            continue
        toplam += len(numaralar) + len(zincirler) + (1 if konum else 0)
        print(f"\n=== {slug} ===")

        for b, dogru in numaralar:
            print(f"  NUMARA  {_kisa(b['url'])}  {b['no']} -> {dogru}   {(b['title'] or '')[:40]}")
            if args.uygula:
                cache.set_chapter_no(b["url"], dogru)

        for b, dp, dn in zincirler:
            print(
                f"  ZİNCİR  {_kisa(b['url'])}  "
                f"prev {_kisa(b['prev'])} -> {_kisa(dp)}  |  "
                f"next {_kisa(b['next'])} -> {_kisa(dn)}"
            )
            if args.uygula:
                cache.update_nav(b["url"], dn, dp)

        if konum:
            baslik, no = konum
            kitap = library.get_book(slug)
            print(
                f"  KONUM   current_url={_kisa(kitap['current_url'])}  "
                f"ad '{(kitap.get('current_title') or '')[:28]}' -> '{baslik[:28]}'  "
                f"no {kitap.get('chapter_no')} -> {no}"
            )
            if args.uygula:
                # `current_url`/`current_ratio` KORUNUR: kullanıcı nerede kaldıysa
                # orada kalır, yalnız o bölümü anlatan türetilmiş alanlar düzelir.
                # `upsert_book(update_position=False)` bu iş için kullanılamaz —
                # o, var olan satıra bilerek hiç dokunmuyor (`INSERT OR IGNORE`).
                library.konum_adini_duzelt(slug, baslik, no)

    if not toplam:
        print("Sapma yok.")
    elif args.uygula:
        print(f"\n{toplam} düzeltme UYGULANDI.")
    else:
        print(f"\n{toplam} sapma bulundu (KURU çalıştırma). Yazmak için: --uygula")


if __name__ == "__main__":
    main()
