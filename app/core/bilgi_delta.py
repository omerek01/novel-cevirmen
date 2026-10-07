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

from . import cache, db, glossary, translate, varlik_cikarim, varlik_grafigi, bilgi_kanit, kapsama_ipuclari

CIKARICI_SURUMU = "7"  # v7: zamir/ceset/çoğul True Names + rün alt satırları + kapsama ipuçları
ISTEM_SURUMU = "6"  # v6: + "COVERAGE CUES — THESE ARE NOT FACTS" bölümü (v5 kapsama taraması korunur)
SEMA_SURUMU = "delta-3-v4-final"  # şema DEĞİŞMEDİ (v5 yalnız istem + bastırma sınıfı)

# ÇIKARICI SAĞLAYICISI — çeviri yapılandırmasından AYRI (kullanıcı kararı 2026-10-07):
# bilgi çıkarımı YALNIZ Vertex'ten geçer; ücretsiz Gemini kotası okumaya kalır. Çeviri
# zinciri (`translate.DEFAULT_MODELS`, ayarlar ucu) buradan etkilenmez, burası da ondan.
CIKARICI_MODELI = "vertex/gemini-3.6-flash"
CIKARICI_SAGLAYICI = "VERTEX"


class SaglayiciHatasi(RuntimeError):
    """Çıkarıcı Vertex dışı bir modelle çağrıldı (ücretsiz Gemini'ye sızma YOK)."""

DURUMLAR = ("pending", "processing", "completed", "failed", "needs_review")
SINIFLAR = ("NEW", "ALREADY_EXISTS", "SUPPORTS_EXISTING", "CONFLICTS_WITH_EXISTING",
            "UPDATES_EXISTING", "NEEDS_REVIEW")
INCELEME_KATEGORILERI = ("identity_merge", "alias", "relationship_conflict", "temporal_conflict",
                         "epistemic_conflict", "duplicate_candidate", "retroactive_revelation",
                         "new_entity", "new_entity_candidate", "schema", "relation_capability_gap",
                         "model_review", "high_impact_review")  # v8 aday yolu
ONEMLER = ("critical", "high", "medium", "low")
KIMLIK_ILISKILERI = ("takma_adi", "gercek_adi", "unvani")

# ---- TEK DOĞRULUK KAYNAĞI (v2): API yanıt şeması, talimat ve doğrulayıcı AYNI sabitleri okur ----
# Durum anahtarları: çıkarıcıda makine adı, depoda MEVCUT adlar (göç YOK; eşleme burada).
DURUM_ANAHTARLARI = {
    "shadow_cores": "Shadow Cores", "shadow_fragments": "Shadow Fragments", "soul": "Soul",
    "memory_tier": "Memory Tier", "role": "Görev", "type": "Tür", "life_status": "Yaşam",
}
LIFE_STATUS = ("alive", "dead", "missing", "presumed_dead", "unknown")
# Değer (life_status) ile bilgi durumu (durum_bilgisi) AYRIDIR: presumed_dead + believed ile
# dead + confirmed farklı anlamlardır; sonra gelen alive + confirmed eskiyi SİLMEZ.
DURUM_BILGISI_TANIMLARI = {
    "confirmed": "Narrative/system/direct reliable observation establishes it as fact.",
    "strongly_implied": "Text strongly supports it but does not explicitly establish it.",
    "believed": "Characters/narration currently believe it, but truth is not established.",
    "rumor": "Information is explicitly hearsay/report/rumor.",
    "uncertain": "Evidence is ambiguous or incomplete.",
    "disproven": "Previously represented claim is now shown false.",
    "deception": "The text establishes that a claim/information was deliberately false or misleading.",
}
assert tuple(DURUM_BILGISI_TANIMLARI) == varlik_grafigi.DURUM_BILGISI

# Bağlam bütçesi (yaklaşık token = karakter / 4). Kaynak metin bütçeye dahil DEĞİL;
# büyüyen şey grafiktir ve bölüm sayısıyla SINIRSIZ büyümemeli.
BAGLAM_BUTCESI = 4000  # kullanıcı kararı (2026-10-07): 2500'de geç bölümlerde 120-320 satır kesiliyordu
SON_BOLUM_PENCERESI = 30  # "son ilgili geçmiş" önceliği için

# ---------------------------------------------------------------------------
# DELTA ŞEMASI — Faz 1 tablolarına birebir eşlenir (Olay/Gizem/Olgu tablosu YOK).
# ---------------------------------------------------------------------------
DELTA_SEMASI = {
    "new_relationships": {   # -> varlik_bag (bag_ekle), ilk_bolum = N
        "zorunlu": ("ozne", "iliski", "nesne", "kanit", "durum_bilgisi"),
        "secimli": ("gecerli_baslangic", "gecerli_bitis"),
    },
    "new_aliases": {         # -> varlik_bag takma_adi (lakap) / gercek_adi / unvani, ilk_bolum = N
        "zorunlu": ("asil", "ad", "tur", "kanit", "durum_bilgisi"),
        "secimli": (),
    },
    "relationship_updates": {  # mevcut bağın bitişi / çürütülmesi (SİLMEZ)
        "zorunlu": ("ozne", "iliski", "nesne", "degisim", "kanit"),
        "secimli": ("gecerli_bitis", "durum_bilgisi"),
    },
    "state_changes": {       # -> varlik_deger (deger_yaz), ilk_bolum = N; anahtar DURUM_ANAHTARLARI
        "zorunlu": ("varlik", "anahtar", "deger", "kanit", "durum_bilgisi"),
        "secimli": (),
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
        "zorunlu": ("kategori", "onem"),
        "secimli": ("aciklama", "kanit", "ozne", "iliski", "nesne"),
    },
}
# Alan -> enum (TEK kaynak). Şema üreteci, talimat ve doğrulayıcı bunu okur.
ALAN_ENUMLARI = {
    "iliski": tuple(varlik_grafigi.ILISKILER),
    "durum_bilgisi": varlik_grafigi.DURUM_BILGISI,
    "degisim": None,            # DEGISIMLER (aşağıda tanımlı)
    "anahtar": tuple(DURUM_ANAHTARLARI),
    "kategori": None,           # INCELEME_KATEGORILERI
    "onem": ONEMLER,
}
DEGISIMLER = ("ended", "disproven")
ALAN_ENUMLARI["degisim"] = DEGISIMLER
ALAN_ENUMLARI["kategori"] = INCELEME_KATEGORILERI


def _alan_enum(bolum: str, alan: str):
    """Alanın enum'u (yoksa None). `tur` yalnız new_aliases'ta enum'ludur (new_entities'te serbest)."""
    if alan == "tur":
        return KIMLIK_ILISKILERI if bolum == "new_aliases" else None
    return ALAN_ENUMLARI.get(alan)


