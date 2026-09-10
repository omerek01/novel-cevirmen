r"""Mevcut kitapların kapağını geriye dönük doldurur (bakım aracı).

Kapak artık her çeviride bölüm sayfasının `og:image`'ından BEDAVAYA alınıyor
(bkz. `fetch._kapak_adresi`), ama bu ancak YENİ çevrilen bölümde çalışır —
kütüphanedeki kitaplar zaten çevrilmiş durumda ve yeni bölüm gelene kadar
kapaksız kalırlardı. Bu araç her kitabın KAYITLI bir bölümünü bir kez çeker ve
kapağı yazar.

Maliyet: kitap başına TEK sayfa çekimi. Cloudflare'e inildiği için varsayılan
KURU çalıştırmadır; `--uygula` ile yazar.

Kullanım (proje kökünden):
    .venv\Scripts\python.exe scripts\kapak_doldur.py
    ... --uygula              # gerçekten çek ve yaz
    ... --slug shadow-slave   # yalnız bu kitap
    ... --hepsi               # kapağı OLAN kitapları da yeniden yokla
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(KOK / ".env")

from core import cache, library  # noqa: E402
from core.fetch import fetch_chapter  # noqa: E402


def _slugify(metin: str) -> str:
    """Başlıktan freewebnovel slug'ı: küçük harf, boşluk -> tire."""
    import re
    temiz = re.sub(r"[^a-z0-9]+", "-", (metin or "").lower()).strip("-")
    return temiz


