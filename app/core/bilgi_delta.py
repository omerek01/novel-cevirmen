"""Bilgi DELTASI çıkarımı — geçmiş doldurma (1..946) ve canlı okuma (947+) için TEK çekirdek.

Faz 2A (2026-10-07, kullanıcı onaylı plan). Soru "bu bölümde ne oldu?" DEĞİL:
"N-1'e kadar bilinebilenlere göre N. bölüm hangi bilgiyi EKLİYOR, DEĞİŞTİRİYOR,
AÇIĞA ÇIKARIYOR, ÇÜRÜTÜYOR?"

    DURUM(N-1) + KAYNAK(N) -> çıkarıcı -> DELTA(N) -> doğrulayıcı -> İŞLEME -> DURUM(N)

Faz 1 doğruluk kaynağıdır; ikinci bir grafik YOK. Yazma yalnız `varlik_grafigi.bag_ekle`
ve `deger_yaz` üzerinden, kanıt doğrulaması `varlik_cikarim._kanitli_coz` ile (aynı
kurallar), sözlüğe hiçbir şey yazılmaz (kapı aynen kalır; yeni ad yalnız raporlanır).

GELECEK BİLGİ GÜVENCESİ: bölüm N'nin bağlamındaki HER grafik/sözlük verisi
`en_cok_bolum = N-1` süzgecinden geçer (`baglam_kur`). Bölümün KENDİ metninde geçen
adlar istisnadır (okur onları zaten N'de görüyor). Bağın `ilk_bolum`u daima N'dir
(learned_at); `gecerli_baslangic` yalnız metin açıkça söylüyorsa yazılır.

Sürümler (zorunlu): her işlenen bölüm `CIKARICI_SURUMU`, `ISTEM_SURUMU`,
`SEMA_SURUMU` ve modeli `bilgi_isleme` tablosunda taşır; her öneri `bilgi_oneri`de
(bölüm, kimlik üçlüsü, çıkarım kimliği) ile — yeniden işleme kopya üretmez, elle
kararlara dokunmaz, v1 ve v2 adaylarını ayırt eder.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time

from . import cache, db, glossary, translate, varlik_cikarim, varlik_grafigi

CIKARICI_SURUMU = "1"
ISTEM_SURUMU = "1"
SEMA_SURUMU = "delta-1"

DURUMLAR = ("pending", "processing", "completed", "failed", "needs_review")
SINIFLAR = ("NEW", "ALREADY_EXISTS", "SUPPORTS_EXISTING", "CONFLICTS_WITH_EXISTING",
            "UPDATES_EXISTING", "NEEDS_REVIEW")
INCELEME_KATEGORILERI = ("identity_merge", "alias", "relationship_conflict", "temporal_conflict",
                         "epistemic_conflict", "duplicate_candidate", "retroactive_revelation",
                         "new_entity", "schema")
ONEMLER = ("critical", "high", "medium", "low")
KIMLIK_ILISKILERI = ("takma_adi", "gercek_adi", "unvani")

# Bağlam bütçesi (yaklaşık token = karakter / 4). Kaynak metin bütçeye dahil DEĞİL;
# büyüyen şey grafiktir ve bölüm sayısıyla SINIRSIZ büyümemeli.
BAGLAM_BUTCESI = 4000  # kullanıcı kararı (2026-10-07): 2500'de geç bölümlerde 120-320 satır kesiliyordu
SON_BOLUM_PENCERESI = 30  # "son ilgili geçmiş" önceliği için

# ---------------------------------------------------------------------------
# DELTA ŞEMASI — Faz 1 tablolarına birebir eşlenir (Olay/Gizem/Olgu tablosu YOK).
# ---------------------------------------------------------------------------
DELTA_SEMASI = {
    "new_relationships": {   # -> varlik_bag (bag_ekle), ilk_bolum = N
        "zorunlu": ("ozne", "iliski", "nesne", "kanit"),
        "secimli": ("durum_bilgisi", "gecerli_baslangic", "gecerli_bitis", "guven"),
    },
    "new_aliases": {         # -> varlik_bag takma_adi / gercek_adi / unvani, ilk_bolum = N
        "zorunlu": ("asil", "ad", "tur", "kanit"),
        "secimli": ("durum_bilgisi", "guven"),
    },
    "relationship_updates": {  # mevcut bağın bitişi / çürütülmesi (SİLMEZ)
        "zorunlu": ("ozne", "iliski", "nesne", "degisim", "kanit"),
        "secimli": ("gecerli_bitis", "durum_bilgisi"),
    },
    "state_changes": {       # -> varlik_deger (deger_yaz), ilk_bolum = N
        "zorunlu": ("varlik", "anahtar", "deger", "kanit"),
        "secimli": ("durum_bilgisi",),
    },
    "identity_revelations": {  # "A aslında B" — YALNIZ inceleme + aday bağ, birleştirme YOK
        "zorunlu": ("ad_1", "ad_2", "kanit"),
        "secimli": ("aciklama",),
    },
    "contradictions": {      # önceki bilginin çelişmesi -> inceleme
        "zorunlu": ("aciklama", "kanit"),
        "secimli": ("ozne", "iliski", "nesne"),
    },
    "new_entities": {        # sözlükte OLMAYAN ad -> yalnız inceleme (sözlük kapısı korunur)
        "zorunlu": ("ad", "kanit"),
        "secimli": ("tur",),
    },
    "review_items": {
        "zorunlu": ("kategori", "aciklama"),
        "secimli": ("onem", "kanit"),
    },
}
DEGISIMLER = ("ended", "disproven")


def sema_dogrula(veri: object) -> list[str]:
    """Delta şema hataları (boş = geçerli). Bilinmeyen alan, eksik zorunlu alan, yanlış
    enum ve sayı olmayan bölüm alanları hata sayılır — sessizce düzeltilmez."""
    if not isinstance(veri, dict):
        return ["delta bir JSON nesnesi değil"]
    hatalar = []
    for ad in veri:
        if ad not in DELTA_SEMASI:
            hatalar.append(f"bilinmeyen bölüm: {ad}")
    for ad, kural in DELTA_SEMASI.items():
        liste = veri.get(ad, [])
        if not isinstance(liste, list):
            hatalar.append(f"{ad} liste değil")
            continue
        izinli = set(kural["zorunlu"]) | set(kural["secimli"])
        for i, x in enumerate(liste):
            if not isinstance(x, dict):
                hatalar.append(f"{ad}[{i}] nesne değil")
                continue
            for z in kural["zorunlu"]:
                if not str(x.get(z) or "").strip():
                    hatalar.append(f"{ad}[{i}].{z} eksik")
            for alan in x:
                if alan not in izinli:
                    hatalar.append(f"{ad}[{i}].{alan} bilinmeyen alan")
            if x.get("iliski") is not None and ad in ("new_relationships", "relationship_updates") \
                    and x["iliski"] not in varlik_grafigi.ILISKILER:
                hatalar.append(f"{ad}[{i}].iliski bilinmiyor: {x['iliski']}")
            if ad == "new_aliases" and x.get("tur") not in KIMLIK_ILISKILERI:
                hatalar.append(f"{ad}[{i}].tur {KIMLIK_ILISKILERI} dışında")
            if ad == "relationship_updates" and x.get("degisim") not in DEGISIMLER:
                hatalar.append(f"{ad}[{i}].degisim {DEGISIMLER} dışında")
            if x.get("durum_bilgisi") is not None and x["durum_bilgisi"] not in varlik_grafigi.DURUM_BILGISI:
                hatalar.append(f"{ad}[{i}].durum_bilgisi bilinmiyor")
            for b in ("gecerli_baslangic", "gecerli_bitis"):
                if x.get(b) is not None and not isinstance(x[b], int):
                    hatalar.append(f"{ad}[{i}].{b} tam sayı değil")
            if ad == "review_items":
                if x.get("kategori") not in INCELEME_KATEGORILERI:
                    hatalar.append(f"{ad}[{i}].kategori bilinmiyor")
                if x.get("onem") is not None and x["onem"] not in ONEMLER:
                    hatalar.append(f"{ad}[{i}].onem bilinmiyor")
    return hatalar


# ---------------------------------------------------------------------------
# DEPOLAMA (eklemeli; Faz 1 tablolarına dokunmaz)
# ---------------------------------------------------------------------------
def _connect() -> sqlite3.Connection:
    varlik_grafigi._connect().close()  # Faz 1 şeması önce kurulur
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bilgi_isleme (
            book_slug TEXT NOT NULL, bolum INTEGER NOT NULL, durum TEXT NOT NULL,
            cikarici_model TEXT, cikarici_surumu TEXT, istem_surumu TEXT, sema_surumu TEXT,
            basladi REAL, bitti REAL, deneme INTEGER NOT NULL DEFAULT 0, hata TEXT, metrik TEXT,
            PRIMARY KEY (book_slug, bolum)
        )
        """
    )
    # Her öneri ve SINIFI/KARARI (yeniden işleme kopya üretmez: PK çıkarım kimliğini içerir).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bilgi_oneri (
            book_slug TEXT NOT NULL, bolum INTEGER NOT NULL, cikarim TEXT NOT NULL,
            tur TEXT NOT NULL, anahtar TEXT NOT NULL, sinif TEXT NOT NULL, karar TEXT NOT NULL,
            veri TEXT, zaman REAL NOT NULL,
            PRIMARY KEY (book_slug, bolum, cikarim, tur, anahtar)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bilgi_inceleme (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_slug TEXT NOT NULL, bolum INTEGER, kategori TEXT NOT NULL, onem TEXT NOT NULL,
            aciklama TEXT NOT NULL, veri TEXT, durum TEXT NOT NULL DEFAULT 'acik',
            anahtar TEXT NOT NULL, zaman REAL NOT NULL,
            UNIQUE (book_slug, anahtar)
        )
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bilgi_bas (book_slug TEXT PRIMARY KEY, bas_bolum INTEGER NOT NULL)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bilgi_kontrol (
            book_slug TEXT NOT NULL, bolum INTEGER NOT NULL, zaman REAL NOT NULL, metrik TEXT NOT NULL,
            PRIMARY KEY (book_slug, bolum)
        )
        """
    )
    return conn


def cikarim_kimligi(model: str) -> str:
    return f"{model}|c{CIKARICI_SURUMU}|i{ISTEM_SURUMU}|{SEMA_SURUMU}"


def bas_bolum(book_slug: str) -> int:
    """Grafiğin kronolojik başı: bu bölüme KADAR (dahil) delta işlendi."""
    conn = _connect()
    try:
        r = conn.execute("SELECT bas_bolum FROM bilgi_bas WHERE book_slug = ?", (book_slug,)).fetchone()
        return r[0] if r else 0
    finally:
        conn.close()


def isleme_durumu(book_slug: str, bolum: int) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT durum, cikarici_model, cikarici_surumu, istem_surumu, sema_surumu, deneme, hata, metrik "
            "FROM bilgi_isleme WHERE book_slug = ? AND bolum = ?", (book_slug, bolum),
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {"durum": r[0], "model": r[1], "cikarici_surumu": r[2], "istem_surumu": r[3],
            "sema_surumu": r[4], "deneme": r[5], "hata": r[6], "metrik": json.loads(r[7] or "{}")}


def _durum_yaz(conn, book_slug, bolum, durum, model=None, hata=None, metrik=None, deneme_artir=False):
    conn.execute(
        "INSERT INTO bilgi_isleme (book_slug, bolum, durum, deneme) VALUES (?, ?, ?, 0) "
        "ON CONFLICT(book_slug, bolum) DO NOTHING", (book_slug, bolum, durum),
    )
    simdi = time.time()
    conn.execute(
        "UPDATE bilgi_isleme SET durum = ?, cikarici_model = COALESCE(?, cikarici_model), "
        "cikarici_surumu = ?, istem_surumu = ?, sema_surumu = ?, hata = ?, "
        "metrik = COALESCE(?, metrik), deneme = deneme + ?, "
        "basladi = CASE WHEN ? = 'processing' THEN ? ELSE basladi END, "
        "bitti = CASE WHEN ? IN ('completed', 'needs_review', 'failed') THEN ? ELSE bitti END "
        "WHERE book_slug = ? AND bolum = ?",
        (durum, model, CIKARICI_SURUMU, ISTEM_SURUMU, SEMA_SURUMU, hata,
         json.dumps(metrik, ensure_ascii=False) if metrik is not None else None,
         1 if deneme_artir else 0, durum, simdi, durum, simdi, book_slug, bolum),
    )


def inceleme_ekle(conn, book_slug: str, bolum: int | None, kategori: str, onem: str,
                  aciklama: str, veri: dict | None = None) -> bool:
    """Kalıcı inceleme kuyruğu. Aynı konu (anahtar) bir kez açılır (yeniden işleme kopyalamaz)."""
    if kategori not in INCELEME_KATEGORILERI:
        raise ValueError(f"Bilinmeyen inceleme kategorisi: {kategori!r}")
    if onem not in ONEMLER:
        raise ValueError(f"Bilinmeyen önem: {onem!r}")
    anahtar = f"{kategori}|{json.dumps(veri or {}, sort_keys=True, ensure_ascii=False)[:400]}"
    n = conn.execute(
        "INSERT OR IGNORE INTO bilgi_inceleme (book_slug, bolum, kategori, onem, aciklama, veri, anahtar, zaman) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (book_slug, bolum, kategori, onem, aciklama[:500], json.dumps(veri or {}, ensure_ascii=False),
         anahtar, time.time()),
    ).rowcount
    return n > 0


def inceleme_listesi(book_slug: str, durum: str = "acik") -> list[dict]:
    conn = _connect()
    try:
        return [
            {"id": r[0], "bolum": r[1], "kategori": r[2], "onem": r[3], "aciklama": r[4],
             "veri": json.loads(r[5] or "{}")}
            for r in conn.execute(
                "SELECT id, bolum, kategori, onem, aciklama, veri FROM bilgi_inceleme "
                "WHERE book_slug = ? AND durum = ? ORDER BY CASE onem WHEN 'critical' THEN 0 "
                "WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, bolum", (book_slug, durum),
            )
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BAĞLAM (deterministik geri getirme, bütçeli, N-1 süzgeçli)
# ---------------------------------------------------------------------------
def _tok(metin: str) -> int:
    return (len(metin) + 3) // 4


def baglam_kur(book_slug: str, bolum: int, kaynak: str, butce: int = BAGLAM_BUTCESI) -> dict:
    """Bölüm N için MEVCUT BİLGİ. Her grafik/sözlük verisi `en_cok_bolum=N-1` ile okunur.

    Öncelik (bütçe dolunca alttakiler kesilir): 1 bölümde geçen varlıklar (sözlük
    eşleşmesi) · 2 bilinen kimlik bağları (takma/Gerçek Ad/unvan) · 3 güncel durum
    değerleri · 4 doğrudan bağlar (en yeni öğrenilen önce) · 5 son SON_BOLUM_PENCERESI
    bölümde öğrenilenler · 6 açık kimlik inceleme adayları. 3 sıçramalı komşuluk YOK."""
    onceki = bolum - 1
    sozluk = glossary.ceviri_sozlugu(book_slug)
    gecen_adlar = translate.metinde_gecen_terimler(sozluk, kaynak)
    gorunur = {r["source"]: r for r in glossary.gorunur_sozluk(book_slug, onceki)["rows"]}
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    gecen = {}
    for ad in gecen_adlar:
        k = cozucu.coz(ad)
        if k:
            gecen[k] = ad
    baglar = varlik_grafigi.baglar(book_slug, en_cok_bolum=onceki)
    degerler = varlik_grafigi.degerler(book_slug, onceki)
    kimlik_k = set(gecen) | {varlik_grafigi.taban_kimlik(k) for k in gecen}

    def _ilgili(b):
        return varlik_grafigi.taban_kimlik(b["kaynak_kimlik"]) in kimlik_k or \
            varlik_grafigi.taban_kimlik(b["hedef_kimlik"]) in kimlik_k

    satirlar: list[tuple[int, str]] = []
    for k, ad in sorted(gecen.items(), key=lambda x: x[1]):
        r = gorunur.get(ad) or {}
        ek = f" — {r['tanim']}" if r.get("tanim") else ""
        satirlar.append((1, f"VARLIK {ad} -> {r.get('target', sozluk.get(ad, ad))}{ek}"))
    ilgili = [b for b in baglar if _ilgili(b)]
    for b in ilgili:
        if b["iliski"] in KIMLIK_ILISKILERI:
            satirlar.append((2, _bag_satiri(b)))
    for k in gecen:
        for anahtar, d in (degerler.get(k) or {}).items():
            satirlar.append((3, f"DURUM {gecen[k]}.{anahtar} = {d['deger']} (b{d['ilk_bolum']}, {d['durum_bilgisi']})"))
    dogrudan = sorted((b for b in ilgili if b["iliski"] not in KIMLIK_ILISKILERI),
                      key=lambda b: -(b["ilk_bolum"] or 0))
    for b in dogrudan:
        oncelik = 4 if (b["ilk_bolum"] or 0) >= onceki - SON_BOLUM_PENCERESI else 5
        satirlar.append((oncelik, _bag_satiri(b)))
    for i in inceleme_listesi(book_slug):
        if i["kategori"] == "identity_merge" and (i["bolum"] or 0) <= onceki:
            satirlar.append((6, f"AÇIK KİMLİK SORUSU (b{i['bolum']}): {i['aciklama']}"))
    satirlar.sort(key=lambda x: x[0])
    secilen, kullanilan, kesilen = [], 0, 0
    sinif_adi = {1: "varlik", 2: "kimlik", 3: "durum", 4: "dogrudan_yeni", 5: "dogrudan_eski", 6: "kimlik_sorusu"}
    sinif = {ad: {"aday": 0, "giren": 0, "kesilen": 0} for ad in sinif_adi.values()}
    for oncelik, s in satirlar:
        t = _tok(s) + 1
        sinif[sinif_adi[oncelik]]["aday"] += 1
        if kullanilan + t > butce:
            kesilen += 1
            sinif[sinif_adi[oncelik]]["kesilen"] += 1
            continue
        secilen.append(s)
        sinif[sinif_adi[oncelik]]["giren"] += 1
        kullanilan += t
    return {"bolum": bolum, "bilgi_siniri": onceki, "satirlar": secilen, "gecen": gecen,
            "baglam_tokeni": kullanilan, "kesilen_satir": kesilen, "aday_satir": len(satirlar),
            "sinif": sinif, "kaynak_tokeni": _tok(kaynak)}


def _bag_satiri(b: dict) -> str:
    def ad(isim, anlam):
        return f"{isim} ({anlam})" if anlam else isim
    zaman = []
    if b.get("gecerli_baslangic") is not None:
        zaman.append(f"başlangıç b{b['gecerli_baslangic']}")
    if not b.get("aktif", True):
        zaman.append(f"BİTTİ (öğrenildi b{b['bitis_ogrenildigi']})")
    durum = b.get("durum_bilgisi") or ("aday" if b["durum"] == "aday" else "değerlendirilmemiş")
    ek = f" [{', '.join(zaman)}]" if zaman else ""
    return (f"BAĞ {ad(b['kaynak'], b.get('kaynak_anlam'))} --{b['iliski']}--> "
            f"{ad(b['hedef'], b.get('hedef_anlam'))} (öğrenildi b{b['ilk_bolum']}, {durum}, {b['origin']}){ek}")


# ---------------------------------------------------------------------------
# İSTEM
# ---------------------------------------------------------------------------
CIKARICI_TALIMATI = (
    "Sen bir romanın kronolojik BİLGİ GRAFİĞİNİ güncelleyen bir analistsin. Roman ilk kez "
    "okunuyormuş gibi çalışırsın: sana yalnız ÖNCEKİ bölümlere kadar bilinen bilgi "
    "(MEVCUT BİLGİ) ve BU bölümün İngilizce metni verilir. Sorun 'bu bölümde ne oldu' "
    "DEĞİL; 'bu bölüm, MEVCUT BİLGİYE göre hangi YENİ bilgiyi ekliyor, değiştiriyor, açığa "
    "çıkarıyor, çürütüyor?' Bilinen bir şeyi tekrar yazma. Çoğu bölümün deltası küçüktür.\n"
    "KURALLAR:\n"
    "- Yalnız metnin AÇIKÇA söylediğini yaz. Her öğenin 'kanit'ı bu bölümden KELİMESİ "
    "KELİMESİNE kopyalanmış TEK bir cümledir ve ilgili adlar o cümlede geçer.\n"
    "- Karakterin inancı/söylentisi gerçek değildir: 'durum_bilgisi' ile ayır (confirmed, "
    "strongly_implied, believed, rumor, uncertain, disproven, deception).\n"
    "- 'gecerli_baslangic' / 'gecerli_bitis' YALNIZ metin hikâye zamanını açıkça söylüyorsa "
    "(ör. 'üç yıl önce katılmıştı' + bölüm bilinmiyorsa YAZMA). Emin değilsen ALANI KOYMA.\n"
    "- Kimlik açığa çıkması ('maskeli kişi aslında X') identity_revelations'a girer; "
    "birleştirme kararı VERME.\n"
    "- Sözlükte olmayan yeni bir özel ad yalnız new_entities'e girer.\n"
    "- Bir önceki bilgiyle çelişki varsa contradictions'a yaz; eskiyi silme.\n"
    "- 'iliski' şu listeden biri (özne -> nesne):\n"
    + "".join(f"    {k}: {v['etiket']}\n" for k, v in varlik_grafigi.ILISKILER.items())
    + "Yanıtı SADECE şu JSON ile ver (boş listeler yazılabilir): "
    + json.dumps({ad: [] for ad in DELTA_SEMASI}, ensure_ascii=False)
    + "\nAlanlar: " + json.dumps({ad: list(k["zorunlu"]) + list(k["secimli"]) for ad, k in DELTA_SEMASI.items()},
                                  ensure_ascii=False)
)


def istem_kur(baglam: dict, kaynak: str) -> str:
    bilgi = "\n".join(baglam["satirlar"]) or "(yok)"
    return (f"BÖLÜM {baglam['bolum']} — MEVCUT BİLGİ (bölüm {baglam['bilgi_siniri']}'e kadar):\n{bilgi}\n\n"
            f"BU BÖLÜMÜN METNİ (İngilizce):\n{kaynak}")


# ---------------------------------------------------------------------------
# SINIFLANDIRMA + İŞLEME
# ---------------------------------------------------------------------------
def _cumle_havuzu(bolum: int, kaynak: str) -> list[tuple]:
    cumleler = re.split(r"(?<=[.!?…])\s+|\n+", kaynak)
    return [(bolum, c.strip(), varlik_cikarim._normal(c)) for c in cumleler if len(c.strip()) >= 8]


def _anahtar(a, iliski, b) -> str:
    return f"{a}|{iliski}|{b}"


def delta_degerlendir(book_slug: str, bolum: int, veri: dict, kaynak: str) -> dict:
    """Modelin deltasını DOĞRULA ve SINIFLA (yazmaz). Döner: {"oneriler": [...], "inceleme": [...]}.

    Sınıf ölçütü (mevcut grafiğe göre, HER durumda — reddedilmiş bağlar dahil):
      ALREADY_EXISTS     aynı bağ var, öğrenilme bölümü <= N
      SUPPORTS_EXISTING  aynı bağ var, AYDAY (incelenmemiş) — yeni kanıt
      UPDATES_EXISTING   aynı bağ var ama SONRAKİ bir bölümde öğrenilmiş (N daha erken
                         kanıt) ya da tekil ilişkinin yeni değeri
      CONFLICTS_WITH_EXISTING  elle/rün bağıyla çelişir ya da reddedilmiş bağı diriltir
      NEEDS_REVIEW       kimlik açığa çıkması, çelişki, yeni ad, kanıtsız öğe
      NEW                hiçbiri"""
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    kategoriler = varlik_grafigi.kategori_kimlikleri(book_slug, cozucu)
    havuz = _cumle_havuzu(bolum, kaynak)
    mevcut = {(b["kaynak_kimlik"], b["iliski"], b["hedef_kimlik"]): b
              for b in varlik_grafigi.baglar(book_slug, durumlar=("aday", "onaylandi", "reddedildi"))}
    oneriler, inceleme = [], []

    ham = [dict(x, kaynak_tur="new_relationships") for x in veri.get("new_relationships", [])]
    ham += [{"ozne": x["asil"], "iliski": x["tur"], "nesne": x["ad"], "kanit": x["kanit"],
             "durum_bilgisi": x.get("durum_bilgisi"), "guven": x.get("guven", 0.9), "kaynak_tur": "new_aliases"}
            for x in veri.get("new_aliases", [])]
    for x in ham:
        x.setdefault("guven", 0.9)
    gecerli, red = varlik_cikarim._kanitli_coz(book_slug, ham, havuz, cozucu, kategoriler)
    for r in red:
        oneriler.append({"tur": r.get("kaynak_tur", "new_relationships"), "sinif": "NEEDS_REVIEW",
                         "karar": "reddedildi:" + str(r.get("sebep")), "veri": r})
    for g in gecerli:
        a, n = varlik_grafigi.anlam_sec(book_slug, g["ozne_kimlik"], g["iliski"], g["nesne_kimlik"])
        if varlik_grafigi.ILISKILER[g["iliski"]].get("simetrik") and a > n:
            a, n = n, a
        var = mevcut.get((a, g["iliski"], n))
        sinif, karar = "NEW", "işle"
        if var is not None:
            if var["durum"] == "reddedildi":
                sinif, karar = "CONFLICTS_WITH_EXISTING", "atla:daha önce reddedildi"
            elif var["ilk_bolum"] is not None and var["ilk_bolum"] <= bolum:
                sinif = "SUPPORTS_EXISTING" if var["durum"] == "aday" else "ALREADY_EXISTS"
                karar = "işle" if sinif == "SUPPORTS_EXISTING" else "atla:zaten var"
            else:
                sinif, karar = "UPDATES_EXISTING", "işle"  # daha erken kanıt: ilk_bolum küçülür
        elif varlik_grafigi.ILISKILER[g["iliski"]].get("tekil"):
            eski = [b for (ka, il, _h), b in mevcut.items()
                    if ka == a and il == g["iliski"] and b["durum"] != "reddedildi"
                    and (b["ilk_bolum"] or 0) <= bolum]
            if eski:
                sinif = "UPDATES_EXISTING"
        if g.get("kaynak_tur") == "new_aliases" and sinif == "NEW":
            inceleme.append(("alias", "medium", f"Yeni kimlik bağı: {g['ozne']} {g['iliski']} {g['nesne']}",
                             {"ozne": g["ozne"], "iliski": g["iliski"], "nesne": g["nesne"], "kanit": g.get("kanit")}))
        for diger in varlik_grafigi.ILISKILER[g["iliski"]].get("kapatir", ()):
            for anahtar in ((a, diger, n), (n, diger, a)):
                b = mevcut.get(anahtar)
                if b and b["durum"] == "onaylandi" and b["origin"] in ("manual", "sistem"):
                    sinif = "CONFLICTS_WITH_EXISTING"
                    inceleme.append(("relationship_conflict", "medium",
                                     f"{g['ozne']} {g['iliski']} {g['nesne']} elle/rün '{diger}' bağıyla çelişiyor",
                                     {"oneri": [g["ozne"], g["iliski"], g["nesne"]], "kanit": g.get("kanit")}))
        oneriler.append({"tur": g.get("kaynak_tur", "new_relationships"), "sinif": sinif, "karar": karar,
                         "veri": {**g, "ozne_kimlik": a, "nesne_kimlik": n}})

    for x in veri.get("relationship_updates", []):
        a, n = cozucu.coz(x["ozne"]), cozucu.coz(x["nesne"])
        var = mevcut.get((a, x["iliski"], n)) or mevcut.get((n, x["iliski"], a))
        kanitli = any(varlik_cikarim._normal(x["kanit"]) in c for _b, _c, c in havuz)
        if var is None or not kanitli or (var["ilk_bolum"] or 0) > bolum:
            oneriler.append({"tur": "relationship_updates", "sinif": "NEEDS_REVIEW",
                             "karar": "reddedildi:bağ yok ya da kanıt bu bölümde değil", "veri": x})
            continue
        sinif = "CONFLICTS_WITH_EXISTING" if var["origin"] in ("manual", "sistem") else "UPDATES_EXISTING"
        karar = "inceleme" if sinif == "CONFLICTS_WITH_EXISTING" else "işle"
        if sinif == "CONFLICTS_WITH_EXISTING":
            inceleme.append(("epistemic_conflict" if x["degisim"] == "disproven" else "temporal_conflict", "high",
                             f"Elle/rün bağı için '{x['degisim']}' önerisi: {x['ozne']} {x['iliski']} {x['nesne']}",
                             {"oneri": x}))
        oneriler.append({"tur": "relationship_updates", "sinif": sinif, "karar": karar,
                         "veri": {**x, "kaynak_kimlik": var["kaynak_kimlik"], "hedef_kimlik": var["hedef_kimlik"]}})

    for x in veri.get("state_changes", []):
        k = cozucu.coz(x["varlik"])
        kanitli = any(varlik_cikarim._normal(x["kanit"]) in c for _b, _c, c in havuz)
        if not k or not kanitli:
            oneriler.append({"tur": "state_changes", "sinif": "NEEDS_REVIEW",
                             "karar": "reddedildi:varlık sözlükte yok ya da kanıt bu bölümde değil", "veri": x})
            continue
        onceki = (varlik_grafigi.degerler(book_slug, bolum - 1, k).get(k) or {}).get(x["anahtar"])
        sinif = "NEW" if onceki is None else ("ALREADY_EXISTS" if onceki["deger"] == x["deger"] else "UPDATES_EXISTING")
        oneriler.append({"tur": "state_changes", "sinif": sinif,
                         "karar": "atla:zaten var" if sinif == "ALREADY_EXISTS" else "işle",
                         "veri": {**x, "kimlik": k}})

    for x in veri.get("identity_revelations", []):
        inceleme.append(("identity_merge", "critical",
                         f"Kimlik açığa çıkması önerisi (b{bolum}): {x['ad_1']} = {x['ad_2']}",
                         {"ad_1": x["ad_1"], "ad_2": x["ad_2"], "kanit": x["kanit"], "aciklama": x.get("aciklama")}))
        oneriler.append({"tur": "identity_revelations", "sinif": "NEEDS_REVIEW", "karar": "inceleme", "veri": x})
    for x in veri.get("contradictions", []):
        inceleme.append(("epistemic_conflict", "medium", x["aciklama"], x))
        oneriler.append({"tur": "contradictions", "sinif": "NEEDS_REVIEW", "karar": "inceleme", "veri": x})
    for x in veri.get("new_entities", []):
        if not cozucu.coz(x["ad"]):
            inceleme.append(("new_entity", "low", f"Sözlükte olmayan ad: {x['ad']}", x))
        oneriler.append({"tur": "new_entities", "sinif": "NEEDS_REVIEW", "karar": "inceleme", "veri": x})
    for x in veri.get("review_items", []):
        inceleme.append((x["kategori"], x.get("onem") or "medium", x["aciklama"], x))
    return {"oneriler": oneriler, "inceleme": inceleme}


def delta_isle(book_slug: str, bolum: int, degerlendirme: dict, model: str) -> dict:
    """Değerlendirilmiş deltayı grafiğe İŞLE — yalnız `bag_ekle` / `deger_yaz` /
    `iddiayi_curut` üzerinden. Model önerisi daima `aday` (incelenmemiş) girer; elle/rün
    bağına dokunulmaz (bag_ekle'nin köken önceliği). Döner: sayaçlar."""
    cikarim = cikarim_kimligi(model)
    sayac = {s: 0 for s in SINIFLAR} | {"yazilan_bag": 0, "yazilan_deger": 0, "kapanan": 0, "inceleme": 0}
    # Önce GRAFİK yazımları (her biri kendi bağlantısıyla, Faz 1 yolları), SONRA öneri
    # günlüğü tek bağlantıda: yazma kilidini tutan bir bağlantı açıkken grafiğe ikinci
    # bağlantıdan yazmak "database is locked" veriyordu (testte ölçüldü).
    gunluk = []
    for o in degerlendirme["oneriler"]:
        sayac[o["sinif"]] += 1
        v = o["veri"]
        if o["karar"] == "işle" and o["tur"] in ("new_relationships", "new_aliases"):
            varlik_grafigi.bag_ekle(
                book_slug, v["ozne_kimlik"], v["iliski"], v["nesne_kimlik"], bolum, v.get("kanit"), "model",
                float(v.get("guven") or 0.9), durum="aday", durum_bilgisi=v.get("durum_bilgisi"),
                gecerli_baslangic=v.get("gecerli_baslangic"), gecerli_bitis=v.get("gecerli_bitis"),
            )
            sayac["yazilan_bag"] += 1
        elif o["karar"] == "işle" and o["tur"] == "state_changes":
            if varlik_grafigi.deger_yaz(book_slug, v["kimlik"], v["anahtar"], v["deger"], bolum, v.get("kanit"),
                                        origin="model", durum_bilgisi=v.get("durum_bilgisi")):
                sayac["yazilan_deger"] += 1
        elif o["karar"] == "işle" and o["tur"] == "relationship_updates":
            if v["degisim"] == "disproven":
                varlik_grafigi.iddiayi_curut(book_slug, v["kaynak_kimlik"], v["iliski"], v["hedef_kimlik"], bolum)
            else:
                c2 = varlik_grafigi._connect()
                try:
                    c2.execute(
                        "UPDATE varlik_bag SET bitis_ogrenildigi = ?, gecerli_bitis = COALESCE(gecerli_bitis, ?) "
                        "WHERE book_slug = ? AND kaynak_kimlik = ? AND iliski = ? AND hedef_kimlik = ? "
                        "AND bitis_ogrenildigi IS NULL",
                        (bolum, v.get("gecerli_bitis"), book_slug, v["kaynak_kimlik"], v["iliski"], v["hedef_kimlik"]),
                    )
                    c2.commit()
                finally:
                    c2.close()
            sayac["kapanan"] += 1
        anahtar = json.dumps({k: v.get(k) for k in ("ozne", "iliski", "nesne", "varlik", "anahtar", "deger",
                                                     "ad", "ad_1", "ad_2", "asil", "aciklama") if v.get(k)},
                             sort_keys=True, ensure_ascii=False)
        gunluk.append((book_slug, bolum, cikarim, o["tur"], anahtar, o["sinif"], o["karar"],
                       json.dumps(v, ensure_ascii=False, default=str), time.time()))
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO bilgi_oneri (book_slug, bolum, cikarim, tur, anahtar, sinif, karar, veri, zaman) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", gunluk,
        )
        for kategori, onem, aciklama, veri in degerlendirme["inceleme"]:
            if inceleme_ekle(conn, book_slug, bolum, kategori, onem, aciklama, veri):
                sayac["inceleme"] += 1
        conn.commit()
    finally:
        conn.close()
    return sayac