def yanit_semasi() -> dict:
    """API düzeyinde zorunlu kılınan JSON şeması — DELTA_SEMASI + ALAN_ENUMLARI'ndan ÜRETİLİR.
    Talimattaki alan listesi de aynı kaynaktan gelir (iki kopya YOK)."""
    def alan(bolum, ad):
        if ad in ("gecerli_baslangic", "gecerli_bitis"):
            return {"type": ["integer", "null"]}
        enum = _alan_enum(bolum, ad)
        return {"type": "string", "enum": list(enum)} if enum else {"type": "string"}
    ozellikler = {}
    for bolum, kural in DELTA_SEMASI.items():
        alanlar = list(kural["zorunlu"]) + list(kural["secimli"])
        ozellikler[bolum] = {"type": "array", "items": {
            "type": "object",
            "properties": {a: alan(bolum, a) for a in alanlar},
            "required": list(kural["zorunlu"]),
            "additionalProperties": False,
        }}
    # life_status değerleri diğer durum değerlerinin serbest metniyle karışmasın.
    durum = ozellikler["state_changes"]["items"]
    yasam = {**durum, "properties": {**durum["properties"],
              "anahtar": {"type": "string", "enum": ["life_status"]},
              "deger": {"type": "string", "enum": list(LIFE_STATUS)}}}
    diger = {**durum, "properties": {**durum["properties"],
              "anahtar": {"type": "string", "enum": [k for k in DURUM_ANAHTARLARI if k != "life_status"]}}}
    ozellikler["state_changes"]["items"] = {"anyOf": [yasam, diger]}
    review = ozellikler['review_items']['items']
    conflict = {**review,'properties':{**review['properties'],'kategori':{'type':'string','enum':['relationship_conflict']}},
                'required':['kategori','ozne','iliski','nesne','kanit','onem']}
    gap={**review,'properties':{**review['properties'],'kategori':{'type':'string','enum':['relation_capability_gap']}},'required':['kategori','ozne','nesne','kanit','onem']}
    other = {**review,'properties':{**review['properties'],'kategori':{'type':'string','enum':[k for k in INCELEME_KATEGORILERI if k not in ('relationship_conflict','relation_capability_gap')]}}}
    ozellikler['review_items']['items']={'anyOf':[conflict,gap,other]}
    return {"type": "object", "properties": ozellikler, "required": list(DELTA_SEMASI),
            "additionalProperties": False}


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
        if ad not in veri:
            hatalar.append(f"{ad} eksik")
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
                if not isinstance(x.get(z), str) or not x[z].strip():
                    hatalar.append(f"{ad}[{i}].{z} eksik")
            if ad=='review_items' and x.get('kategori')=='relationship_conflict':
                for z in ('ozne','iliski','nesne','kanit'):
                    if not isinstance(x.get(z),str) or not x[z].strip():
                        hatalar.append(f'{ad}[{i}].{z} eksik')
            if ad=='review_items' and x.get('kategori')=='relation_capability_gap':
                for z in ('ozne','nesne','kanit'):
                    if not isinstance(x.get(z),str) or not x[z].strip():
                        hatalar.append(f'{ad}[{i}].{z} eksik')
            for alan in x:
                if alan not in izinli:
                    hatalar.append(f"{ad}[{i}].{alan} bilinmeyen alan")
            for alan_adi, deger in x.items():
                if alan_adi == "anahtar":
                    continue  # bilinmeyen durum anahtarı ŞEMA hatası değil: ölçülür (unsupported_state_key)
                enum = _alan_enum(ad, alan_adi)
                if enum and deger is not None and deger not in enum:
                    hatalar.append(f"{ad}[{i}].{alan_adi} enum dışında: {deger}")
                if alan_adi not in ("gecerli_baslangic", "gecerli_bitis") and not isinstance(deger, str):
                    hatalar.append(f"{ad}[{i}].{alan_adi} metin değil")
            if ad == "state_changes" and x.get("anahtar") == "life_status" and x.get("deger") not in LIFE_STATUS:
                hatalar.append(f"{ad}[{i}].deger life_status enum dışında")
            for b in ("gecerli_baslangic", "gecerli_bitis"):
                if x.get(b) is not None and type(x[b]) is not int:
                    hatalar.append(f"{ad}[{i}].{b} tam sayı değil")
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


def deterministik_plan(book_slug: str, kaynak: str) -> list[tuple]:
    """Mevcut rün parser'ının yazmasız planı; ikinci parser/kalıcı grafik yok."""
    p = varlik_grafigi.profil(book_slug) or {}
    return varlik_grafigi.sistem_baglarini_bul(kaynak, p.get("ana_karakter", ""),
                                             tuple(p.get("ana_karakter_adlari", ())))


def canonical_triple(s: str, r: str, o: str, cozucu) -> tuple:
    """Prompt ve same-chapter karşılaştırmasının ortak ad normalizasyonu."""
    def ad(v):
        k = cozucu.coz(v)
        return cozucu.kaynak(k) if k else varlik_cikarim._normal(v)
    return ad(s), r, ad(o) if r != varlik_grafigi.DEGER else o


