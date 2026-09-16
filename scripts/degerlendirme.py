"""Gerçek bölümlerle ÇEVİRİ KALİTESİ değerlendirme seti.

Belge (2026-09-16): kalite ölçümü terim uyumu + hizalama + eksik içerik + İNSAN
akıcılık değerlendirmesini birlikte kapsamalı; uzunluk oranı içerik kaybı için
ALARMDIR, tek başına kalite puanı değildir; terim düzeyi ile cümle düzeyi ayrı
ölçülür. Bu araç o dört boyutu tek raporda toplar. Ölçütler projenin KENDİ
deterministik fonksiyonlarıdır (`sozluk_ihlalleri`, `ingilizce_kalinti`, hizalama);
kopyalanırsa ikinci bir kural kümesi doğardı.

METİNLER DEPOYA GİRMEZ: set yalnız bölüm ADRESLERİdir, çıktılar `cache/degerlendirme/`
altına yazılır (`cache/` git'e girmez). Kaynak metin veritabanından okunur,
siteye inilmez. Önbelleğe ve sözlüğe HİÇBİR ŞEY YAZILMAZ — okuyucunun gördüğü
çeviri değişmez.

Üç kip (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\degerlendirme.py
        KURU: seti seçer/gösterir, önbellekteki MEVCUT çevirileri ölçer (taban).
        API ÇAĞIRMAZ, kota yakmaz.
    ... --calistir [--model gemini-3.6-flash]
        Seti ŞU ANKİ sözlük ve zincirle yeniden çevirir ve ölçer. Bölüm başına en
        az 1 Gemini isteği (+ onarım turları) harcar. ÜCRETLİ modeller (Claude)
        REDDEDİLİR — bu araç para harcayamaz.
    ... --ozet cache/degerlendirme/<koşu>
        Koşunun ölçümlerini ve doldurulmuş insan puanlarını tablo olarak basar.

    --adet N (varsayılan 6) · --kitap SLUG (tek kitap) · --yeni-set (seti yeniden seç)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from core import cache, glossary, translate  # noqa: E402

CIKTI_KOKU = KOK / "cache" / "degerlendirme"
SET_DOSYASI = CIKTI_KOKU / "set.json"
# Uzunluk oranı bu değerin altındaysa EKSİK İÇERİK alarmı. Önbellekteki 3.6-flash
# üretim verisinin medyanı 0,972; özetleyen model (3-flash-preview) 0,436 verdi.
EKSIK_ICERIK_ESIGI = 0.85
# Paragraf düzeyi: tek bir paragrafın oranı bunun altındaysa o paragraf atlanmış/
# kısaltılmış olabilir (bölüm ortalaması iyi olsa bile).
PARAGRAF_ESIGI = 0.5
INSAN_ALANI = re.compile(r"^- (?P<ad>[^:]+) \(1-5\): *(?P<puan>[1-5])?\s*$", re.M)


def _paragraflar(metin: str | None) -> list[str]:
    return [p.strip() for p in (metin or "").split("\n\n") if p.strip()]


def _cumle_sayisi(metin: str) -> int:
    return len([c for c in re.split(r"(?<=[.!?…])\s+", metin) if c.strip()])


def olc(kaynak: str, ceviri: str, sozluk: dict, kosullar: dict) -> dict:
    """Tek bölümün deterministik ölçümleri (API çağırmaz)."""
    en, tr = _paragraflar(kaynak), _paragraflar(ceviri)
    hizali = bool(en) and len(en) == len(tr)
    oran = round(len(ceviri or "") / max(1, len(kaynak or "")), 3)
    kisa_paragraflar = (
        [i for i, (e, t) in enumerate(zip(en, tr)) if len(t) / max(1, len(e)) < PARAGRAF_ESIGI]
        if hizali else []
    )
    return {
        # Terim düzeyi
        "sozluk_ihlali": sorted(translate.sozluk_ihlalleri(sozluk, kaynak, ceviri, kosullar)),
        # Cümle / paragraf düzeyi
        "hizali": hizali,
        "paragraf": [len(en), len(tr)],
        "cumle": [_cumle_sayisi(kaynak or ""), _cumle_sayisi(ceviri or "")],
        "ingilizce_kalinti": sorted(translate.ingilizce_kalinti(tr, en, sozluk)) if hizali else [],
        "kisa_paragraflar": kisa_paragraflar,
        # İçerik kaybı ALARMI (kalite puanı değil)
        "uzunluk_orani": oran,
        "eksik_icerik_alarmi": oran < EKSIK_ICERIK_ESIGI,
    }


def set_sec(adet: int, kitap: str | None) -> list[dict]:
    """Deterministik ve DENGELİ seçim: kitaplar arasında sırayla, her kitapta bölüm
    numarası aralığına yayılmış. Tek kitaptan seçmek o kitabın üslubunu ölçer."""
    adaylar: dict[str, list[dict]] = {}
    for b in cache.denetim_bolumleri(kitap):
        adaylar.setdefault(b["book_slug"], []).append(b)
    kitaplar = sorted(adaylar)
    if not kitaplar:
        return []
    secilen: list[dict] = []
    tur = 0
    while len(secilen) < adet and any(adaylar.values()):
        for slug in kitaplar:
            liste = adaylar[slug]
            if not liste or len(secilen) >= adet:
                continue
            # Kitap içinde: 1., son, orta … (aralığa yayılım)
            idx = [0, len(liste) - 1, len(liste) // 2][tur % 3] if len(liste) > 2 else 0
            b = liste.pop(idx)
            secilen.append({"url": b["url"], "book_slug": slug, "chapter_no": b["chapter_no"],
                            "title": b["title"]})
        tur += 1
    return secilen


def seti_yukle(adet: int, kitap: str | None, yeni: bool) -> list[dict]:
    if SET_DOSYASI.exists() and not yeni:
        return json.loads(SET_DOSYASI.read_text(encoding="utf-8"))["bolumler"]
    bolumler = set_sec(adet, kitap)
    SET_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    SET_DOSYASI.write_text(
        json.dumps({"secim_zamani": time.time(), "bolumler": bolumler}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bolumler


def _satir_bul(url: str) -> dict | None:
    return next((b for b in cache.denetim_bolumleri(None) if b["url"] == url), None)


def ucretli_mi(model: str) -> bool:
    """Ücretsiz olduğu BİLİNEN tek aile Gemini; geri kalan her ad reddedilir (izin
    listesi — yeni bir ücretli sağlayıcı eklendiğinde sessizce geçmesin)."""
    return translate._claude_modeli(model) or not (model or "").startswith("gemini")


def insan_formu(klasor: Path, sonuclar: list[dict]) -> Path:
    """Akıcılık/doğruluk için doldurulacak form. Ölçütler deterministik olarak
    ÖLÇÜLEMEYEN şeydir: cümle doğal mı, anlam korunmuş mu."""
    satirlar = [
        "# İnsan değerlendirmesi",
        "",
        "Her bölüm için ilk paragrafları oku; puanları 1 (kötü) – 5 (çok iyi) arası yaz.",
        "Yalnız bu dosyadaki puan satırlarını doldur; `--ozet` okur.",
        "",
    ]
    for s in sonuclar:
        satirlar += [f"## {s['book_slug']} #{s['chapter_no']} — {s['model']}", ""]
        en, tr = _paragraflar(s["kaynak"]), _paragraflar(s["ceviri"])
        for e, t in list(zip(en, tr))[:3]:
            satirlar += [f"> EN: {e}", ">", f"> TR: {t}", ""]
        satirlar += ["- Akıcılık (1-5): ", "- Anlam doğruluğu (1-5): ", ""]
    yol = klasor / "insan-degerlendirmesi.md"
    yol.write_text("\n".join(satirlar), encoding="utf-8")
    return yol


def calistir(bolumler: list[dict], model: str | None, taban: bool, klasor: Path) -> list[dict]:
    """Taban kipinde önbellekteki çeviri ölçülür; değilse yeniden çevrilir (DB'ye yazmadan)."""
    klasor.mkdir(parents=True, exist_ok=True)
    sonuclar = []
    for b in bolumler:
        satir = _satir_bul(b["url"])
        if satir is None:
            print(f"  ATLANDI (önbellekte kaynağı yok): {b['url']}")
            continue
        slug = b["book_slug"]
        kosullar = glossary.ceviri_kosullari(slug)
        if taban:
            # O bölüm çevrilirken sözlükte DURAN kayıtlarla ölç (bkz. uyum_denetle).
            sozluk = glossary.bolumdeki_sozluk(slug, satir["chapter_no"])
            ceviri, kullanilan = satir["translation"], satir.get("model") or "?"
            sure = None
        else:
            sozluk = glossary.ceviri_sozlugu(slug)
            baslangic = time.time()
            sonuc = translate.translate_chapter(
                satir["source"],
                api_key=os.environ.get("GEMINI_API_KEY"),
                glossary=sozluk,
                models=(model,) if model else None,
                kosullar=kosullar,
            )
            ceviri, kullanilan = sonuc["translation"], sonuc.get("model") or model or "?"
            sure = round(time.time() - baslangic, 1)
        kayit = {
            **b, "model": kullanilan, "sure_sn": sure, "taban": taban,
            "olcum": olc(satir["source"], ceviri, sozluk, kosullar),
            "kaynak": satir["source"], "ceviri": ceviri,
        }
        (klasor / f"{slug}-{b['chapter_no']}.json").write_text(
            json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sonuclar.append(kayit)
    insan_formu(klasor, sonuclar)
    return sonuclar


def ozet(klasor: Path) -> list[dict]:
    """Koşunun ölçümleri + formdaki insan puanları (bölüm sırasıyla)."""
    sonuclar = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(klasor.glob("*.json"))
    ]
    form = klasor / "insan-degerlendirmesi.md"
    puanlar: list[dict] = []
    if form.exists():
        metin = form.read_text(encoding="utf-8")
        bolumler = re.split(r"^## ", metin, flags=re.M)[1:]
        for parca in bolumler:
            baslik = parca.splitlines()[0]
            alanlar = {m["ad"].strip(): (int(m["puan"]) if m["puan"] else None)
                       for m in INSAN_ALANI.finditer(parca)}
            puanlar.append({"baslik": baslik, **alanlar})
    satirlar = []
    for s in sonuclar:
        o = s["olcum"]
        anahtar = f"{s['book_slug']} #{s['chapter_no']}"
        insan = next((p for p in puanlar if p["baslik"].startswith(anahtar)), {})
        satirlar.append({
            "bolum": anahtar, "model": s["model"], "oran": o["uzunluk_orani"],
            "alarm": o["eksik_icerik_alarmi"], "hizali": o["hizali"],
            "ihlal": len(o["sozluk_ihlali"]), "kalinti": len(o["ingilizce_kalinti"]),
            "kisa_paragraf": len(o["kisa_paragraflar"]),
            "akicilik": insan.get("Akıcılık"), "anlam": insan.get("Anlam doğruluğu"),
        })
    return satirlar


def _tablo(satirlar: list[dict]) -> None:
    if not satirlar:
        print("(sonuç yok)")
        return
    print(f"{'bölüm':32} {'model':22} {'oran':>5} {'hiz':>3} {'ihl':>3} {'kal':>3} {'kısa':>4} {'akı':>3} {'anl':>3}")
    for r in satirlar:
        print(
            f"{r['bolum'][:32]:32} {str(r['model'])[:22]:22} {r['oran']:>5}{'!' if r['alarm'] else ' '}"
            f"{'E' if r['hizali'] else 'H':>3} {r['ihlal']:>3} {r['kalinti']:>3} {r['kisa_paragraf']:>4} "
            f"{r['akicilik'] if r['akicilik'] is not None else '-':>3} {r['anlam'] if r['anlam'] is not None else '-':>3}"
        )
    print("\n! = eksik içerik alarmı (oran < %.2f) — alarm, kalite puanı DEĞİL." % EKSIK_ICERIK_ESIGI)


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--adet", type=int, default=6)
    a.add_argument("--kitap")
    a.add_argument("--yeni-set", action="store_true")
    a.add_argument("--calistir", action="store_true", help="API ile yeniden çevir (kota harcar)")
    a.add_argument("--model", help="yalnız bu Gemini modeli (varsayılan: seçili zincir)")
    a.add_argument("--ozet", help="koşu klasörünün özetini bas")
    s = a.parse_args(argv)

    if s.ozet:
        _tablo(ozet(Path(s.ozet)))
        return 0
    if s.model and ucretli_mi(s.model):
        print(f"REDDEDİLDİ: {s.model} ücretli bir model. Değerlendirme aracı para harcamaz.")
        return 2
    if s.calistir and not s.model and any(ucretli_mi(m) for m in translate.secili_zincir()):
        print("REDDEDİLDİ: seçili çeviri modeli ücretli. --model ile bir Gemini modeli ver.")
        return 2

    bolumler = seti_yukle(s.adet, s.kitap, s.yeni_set)
    if not bolumler:
        print("Önbellekte kaynağı ve çevirisi olan bölüm yok.")
        return 1
    print(f"Set ({len(bolumler)} bölüm, {len({b['book_slug'] for b in bolumler})} kitap): {SET_DOSYASI}")
    for b in bolumler:
        print(f"  {b['book_slug']} #{b['chapter_no']}  {b['title'] or ''}")
    kosu = CIKTI_KOKU / time.strftime("%Y%m%d-%H%M%S")
    if s.calistir:
        from dotenv import load_dotenv

        load_dotenv(KOK / ".env")
        print(f"\nYeniden çeviriliyor — en az {len(bolumler)} Gemini isteği (+ onarım turları)…")
        sonuclar = calistir(bolumler, s.model, taban=False, klasor=kosu)
    else:
        print("\nKURU kip: önbellekteki MEVCUT çeviriler ölçülüyor (API yok).")
        sonuclar = calistir(bolumler, None, taban=True, klasor=kosu / "taban")
        kosu = kosu / "taban"
    print(f"\nÇıktılar: {kosu}  (insan formu: insan-degerlendirmesi.md)\n")
    _tablo(ozet(kosu))
    return 0 if sonuclar else 1


if __name__ == "__main__":
    raise SystemExit(main())