# ---------------------------------------------------------------------------
# ORKESTRASYON — geçmiş doldurma ve canlı okuma AYNI fonksiyonu çağırır
# ---------------------------------------------------------------------------
class KronolojiHatasi(RuntimeError):
    """Bölüm N, baş N-1 değilken İLERİ işlenmeye çalışıldı (atlama = sessiz delik)."""


def kaynak_metin(book_slug: str, bolum: int) -> str | None:
    for b in cache.kaynak_bolumleri(book_slug):
        if b["chapter_no"] == bolum:
            return b["source"]
    return None


def bolum_degerlendir(book_slug: str, bolum: int, model: str, cagri=None) -> dict:
    """DOĞRULAMA kipi: model çağrılır, delta doğrulanır ve SINIFLANIR ama grafiğe,
    kuyruğa, işleme durumuna HİÇBİR ŞEY YAZILMAZ ve baş ilerlemez. Bağlam yine N-1
    süzgeçli: doğrulama seti bölümleri (kronolojik olmayan seçim) gelecek görmez.
    Döner: girdi bilgisi, model deltası, doğrulayıcı kararları, planlanan mutasyon."""
    kaynak = kaynak_metin(book_slug, bolum)
    if not kaynak:
        return {"bolum": bolum, "durum": "failed", "hata": "kaynak metin yok"}
    baglam = baglam_kur(book_slug, bolum, kaynak)
    istem = istem_kur(baglam, kaynak)
    metin, kullanim = (cagri or _model_cagir(model))(istem, CIKARICI_TALIMATI)
    veri = varlik_cikarim_ayristir(metin)
    hatalar = sema_dogrula(veri) if veri is not None else ["yanıt JSON değil"]
    degerlendirme = delta_degerlendir(book_slug, bolum, veri, kaynak) if not hatalar else None
    return {"bolum": bolum, "durum": "dogrulama", "girdi_bilgisi": baglam["satirlar"],
            "olcum": {"kaynak_tokeni": baglam["kaynak_tokeni"], "baglam_tokeni": baglam["baglam_tokeni"],
                      "kesilen_satir": baglam["kesilen_satir"], "aday_satir": baglam["aday_satir"],
                      "giren_satir": len(baglam["satirlar"]), "sinif": baglam["sinif"], **(kullanim or {})},
            "ham_yanit": metin,
            "model_deltasi": veri, "sema_hatalari": hatalar, "degerlendirme": degerlendirme}