def canonical_plan(book_slug: str, kaynak: str, cozucu=None) -> list[tuple]:
    cozucu = cozucu or varlik_grafigi.DugumCozucu(book_slug)
    return [(*canonical_triple(s, r, o, cozucu), e) for s, r, o, e in deterministik_plan(book_slug, kaynak)
            if r in varlik_grafigi.ILISKILER or r == varlik_grafigi.DEGER]


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
    # AYNI BÖLÜMÜN rün (deterministik) bilgisi: N'de öğrenilmiştir, GELECEK DEĞİLDİR;
    # modele "bunu tekrar etme" diye verilir (v1'de tekrarın ana kaynağı buydu).
    def run_satiri(s, r, o):
        s, r, o = canonical_triple(s, r, o, cozucu)
        if r == varlik_grafigi.DEGER:
            key, value = o.split("\t", 1)
            x = {"varlik": s, "anahtar": next((a for a,b in DURUM_ANAHTARLARI.items() if b==key),key), "deger": value}
        else:
            x = {"ozne": s, "iliski": r, "nesne": o}
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    run_satirlari = [run_satiri(b['kaynak'], b['iliski'], b['hedef']) for b in varlik_grafigi.baglar(book_slug, en_cok_bolum=bolum)
                     if b["origin"] == "sistem" and b["ilk_bolum"] == bolum]
    plan_kanitlari = []
    for s, r, o, _e in canonical_plan(book_slug, kaynak, cozucu):
        run_satirlari.append(run_satiri(s, r, o))
        plan_kanitlari.append(_e)
    run_satirlari = list(dict.fromkeys(run_satirlari))
    ters_anahtar = {v: k for k, v in DURUM_ANAHTARLARI.items()}
    conn_d = varlik_grafigi._connect()
    try:
        for kimlik, anahtar, deger in conn_d.execute(
            "SELECT kimlik, anahtar, deger FROM varlik_deger WHERE book_slug = ? AND ilk_bolum = ? AND origin = 'sistem'",
            (book_slug, bolum),
        ):
            ad = gecen.get(kimlik) or (cozucu.satirlar.get(varlik_grafigi.taban_kimlik(kimlik)) or {}).get("source", kimlik)
            run_satirlari.append(run_satiri(ad, varlik_grafigi.DEGER, f"{anahtar}\t{deger}"))
    finally:
        conn_d.close()
    run_satirlari = list(dict.fromkeys(run_satirlari))
    satirlar.sort(key=lambda x: x[0])
    # Aynı bölüm verisi de grafik bağlamıdır: toplam bütçe hâlâ 4000, ek bütçe YOK.
    run_secilen, run_tokeni = [], 0
    for s in run_satirlari:
        t = _tok(s) + 1
        if run_tokeni + t <= butce:
            run_secilen.append(s)
            run_tokeni += t
    run_kesilen = len(run_satirlari) - len(run_secilen)
    secilen, kullanilan, kesilen = [], run_tokeni, run_kesilen
    sinif_adi = {1: "varlik", 2: "kimlik", 3: "durum", 4: "dogrudan_yeni", 5: "dogrudan_eski", 6: "kimlik_sorusu"}
    sinif = {ad: {"aday": 0, "giren": 0, "kesilen": 0} for ad in sinif_adi.values()}
    sinif["ayni_bolum_deterministik"] = {"aday": len(run_satirlari), "giren": len(run_secilen), "kesilen": run_kesilen}
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
    # Kapsama ipuçları AYRI istem yüküdür: 4000'lik bilgi bütçesine girmez, ondan da kesmez.
    ipuclari = kapsama_ipuclari.ipuclari(kaynak, tuple(plan_kanitlari))
    return {"bolum": bolum, "bilgi_siniri": onceki, "satirlar": secilen, "gecen": gecen,
            "ipuclari": ipuclari, "ipucu_tokeni": _tok(kapsama_ipuclari.ipucu_bolumu(ipuclari)),
            "run_satirlari": run_secilen, "run_tokeni": run_tokeni,
            "baglam_tokeni": kullanilan, "kesilen_satir": kesilen, "aday_satir": len(satirlar) + len(run_satirlari),
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
AYNI_BOLUM_BASLIGI = "ALREADY EXTRACTED FROM THIS CHAPTER — DO NOT RE-EXTRACT"

# Kapsama taraması kontrol listesi (v5). Kategori adları istemde ve testlerde AYNI
# kaynaktan okunur. TEK model çağrısı: model taramayı içinde yapar, çıktısı yalnız delta.
KAPSAMA_KATEGORILERI = {
    "A. IDENTITY": "True Name, ordinary personal name, title, alias, identity revelation.",
    "B. RELATIONSHIPS": "companion/ally, enemy, teacher/student, clan/group membership, leader, "
                        "ownership-like relations, shadow/master, echo/master, Memory ownership, location, "
                        "attributes, abilities, transformation, kill, conflict/end of an existing relation.",
    "C. STATE": ", ".join(DURUM_ANAHTARLARI) + ".",
    "D. CHANGE": "relationship begins, relationship ends, relationship conflicts with current knowledge, "
                 "transformation, state change, prior claim disproven.",
    "E. EPISTEMIC STATUS": "confirmed vs strongly_implied/believed/rumor/uncertain/disproven/deception.",
    "F. REPRESENTATION GAP": "graph-worthy knowledge the controlled vocabulary cannot represent safely "
                             "(e.g. transfer, entrustment, custody).",
}
BOS_DELTA_ONCESI_SINYALLER = (
    "explicit death", "explicit alive", "explicit teacher/student", "title/name statement",
    "transfer/entrustment", "relationship rupture", "collective belief", "identity revelation",
    "transformation",
)


def _talimat() -> str:
    tanim = "".join(f"    {k}: {v}\n" for k, v in DURUM_BILGISI_TANIMLARI.items())
    iliski = "".join(f"    {k}: {v['subject_role']} -> {v['object_role']} ({v['etiket']})\n" for k, v in varlik_grafigi.ILISKILER.items())
    kapsama = "".join(f"  {k}: {v}\n" for k, v in KAPSAMA_KATEGORILERI.items())
    return (
        "You update a novel's CHRONOLOGICAL KNOWLEDGE GRAPH as if reading it for the first time. "
        "You receive (1) KNOWN THROUGH N-1, (2) " + AYNI_BOLUM_BASLIGI + " (deterministic rune/system "
        "parser output for this chapter), and (3) this chapter's English text. The question is NOT 'what "
        "happened in this chapter' but 'what NEW knowledge does this chapter add, change, reveal or disprove "
        "relative to (1) and (2)'. Goal: high-value, high-confidence, spoiler-safe, temporally correct "
        "knowledge; a wrong item is worse than a missing one.\n"
        "WORK IN TWO STAGES INSIDE THIS SINGLE RESPONSE:\n"
        "STAGE A — COVERAGE SCAN (internal; do NOT output it, do NOT explain it). Go through the prose and "
        "check EVERY category below against KNOWN and the same-chapter list:\n" + kapsama +
        "STAGE B — DELTA OUTPUT. Output ONLY the JSON delta: items that are new, changed, contradicted, "
        "epistemically relevant, or a representation gap. CHECK != EMIT: checking a category does not "
        "require output; emit nothing for it when there is no new, evidenced knowledge.\n"
        "COVERAGE CUES CONTRACT: the section '" + kapsama_ipuclari.IPUCU_BASLIGI + "' lists source spans "
        "found by a keyword scanner. They are NOT facts and NOT evidence. Inspect each cue; do not assume it "
        "is true; emit only what the source and context actually establish; exact evidence must still be "
        "copied from the chapter text; known and same-chapter facts must still not be duplicated. A cue may "
        "point to nothing graph-worthy.\n"
        "COVERAGE BEFORE AN EMPTY DELTA: an empty delta is valid only after you have checked the prose for: "
        + ", ".join(BOS_DELTA_ONCESI_SINYALLER) + ". Most chapters have a small delta.\n"
        "EVIDENCE COPY DISCIPLINE: 'kanit' is ONE contiguous span COPIED character-for-character from THIS "
        "chapter's text. DO NOT reconstruct evidence from memory. DO NOT paraphrase, shorten inside, reorder, "
        "or stitch passages. DO NOT add or close quotation marks, ellipses or punctuation that are not at "
        "that exact place in the source: if a quotation continues past your span, end the span at a sentence "
        "end WITHOUT adding a closing quote mark. Every named entity of the item must appear in the span. "
        "Default: 1-3 sentences. Reviews: at most SIX contiguous sentences and 900 characters. Two names in "
        "one sentence is NOT evidence of a relationship; do not infer ally/friend/enemy/member from "
        "co-presence, guessed motivation or world knowledge.\n"
        "SAME-CHAPTER DETERMINISTIC KNOWLEDGE: items under " + AYNI_BOLUM_BASLIGI + " use EXACT "
        "canonical output-field names and are already handled even when not persisted. DO NOT emit those "
        "triples/states in any array. But a rune listing an entity is NOT every prose fact about it: death, "
        "life status, transfer, relationship, belief or title stated in the PROSE is still new knowledge.\n"
        "COMPLEMENTARY REPRESENTATIONS ARE NOT DUPLICATES: suppress only the SAME knowledge in the SAME "
        "representation (same triple, same state key/value/status). A relation and a state answer different "
        "graph queries. Example: KNOWN 'Arden --oldurdu--> Mira' does NOT make 'Mira.life_status = dead' "
        "redundant; if this chapter explicitly states Mira is dead, emit the state. Likewise an existing "
        "title does not cover a different title, and an existing location does not cover a new one.\n"
        "RULES:\n"
        "- Only what the text EXPLICITLY establishes.\n"
        "- durum_bilgisi (epistemic status) definitions:\n" + tanim +
        "  Do not downgrade explicit facts to create variety; but mark non-confirmed knowledge when the "
        "text really contains belief, rumor, uncertainty or deception. What one named character privately "
        "knows/believes ('X knows Y', 'X believes Y') is out of scope.\n"
        "- gecerli_baslangic / gecerli_bitis: story-time chapter numbers ONLY if the text explicitly "
        "establishes them; otherwise null. Never guess.\n"
        "- state_changes.anahtar must be one of the allowed keys; life_status value must be one of "
        + ", ".join(LIFE_STATUS) + ". Location is NOT a state: use relationship bulundugu_yer, only for a "
        "real named place. Never invent other state keys.\n"
        "- LIFE STATUS: explicit statements such as 'X, who was now dead', 'X died', 'X was killed', "
        "'X is still alive', 'X survived' establish life_status for the NAMED entity X. Appeared/moved/spoke/"
        "present alone do NOT establish alive; uncertainty/negation must be respected. Never transfer a "
        "death to another entity: a parasite, rider, weapon, summon, shadow or part being destroyed or cut "
        "apart does NOT make its host/owner dead, and a crumbling or collapsing body is not an explicit "
        "death statement for the host. oldurdu requires explicit kill/death evidence; stabbing, attacking, "
        "wounding or defeating is insufficient.\n"
        "- TEACHER/STUDENT: check 'X taught Y', 'X trained Y', 'Y learned from X', 'X was Y's teacher', "
        "'X mentored Y', and past lessons mentioned in passing ('since X had taught him to ...'). Storage "
        "direction is student --ogretmeni--> teacher: 'Ayla taught Boran swordsmanship.' => Boran ogretmeni "
        "Ayla. NEVER output the reverse. If the edge is not in KNOWN THROUGH N-1, it is new knowledge even "
        "when mentioned as background.\n"
        "- IDENTITY / NAMES: keep these distinct. ORDINARY NAME = a person's normal name (the canonical "
        "glossary name). TITLE (unvani) = an epithet/honorific/rank-like designation borne by a named entity. "
        "ALIAS (takma_adi) = another name/nickname for the same entity. TRUE NAME (gercek_adi) = the magical "
        "True Name of the setting's system; require the words 'True Name' (or an equally explicit magical "
        "True Name statement). 'real name', 'actual name', 'was called' or 'named' alone NEVER establish "
        "gercek_adi. IDENTITY REVELATION = the READER learns two previously SEPARATE identities are the same "
        "entity; a character recognizing someone, or learning a title/name, is NOT one. Patterns: 'X, the Y' "
        "/ 'X — the Y' (title Y for X); 'the Y was actually called X' / 'the Y ... becoming known as X' "
        "(X's title is Y — prefer unvani with ozne = named person X, nesne = the title Y; NOT an identity "
        "revelation, NOT an identity merge); 'X was known as Y' (alias or title, decide by whether Y is a "
        "name or an epithet). Prefer ONE specific representation per fact; do not add redundant identity "
        "reviews. new_aliases.tur: takma_adi | unvani | gercek_adi.\n"
        "- TRANSFER / ENTRUSTMENT (representation gap): 'X gave Y to Z', 'X entrusted Y to Z', 'Y was given "
        "to Z', 'X handed Y over to Z', 'Y now belongs to Z'. Identify previous_holder, transferred_entity, "
        "new_holder. Transfer is NOT automatically friendship/group membership/Memory ownership/Shadow "
        "mastership. golgesi means master -> Shadow, not generic custody. No generic transfer/custody "
        "relation exists, so report review_items kategori=relation_capability_gap, ozne=new_holder, "
        "nesne=transferred_entity (no iliski), aciklama='MISSING_RELATION_CAPABILITY: transfer/entrustment "
        "requires human representation decision', bounded verbatim kanit containing both names, onem=medium. "
        "Never emit a false ownership triple. Use relation_capability_gap for any graph-worthy fact the "
        "vocabulary cannot represent instead of silently dropping it or forcing a wrong triple.\n"
        "- COLLECTIVE BELIEF: 'Some people believed X', 'it was widely believed that X', 'people thought X', "
        "'according to common belief X', 'it was generally assumed that X' are graph-worthy and are believed "
        "(or rumor when hearsay), NEVER confirmed. Example: 'People believed the Glass Tower had stood in the "
        "Hollow.' => Glass Tower bulundugu_yer Hollow, believed, gecerli_baslangic=null, gecerli_bitis=null. "
        "If the two names are in adjacent sentences, quote both as ONE contiguous span. Never delete an "
        "earlier claim when later disproven.\n"
        "- RELATIONSHIP RUPTURE: if an EXISTING companion/friend relation in KNOWN is explicitly challenged "
        "by confessed betrayal, broken trust or permanent separation, emit a relationship_conflict REVIEW "
        "(ozne, iliski=yoldasi, nesne, kanit, onem); never auto-close and never invent a betrayal relation. "
        "Example: 'Lina ... admitted: I betrayed you ... Orion ... I cannot forgive it.' with KNOWN Orion "
        "yoldasi Lina => review. Argument/disagreement/anger alone is insufficient. Without reliable "
        "evidence leave existing relations alone.\n"
        "- STRUCTURED REVIEW CONTRACT: kategori, ozne, iliski, nesne, kanit, onem are REQUIRED for "
        "relationship_conflict; aciklama is OPTIONAL and is NOT evidence. ozne/nesne are ONLY exact canonical "
        "entity names, never prose. A relationship_conflict triple MUST refer to an existing KNOWN THROUGH "
        "N-1 edge. Example: {\"kategori\":\"relationship_conflict\",\"ozne\":\"Orion\",\"iliski\":\"yoldasi\","
        "\"nesne\":\"Lina\",\"kanit\":\"Lina admitted betraying Orion. Orion told Lina he could not forgive "
        "her.\",\"onem\":\"medium\"}. review_items are graph issues with verified evidence, not event "
        "summaries, motives, atmosphere or moods. Unsupported reviews must be omitted.\n"
        "- state_changes must name the actual subject and establish the actual value; a bounded verbatim span "
        "of up to 1400 characters may be used when needed, never fabricated.\n"
        "- A named thing not in the glossary goes to new_entities (it is not created automatically).\n"
        "- Use ONLY the controlled relation vocabulary below; never invent a relation.\n"
        "- Relationship types (subject -> object):\n" + iliski
        + "\nOUTPUT CONTRACT (objects with named fields, never positional arrays):\n"
        + json.dumps(yanit_semasi(), ensure_ascii=False)
    )


CIKARICI_TALIMATI = _talimat()


def istem_kur(baglam: dict, kaynak: str) -> str:
    bilgi = "\n".join(baglam["satirlar"]) or "(none)"
    run = "\n".join(baglam.get("run_satirlari") or []) or "(none)"
    return (f"CHAPTER {baglam['bolum']}\n\nKNOWN THROUGH {baglam['bilgi_siniri']}:\n{bilgi}\n\n"
            f"{AYNI_BOLUM_BASLIGI} (CHAPTER {baglam['bolum']}):\n{run}\n\n"
            f"{kapsama_ipuclari.ipucu_bolumu(baglam.get('ipuclari') or [])}\n\n"
            f"THIS CHAPTER'S TEXT (English):\n{kaynak}")


# ---------------------------------------------------------------------------
# SINIFLANDIRMA + İŞLEME
# ---------------------------------------------------------------------------
def _cumle_havuzu(bolum: int, kaynak: str) -> list[tuple]:
    cumleler = re.split(r"(?<=[.!?…])\s+|\n+", kaynak)
    return [(bolum, c.strip(), varlik_cikarim._normal(c)) for c in cumleler if len(c.strip()) >= 8]


def _anahtar(a, iliski, b) -> str:
    return f"{a}|{iliski}|{b}"


# BASTIRMA SINIFLARI (v5 denetimi). Doğrulayıcının bir öneriyi "zaten var" diye atladığı
# HER yol bu üç sınıftan birine girer. COMPLEMENTARY_KNOWLEDGE ASLA bastırılmaz: ilişki
# (X oldurdu Y) ile durum (Y.life_status = dead) farklı sorguların cevabıdır.
EXACT_DUPLICATE = "EXACT_DUPLICATE"            # aynı bilgi, aynı temsil
SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"      # aynı bilgi, eşdeğer temsil (alias/simetri/rün eşleşmesi)
COMPLEMENTARY_KNOWLEDGE = "COMPLEMENTARY_KNOWLEDGE"


def bastirma_sinifi(oneri: tuple, mevcut: tuple) -> str:
    """İki temsil arasındaki ilişki. Temsil: ("bag", ozne_k, iliski, nesne_k) ya da
    ("deger", varlik_k, anahtar, deger). Kimlikler çağıranda kanonikleştirilmiş olmalıdır
    (alias -> asıl, simetrik ilişki sıralı). Farklı TÜR (bağ vs değer) daima tamamlayıcıdır."""
    if oneri == mevcut:
        return EXACT_DUPLICATE
    if oneri[0] != mevcut[0]:
        return COMPLEMENTARY_KNOWLEDGE
    if oneri[0] == "bag" and oneri[2] == mevcut[2] and             varlik_grafigi.ILISKILER.get(oneri[2], {}).get("simetrik") and             {oneri[1], oneri[3]} == {mevcut[1], mevcut[3]}:
        return SEMANTIC_DUPLICATE
    return COMPLEMENTARY_KNOWLEDGE


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
              for b in varlik_grafigi.baglar(book_slug, en_cok_bolum=bolum,
                                            durumlar=("aday", "onaylandi", "reddedildi"))}
    oneriler, inceleme = [], []
    # Yalnız N'ye kadar bilinen KESİN alias'lar; gelecekte öğrenilen kimlik yok.
    asil = {b["hedef_kimlik"]: b["kaynak_kimlik"] for b in mevcut.values()
            if b["iliski"] in ("takma_adi", "gercek_adi") and b["durum"] == "onaylandi" and (b["ilk_bolum"] or 0) < bolum}
    profil = varlik_grafigi.profil(book_slug) or {}
    det = canonical_plan(book_slug, kaynak, cozucu)
    yazimlar = {k: list(v["yazimlar"]) for k, v in glossary.ekler(book_slug).items()}
    hedefler = {}
    for row in cozucu.satirlar.values():
        hedefler.setdefault(glossary.fold_term(row["target"]), []).append(row["source"])

    def kaynak_adi(ad):
        resolved = cozucu.coz(ad)
        if resolved:
            return cozucu.kaynak(resolved)
        names = hedefler.get(glossary.fold_term(ad), [])
        # Model bazen VARLIK satırının Türkçe karşılığını kullanıyor. Yalnız
        # mevcut sözlüğün tekil hedef eşlemesi; kimlik çıkarımı/birleştirme yok.
        return names[0] if len(names) == 1 else ad
    for b in mevcut.values():
        if b["iliski"] in ("takma_adi", "gercek_adi") and b["durum"] == "onaylandi" and (b["ilk_bolum"] or 0) < bolum:
            yazimlar.setdefault(b["kaynak"], []).append(b["hedef"])
    sayac = {"already_known_proposals": 0, "deterministic_same_chapter_duplicates": 0,
             "same_chapter_existing_proposals": 0, "unsupported_state_keys": 0, "new_entity_candidates": 0,
             "direction_errors": 0, "high_impact_evidence_failures": 0, "unsupported_review_items": 0}

    def aday(ad, x):
        if not any(i[0] == "new_entity_candidate" and i[3].get("ad") == ad for i in inceleme):
            inceleme.append(("new_entity_candidate", "low", f"Sözlükte olmayan ad: {ad}",
                             {"ad": ad, "oneri": x, "kanit": x.get("kanit")}))
            sayac["new_entity_candidates"] += 1

    def tekrar(var, x, tur, cozulmus):
        if var and var["durum"] == "onaylandi" and var.get("aktif", True):
            if var["ilk_bolum"] is not None and var["ilk_bolum"] < bolum:
                metrik = "already_known_proposals"
                sebep = "zaten var"
            elif var["ilk_bolum"] == bolum and var["origin"] == "sistem":
                metrik = "deterministic_same_chapter_duplicates"
                sebep = "aynı bölüm deterministik"
            elif var["ilk_bolum"] == bolum:
                metrik = "same_chapter_existing_proposals"
                sebep = "aynı bölüm eski grafik"
            else:
                return False
            # Yeni epistemik/zamansal iddia tekrar değildir; kanıt denetimine gider.
            ayni_durum = x.get("durum_bilgisi") in (None, var.get("durum_bilgisi")) or (
                var.get("durum_bilgisi") is None and x.get("durum_bilgisi") == "confirmed")
            if not ayni_durum or any(
                x.get(a) is not None and x[a] != var.get(a) for a in ("gecerli_baslangic", "gecerli_bitis")
            ):
                return False
            sayac[metrik] += 1
            ayni_ad = (var["kaynak"], var["hedef"]) == (x["ozne"], x["nesne"])
            oneriler.append({"tur": tur, "sinif": "ALREADY_EXISTS", "karar": "atla:" + sebep,
                             "bastirma": EXACT_DUPLICATE if ayni_ad else SEMANTIC_DUPLICATE,
                             "veri": {**x, **cozulmus}})
            return True
        return False

    ham = [dict(x, kaynak_tur="new_relationships") for x in veri.get("new_relationships", [])]
    ham += [{"ozne": x["asil"], "iliski": x["tur"], "nesne": x["ad"], "kanit": x["kanit"],
             "durum_bilgisi": x.get("durum_bilgisi"), "guven": x.get("guven", 0.9), "kaynak_tur": "new_aliases"}
            for x in veri.get("new_aliases", [])]
    for x in ham:
        x.setdefault("guven", 0.9)
    yeni = []
    gorulen_delta = set()
    for x in ham:
        x = {**x, "ozne": varlik_cikarim.ad_temizle(x["ozne"]),
             "nesne": varlik_cikarim.ad_temizle(x["nesne"])}
        x = {**x, "ozne": kaynak_adi(x["ozne"]), "nesne": kaynak_adi(x["nesne"])}
        # "[title] ... becoming known as [name]": sıradan ad ilişkisi eklemek
        # yerine mevcut unvani taşıyıcı→unvan biçimi. Kişiye özgü lore yok.
        if x["iliski"] == "takma_adi" and re.match(r"^(?:Demon|Prince|Lord|King|Queen|Goddess|God) of\b", x["ozne"]) and re.search(r"(?:becoming|became) known as", x["kanit"], re.I):
            x = {**x, "ozne": x["nesne"], "nesne": x["ozne"], "iliski": "unvani"}
        x = varlik_cikarim.duzen_iliskisini_duzelt(x, profil.get("diziler", {}), profil.get("ek_rutbeler", ()))
        delta_key = (x["ozne"], x["iliski"], x["nesne"], x.get("durum_bilgisi"), x.get("gecerli_baslangic"), x.get("gecerli_bitis"))
        if delta_key in gorulen_delta:
            sayac["same_delta_duplicates"] = sayac.get("same_delta_duplicates", 0) + 1
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "ALREADY_EXISTS", "karar": "atla:aynı delta tekrarı",
                             "bastirma": EXACT_DUPLICATE, "veri": x})
            continue
        gorulen_delta.add(delta_key)
        a, n = varlik_grafigi.anlam_sec(book_slug, cozucu.coz(x["ozne"]), x["iliski"], cozucu.coz(x["nesne"]))
        a = asil.get(a, a)
        if x["iliski"] not in KIMLIK_ILISKILERI:
            n = asil.get(n, n)
        if a and n and varlik_grafigi.ILISKILER[x["iliski"]].get("simetrik") and a > n:
            a, n = n, a
        # v8: aday doğrulayıcısından geçmiş öğe (span kimlikli kanıt + risk katmanı) yeniden
        # regex'le ayrıştırılmaz; burada yalnız kopya/çelişki/grafik sınıflaması yapılır.
        preliminary, preliminary_reason = (("verified", "aday_dogrulandi") if x.get("_dogrulandi")
                                           else bilgi_kanit.semantik_sonuc(x, yazimlar, det, kaynak))
        if preliminary_reason in ("direction_reversed", "ordinary_name_is_not_true_name", "high_impact_evidence_missing"):
            sayac["direction_errors"] += preliminary_reason == "direction_reversed"
            sayac["high_impact_evidence_failures"] += preliminary_reason == "high_impact_evidence_missing"
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:" + preliminary_reason, "veri": x})
            continue
        if tekrar(mevcut.get((a, x["iliski"], n)), x, x["kaynak_tur"],
                  {"ozne_kimlik": a, "nesne_kimlik": n}):
            continue
        semantic, reason = (("verified", "aday_dogrulandi") if x.get("_dogrulandi")
                            else bilgi_kanit.semantik_sonuc(x, yazimlar, det, kaynak))
        epi = None if x.get("_dogrulandi") else bilgi_kanit.epistemik_kontrol(x["kanit"], x.get("durum_bilgisi"))
        if not bilgi_kanit.span_gecerli(x["kanit"], kaynak) or semantic == "wrong" or epi:
            sayac["direction_errors"] += reason == "direction_reversed"
            sayac["high_impact_evidence_failures"] += varlik_grafigi.ILISKILER[x["iliski"]]["requires_strong_evidence"]
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:" + (epi or reason), "veri": x})
            continue
        if semantic == "unknown":
            if reason == "MISSING_RELATION_CAPABILITY":
                inceleme.append(("relation_capability_gap", "medium", f"MISSING_RELATION_CAPABILITY: {x['nesne']} öğesinin {x['ozne']} tarafına teslim/emanet devri; master/ownership bağı kurulmadı. İnsan temsil kararı gerekli.", {"new_holder":x['ozne'],"transferred_entity":x['nesne'],"kanit":x['kanit'],"capability_gap":True}))
            # Unresolved new-edge roles remain NEEDS_REVIEW proposals, but are
            # not labelled existing-edge conflicts when no prior edge exists.
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "NEEDS_REVIEW", "karar": "inceleme:yön doğrulanamadı", "veri": x})
            continue
        if reason == "system_block":
            sayac["deterministic_same_chapter_duplicates"] += 1
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "ALREADY_EXISTS", "karar": "atla:aynı bölüm deterministik plan",
                             "bastirma": EXACT_DUPLICATE, "veri": x})
            continue
        if not a or not n:
            for ad, k in ((x["ozne"], a), (x["nesne"], n)):
                if not k:
                    aday(ad, x)
            oneriler.append({"tur": x["kaynak_tur"], "sinif": "NEEDS_REVIEW",
                             "karar": "inceleme:yeni varlık adayı", "veri": x})
            continue
        yeni.append(x)
    # V3'in kaynak/rol/epistemik kapıları yukarıda geçti. Genel çıkarıcının
    # varsayım reddi confirmed dışı okur bilgisini silmemeli; yapı kuralları aynı.
    gecerli, red = [], []
    sistem = {}
    for b in mevcut.values():
        if b["origin"] == "sistem":
            sistem.setdefault((b["kaynak_kimlik"], b["hedef_kimlik"]), set()).add(b["iliski"])
    for x in yeni:
        a, n = varlik_grafigi.anlam_sec(book_slug, cozucu.coz(x["ozne"]), x["iliski"], cozucu.coz(x["nesne"]))
        a = asil.get(a, a)
        if x["iliski"] not in KIMLIK_ILISKILERI:
            n = asil.get(n, n)
        reason = varlik_cikarim.yapisal_red(x, a, n, kategoriler, sistem)
        (red if reason else gecerli).append({**x, "ozne_kimlik": a, "nesne_kimlik": n, "bolum": bolum, "sebep": reason})
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
                epistemik_yeni = g.get("durum_bilgisi") not in (None, var.get("durum_bilgisi")) and not (var.get("durum_bilgisi") is None and g.get("durum_bilgisi") == "confirmed")
                if epistemik_yeni and var["origin"] in ("manual", "sistem"):
                    sinif, karar = "CONFLICTS_WITH_EXISTING", "inceleme"
                    inceleme.append(("epistemic_conflict", "medium", f"Yeni epistemik iddia: {g['ozne']} {g['iliski']} {g['nesne']} ({g['durum_bilgisi']})", g))
                else:
                    sinif = "SUPPORTS_EXISTING" if var["durum"] == "aday" or epistemik_yeni else "ALREADY_EXISTS"
                    karar = "işle" if sinif == "SUPPORTS_EXISTING" else "atla:zaten var"
            else:
                sinif, karar = "UPDATES_EXISTING", "işle"  # daha erken kanıt: ilk_bolum küçülür
        elif varlik_grafigi.ILISKILER[g["iliski"]].get("tekil"):
            eski = [b for (ka, il, _h), b in mevcut.items()
                    if ka == a and il == g["iliski"] and b["durum"] != "reddedildi"
                    and (b["ilk_bolum"] or 0) <= bolum]
            if eski:
                sinif = "UPDATES_EXISTING"
        if g.get("kaynak_tur") == "new_aliases" and g["iliski"] == "takma_adi" and sinif == "NEW":
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
                         **({"bastirma": EXACT_DUPLICATE} if karar == "atla:zaten var" else {}),
                         "veri": {**g, "ozne_kimlik": a, "nesne_kimlik": n}})

    for x in veri.get("relationship_updates", []):
        if not bilgi_kanit.span_gecerli(x["kanit"], kaynak) or not bilgi_kanit.isaretle(x["kanit"], x["ozne"], x["nesne"], yazimlar) or not re.search(r"no longer|not anymore|ceased|ended|broken|disproven|false|wrong|betray|never", x["kanit"], re.I):
            oneriler.append({"tur": "relationship_updates", "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:bağ değişimi kurulmadı", "veri": x})
            continue
        a, n = cozucu.coz(x["ozne"]), cozucu.coz(x["nesne"])
        if not a or not n:
            for ad, k in ((x["ozne"], a), (x["nesne"], n)):
                if not k:
                    aday(ad, x)
            oneriler.append({"tur": "relationship_updates", "sinif": "NEEDS_REVIEW",
                             "karar": "inceleme:yeni varlık adayı", "veri": x})
            continue
        var = mevcut.get((a, x["iliski"], n))
        if var is None and varlik_grafigi.ILISKILER[x["iliski"]].get("simetrik"):
            var = mevcut.get((n, x["iliski"], a))
        kanitli = bilgi_kanit.span_gecerli(x['kanit'], kaynak)
        if var is None or not kanitli or (var["ilk_bolum"] or 0) > bolum:
            oneriler.append({"tur": "relationship_updates", "sinif": "NEEDS_REVIEW",
                             "karar": "reddedildi:bağ yok ya da kanıt bu bölümde değil", "veri": x})
            continue
        if x['iliski']=='yoldasi':
            if bilgi_kanit.review_span_gecerli(x['kanit'],kaynak) and bilgi_kanit.rupture_kaniti(x['kanit'],x['ozne'],x['nesne'],yazimlar):
                inceleme.append(('relationship_conflict','medium',f"Mevcut yoldaşlık: {x['ozne']} ↔ {x['nesne']}. İnsan kararı: açık bozulma kanıtı nedeniyle ilişki bu bölümde bitmeli mi? Otomatik kapanış yok.",{'ozne':x['ozne'],'iliski':'yoldasi','nesne':x['nesne'],'kanit':x['kanit'],'auto_close':False}))
                oneriler.append({'tur':'relationship_updates','sinif':'NEEDS_REVIEW','karar':'inceleme:otomatik yoldaşlık kapanışı yok','veri':x})
            else:
                oneriler.append({'tur':'relationship_updates','sinif':'NEEDS_REVIEW','karar':'reddedildi:kanıt:ilişki kopuşu kurulmadı','veri':x})
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
        if x["anahtar"] not in DURUM_ANAHTARLARI:
            sayac["unsupported_state_keys"] += 1
            oneriler.append({"tur": "state_changes", "sinif": "NEEDS_REVIEW",
                             "karar": "reddedildi:unsupported_state_key", "veri": x})
            continue
        x = {**x, "makine_anahtari": x["anahtar"], "anahtar": DURUM_ANAHTARLARI[x["anahtar"]]}
        x["varlik"] = kaynak_adi(x["varlik"])
        k = cozucu.coz(x["varlik"])
        k = asil.get(k, k)
        durumlar = (varlik_grafigi.degerler(book_slug, bolum, k).get(k) or {}) if k else {}
        onceki = durumlar.get(x["anahtar"])
        if onceki and onceki["deger"] == x["deger"] and onceki["durum_bilgisi"] == x.get("durum_bilgisi"):
            if onceki["ilk_bolum"] < bolum:
                sayac["already_known_proposals"] += 1
                sebep = "zaten var"
            else:
                c = varlik_grafigi._connect()
                try:
                    run = c.execute("SELECT 1 FROM varlik_deger WHERE book_slug=? AND kimlik=? AND anahtar=? "
                                    "AND ilk_bolum=? AND origin='sistem'", (book_slug, k, x["anahtar"], bolum)).fetchone()
                finally:
                    c.close()
                sebep = "aynı bölüm deterministik" if run else "zaten var"
                if run:
                    sayac["deterministic_same_chapter_duplicates"] += 1
                else:
                    sayac["same_chapter_existing_proposals"] += 1
            oneriler.append({"tur": "state_changes", "sinif": "ALREADY_EXISTS", "karar": "atla:" + sebep,
                             "bastirma": EXACT_DUPLICATE, "veri": {**x, "kimlik": k}})
            continue
        valid, reason = ((True, "aday_dogrulandi") if x.get("_dogrulandi")
                         else bilgi_kanit.state_kaniti(x, kaynak, yazimlar, det))
        if not valid:
            sayac["high_impact_evidence_failures"] += x["makine_anahtari"] == "life_status" and x["deger"] == "dead"
            oneriler.append({"tur": "state_changes", "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:" + reason, "veri": x})
            continue
        if reason == "system_block":
            sayac["deterministic_same_chapter_duplicates"] += 1
            oneriler.append({"tur": "state_changes", "sinif": "ALREADY_EXISTS", "karar": "atla:aynı bölüm deterministik plan",
                             "bastirma": EXACT_DUPLICATE, "veri": x})
            continue
        if not k:
            aday(x["varlik"], x)
            oneriler.append({"tur": "state_changes", "sinif": "NEEDS_REVIEW",
                             "karar": "inceleme:yeni varlık adayı", "veri": x})
            continue
        kanitli = bilgi_kanit.span_gecerli(x['kanit'], kaynak)
        if not k or not kanitli:
            oneriler.append({"tur": "state_changes", "sinif": "NEEDS_REVIEW",
                             "karar": "reddedildi:varlık sözlükte yok ya da kanıt bu bölümde değil", "veri": x})
            continue
        sinif = "NEW" if onceki is None else "UPDATES_EXISTING"
        oneriler.append({"tur": "state_changes", "sinif": sinif,
                         "karar": "atla:zaten var" if sinif == "ALREADY_EXISTS" else "işle",
                         "veri": {**x, "kimlik": k}})

    for x in veri.get("identity_revelations", []):
        represented = any({x["ad_1"], x["ad_2"]} == {a["asil"], a["ad"]} for a in veri.get("new_aliases", []))
        marker = bilgi_kanit.isaretle(x["kanit"], x["ad_1"], x["ad_2"], yazimlar)
        if represented or not bilgi_kanit.span_gecerli(x["kanit"], kaynak) or not marker or not re.search(r"actually|turned out|one and the same|true identity", marker) or re.search(r"called|named|known as", marker):
            sayac["unsupported_review_items"] += 1
            oneriler.append({"tur": "identity_revelations", "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:kimlik açığa çıkması kurulmadı veya zaten temsil edildi", "veri": x})
            continue
        inceleme.append(("identity_merge", "critical",
                         f"Kimlik açığa çıkması önerisi (b{bolum}): {x['ad_1']} = {x['ad_2']}",
                         {"ad_1": x["ad_1"], "ad_2": x["ad_2"], "kanit": x["kanit"], "aciklama": x.get("aciklama")}))
        oneriler.append({"tur": "identity_revelations", "sinif": "NEEDS_REVIEW", "karar": "inceleme", "veri": x})
    for x in veri.get("contradictions", []):
        if all(x.get(k) for k in ("ozne", "iliski", "nesne")) and bilgi_kanit.span_gecerli(x["kanit"], kaynak) and bilgi_kanit.isaretle(x["kanit"], x["ozne"], x["nesne"], yazimlar) and re.search(r"\b(?:not|never|false|wrong|disproven)\b|no longer|in fact", x["kanit"], re.I):
            inceleme.append(("epistemic_conflict", "medium", f"Çelişki adayı: {x['ozne']} {x['iliski']} {x['nesne']}", x))
        else:
            sayac["unsupported_review_items"] += 1
    for x in veri.get("new_entities", []):
        if not bilgi_kanit.span_gecerli(x["kanit"], kaynak) or not varlik_cikarim._gecer_mi(x["ad"], [], x["kanit"]):
            oneriler.append({"tur": "new_entities", "sinif": "NEEDS_REVIEW", "karar": "reddedildi:kanıt:yeni ad kaynakta kurulmadı", "veri": x})
            sayac["unsupported_review_items"] += 1
            continue
        if not cozucu.coz(x["ad"]):
            aday(x["ad"], x)
        oneriler.append({"tur": "new_entities", "sinif": "NEEDS_REVIEW", "karar": "inceleme", "veri": x})
    for x in veri.get("review_items", []):
        x={**x,'ozne':kaynak_adi(x.get('ozne','')),'nesne':kaynak_adi(x.get('nesne',''))}
        if x.get('kategori')=='relation_capability_gap':
            if bilgi_kanit.review_span_gecerli(x.get('kanit',''),kaynak) and cozucu.coz(x['ozne']) and cozucu.coz(x['nesne']) and bilgi_kanit.transfer_kaniti(x['kanit'],x['ozne'],x['nesne'],yazimlar):
                inceleme.append(('relation_capability_gap','medium',f"MISSING_RELATION_CAPABILITY: {x['nesne']} öğesinin {x['ozne']} tarafına teslim/emanet devri; mevcut graph'ta genel transfer/custody temsili yok. Mastership veya yeni ilişki yazımı önerilmedi.",{'new_holder':x['ozne'],'transferred_entity':x['nesne'],'kanit':x['kanit'],'capability_gap':True}))
            else:
                sayac['unsupported_review_items']+=1
            continue
        if all(x.get(k) for k in ("kanit", "ozne", "iliski", "nesne")) and bilgi_kanit.review_span_gecerli(x["kanit"], kaynak) and cozucu.coz(x['ozne']) and cozucu.coz(x['nesne']) and bilgi_kanit.isaretle(x["kanit"], x["ozne"], x["nesne"], yazimlar) and x["kategori"] in ("relationship_conflict", "temporal_conflict", "epistemic_conflict"):
            if x.get('aciklama','').startswith('MISSING_RELATION_CAPABILITY'):
                sayac['unsupported_review_items'] += 1
                continue
            a, n = cozucu.coz(x['ozne']), cozucu.coz(x['nesne'])
            existing = mevcut.get((a,x['iliski'],n))
            if not existing and varlik_grafigi.ILISKILER[x['iliski']].get('simetrik'):
                existing=mevcut.get((n,x['iliski'],a))
            if x['kategori']=='relationship_conflict' and not(existing and (existing['ilk_bolum'] or 0)<bolum and existing.get('aktif',True)):
                sayac['unsupported_review_items']+=1
                continue
            if x['iliski']=='yoldasi' and existing and (existing['ilk_bolum'] or 0)<bolum and existing.get('aktif',True) and bilgi_kanit.rupture_kaniti(x['kanit'],x['ozne'],x['nesne'],yazimlar):
                inceleme.append(('relationship_conflict','medium',f"Mevcut yoldaşlık: {x['ozne']} ↔ {x['nesne']}. Kanıt ilişkiyle çelişen açık ihanet/güven kırılması içeriyor. İnsan kararı: ilişki bu bölümde bitmeli mi? Otomatik kapanış yok.",{'ozne':x['ozne'],'iliski':'yoldasi','nesne':x['nesne'],'kanit':x['kanit'],'existing_first_chapter':existing['ilk_bolum'],'auto_close':False}))
                continue
            if x['kategori']=='relationship_conflict' and x['iliski']=='yoldasi':
                sayac['unsupported_review_items'] += 1
                continue
            status, reason = bilgi_kanit.semantik_sonuc(x, yazimlar, det)
            change = re.search(r"friendship.{0,30}(?:broken|ended|over)|betray|no longer|ceased|disproven|false", x["kanit"], re.I)
            if x['kategori']=='relationship_conflict' and not change:
                sayac['unsupported_review_items']+=1
                continue
            if status == "verified" or change:
                inceleme.append((x["kategori"], x.get("onem") or "medium", f"Grafik incelemesi: {x['ozne']} {x['iliski']} {x['nesne']}", {k: x[k] for k in ("ozne", "iliski", "nesne", "kanit")}))
                continue
        sayac["unsupported_review_items"] += 1
    return {"oneriler": oneriler, "inceleme": inceleme, "sayac": sayac,
            "deterministik_plan": det, "deterministik_kaynak": kaynak}


