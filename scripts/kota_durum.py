"""Anahtar havuzunun kota durumunu gösterir (bakım aracı).

"Kotam doldu mu, ne zaman açılır" sorusu tahminle cevaplanamaz: Gemini'nin 429'u
İKİ ayrı sınırdan gelebilir ve ikisinin açılma süresi tamamen farklıdır.

  * DAKİKALIK (RPM / TPM) — bir dakika içinde kendiliğinden açılır.
  * GÜNLÜK   (RPD)        — Pasifik gece yarısına kadar KAPALI kalır.

429 gövdesindeki `QuotaFailure.violations[].quotaId` hangisi olduğunu söyler ve
`RetryInfo.retryDelay` önerilen beklemeyi verir. Araç ikisini de basar.

DİKKAT — bu araç KÜÇÜK bir istek atar, yani RPM ve RPD'yi yoklar ama TPM'i
(dakikadaki TOKEN) YOKLAMAZ. Bu projenin gerçek isteği ~8.000 giriş token'ı
taşıyor; küçük istek geçse bile gerçek çeviri TPM'e takılabilir. "AÇIK" sonucu
"kota tamamen boş" demek DEĞİLDİR.

Kota PROJE başınadır, anahtar başına değil: aynı Google Cloud projesinden alınmış
iki anahtar aynı havuzdan içer ve ikincisi hiçbir şey kazandırmaz. Araç bunu
anahtardan okuyamaz ama bir İPUCU verir — iki anahtarın model erişimi FARKLIYSA
(biri bir modele 404 derken öteki demiyorsa) projeleri kesinlikle ayrıdır.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe scripts\\kota_durum.py
    ... --model gemini-3.6-flash    # yalnız bu modeli yokla
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "app"))

# Windows konsolu varsayılan olarak cp1252 kullanır ve Türkçe `ı`/`ş`/`ğ` orada
# YOK: araç tabloyu basarken `UnicodeEncodeError` ile ÇÖKÜYORDU (gerçek vaka
# 2026-09-09 — ilk anahtarın kota satırında öldü, kalan dört anahtar hiç
# yoklanmadı ve "kotam dolu mu" sorusu cevapsız kaldı). Bir teşhis aracının
# konsol kodlaması yüzünden ölmesi, teşhis edilen arızadan daha çok vakit yakar.
# `errors="replace"` ikinci ağ: UTF-8'e geçilemeyen bir terminalde bile araç
# çökmek yerine karakteri değiştirip çalışmaya devam eder.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover — çok eski/tuhaf konsol
    pass

from dotenv import load_dotenv  # noqa: E402

from core import translate  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python 3.9 altı
    ZoneInfo = None  # type: ignore[assignment]


def maskele(deger: str) -> str:
    """Anahtarın parmak izi. DEĞERİ asla tam yazılmaz (log/ekran görüntüsü riski)."""
    return f"{deger[:4]}…{deger[-2:]}" if deger else "(boş)"


# Gövde ayrıştırması ve GÜNLÜK/DAKİKALIK ayrımı `translate` ile PAYLAŞILIR.
# İkinci bir kopya yazmak, bu araç "GÜNLÜK" derken çeviri yolunun anahtarı 60 sn
# sonra yeniden denemesi gibi sessiz bir ayrışma üretirdi — bu projede aynı
# kuralın iki yerde yaşaması defalarca böyle bitti (künye alanları, motor adı).
_hata_govdesi = translate._hata_govdesi


def kota_ayrinti(hata: Exception) -> str:
    """429 gövdesinden kota kimliğini ve önerilen beklemeyi çıkarır."""
    govde = _hata_govdesi(hata)
    err = govde.get("error", govde) if isinstance(govde, dict) else {}
    parcalar: list[str] = []
    for d in err.get("details") or []:
        tur = (d.get("@type") or "").split(".")[-1]
        if tur == "QuotaFailure":
            for ihlal in d.get("violations") or []:
                kimlik = ihlal.get("quotaId") or ihlal.get("quotaMetric") or "?"
                sinir = ihlal.get("quotaValue")
                gunluk = translate.gunluk_kota_mi(hata)
                parcalar.append(
                    ("GÜNLÜK" if gunluk else "DAKİKALIK")
                    + f" ({kimlik}" + (f", sınır {sinir}" if sinir else "") + ")"
                )
        elif tur == "RetryInfo" and d.get("retryDelay"):
            parcalar.append(f"öneri: {d['retryDelay']} bekle")
    return " | ".join(parcalar) or "(ayrıntı yok)"


def erisim_kesin_farkli(a: dict[str, set[str]], b: dict[str, set[str]]) -> bool:
    """İki anahtarın model erişimi KESİN olarak farklı mı?

    Girdi: {"acik": {...}, "yok": {...}} — yalnız KESİN cevaplar (AÇIK / 404).
    Geçici hata (503, 429) erişim hakkında bir şey SÖYLEMEZ: ilk sürüm "açık
    kümesi eşit mi" diye bakıyordu ve aynı anda birinde 503 verip ötekinde açık
    dönen bir model, projeleri "kesinlikle ayrı" gösteriyordu (gerçek çıktı
    2026-09-16: 3.5-flash'taki 503 dalgası 10 çiftin 10'unu ayrı saydı, oysa
    kanıt yalnız 2.5-flash'ın 404 deseniydi).
    """
    return bool((a["acik"] & b["yok"]) or (b["acik"] & a["yok"]))


def _pasifik_gece_yarisi() -> tuple[datetime, datetime]:
    """(Pasifik şimdi, bir sonraki Pasifik gece yarısı) — yaz saatine duyarlı."""
    simdi = datetime.now(timezone.utc)
    if ZoneInfo is not None:
        try:
            pas = simdi.astimezone(ZoneInfo("America/Los_Angeles"))
        except Exception:  # tzdata yoksa
            pas = simdi.astimezone(timezone(timedelta(hours=-8)))
    else:  # pragma: no cover
        pas = simdi.astimezone(timezone(timedelta(hours=-8)))
    ertesi = (pas + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return pas, ertesi


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--model", action="append",
                             help="yalnız bu model(ler)i yokla")
    a = ayristirici.parse_args()

    load_dotenv(KOK / ".env")
    from google import genai  # .env yüklendikten SONRA

    degiskenler = translate.gemini_anahtar_degiskenleri()
    anahtarlar = translate.gemini_anahtarlari()
    if not anahtarlar:
        print("Havuzda hiç Gemini anahtarı yok (.env).")
        return 1

    modeller = tuple(a.model) if a.model else tuple(
        dict.fromkeys(translate.DEFAULT_MODELS + translate.SECILEBILIR_ADLAR)
    )
    modeller = tuple(m for m in modeller if m.startswith("gemini"))

    print(f"Havuz: {len(anahtarlar)} anahtar — {', '.join(degiskenler)}\n")
    erisim: dict[str, dict[str, set[str]]] = {}
    for ad, anahtar in zip(degiskenler, anahtarlar):
        print(f"--- {ad}  {maskele(anahtar)}")
        istemci = genai.Client(api_key=anahtar)
        acik: set[str] = set()
        yok: set[str] = set()
        for model in modeller:
            try:
                istemci.models.generate_content(model=model, contents="OK")
            except Exception as hata:  # noqa: BLE001 — teşhis aracı
                kod = getattr(hata, "code", None) or ""
                if kod == 429:
                    print(f"      {model:26} KOTA DOLU  {kota_ayrinti(hata)}")
                elif kod == 404:
                    print(f"      {model:26} YOK (bu projede sunulmuyor)")
                    yok.add(model)
                else:
                    print(f"      {model:26} HATA {kod}  {str(hata)[:80]}")
            else:
                print(f"      {model:26} AÇIK")
                acik.add(model)
        erisim[ad] = {"acik": acik, "yok": yok}
        print()

    # Proje AYRILIĞI ipucu: model erişimi farklıysa projeler kesinlikle ayrıdır.
    farkli = [
        (a1, a2)
        for i, a1 in enumerate(degiskenler)
        for a2 in degiskenler[i + 1:]
        if erisim_kesin_farkli(erisim[a1], erisim[a2])
    ]
    if farkli:
        print("Model erişimi FARKLI olan çiftler (projeleri kesinlikle ayrı):")
        for a1, a2 in farkli:
            print(f"   {a1} <-> {a2}")
    else:
        print("Kesin bir erişim farkı yok (geçici hatalar sayılmaz) — projelerin ayrı olduğunu")
        print("bu araç kanıtlayamaz. Kota PROJE başınadır: aynı projeden alınmış")
        print("anahtarlar aynı havuzdan içer ve ikincisi hiçbir şey kazandırmaz.")

    pas, ertesi = _pasifik_gece_yarisi()
    yerel = datetime.now().astimezone()
    kalan = ertesi - pas
    print()
    print(f"Pasifik saati şu an : {pas:%Y-%m-%d %H:%M %Z}")
    print("GÜNLÜK kota (RPD) Pasifik gece yarısı sıfırlanır:")
    print(f"   {ertesi.astimezone(yerel.tzinfo):%Y-%m-%d %H:%M} yerel saatle"
          f"  (~{kalan.total_seconds() / 3600:.1f} saat sonra)")
    # Bulut sunucunun "yerel" saati UTC'dir; kullanıcı TSİ ile düşünüyor.
    if ZoneInfo is not None:
        try:
            print(f"   {ertesi.astimezone(ZoneInfo('Europe/Istanbul')):%Y-%m-%d %H:%M} TSİ")
        except Exception:  # tzdata yoksa
            pass
    print("DAKİKALIK kota (RPM/TPM) bir dakika içinde kendiliğinden açılır;")
    print(f"   uygulama anahtarı {translate.ANAHTAR_SOGUMA_SN} sn soğumaya alır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
