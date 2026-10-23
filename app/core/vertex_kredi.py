"""Vertex kredisi göstergesi: Google'ın ÖLÇTÜĞÜ token sayısından harcama.

Neden `kullanim` tablosu yetmiyor: o yalnız uygulamanın kendi çeviri çağrılarını sayıyor.
Betikler (defterin toplu işlenmesi, ölçüm ve hakem turları) oraya yazmıyor; 2026-10-23
ölçümünde uygulama ≈51 $ derken Google'ın token sayısı ≈132 $ ediyordu, konsol ise %55
(165 $) diyordu. Kaynak: Cloud Monitoring
`aiplatform.googleapis.com/publisher/online_serving/token_count` (model + input/output).

Kalan kredi ve bitiş tarihi için Google'ın bir API'si YOK; ikisi kullanıcıdan bir kez
alınır. Fiyat tablosu (`kullanim.FIYAT`) Vertex faturasıyla birebir tutmayabilir; bu
yüzden kullanıcı konsolda gördüğü kullanılan tutarı girebilir (`okuma`): toplam = o
okuma + okumadan SONRAKİ saatlerin tahmini. Tahmin hatası böylece yalnız yeni harcamaya
yayılır.

Monitoring veriyi 6 hafta tutar: saatlik toplamlar bu yüzden kendi tablomuza yazılır
(`vertex_token_saat`), eskiyen saatler kaybolmaz. Eşitleme en çok saatte bir koşar.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import db, kullanim, settings

METRIK = "aiplatform.googleapis.com/publisher/online_serving/token_count"
SAKLAMA_GUN = 42  # Monitoring'in bu metrik için tuttuğu süre
ESITLEME_ARALIK_SN = 3600
ZAMAN_ASIMI_SN = 15
VARSAYILAN_TUTAR = 300.0
DENEME_GUN = 90  # ücretsiz deneme kredisinin süresi (Google kuralı)

ANAHTAR_TUTAR = "kredi.tutar"
ANAHTAR_BITIS = "kredi.bitis"
ANAHTAR_OKUMA_TUTAR = "kredi.okuma_tutar"
ANAHTAR_OKUMA_ZAMAN = "kredi.okuma_zaman"
ANAHTAR_ESITLEME = "kredi.esitleme"
ANAHTAR_HATA = "kredi.hata"

_KILIT = threading.Lock()


def acik_mi() -> bool:
    """Testler Google'a gitmesin diye `VERTEX_KREDI=0` kapatır (sunucu .env'i yükler)."""
    return os.getenv("VERTEX_KREDI", "1") != "0"


def _proje() -> str:
    return (os.getenv("VERTEX_PROJE") or "").strip()


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vertex_token_saat (
            saat TEXT NOT NULL,
            model TEXT NOT NULL,
            tur TEXT NOT NULL,
            token INTEGER NOT NULL,
            PRIMARY KEY (saat, model, tur)
        )
        """
    )
    return conn