def delta_isle(book_slug: str, bolum: int, degerlendirme: dict, model: str) -> dict:
    """Değerlendirilmiş deltayı grafiğe İŞLE — yalnız `bag_ekle` / `deger_yaz` /
    `iddiayi_curut` üzerinden. Model önerisi daima `aday` (incelenmemiş) girer; elle/rün
    bağına dokunulmaz (bag_ekle'nin köken önceliği). Döner: sayaçlar."""
    cikarim = cikarim_kimligi(model)
    sayac = {s: 0 for s in SINIFLAR} | {"yazilan_bag": 0, "yazilan_deger": 0, "kapanan": 0, "inceleme": 0}
    # Simulation bunu çağırmaz. Gerçek işleme yetkilendirildiğinde modelden
    # bastırılan rün planı mevcut Faz 1 yazma yoluyla gerçekten uygulanır.
    if degerlendirme.get("deterministik_kaynak"):
        sayac["deterministik_yazilan"] = varlik_grafigi.bolumden_sistem_baglari(
            book_slug, bolum, degerlendirme["deterministik_kaynak"])
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


def _hata_sinifi(exc: Exception) -> str:
    """Yedek zincirinin sardığı ASIL HTTP/SDK hatasını kaybetmeden teşhis et."""
    zincir, gorulen = exc, set()
    while zincir is not None and id(zincir) not in gorulen:
        gorulen.add(id(zincir))
        if isinstance(zincir, SaglayiciHatasi):
            return "provider_policy_violation"
        if getattr(zincir, "asil_kod", None) == 400 or getattr(zincir, "code", None) == 400:
            return "api_schema_incompatibility"
        if isinstance(zincir, (TypeError, ValueError)) or type(zincir).__name__ == "ValidationError":
            return "schema_design_error"
        zincir = zincir.__cause__ or zincir.__context__
    return "model_api_failure"


