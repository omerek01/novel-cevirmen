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

Paragraf önerisi (2026-10-19, kullanıcı isteği): okuyucunun tek paragraf önerisi
hafif kipte koşar ve ek turları atlar (`translate._translate_chapter_impl`, `hafif`).
`paragraf: True` taşıyan aşamalar orada AYRI bir anahtarla açılabilir. Anahtar bölüm
seçiminden bağımsızdır, varsayılanı kapalıdır ve ortam değişkeni okumaz: öneri bilinçli
olarak kısıtlandı, açmak her aşama için ayrı bir seçimdir.
"""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict

from . import db, settings

AYAR_ONEKI = "ceviri_asama."
PARAGRAF_ONEKI = "paragraf."

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
     "olcum": ("cilalama",), "paragraf": True},
    {"ad": "kalite", "ortam": "CEVIRI_KALITE", "varsayilan": True,
     "etiket": "Kalite denetimi",
     "aciklama": "Çeviriyi kaynakla karşılaştırır; anlam hatası bulursa paragrafı onarıp doğrular.",
     "olcum": ("kalite_denetimi", "kalite_onarimi", "kalite_dogrulama"), "paragraf": True},
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


def paragrafta_acik(ad: str) -> bool:
    """Aşama okuyucunun paragraf önerisinde de çalışsın mı (varsayılan kapalı)."""
    if not _ADLAR.get(ad, {}).get("paragraf"):
        return False
    return _kayit(PARAGRAF_ONEKI + ad) == "1"


def ayarla_paragraf(ad: str, acik_mi: bool) -> None:
    if not _ADLAR.get(ad, {}).get("paragraf"):
        raise KeyError(ad)
    settings.set(AYAR_ONEKI + PARAGRAF_ONEKI + ad, "1" if acik_mi else "0")


def calisir(ad: str, paragraf: bool = False) -> bool:
    """Çeviri hattının sorduğu tek soru: bu kipte (bölüm ya da paragraf) aşama koşsun mu."""
    return paragrafta_acik(ad) if paragraf else acik(ad)


def durum() -> list[dict]:
    """Okuyucu paneli için: her aşamanın etiketi, açıklaması, durumu ve kaynağı.

    `paragraf`: paragraf önerisinde çalışıyor mu; o kipte açılamayan aşamada None."""
    sonuc = []
    for a in ASAMALAR:
        kayitli = _kayit(a["ad"]) in ("0", "1")
        sonuc.append({"ad": a["ad"], "etiket": a["etiket"], "aciklama": a["aciklama"],
                      "acik": acik(a["ad"]), "kaynak": "ayar" if kayitli else "ortam",
                      "paragraf": paragrafta_acik(a["ad"]) if a.get("paragraf") else None})
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


# ---------------------------------------------------------------------------
# Bölüm künyesi: bu bölümün çevirisi nereye ne kadar süre harcadı (2026-11-01,
# kullanıcı isteği). Model çağrılarının süresi zaten `api_olay`'da işlem + URL
# kimliğiyle duruyor; çeviri bitince o işlemin kayıtları toplanıp bölüme yazılır.
# `api_olay` budandığı için sonradan hesaplanamaz, kayıt anında saklanır.
# ---------------------------------------------------------------------------

# Düzeltme turları aşama düğmesine bağlı değil; çeviri hatası görülünce kendiliğinden koşar.
DUZELTME_ETIKETLERI = {
    "hizalama_onarimi": "Düzeltme: paragraf eşleştirme",
    "kalinti_onarimi": "Düzeltme: İngilizce kalan paragraflar",
    "alfabe_onarimi": "Düzeltme: yabancı alfabe",
    "sozluk_onarimi": "Düzeltme: sözlüğe uymayan terimler",
    "karsilik_onarimi": "Düzeltme: terim karşılıkları",
    "sayi_onarimi": "Düzeltme: sayılar",
    "kisalma_onarimi": "Düzeltme: kısa kalan çeviri",
    "ret_onarimi": "Düzeltme: modelin reddettiği parça",
    "anlam_onarimi": "Düzeltme: anlam hataları",
}


def _basarisizlik_nedeni(sonuc: str | None, kod: int | None) -> str:
    if kod == 504:
        return "zaman aşımı"
    if kod == 429 or sonuc == "kota_gunluk":
        return "kota doldu"
    if kod in (500, 502, 503):
        return "Google meşgul"
    if sonuc == "ret":
        return "model yanıt vermeyi reddetti"
    if sonuc == "erisim":
        return "erişim izni yok"
    return "hata"


def _model_etiketi(model: str) -> str:
    """Okuyucunun model seçicisindeki kısa ad + ücret bilgisi ("4 Argon · ücretli")."""
    from . import translate  # döngüsel içe aktarmayı önler

    for s in translate.SECILEBILIR_MODELLER:
        if s["ad"] == model:
            return f"{s['kisa']} · {'ücretli' if s.get('ucretli') else 'ücretsiz'}"
    kisa = model.split("/")[-1].removeprefix("gemini-").replace("-", " ").title()
    return f"{kisa} · {'ücretli' if '/' in model else 'ücretsiz'}"


def sure_dokumu(islem: str | None, url: str, baslangic: float, bitis: float,
                indirme_sn: float = 0.0, bekleme_sn: float = 0.0) -> dict:
    """Bölüm çevirisinin süre dökümü: toplam, aşamalar, modeller, kapalı aşamalar.

    Yalnız bu işlemin bu URL için yaptığı model istekleri sayılır. Çağrılar sıralı
    olduğu için model süreleri toplamı duvar saatini aşmaz; aradaki fark (sözlük
    işleri, yerel denetimler) "Öteki işler" satırına gider.
    """
    satirlar = []
    if islem:
        conn = db.connect()
        try:
            satirlar = conn.execute(
                "SELECT COALESCE(asama, 'ceviri'), model, sonuc, http_kodu, sure_ms"
                " FROM api_olay WHERE tur = 'istek' AND islem = ? AND url = ?"
                " AND zaman >= ? AND sure_ms IS NOT NULL ORDER BY id",
                (islem, url, baslangic - 1),
            ).fetchall()
        except sqlite3.OperationalError:
            satirlar = []  # api_olay henüz kurulmadı
        finally:
            conn.close()

    olcum_asama = {o: a for a in ASAMALAR for o in a["olcum"]}
    asama_ms: dict[str, int] = {}
    model_bilgi: dict[str, dict] = {}
    for asama, model, sonuc, kod, ms in satirlar:
        if asama == "ceviri":
            anahtar, etiket = "ceviri", "Çeviri"
        elif asama in olcum_asama:
            anahtar, etiket = olcum_asama[asama]["ad"], olcum_asama[asama]["etiket"]
        else:
            anahtar = asama
            etiket = DUZELTME_ETIKETLERI.get(asama, "Düzeltme: öteki")
        asama_ms.setdefault((anahtar, etiket), 0)
        asama_ms[(anahtar, etiket)] += ms
        m = model_bilgi.setdefault(model or "?", {"ms": 0, "istek": 0, "basarisiz": 0,
                                                  "basarisiz_ms": 0, "nedenler": {}})
        m["ms"] += ms
        m["istek"] += 1
        if sonuc != "basari":
            m["basarisiz"] += 1
            m["basarisiz_ms"] += ms
            neden = _basarisizlik_nedeni(sonuc, kod)
            m["nedenler"][neden] = m["nedenler"].get(neden, 0) + 1

    toplam_sn = max(0.0, bitis - baslangic)
    model_sn = sum(asama_ms.values()) / 1000
    asamalar = [{"ad": ad, "etiket": et, "sn": round(ms / 1000, 1)}
                for (ad, et), ms in asama_ms.items()]
    oteki = toplam_sn - model_sn - indirme_sn - bekleme_sn
    return {
        "toplam_sn": round(toplam_sn, 1),
        "indirme_sn": round(indirme_sn, 1),
        "bekleme_sn": round(bekleme_sn, 1),
        "oteki_sn": round(max(0.0, oteki), 1),
        "asamalar": asamalar,
        "modeller": [
            {"model": ad, "etiket": _model_etiketi(ad), "sn": round(b["ms"] / 1000, 1),
             "istek": b["istek"], "basarisiz": b["basarisiz"],
             "basarisiz_sn": round(b["basarisiz_ms"] / 1000, 1), "nedenler": b["nedenler"]}
            for ad, b in sorted(model_bilgi.items(), key=lambda x: -x[1]["ms"])
        ],
        # Okur "cilalama ne kadar sürdü" diye bakıp satırı bulamazsa nedenini görsün.
        "kapali": [a["etiket"] for a in ASAMALAR if not acik(a["ad"])],
    }
