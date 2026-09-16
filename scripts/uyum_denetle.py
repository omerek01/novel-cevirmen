"""Önbellekteki bölümleri sözlük uyumu için denetle (bakım aracı).

Neden var: çeviri yolundaki denetim (`pipeline._uyum_denetimi`) yalnız BUNDAN
SONRA çevrilen bölümleri işaretler, oysa bozukluk zaten önbellekte duran eski
bölümlerde. Model zinciri yalnız ERİŞİLEBİLİRLİĞE bakarak iniyor (kota dolunca
bir alt halka) ve kaliteyi hiçbir yerde ölçmüyordu; alt halkanın çevirisi sessizce
kalıcı önbelleğe yazılıp bir daha kontrol edilmiyordu.

Ölçüm (2026-08-30, Shadow Slave'in önbellekteki 110 bölümü) halkaların sözlük
kuralına EŞİT uymadığını gösterdi:

    gemini-3.6-flash        60 bölüm ->  5 ihlal
    gemini-3.5-flash        45 bölüm ->  1 ihlal
    gemini-3.5-flash-lite    4 bölüm -> 36 ihlal

Somut vaka: 109. bölümü flash-lite çevirdi; `Saint -> Aziz` kaynakta 12 kez
geçiyordu ve 12'si de İngilizce kaldı.

Denetim DETERMİNİSTİKTİR ve API çağırmaz (ne Gemini ne Mistral) — bedava koşar,
kota yakmaz. Yalnız RAPORLAR ve isteğe bağlı olarak `chapters.glossary_leaks`
bayrağını yazar; hiçbir bölümü YENİDEN ÇEVİRMEZ. Yeniden çeviriyi okuyucudan
"Yeniden Çevir" ile siz tetiklersiniz (kaynak önbellekte olduğu için siteye
yeniden inilmez, yalnız çeviri çağrısı yapılır).

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\uyum_denetle.py              # RAPOR (yazmaz)
    .venv\\Scripts\\python.exe scripts\\uyum_denetle.py --uygula     # bayrakları yaz
    ... --kitap shadow-slave        # tek kitap
    ... --ayrinti                   # ihlalli her bölümü terimleriyle listele

Varsayılan KURU çalıştırmadır.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

from core import cache, glossary, translate  # noqa: E402


def denetle(kitap: str | None) -> list[dict]:
    """Her bölüm için ihlalleri hesapla.

    Ölçüt BUGÜNKÜ sözlük DEĞİL, o bölüm çevrilirken sözlükte DURAN kayıtlardır
    (`glossary.bolumdeki_sozluk`): 200. bölümde kaydedilmiş bir terim 50. bölümün
    prompt'unda yoktu, model onu ihlal edemezdi. Süzmesiz ölçüm en eski bölümlerde
    ihlal sayısını ciddi biçimde şişiriyordu.

    KOŞULLAR bilerek BUGÜNKÜ hâliyle okunur (kökene göre süzülmez): koşullu bir
    kayıt ölçülemez sınıftır ve "bugün koşullu" olması onu bugün de ölçülemez
    yapar. Koşulları hiç geçirmemek, doğru çeviriye sahte ihlal yazmak olurdu —
    üstelik `--uygula` o bayrağı kalıcı olarak DB'ye basar.
    """
    sonuc = []
    kosul_onbellegi: dict[str, dict[str, str]] = {}
    for bolum in cache.denetim_bolumleri(kitap):
        slug = bolum["book_slug"]
        if slug not in kosul_onbellegi:
            kosul_onbellegi[slug] = glossary.ceviri_kosullari(slug)
        bolum["ihlaller"] = translate.sozluk_ihlalleri(
            glossary.bolumdeki_sozluk(slug, bolum["chapter_no"]),
            bolum["source"],
            bolum["translation"],
            kosullar=kosul_onbellegi[slug],
        )
        sonuc.append(bolum)
    return sonuc


# Sözlük kayıtlarının bu oranından AZI köken (`first_chapter`) taşıyorsa o kitabın
# sayıları GÜVENİLMEZ sayılır ve raporda işaretlenir. Sebep ölçüldü: köken sütunu
# sonradan eklendi ve eski kitaplarda hiç dolmadı (gerçek veri:
# reincarnation-of-the-strongest-sword-god, 267 kaydın 267'si kökensiz). Kökensiz
# kayıt "her zaman vardı" sayılır, dolayısıyla sözlük daha 5 satırken çevrilmiş bir
# bölüm bugünün 267 satırına göre denetlenir ve ihlal sayısı şişer. Aynı eşik ve aynı
# gerekçe `sozluk_gozden_gecir.py`de de var (MIN_KAYNAK_KAPSAMA).
MIN_KOKEN_KAPSAMA = 0.8


def koken_kapsamasi(book_slug: str) -> tuple[int, int]:
    """(kökeni bilinen kayıt, toplam kayıt) — sayının güvenilirliğini belirler."""
    satirlar = glossary.get_glossary_rows(book_slug)
    return sum(1 for r in satirlar if r["first_chapter"] is not None), len(satirlar)


def _model_tablosu(bolumler: list[dict]) -> str:
    """Halka başına ihlal oranı — zincir sırasının gerekçesi bu tablodan gelir."""
    stat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for b in bolumler:
        s = stat[b["model"] or "(bilinmiyor)"]
        s[0] += 1
        s[1] += len(b["ihlaller"])
    satirlar = [f"{'model':28} {'bölüm':>6} {'ihlal':>6} {'bölüm başına':>13}"]
    for model, (adet, ihlal) in sorted(stat.items(), key=lambda x: -x[1][1]):
        satirlar.append(f"{model:28} {adet:6} {ihlal:6} {ihlal / adet:13.2f}")
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kitap", help="yalnız bu kitap (slug)")
    ayristirici.add_argument("--uygula", action="store_true",
                             help="bayrakları DB'ye yaz (varsayılan: yalnız rapor)")
    ayristirici.add_argument("--ayrinti", action="store_true",
                             help="ihlalli her bölümü terimleriyle listele")
    args = ayristirici.parse_args()

    bolumler = denetle(args.kitap)
    if not bolumler:
        print("Denetlenecek bölüm yok (kaynağı ve çevirisi olan satır bulunamadı).")
        return 0

    ihlalli = [b for b in bolumler if b["ihlaller"]]
    print(f"Denetlenen bölüm: {len(bolumler)}   ihlalli bölüm: {len(ihlalli)}")
    print()
    print(_model_tablosu(bolumler))

    # Kökeni bilinmeyen sözlükte sayı ŞİŞER (bkz. MIN_KOKEN_KAPSAMA). Sessiz kalmak,
    # kullanıcıyı olmayan bir bozukluğu kovalamaya iterdi.
    supheli = []
    for slug in sorted({b["book_slug"] for b in bolumler}):
        bilinen, toplam = koken_kapsamasi(slug)
        if toplam and bilinen / toplam < MIN_KOKEN_KAPSAMA:
            supheli.append((slug, bilinen, toplam))
    if supheli:
        print()
        print("UYARI — bu kitapların sayıları GÜVENİLMEZ (sözlük kaydı köken taşımıyor,")
        print("yani sonradan eklenen terimler eski bölümlere geriye dönük uygulanıyor):")
        for slug, bilinen, toplam in supheli:
            print(f"  {slug}: {toplam} kaydın yalnız {bilinen}'i kökenli")

    if args.ayrinti and ihlalli:
        print()
        print("İhlalli bölümler:")
        for b in ihlalli:
            terimler = ", ".join(
                f"{k} → {v}" for k, v in sorted(b["ihlaller"].items())
            )
            print(f"  [{b['book_slug']}] {b['chapter_no']} · {b['model']}")
            print(f"      {terimler}")

    if not args.uygula:
        print()
        print("KURU çalıştırma — hiçbir şey yazılmadı. Yazmak için: --uygula")
        return 0

    yazilan = 0
    for b in bolumler:
        # Bayrak zaten AYNIysa yazma: gereksiz UPDATE'ler WAL'i şişirir.
        if b["glossary_leaks"] == b["ihlaller"]:
            continue
        if cache.set_glossary_leaks(b["url"], b["ihlaller"]):
            yazilan += 1
    print()
    print(f"{yazilan} bölümün bayrağı güncellendi.")
    if ihlalli:
        print("İhlalli bölümler okuyucuda künye rozetinde ⚠ ile görünecek; "
              "düzeltmek için o bölümde 'Yeniden Çevir'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