def _ad_uyusuyor(a: str, b: str) -> bool:
    """İki kitap adı AYNI kitabı mı gösteriyor (gevşek karşılaştırma).

    Doğrulama ŞART: freewebnovel'de aynı slug BAŞKA bir kitaba ait olabilir ve
    o zaman kütüphaneye sessizce YANLIŞ kapak yazılırdı — kullanıcı yanlış
    kapağı, kapak yokluğundan çok daha geç fark eder.
    """
    import re
    n = lambda x: set(re.sub(r"[^a-z0-9 ]+", " ", (x or "").lower()).split())
    x, y = n(a), n(b)
    if not x or not y:
        return False
    ortak = len(x & y)
    return ortak >= max(2, min(len(x), len(y)) // 2)


def _freewebnovel_kapak(kitap: dict, zorla: bool) -> tuple[str | None, str]:
    """Kitabın kapağını freewebnovel'de arar; (kapak, aciklama) döner.

    KİTAP sayfası değil BÖLÜM sayfası çekilir: ölçüldü ki `og:image` bölüm
    sayfasında da kitap kapağını veriyor, ve bölüm yolu mevcut çekme
    altyapısının (Cloudflare + tek çekim kapısı) doğrudan kullanılmasını
    sağlıyor — kapak için ikinci bir kod yolu açmaya gerek kalmıyor.
    """
    # 1) EN GUVENILIR yol: kitabin ZATEN kayitli bir freewebnovel bolumu varsa
    #    onu cek. Slug tahmin edilmedigi icin yanlis kitaba dusme riski YOK ve
    #    ad dogrulamasina da gerek kalmaz. (Olculen vaka: `solo-leveling`in
    #    onbelleginde hem novelbin hem freewebnovel bolumleri duruyor.)
    kayitli = [c["url"] for c in cache.list_chapters(kitap["slug"])
               if "freewebnovel.com" in (c.get("url") or "")]
    if kayitli:
        try:
            bolum = fetch_chapter(kayitli[0], priority="bulk")
            kapak = (bolum.get("cover") or "").strip()
            if kapak:
                return kapak, "kayıtlı freewebnovel bölümü"
        except Exception:  # noqa: BLE001 — bakim araci; slug tahminine dusulur
            pass

    # 2) Kayitli bolum yoksa slug TAHMIN et. Burada ad dogrulamasi sart.
    adaylar = []
    for aday in (kitap["slug"], _slugify(kitap.get("title") or "")):
        if aday and aday not in adaylar:
            adaylar.append(aday)
    for aday in adaylar:
        url = f"https://freewebnovel.com/novel/{aday}/chapter-1"
        try:
            bolum = fetch_chapter(url, priority="bulk")
        except Exception as exc:  # noqa: BLE001 — bakim araci
            son = f"{type(exc).__name__}"
            continue
        kapak = (bolum.get("cover") or "").strip()
        if not kapak:
            son = "og:image yok"
            continue
        bulunan = bolum.get("book_title") or aday
        if not zorla and not _ad_uyusuyor(bulunan, kitap.get("title") or ""):
            return None, f"ad UYUSMADI (freewebnovel: {bulunan!r}) — --zorla ile yazılır"
        return kapak, f"slug={aday}"
    return None, locals().get("son", "aday slug bulunamadı")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uygula", action="store_true", help="gerçekten çek ve yaz")
    ap.add_argument("--slug", help="yalnız bu kitap")
    ap.add_argument("--hepsi", action="store_true",
                    help="kapağı olanları da yeniden yokla")
    ap.add_argument("--freewebnovel", action="store_true",
                    help="kapağı kitabın KENDİ kaynağından değil freewebnovel'den ara")
    ap.add_argument("--zorla", action="store_true",
                    help="freewebnovel modunda kitap adı uyuşmasa da yaz")
    a = ap.parse_args()

    kitaplar = library.list_books()
    if a.slug:
        kitaplar = [k for k in kitaplar if k["slug"] == a.slug]
    if not a.hepsi:
        kitaplar = [k for k in kitaplar if not (k.get("cover") or "").strip()]

    if not kitaplar:
        print("Kapağı eksik kitap yok.")
        return 0

    print(f"{len(kitaplar)} kitap işlenecek"
          f"{'' if a.uygula else '  (KURU çalıştırma — --uygula ile yazar)'}\n")
    yazilan = atlanan = hata = 0
    for k in kitaplar:
        slug = k["slug"]
        if a.freewebnovel:
            # MANGA HARIC (kullanici karari): manga kitaplarinin butun bolumleri
            # `manga://` semali yerel sayfalar; freewebnovel'de karsiligi yok ve
            # slug tahmini baska bir kitaba dusebilirdi.
            bolumler_ = cache.list_chapters(slug)
            if bolumler_ and all((c.get("url") or "").startswith("manga://")
                                 for c in bolumler_):
                print(f"  {slug:42} ATLANDI (manga)")
                atlanan += 1
                continue
            if not a.uygula:
                print(f"  {slug:42} freewebnovel'de aranacak")
                continue
            kapak, aciklama = _freewebnovel_kapak(k, a.zorla)
            if kapak:
                library.set_cover(slug, kapak)
                print(f"  {slug:42} OK  ({aciklama})  {kapak[-34:]}")
                yazilan += 1
            else:
                print(f"  {slug:42} bulunamadı: {aciklama}")
                hata += 1
            continue
        # Kapak WEB'den gelir; içe aktarılan (pdf://, epub://, manga://, paste)
        # kitapların kaynağı yok ve onları çekmeye çalışmak boşuna hata üretir.
        bolumler = [c for c in cache.list_chapters(slug)
                    if (c.get("url") or "").startswith("http")]
        if not bolumler:
            print(f"  {slug:42} ATLANDI (web kaynaklı bölümü yok)")
            atlanan += 1
            continue
        url = bolumler[0]["url"]
        if not a.uygula:
            print(f"  {slug:42} çekilecek: {url[:56]}")
            continue
        try:
            bolum = fetch_chapter(url, priority="bulk")
        except Exception as exc:  # noqa: BLE001 — bakim araci
            # `FetchError` DEGIL genel yakalama: taşıma katmanı hataları
            # (ör. alan adı artık çözülmüyor -> ERR_NAME_NOT_RESOLVED) tipli
            # hataya sarılmadan yukarı sızıyor ve TEK kitap bütün turu
            # öldürüyordu — ölçülen vaka: novelbin.com. Bir kitabın kapağı
            # alınamaması kalanları engellememeli; kapak süslemedir.
            print(f"  {slug:42} HATA: {type(exc).__name__}: {str(exc)[:50]}")
            hata += 1
            continue
        kapak = (bolum.get("cover") or "").strip()
        if not kapak:
            print(f"  {slug:42} kapak bulunamadı (og:image yok)")
            atlanan += 1
            continue
        library.set_cover(slug, kapak)
        print(f"  {slug:42} OK  {kapak[:52]}")
        yazilan += 1

    if a.uygula:
        print(f"\nyazılan {yazilan} · atlanan {atlanan} · hata {hata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