def _saat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def _zaman_serisi(proje: str, bas: datetime, son: datetime) -> list[dict]:
    """Monitoring'den saatlik token serileri. Ayrı fonksiyon: testler bunu yamalar."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    kimlik, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    oturum = AuthorizedSession(kimlik)
    seriler: list[dict] = []
    sayfa = None
    while True:
        params = {
            "filter": f'metric.type="{METRIK}"',
            "interval.startTime": bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": son.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aggregation.alignmentPeriod": f"{ESITLEME_ARALIK_SN}s",
            "aggregation.perSeriesAligner": "ALIGN_SUM",
        }
        if sayfa:
            params["pageToken"] = sayfa
        yanit = oturum.get(f"https://monitoring.googleapis.com/v3/projects/{proje}/timeSeries",
                           params=params, timeout=ZAMAN_ASIMI_SN)
        if yanit.status_code == 403:
            raise PermissionError("izin yok")
        yanit.raise_for_status()
        veri = yanit.json()
        seriler += veri.get("timeSeries", [])
        sayfa = veri.get("nextPageToken")
        if not sayfa:
            return seriler


def esitle(zorla: bool = False, simdi: datetime | None = None) -> str | None:
    """Son eşitlemeden bu yana (en çok 42 gün) saatlik token toplamlarını yaz.

    Dönen değer hata metnidir (yoksa None). Aynı saat yeniden gelirse ÜZERİNE yazılır:
    son saat eşitleme anında eksiktir, bir sonraki eşitleme onu tamamlar."""
    if not acik_mi() or not _proje():
        return None
    simdi = simdi or datetime.now(timezone.utc)
    with _KILIT:
        onceki = float(settings.get(ANAHTAR_ESITLEME, "0") or 0)
        if not zorla and time.time() - onceki < ESITLEME_ARALIK_SN:
            return settings.get(ANAHTAR_HATA) or None
        en_eski = simdi - timedelta(days=SAKLAMA_GUN - 1)
        bas = en_eski
        conn = _connect()
        try:
            son_saat = conn.execute("SELECT MAX(saat) FROM vertex_token_saat").fetchone()[0]
        finally:
            conn.close()
        if son_saat:
            # Son kayıtlı saatten 2 saat geriden başla: o saatler eşitlemede eksik kalmış olabilir.
            bas = max(en_eski, datetime.strptime(son_saat, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
                      - timedelta(hours=2))
        try:
            seriler = _zaman_serisi(_proje(), bas, simdi)
        except PermissionError:
            hata = "Google ölçümü okunamadı: sunucu hesabının izleme okuma izni yok (monitoring.viewer)."
        except Exception as exc:  # noqa: BLE001 — gösterge; ağ/kimlik hatası sunucuyu düşürmez
            hata = f"Google ölçümü okunamadı: {type(exc).__name__}"
        else:
            hata = ""
            toplam: dict[tuple[str, str, str], int] = {}
            for s in seriler:
                model = (s.get("resource", {}).get("labels", {}).get("model_user_id") or "").strip()
                tur = s.get("metric", {}).get("labels", {}).get("type") or ""
                if not model or tur not in ("input", "output"):
                    continue
                for p in s.get("points", []):
                    bitis = p.get("interval", {}).get("endTime", "")
                    deger = p.get("value", {})
                    adet = int(float(deger.get("int64Value", deger.get("doubleValue", 0)) or 0))
                    if not bitis or not adet:
                        continue
                    # Hizalı nokta, aralığın SONUNU taşır: 10:00 noktası 09:00-10:00 saatidir.
                    saat = _saat(datetime.fromisoformat(bitis.replace("Z", "+00:00")) - timedelta(seconds=1))
                    anahtar = (saat, model, tur)
                    toplam[anahtar] = toplam.get(anahtar, 0) + adet
            conn = _connect()
            try:
                conn.executemany(
                    "INSERT INTO vertex_token_saat (saat, model, tur, token) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(saat, model, tur) DO UPDATE SET token = excluded.token",
                    [(s, m, t, n) for (s, m, t), n in toplam.items()],
                )
                conn.commit()
            finally:
                conn.close()
        # Hata varsa bir dakika sonra yeniden denenir: izin verildiğinde saat beklenmesin.
        settings.set(ANAHTAR_ESITLEME, str(time.time() - (ESITLEME_ARALIK_SN - 60 if hata else 0)))
        settings.set(ANAHTAR_HATA, hata)
        return hata or None


def _fiyat(model: str) -> dict | None:
    return kullanim.FIYAT.get(f"vertex/{model}") or kullanim.FIYAT.get(model)


def _maliyetler(sonra: str | None = None, once: str | None = None) -> dict[str, dict]:
    """Model başına token ve tahmini maliyet; `sonra` < saat <= `once` (ikisi de isteğe bağlı)."""
    kosul, deger = [], []
    if sonra:
        kosul.append("saat > ?")
        deger.append(sonra)
    if once:
        kosul.append("saat <= ?")
        deger.append(once)
    nerede = f"WHERE {' AND '.join(kosul)}" if kosul else ""
    conn = _connect()
    try:
        satirlar = conn.execute(
            f"SELECT model, tur, SUM(token) FROM vertex_token_saat {nerede} GROUP BY model, tur", deger
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, dict] = {}
    for model, tur, adet in satirlar:
        m = out.setdefault(model, {"model": model, "giris_token": 0, "cikis_token": 0,
                                   "maliyet": 0.0, "fiyat_bilinmiyor": _fiyat(model) is None})
        m["giris_token" if tur == "input" else "cikis_token"] += int(adet or 0)
    for m in out.values():
        f = _fiyat(m["model"])
        if f:
            m["maliyet"] = round((m["giris_token"] * f["giris"] + m["cikis_token"] * f["cikis"]) / 1e6, 4)
    return out


def _sayi(anahtar: str) -> float | None:
    try:
        deger = settings.get(anahtar, "")
        return float(deger) if deger != "" else None
    except ValueError:
        return None


def ayarla(tutar: float | None = None, bitis: str | None = None, okuma_tutar: float | None = None,
           okuma_sil: bool = False, simdi: datetime | None = None) -> None:
    """Kullanıcının girdiği kredi bilgisi. `okuma_tutar` konsolda görülen KULLANILAN tutardır;
    zamanı kayıt anıdır (o saatten sonrası tahminle eklenir)."""
    if tutar is not None:
        if tutar <= 0:
            raise ValueError("tutar")
        settings.set(ANAHTAR_TUTAR, str(tutar))
    if bitis is not None:
        if bitis:
            date.fromisoformat(bitis)  # biçim denetimi: ValueError
        settings.set(ANAHTAR_BITIS, bitis)
    if okuma_sil:
        settings.set(ANAHTAR_OKUMA_TUTAR, "")
        settings.set(ANAHTAR_OKUMA_ZAMAN, "")
    elif okuma_tutar is not None:
        if okuma_tutar < 0:
            raise ValueError("okuma")
        settings.set(ANAHTAR_OKUMA_TUTAR, str(okuma_tutar))
        settings.set(ANAHTAR_OKUMA_ZAMAN, (simdi or datetime.now(timezone.utc)).isoformat(timespec="seconds"))


def durum(esitle_once: bool = True, simdi: datetime | None = None) -> dict:
    """Göstergenin tamamı: kullanılan, kalan, oran, kalan gün ve son 7 günün hızı."""
    simdi = simdi or datetime.now(timezone.utc)
    if esitle_once:
        esitle(simdi=simdi)
    tutar = _sayi(ANAHTAR_TUTAR) or VARSAYILAN_TUTAR
    bitis = settings.get(ANAHTAR_BITIS, "") or None
    okuma_tutar = _sayi(ANAHTAR_OKUMA_TUTAR)
    okuma_zaman = settings.get(ANAHTAR_OKUMA_ZAMAN, "") or None
    okuma_saat = None
    if okuma_tutar is not None and okuma_zaman:
        okuma_saat = _saat(datetime.fromisoformat(okuma_zaman))

    modeller = _maliyetler(sonra=okuma_saat)
    tahmin = round(sum(m["maliyet"] for m in modeller.values()), 2)
    kullanilan = round((okuma_tutar or 0) + tahmin, 2)
    hafta = _maliyetler(sonra=_saat(simdi - timedelta(days=7)))
    son_7_gun = round(sum(m["maliyet"] for m in hafta.values()), 2)

    kalan_gun = None
    if bitis:
        kalan_gun = max(0, (date.fromisoformat(bitis) - simdi.date()).days)
    conn = _connect()
    try:
        ilk = conn.execute("SELECT MIN(saat) FROM vertex_token_saat").fetchone()[0]
    finally:
        conn.close()
    esitleme = _sayi(ANAHTAR_ESITLEME)
    return {
        "kaynak": "google" if (acik_mi() and _proje()) else "kapali",
        "hata": settings.get(ANAHTAR_HATA, "") or None,
        "guncellendi": (datetime.fromtimestamp(esitleme, timezone.utc).isoformat(timespec="seconds")
                        if esitleme else None),
        "ilk_olcum": f"{ilk}:00Z" if ilk else None,
        "tutar": tutar,
        "bitis": bitis,
        "deneme_gun": DENEME_GUN,
        "kalan_gun": kalan_gun,
        "okuma": ({"tutar": okuma_tutar, "zaman": okuma_zaman} if okuma_saat else None),
        "tahmin": tahmin,
        "kullanilan": kullanilan,
        "kalan": round(max(0.0, tutar - kullanilan), 2),
        "oran": round(min(1.0, kullanilan / tutar), 4),
        "son_7_gun": son_7_gun,
        "modeller": sorted(modeller.values(), key=lambda m: -m["maliyet"]),
    }


def arka_planda_esitle() -> None:
    """Açılışta bir kez: Monitoring 6 haftadan eskiyi siler, ekran açılmasa da veri birikir."""
    if not acik_mi() or not _proje():
        return
    threading.Thread(target=lambda: esitle(zorla=True), name="vertex-kredi", daemon=True).start()
