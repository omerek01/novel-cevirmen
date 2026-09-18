"""API gözlem kaydını okur (bakım aracı; Google'a İSTEK ATMAZ, kota harcamaz).

"3.6 seçiliyken neden 3.5 ile çevrildi?" sorusunun cevabı artık kayıtta:
her gerçek Gemini isteği, soğuma nedeniyle atlanan her anahtar ve zincirin ilk
halkası dışına her iniş `core.api_durum` tablolarına yazılıyor. Bu araç onları
insan okuyacak biçimde basar. Arayüzdeki panel gelene kadar tek okuma yolu budur.

`scripts/kota_durum.py`den farkı: o araç her anahtara KÜÇÜK bir istek atıp ŞU
ANKİ durumu yoklar (kota harcar). Bu araç yalnız uygulamanın zaten yaptığı
isteklerin kaydını okur (harcamaz), ama yalnız kayıt başladıktan sonrasını bilir.

Kullanım (proje kökünden; sunucuda `.venv/bin/python`):
    .venv\\Scripts\\python.exe scripts\\api_durum_rapor.py
    ... --gecis 50             # son 50 model geçişi
    ... --url <bölüm-url>      # tek bölümün bütün denemeleri
    ... --olay 100             # son 100 ham olay (istek + atlama + geçiş)
    ... --gun 2026-09-17       # başka bir Pasifik gününün sayaçları
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from dotenv import load_dotenv  # noqa: E402

from core import api_durum, translate  # noqa: E402

try:
    from zoneinfo import ZoneInfo

    _TSI = ZoneInfo("Europe/Istanbul")
except Exception:  # noqa: BLE001 — tzdata yoksa yerel saat
    _TSI = None


def _saat(ts: float | None) -> str:
    if not ts:
        return "-"
    an = datetime.fromtimestamp(ts, _TSI) if _TSI else datetime.fromtimestamp(ts)
    return an.strftime("%m-%d %H:%M:%S")


def _sira_haritasi() -> dict[str, str]:
    """Kimlik -> "Anahtar N" (bugünkü .env sırasıyla). Kayıtta olup .env'de
    olmayan kimlik "çıkarılmış" diye gösterilir."""
    anahtarlar = translate.gemini_anahtarlari(os.getenv("GEMINI_API_KEY"))
    return {
        api_durum.anahtar_kimligi(a): f"Anahtar {i + 1}" for i, a in enumerate(anahtarlar)
    }


def _ad(harita: dict[str, str], kimlik: str | None, sira: int | None = None) -> str:
    if kimlik in harita:
        return harita[kimlik]
    if kimlik and kimlik.startswith("sira"):
        return f"Anahtar {kimlik[4:]}"
    return f"(çıkarılmış anahtar, o gün #{sira})" if sira else "(bilinmeyen anahtar)"


def _kisa_url(url: str | None) -> str:
    if not url:
        return "-"
    parcalar = url.rstrip("/").split("/")
    return "/".join(parcalar[-2:])


def ozet_bas(gun: str | None) -> None:
    harita = _sira_haritasi()
    gun = gun or api_durum.pasifik_gunu()
    bas = api_durum.kayit_baslangici()
    print(f"Kayıt başlangıcı: {_saat(bas)} (TSİ). Öncesi bilinmiyor.")
    print(
        f"Pasifik günü {gun} — günlük kota sıfırlanması: "
        f"{_saat(api_durum.sonraki_sifirlama())} (TSİ)\n"
    )

    print("== Bu günün gerçek istekleri (soğuma atlamaları SAYILMAZ)")
    sayaclar = api_durum.gunluk_sayaclar(gun)
    if not sayaclar:
        print("  (kayıt yok)")
    for s in sorted(sayaclar, key=lambda s: (_ad(harita, s["anahtar"]), s["model"])):
        print(
            f"  {_ad(harita, s['anahtar']):<12} {s['model']:<20} deneme {s['deneme']:>3}"
            f"  başarı {s['basari']:>3}  hata {s['hata']:>3}  (kota {s['kota']})"
            f"  token {s['giris_token']}/{s['cikis_token']}"
        )

    print("\n== Son gözlem (anahtar x model)")
    simdi = time.time()
    for d in sorted(api_durum.son_durumlar(),
                    key=lambda d: (_ad(harita, d["anahtar"], d["sira"]), d["model"])):
        soguma = ""
        if d.get("soguma_bitis") and d["soguma_bitis"] > simdi:
            soguma = f"  SOĞUMADA → {_saat(d['soguma_bitis'])}"
        hata = ""
        if d.get("hata_sinifi"):
            hata = f"  son hata {_saat(d['son_hata'])}: {api_durum.ETIKET.get(d['hata_sinifi'])}"
            if d.get("http_kodu"):
                hata += f" (HTTP {d['http_kodu']})"
            if d.get("kota_sinir"):
                hata += f" sınır {d['kota_sinir']}"
        print(
            f"  {_ad(harita, d['anahtar'], d['sira']):<12} {d['model']:<20}"
            f" son: {api_durum.ETIKET.get(d['sonuc'], d['sonuc'])}"
            f"  son başarı {_saat(d['son_basari'])}{hata}{soguma}"
        )


def gecis_bas(limit: int) -> None:
    print(f"\n== Son {limit} model geçişi (ilk halka dışına iniş / zincir tükenmesi)")
    olaylar = api_durum.son_olaylar(limit, turler=("gecis", "tukendi"))
    if not olaylar:
        print("  (kayıt yok — kayıt başladıktan sonra hiç inilmemiş)")
    for o in olaylar:
        ayrinti = o.get("ayrinti") if isinstance(o.get("ayrinti"), dict) else {}
        print(
            f"  {_saat(o['zaman'])}  {o.get('amac') or '-':<14} "
            f"{_kisa_url(o.get('url')):<28} {ayrinti.get('ozet', '')}"
        )


def olay_bas(limit: int, url: str | None) -> None:
    harita = _sira_haritasi()
    baslik = f"bölüm {url}" if url else f"son {limit} olay"
    print(f"\n== Ham olaylar: {baslik} (yeniden eskiye)")
    for o in api_durum.son_olaylar(limit, url=url):
        if o["tur"] in ("gecis", "tukendi"):
            ayrinti = o.get("ayrinti") if isinstance(o.get("ayrinti"), dict) else {}
            satir = f"{o['tur'].upper():<7} {ayrinti.get('ozet', '')}"
        else:
            kod = f" HTTP {o['http_kodu']}" if o.get("http_kodu") else ""
            sure = f" {o['sure_ms']} ms" if o.get("sure_ms") is not None else ""
            satir = (
                f"{o['tur']:<7} {_ad(harita, o.get('anahtar'), o.get('sira')):<12}"
                f" {o.get('model') or '':<20} "
                f"{api_durum.ETIKET.get(o.get('sonuc'), o.get('sonuc'))}{kod}{sure}"
            )
        print(
            f"  {_saat(o['zaman'])} {o.get('amac') or '-':<14} "
            f"{(o.get('asama') or ''):<16} {satir}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gun", help="Pasifik günü (YYYY-MM-DD); varsayılan bugün")
    ap.add_argument("--gecis", type=int, default=20, help="kaç model geçişi basılsın")
    ap.add_argument("--olay", type=int, default=0, help="kaç ham olay basılsın")
    ap.add_argument("--url", help="yalnız bu bölümün olayları")
    args = ap.parse_args()

    load_dotenv(KOK / ".env")
    ozet_bas(args.gun)
    gecis_bas(args.gecis)
    if args.olay or args.url:
        olay_bas(args.olay or 200, args.url)


if __name__ == "__main__":
    main()