def bolum_isle(book_slug: str, bolum: int, model: str, kuru: bool = False, yeniden: bool = False,
               cagri=None) -> dict:
    """TEK çekirdek: bölüm N'yi işle. `kuru` = model çağrılmaz, yazılmaz (bağlam + maliyet).

    Kronoloji: ileri işleme yalnız `bas_bolum == N-1` iken (atlama yok). `yeniden` =
    zaten işlenmiş bir bölümü yeniden işle (baş ilerlemez; bağlam yine N-1 süzgeçli).
    `cagri(user, system) -> (metin, kullanim)` test/değerlendirme için enjekte edilir."""
    kaynak = kaynak_metin(book_slug, bolum)
    if not kaynak:
        return {"bolum": bolum, "durum": "failed", "hata": "kaynak metin (source_text) yok"}
    bas = bas_bolum(book_slug)
    if not kuru and not yeniden and bas != bolum - 1:
        raise KronolojiHatasi(f"baş {bas}, istenen {bolum}: önce {bas + 1} işlenmeli")
    if yeniden and bolum > bas:
        raise KronolojiHatasi(f"{bolum} henüz işlenmedi (baş {bas}); yeniden işleme yalnız geriye")
    baglam = baglam_kur(book_slug, bolum, kaynak)
    istem = istem_kur(baglam, kaynak)
    olcum = {"kaynak_tokeni": baglam["kaynak_tokeni"], "baglam_tokeni": baglam["baglam_tokeni"],
             "talimat_tokeni": _tok(CIKARICI_TALIMATI), "kesilen_satir": baglam["kesilen_satir"],
             "toplam_giris_tahmini": _tok(istem) + _tok(CIKARICI_TALIMATI)}
    if kuru:
        return {"bolum": bolum, "durum": "kuru", "olcum": olcum, "baglam": baglam["satirlar"]}
    conn = _connect()
    try:
        _durum_yaz(conn, book_slug, bolum, "processing", model=model, deneme_artir=True)
        conn.commit()
    finally:
        conn.close()
    try:
        metin, kullanim = (cagri or _model_cagir(model))(istem, CIKARICI_TALIMATI)
        olcum.update(kullanim or {})
        veri = varlik_cikarim_ayristir(metin)
        hatalar = sema_dogrula(veri) if veri is not None else ["yanıt JSON değil"]
        if hatalar:
            raise ValueError("şema: " + "; ".join(hatalar[:5]))
        degerlendirme = delta_degerlendir(book_slug, bolum, veri, kaynak)
        sayac = delta_isle(book_slug, bolum, degerlendirme, model)
    except Exception as exc:  # noqa: BLE001 — her hata bölümü 'failed' yapar, okumayı DURDURMAZ
        conn = _connect()
        try:
            _durum_yaz(conn, book_slug, bolum, "failed", model=model, hata=f"{type(exc).__name__}: {exc}"[:500],
                       metrik=olcum)
            conn.commit()
        finally:
            conn.close()
        return {"bolum": bolum, "durum": "failed", "hata": str(exc), "olcum": olcum}
    durum = "needs_review" if any(i[1] in ("critical", "high") for i in degerlendirme["inceleme"]) else "completed"
    conn = _connect()
    try:
        _durum_yaz(conn, book_slug, bolum, durum, model=model, metrik={**olcum, **sayac})
        if not yeniden:
            conn.execute("INSERT INTO bilgi_bas (book_slug, bas_bolum) VALUES (?, ?) "
                         "ON CONFLICT(book_slug) DO UPDATE SET bas_bolum = excluded.bas_bolum", (book_slug, bolum))
        conn.commit()
    finally:
        conn.close()
    return {"bolum": bolum, "durum": durum, "olcum": olcum, "sayac": sayac,
            "degerlendirme": degerlendirme, "veri": veri, "baglam": baglam["satirlar"]}