def bolum_degerlendir(book_slug: str, bolum: int, model: str, cagri=None) -> dict:
    """DOĞRULAMA kipi: model çağrılır, delta doğrulanır ve SINIFLANIR ama grafiğe,
    kuyruğa, işleme durumuna HİÇBİR ŞEY YAZILMAZ ve baş ilerlemez. Bağlam yine N-1
    süzgeçli: doğrulama seti bölümleri (kronolojik olmayan seçim) gelecek görmez.
    Döner: girdi bilgisi, model deltası, doğrulayıcı kararları, planlanan mutasyon."""
    if cagri is None:
        saglayici_dogrula(model)  # Vertex dışı model: sessiz 'failed' değil, açık hata
    kaynak = kaynak_metin(book_slug, bolum)
    if not kaynak:
        return {"bolum": bolum, "durum": "failed", "hata": "kaynak metin yok"}
    baglam = baglam_kur(book_slug, bolum, kaynak)
    istem = istem_kur(baglam, kaynak)
    try:
        metin, kullanim = (cagri or _model_cagir(model))(istem, CIKARICI_TALIMATI)
    except Exception as exc:
        # Tekrar öncesi teşhis; doğrulama kipi hiçbir işleme/review kaydı yazmaz.
        neden = _hata_sinifi(exc)
        return {"bolum": bolum, "durum": "failed", "hata": f"{type(exc).__name__}: {exc}",
                "hata_sinifi": neden, "sema_hatalari": [], "girdi_bilgisi": baglam["satirlar"]}
    veri = varlik_cikarim_ayristir(metin)
    hatalar = sema_dogrula(veri) if veri is not None else ["yanıt JSON değil"]
    degerlendirme = delta_degerlendir(book_slug, bolum, veri, kaynak) if not hatalar else None
    return {"bolum": bolum, "durum": "dogrulama", "girdi_bilgisi": baglam["satirlar"],
            "deterministik_bilgi": baglam["run_satirlari"],
            "hata_sinifi": "model_output_failure" if hatalar else None,
            "surumler": {"cikarici": CIKARICI_SURUMU, "istem": ISTEM_SURUMU, "sema": SEMA_SURUMU},
            "saglayici": CIKARICI_SAGLAYICI if cagri is None else "enjekte", "model": model,
            "olcum": {"kaynak_tokeni": baglam["kaynak_tokeni"], "baglam_tokeni": baglam["baglam_tokeni"],
                      "run_tokeni": baglam["run_tokeni"],
                      "kesilen_satir": baglam["kesilen_satir"], "aday_satir": baglam["aday_satir"],
                      "giren_satir": len(baglam["satirlar"]) + len(baglam["run_satirlari"]),
                      "ipucu_sayisi": len(baglam.get("ipuclari") or []), "ipucu_tokeni": baglam.get("ipucu_tokeni"),
                      "talimat_tokeni": _tok(CIKARICI_TALIMATI),
                      "sinif": baglam["sinif"], **(kullanim or {})},
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
    if not kuru and cagri is None:
        saglayici_dogrula(model)
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


def saglayici_dogrula(model: str) -> str:
    """Bilgi çıkarımı YALNIZ tanımlı bir Vertex modeliyle. Tanınmayan `vertex/...` adı da
    reddedilir: çeviri yolu onu Gemini ANAHTAR havuzuna (ücretsiz kota) yönlendirirdi."""
    if not translate._vertex_modeli(model):
        raise SaglayiciHatasi(f"bilgi çıkarımı yalnız Vertex: {model!r} reddedildi")
    return CIKARICI_SAGLAYICI


def _model_cagir(model: str):
    saglayici = saglayici_dogrula(model)

    def cagir(user: str, system: str):
        # Zincir TEK halkadır: Vertex düşerse başka model/sağlayıcıya inilmez; geçici
        # hatada `_tek_anahtarla_uret`in mevcut sınırlı geri-çekilmesi geçerlidir.
        with translate.yanit_semasi(yanit_semasi()):
            yanit, fiili = translate._generate_with_fallback(
                translate._gemini_fabrikasi(""), (model,), user, system=system, max_tokens=translate.MAX_OUTPUT_TOKENS,
            )
        if fiili != model:
            raise SaglayiciHatasi(f"beklenen {model}, yanıtlayan {fiili}")
        meta = getattr(yanit, "usage_metadata", None)
        kullanim = {"fiili_model": fiili, "saglayici": saglayici}
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
