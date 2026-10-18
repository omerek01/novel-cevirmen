"""Çeviri aşamalarını okuyucudan aç/kapa (2026-10-18, kullanıcı isteği).

Beş ek aşama eskiden YALNIZ ortam değişkeniyle (`.env`) yönetiliyordu; değiştirmek
sunucuya girip servisi yeniden başlatmak demekti. Artık seçim sunucuda (`settings`)
durur, okuyucunun ayarlar panelinden değişir ve yeniden başlatma istemez. Seçim
model seçimiyle aynı kuralla yalnız YENİ çevrilen bölümde geçerlidir.

Öncelik: kayıtlı ayar > ortam değişkeni > varsayılan. Düğmeye hiç dokunulmadıysa
davranış bugünküyle aynıdır. Testler aşamaları `monkeypatch.setenv` ile açıp
kapatıyor; ayar yazılmadıkça o yol da aynen çalışır.

Bayrağı doğrudan `os.getenv` ile okuyan yeni bir yer düğmeyi SESSİZCE etkisiz
bırakır (düğme "kapalı" der, aşama yine çalışır); `tests/test_ceviri_asamalari.py`
statik tel tuzağıyla tutar.
"""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict

from . import db, settings

AYAR_ONEKI = "ceviri_asama."

# `olcum`: aşamanın `api_olay.asama` adları (bkz. `api_durum.baglam(asama=...)`).
ASAMALAR = (
    {"ad": "analiz", "ortam": "CEVIRI_ANALIZ", "varsayilan": True,
     "etiket": "Bölüm analizi",
     "aciklama": "Çeviriden önce bölümü okuyup sahne, kişi ve terim bağlamı çıkarır.",
     "olcum": ("bolum_analizi", "onceki_bolum_ozeti")},
    {"ad": "ozet", "ortam": "CEVIRI_OZET", "varsayilan": False,
     "etiket": "Bölüm özeti",
     "aciklama": "Çeviriden önce bölümün kısa özetini çıkarıp çeviriye bağlam olarak verir.",
     "olcum": ("ozet_zinciri",)},
    {"ad": "cilalama", "ortam": "CEVIRI_CILALA", "varsayilan": False,
     "etiket": "Türkçe cilalama",
     "aciklama": "Çeviriyi ayrı bir turda okuyup çeviri kokan cümleleri düzeltir.",
     "olcum": ("cilalama",)},
    {"ad": "kalite", "ortam": "CEVIRI_KALITE", "varsayilan": True,
     "etiket": "Kalite denetimi",
     "aciklama": "Çeviriyi kaynakla karşılaştırır; anlam hatası bulursa paragrafı onarıp doğrular.",
     "olcum": ("kalite_denetimi", "kalite_onarimi", "kalite_dogrulama")},
    {"ad": "terim_alani", "ortam": "CEVIRI_TERIM_ALANI_ONARIM", "varsayilan": True,
     "etiket": "Terim listesi tekrarı",
     "aciklama": "Model yeni ad/terim listesini hiç yazmazsa parçayı bir kez daha ister. "
                 "Kapalıyken o bölümdeki yeni adlar sözlüğe önerilmeyebilir.",
     "olcum": ("terim_alani_onarimi",)},
)
_ADLAR = {a["ad"]: a for a in ASAMALAR}

# Ölçüme yalnız BÖLÜM çevirisi girer. Varlık grafiği ve sözlük doğrulaması da aşaması
# boş kayıt yazıyor; onları "çeviri" saymak süreyi yarıya indiriyordu (ölçülen hata).
CEVIRI_AMACLARI = ("prefetch", "okuma", "yeniden_ceviri")
OLCUM_BOLUM = 40


def _ortam(asama: dict) -> bool:
    deger = os.getenv(asama["ortam"])
    if deger is None:
        return asama["varsayilan"]
    # Eski okuma kuralları aynen: varsayılanı açık olan yalnız "0" ile kapanır,
    # varsayılanı kapalı olan yalnız "1" ile açılır.
    return deger != "0" if asama["varsayilan"] else deger == "1"


def _kayit(ad: str) -> str:
    try:
        return settings.get(AYAR_ONEKI + ad)
    except sqlite3.Error:
        # Ayar okunamazsa (kilitli veritabanı) çeviri durmamalı: ortam değişkenine düş.
        return ""


def acik(ad: str) -> bool:
    """Aşama şu an açık mı (kayıtlı ayar > ortam değişkeni > varsayılan)."""
    kayit = _kayit(ad)
    if kayit in ("0", "1"):
        return kayit == "1"
    return _ortam(_ADLAR[ad])


def ayarla(ad: str, acik_mi: bool) -> None:
    if ad not in _ADLAR:
        raise KeyError(ad)
    settings.set(AYAR_ONEKI + ad, "1" if acik_mi else "0")


def durum() -> list[dict]:
    """Okuyucu paneli için: her aşamanın etiketi, açıklaması, durumu ve kaynağı."""
    sonuc = []
    for a in ASAMALAR:
        kayitli = _kayit(a["ad"]) in ("0", "1")
        sonuc.append({"ad": a["ad"], "etiket": a["etiket"], "aciklama": a["aciklama"],
                      "acik": acik(a["ad"]), "kaynak": "ayar" if kayitli else "ortam"})
    return sonuc


def olcum(son: int = OLCUM_BOLUM) -> dict:
    """Son `son` bölüm çevirisinde aşamaların GERÇEK süresi (`api_olay` kaydından; API'siz).

    Süre model çağrılarının toplamıdır (başarısız denemeler dahil); sayfa çekimi
    girmez. `ort_sn` bölüm BAŞINA ortalamadır: aşamanın çalışmadığı bölüm sıfır sayılır,
    yani bir aşamayı kapatınca bölüm başına kazanılacak süreyi doğrudan söyler.
    """
    yer = ",".join("?" * len(CEVIRI_AMACLARI))
    conn = db.connect()
    try:
        satirlar = conn.execute(
            "SELECT islem, url, COALESCE(asama, 'ceviri'), sure_ms FROM api_olay"
            f" WHERE tur = 'istek' AND sure_ms IS NOT NULL AND amac IN ({yer})"
            " AND islem IS NOT NULL ORDER BY zaman DESC LIMIT 5000",
            CEVIRI_AMACLARI,
        ).fetchall()
    except sqlite3.OperationalError:
        satirlar = []  # api_olay henüz kurulmadı: hiç çağrı yapılmamış
    finally:
        conn.close()
    islemler: dict[tuple, dict[str, int]] = {}
    for islem, url, asama, ms in satirlar:
        islemler.setdefault((islem, url), defaultdict(int))[asama] += ms
    bolumler = [a for a in islemler.values() if "ceviri" in a][:son]
    n = len(bolumler)

    def ort(toplam_ms: float) -> float:
        return round(toplam_ms / n / 1000, 1) if n else 0.0

    asamalar = {}
    for a in ASAMALAR:
        sureler = [sum(b.get(s, 0) for s in a["olcum"]) for b in bolumler]
        asamalar[a["ad"]] = {
            "bolum_orani": round(sum(1 for x in sureler if x) / n, 2) if n else 0.0,
            "ort_sn": ort(sum(sureler)),
        }
    return {"bolum": n,
            "toplam_ort_sn": ort(sum(sum(b.values()) for b in bolumler)),
            "ceviri_ort_sn": ort(sum(b["ceviri"] for b in bolumler)),
            "asamalar": asamalar}