def varlik_cikarim_ayristir(metin: str | None) -> dict | None:
    ham = (metin or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return None
    return veri if isinstance(veri, dict) else None


def _model_cagir(model: str):
    def cagir(user: str, system: str):
        yanit, fiili = translate._generate_with_fallback(
            translate._gemini_fabrikasi(""), (model,), user, system=system, max_tokens=translate.MAX_OUTPUT_TOKENS,
        )
        meta = getattr(yanit, "usage_metadata", None)
        kullanim = {"fiili_model": fiili}
        if meta is not None:
            kullanim.update({"giris_tokeni": getattr(meta, "prompt_token_count", None),
                             "cikis_tokeni": getattr(meta, "candidates_token_count", None),
                             "dusunme_tokeni": getattr(meta, "thoughts_token_count", None)})
        return getattr(yanit, "text", None), kullanim
    return cagir


def kontrol_noktasi(book_slug: str, bolum: int) -> dict:
    """Grafik sağlığı anlık görüntüsü (her 25 bölümde kaydedilir; bozulmayı erken yakalamak için)."""
    bag = varlik_grafigi.baglar(book_slug, en_cok_bolum=bolum, durumlar=("aday", "onaylandi"))
    durum = {}
    for b in bag:
        durum[b["durum_bilgisi"] or "değerlendirilmemiş"] = durum.get(b["durum_bilgisi"] or "değerlendirilmemiş", 0) + 1
    conn = _connect()
    try:
        isleme = dict(conn.execute("SELECT durum, COUNT(*) FROM bilgi_isleme WHERE book_slug = ? GROUP BY durum",
                                   (book_slug,)).fetchall())
        inceleme = conn.execute("SELECT COUNT(*) FROM bilgi_inceleme WHERE book_slug = ? AND durum = 'acik'",
                                (book_slug,)).fetchone()[0]
        tokenler = [json.loads(r[0] or "{}").get("toplam_giris_tahmini") or 0 for r in conn.execute(
            "SELECT metrik FROM bilgi_isleme WHERE book_slug = ? AND bolum <= ?", (book_slug, bolum))]
        degerler = sum(len(v) for v in varlik_grafigi.degerler(book_slug, bolum).values())
        metrik = {
            "varlik": len({b["kaynak_kimlik"] for b in bag} | {b["hedef_kimlik"] for b in bag}),
            "bag": len(bag), "takma_ad": sum(b["iliski"] in KIMLIK_ILISKILERI for b in bag), "deger": degerler,
            "durum_bilgisi": durum, "inceleme_kuyrugu": inceleme, "isleme": isleme,
            "ortalama_giris_tokeni": round(sum(tokenler) / len(tokenler)) if tokenler else 0,
            "basarisiz": isleme.get("failed", 0),
        }
        conn.execute("INSERT OR REPLACE INTO bilgi_kontrol (book_slug, bolum, zaman, metrik) VALUES (?, ?, ?, ?)",
                     (book_slug, bolum, time.time(), json.dumps(metrik, ensure_ascii=False)))
        conn.commit()
        return metrik
    finally:
        conn.close()


def canli_kuyruga_ekle(book_slug: str, bolum: int | None) -> None:
    """CANLI mod: çeviri kaydedildikten SONRA bölümü 'pending' olarak sıraya koy.
    Okumayı ASLA engellemez: her hata yutulur (grafik çeviriden sonra gelir)."""
    if not bolum:
        return
    try:
        conn = _connect()
        try:
            conn.execute("INSERT OR IGNORE INTO bilgi_isleme (book_slug, bolum, durum, deneme) VALUES (?, ?, 'pending', 0)",
                         (book_slug, bolum))
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass
