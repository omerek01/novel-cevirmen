"""Önbellekte İNGİLİZCE kalmış paragrafları bul ve hedefli olarak onar (bakım aracı).

Neden var: çeviri yolundaki onarım (`translate._kalintiyi_onar`) yalnız BUNDAN
SONRA çevrilen bölümleri kurtarır, oysa bozukluk zaten önbellekte duran bölümlerde
ve önbellek isabeti bir daha çeviri TETİKLEMEZ — yani kullanıcı o paragrafı
sonsuza dek İngilizce görür.

Ölçüm (2026-09-05, önbellekteki 392 hizalı bölüm) altı vaka buldu, altısı da
`gemini-3.5-flash`:

    shadow-slave #58   p26  iki özel ad arasındaki bağlaç kalmış
    shadow-slave #177  p41  cümle başındaki yardımcı fiil kalmış
    shadow-slave #179  p51  replik hiç çevrilmemiş
    shadow-slave #181  p56  cümle hiç çevrilmemiş
    shadow-slave #188  p46  replik hiç çevrilmemiş
    shadow-slave #194  p41  cümle başındaki bağlaç kalmış

DENETİM bedavadır (deterministik, API'siz). ONARIM değildir: `--uygula` yalnız
sızan paragrafları yeniden çevirir — bölümün tamamını DEĞİL. Tipik vaka 60
paragraflık bölümde 1 paragraftır, yani maliyet tam bölümün yüzde birkaçıdır.
Ücretli bir model seçiliyse bu da PARA harcar; varsayılan bu yüzden KURU
çalıştırmadır ve araç ne harcayacağını önce raporlar.

Kaynak metin önbellekten okunur — siteye YENİDEN İNİLMEZ, Cloudflare'e
dokunulmaz.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\kalinti_onar.py              # RAPOR (yazmaz)
    .venv\\Scripts\\python.exe scripts\\kalinti_onar.py --isaretle   # yalnız bayrak yaz (API'siz)
    .venv\\Scripts\\python.exe scripts\\kalinti_onar.py --uygula     # yeniden çevir + yaz
    ... --kitap shadow-slave        # tek kitap
    ... --bolum 188                 # tek bölüm (--kitap ile birlikte)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from dotenv import load_dotenv  # noqa: E402

from core import cache, translate  # noqa: E402


def _sozlukler() -> dict[str, dict[str, str]]:
    """Kitap başına {kaynak: karşılık}. Tek seferde okunur, bölüm başına değil."""
    from core import glossary

    out: dict[str, dict[str, str]] = {}
    for bolum in cache.denetim_bolumleri(None):
        slug = bolum["book_slug"]
        if slug not in out:
            out[slug] = glossary.get_glossary(slug)
    return out


def _paragraflar(metin: str | None) -> list[str]:
    return [p for p in (metin or "").split("\n\n") if p.strip()]


def denetle(kitap: str | None, bolum_no: int | None) -> list[dict]:
    """Sızıntısı olan bölümleri bul. API ÇAĞIRMAZ — bedava koşar.

    Ölçüt hizalamaya dayanır: `source_text` NULL olan (hizalaması tutmamış) bölümde
    hangi Türkçe paragrafın hangi İngilizce paragrafa karşılık geldiği bilinmediği
    için denetim UYGULANAMAZ ve o bölüm listeye hiç girmez.
    """
    sozlukler = _sozlukler()
    sonuc: list[dict] = []
    for b in cache.denetim_bolumleri(kitap):
        if bolum_no is not None and b["chapter_no"] != bolum_no:
            continue
        tp = _paragraflar(b["translation"])
        sp = _paragraflar(b["source"])
        kalinti = translate.ingilizce_kalinti(tp, sp, sozlukler.get(b["book_slug"]))
        if kalinti:
            b["kalinti"] = kalinti
            b["tr_paras"], b["en_paras"] = tp, sp
            sonuc.append(b)
    return sonuc


def onar(bolum: dict, sozluk: dict[str, str]) -> dict[int, str]:
    """Bölümün sızan paragraflarını yeniden çevirip DB'ye yazar; KALANI döner.

    Çeviri yolundaki onarımla AYNI fonksiyonu (`translate._kalintiyi_onar`)
    kullanır — ikinci bir onarım kuralı yazmak, iki yolun zamanla ayrışması
    demekti (bu projede künye alanları tam olarak böyle ayrışmıştı).
    """
    kullanilan: dict[str, None] = {}
    kalan = translate._kalintiyi_onar(
        translate._gemini_fabrikasi(None),
        translate.secili_zincir(),
        bolum["tr_paras"],
        bolum["en_paras"],
        bolum["kalinti"],
        sozluk,
        kullanilan,
        set(),   # yeni karakter adları: onarım sözlüğe YAZMAZ (aşağıdaki nota bak)
        {},      # yeni terimler: aynı sebep
    )
    # Onarım sözlüğe kayıt EKLEMEZ: tek bir paragraftan çıkan öneri, bölümün
    # tamamını görerek verilmiş özgün kararla çelişebilir ve sözlük kaydı sonraki
    # bütün bölümlerde KURAL olarak uygulanır — geri alması pahalı bir yan etki.
    yeni_model = " + ".join(kullanilan) or None
    birlesik = bolum.get("model")
    if yeni_model and yeni_model not in (birlesik or ""):
        birlesik = f"{birlesik} + {yeni_model}" if birlesik else yeni_model
    cache.set_translation(
        bolum["url"],
        "\n\n".join(bolum["tr_paras"]),
        model=birlesik,
        engine=translate.motor_adi(birlesik),
    )
    cache.set_ingilizce_kalinti(bolum["url"], kalan)
    return kalan


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", help="yalnız bu kitap (slug)")
    ayristirici.add_argument("--bolum", type=int, help="yalnız bu bölüm numarası")
    ayristirici.add_argument(
        "--isaretle", action="store_true",
        help="bayrakları yaz ama YENİDEN ÇEVİRME (API'siz, bedava)")
    ayristirici.add_argument(
        "--uygula", action="store_true",
        help="sızan paragrafları yeniden çevir ve DB'ye yaz (API harcar)")
    a = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
    bozuklar = denetle(a.kitap, a.bolum)

    if not bozuklar:
        print("Sızıntı bulunamadı — denetlenen bölümlerin hepsi temiz.")
        return 0

    toplam = sum(len(b["kalinti"]) for b in bozuklar)
    print(f"{len(bozuklar)} bölümde {toplam} paragraf İngilizce kalmış:\n")
    for b in bozuklar:
        print(f"  {b['book_slug']} #{b['chapter_no']}  [{b['model'] or '?'}]")
        for i in sorted(b["kalinti"]):
            metin = b["kalinti"][i]
            kisa = metin if len(metin) <= 100 else metin[:100] + "…"
            print(f"      p{i}: {kisa}")
    print()

    if a.isaretle:
        for b in bozuklar:
            cache.set_ingilizce_kalinti(b["url"], b["kalinti"])
        print(f"{len(bozuklar)} bölüm işaretlendi (yeniden çeviri YAPILMADI).")
        return 0

    if not a.uygula:
        print("KURU çalıştırma — hiçbir şey yazılmadı.")
        print("  --isaretle : yalnız bayrakları yaz (API'siz)")
        print(f"  --uygula   : {toplam} paragrafı yeniden çevir (API harcar)")
        return 0

    if not translate.ceviri_anahtari_var_mi():
        print("HATA: Gemini API anahtarı yok (.env). Onarım yapılamaz.")
        return 1

    sozlukler = _sozlukler()
    duzelen = kalan_toplam = 0
    for b in bozuklar:
        onceki = len(b["kalinti"])
        try:
            kalan = onar(b, sozlukler.get(b["book_slug"], {}))
        except Exception as hata:  # noqa: BLE001 — araç TEK bölümde durmamalı
            # Bir bölümün onarımı çökerse geri kalanlar denenmeye devam etmeli:
            # 6 bölümlük bir listede ilk bölümdeki kota hatası, hepsini kaybettirirdi.
            print(f"  {b['book_slug']} #{b['chapter_no']}: ONARILAMADI ({hata})")
            kalan_toplam += onceki
            continue
        duzelen += onceki - len(kalan)
        kalan_toplam += len(kalan)
        durum = "temiz" if not kalan else f"{len(kalan)} paragraf hâlâ İngilizce"
        print(f"  {b['book_slug']} #{b['chapter_no']}: {durum}")

    print(f"\nOnarılan paragraf: {duzelen} · kalan: {kalan_toplam}")
    if kalan_toplam:
        print("Kalanlar künyeye bayrak olarak yazıldı; okuyucuda ⚠ ile görünür.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
