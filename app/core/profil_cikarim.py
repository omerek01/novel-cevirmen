"""Yeni kitapta otomatik kitap profili + sözlük ön taraması (2026-10-16, plan Faz 3: soğuk başlangıç).

Kitaba özel bilgi Faz 1'de veriye taşındı (`kitap_profili`), ama yeni bir kitapta profil boştu:
rütbe, sistem sesi, kategori ve Gerçek Ad katmanları kullanıcı elle yazana kadar kapalı kalıyordu.
Bu modül kitabın İLK bölümlerinden profil ADAYLARI çıkarır (TransAgents'ın kitap başı "çeviri
rehberi"nin bizdeki karşılığı) ve isteğe bağlı olarak sözlük ön taramasını koşar.

Kurallar (projenin kanıt ilkesi, `sozluk_tarama` / `varlik_cikarim` ile aynı):
  * Model YALNIZ ücretsiz zincirden; sonuç ÖNERİDİR: satırlar `origin='model', durum='aday'`
    yazılır ve kullanıcı onaylamadan hiçbir istem/denetime girmez (`kitap_profili.profil`).
  * Her öneri örnekte BİREBİR geçen bir alıntı taşır ve değer YEREL sayımla doğrulanır
    (ana karakter ilk bölümlerde ≥ `ANA_KARAKTER_MIN` kez, sistem sesi ≥2 sistem satırı açar,
    dizinin her basamağı ve her kategori terimi örnekte geçer). Tutmayan atılır.
  * Kullanıcının kararı ezilmez: alanın `manual` satırı ya da onaylanmış/reddedilmiş `model`
    satırı varsa o alan yeniden yazılmaz; koddaki kayıtta (SS) bulunan alan hiç önerilmez.
  * Onay bedeli: profili olan kitapta defter işçisi açılır (`karakter_defteri.kitap_acik`,
    bölüm başına model çağrısı). Arayüz bunu söyler; otomatik onay YOK.

Otomatik tetik (`gerekirse_baslat`, `pipeline`): kodda profili olmayan kitapta kaynağı olan bölüm
sayısı `OTOMATIK_MIN`..`OTOMATIK_UST` arasındaysa ve kitap için daha önce çıkarım koşmadıysa
(`kitap_profili_cikarim` tablosu). Üst sınır bilerek var: canlıdaki eski kitaplar (yüzlerce
bölüm) kendiliğinden taranmaz, kullanıcı arayüzden ister.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from collections import Counter

from . import api_durum, cache, db, kitap_profili, sozluk_tarama, varlik_grafigi
from .runler import genel

ILK_BOLUM = 10
ORNEK_KARAKTER = 14000
BOLUM_BASI = 900  # her bölümün başından alınan anlatım (karakterler orada tanıtılır)
ANA_KARAKTER_MIN = 5
OTOMATIK_MIN = 3
OTOMATIK_UST = 30
ANAHTAR_MIN = 2
ANAHTAR_EN_COK = 20
ALANLAR = ("kitap_turu", "ana_karakter", "sistem_sesi", "sistem_anahtarlari", "diziler", "kategori_terimleri",
           "gercek_ad_sozcugu")
TURLER = ("sistem", "kultivasyon", "duz")

PROFIL_INSTRUCTION = (
    "Sen bir web romanının İLK bölümlerini inceleyip çeviri sistemine KİTAP PROFİLİ çıkaran bir "
    "analizcisin. Yalnız verilen parçalarda AÇIKÇA görülen bilgiyi yaz; tahmin etme.\n"
    "Alanlar:\n"
    "- kitap_turu: 'sistem' (oyun/LitRPG: seviye, beceri, sistem mesajı), 'kultivasyon' (Qi, alem, "
    "tarikat) ya da 'duz'.\n"
    "- ana_karakter: anlatının odaklandığı kişinin metinde en sık geçen ADI (İngilizce, metindeki gibi).\n"
    "- sistem_sesi: oyuncuya mesaj veren sistemin metinde satır başında kullanılan adı (ör. 'System'); "
    "yoksa boş liste.\n"
    "- diziler: metinde geçen SIRALI basamak dizileri (rütbe, seviye, eşya kalitesi, alem…), en "
    "düşükten en yükseğe, her basamak metindeki yazımıyla; en az 3 basamak. Metinde görünmeyen "
    "basamağı EKLEME.\n"
    "- kategori_terimleri: belirli bir varlığı değil TÜRÜ adlandıran sistem terimleri (Skill, Level, "
    "Class, Quest…), metindeki yazımıyla.\n"
    "- gercek_ad_sozcugu: kitapta sistemin kişiye verdiği özel bir 'gerçek ad' kavramı varsa onun "
    "sözcüğü ('True Name'), yoksa null.\n"
    "Her değerin yanına parçalarda BİREBİR geçen ve o değeri içeren TEK cümleyi 'kanit' olarak kopyala.\n"
    "Yanıtı SADECE şu JSON ile ver: {\"kitap_turu\": {\"deger\": \"sistem\", \"kanit\": \"...\"}, "
    "\"ana_karakter\": {\"deger\": \"...\", \"kanit\": \"...\"}, \"sistem_sesi\": [{\"deger\": \"...\", "
    "\"kanit\": \"...\"}], \"diziler\": [{\"ad\": \"kisa_ad\", \"deger\": [\"...\", \"...\", \"...\"], "
    "\"kanit\": \"...\"}], \"kategori_terimleri\": [{\"deger\": \"...\", \"kanit\": \"...\"}], "
    "\"gercek_ad_sozcugu\": {\"deger\": \"...\", \"kanit\": \"...\"} }"
)


# ---------- iş kaydı ----------
def _connect():
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kitap_profili_cikarim (
            book_slug TEXT PRIMARY KEY,
            zaman REAL NOT NULL,
            sonuc TEXT NOT NULL
        )
        """
    )
    return conn


def son_cikarim(book_slug: str) -> dict | None:
    # Okuma şema yaratmaz (her bölümde çağrılır; `kitap_profili` okumasıyla aynı ilke).
    conn = db.connect()
    try:
        r = conn.execute("SELECT zaman, sonuc FROM kitap_profili_cikarim WHERE book_slug = ?", (book_slug,)).fetchone()
    except sqlite3.OperationalError:  # tablo yok: hiç çıkarım koşmadı
        r = None
    finally:
        conn.close()
    return {"zaman": r[0], **json.loads(r[1])} if r else None


def _kaynakli_bolum_sayisi(book_slug: str) -> int:
    conn = db.connect()
    try:
        return conn.execute(
            "SELECT COUNT(DISTINCT chapter_no) FROM chapters WHERE book_slug = ? AND chapter_no IS NOT NULL "
            "AND source_text IS NOT NULL", (book_slug,)).fetchone()[0]
    finally:
        conn.close()


def _kaydet(book_slug: str, sonuc: dict) -> None:
    conn = _connect()
    try:
        conn.execute("INSERT OR REPLACE INTO kitap_profili_cikarim (book_slug, zaman, sonuc) VALUES (?, ?, ?)",
                     (book_slug, time.time(), json.dumps(sonuc, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()


# ---------- örnek ----------
def ilk_bolumler(book_slug: str, adet: int = ILK_BOLUM) -> list[dict]:
    """Kaynağı olan en düşük numaralı `adet` bölüm; aynı bölümün yalnız en yeni kaydı."""
    secilen: dict[int, dict] = {}
    for b in cache.kaynak_bolumleri(book_slug):
        no = b.get("chapter_no")
        if no is None or not b.get("source"):
            continue
        if no not in secilen or (b.get("created_at") or 0) > (secilen[no].get("created_at") or 0):
            secilen[no] = b
    return [secilen[no] for no in sorted(secilen)[:adet]]


def ornek_kur(bolumler: list[dict], toplam: int = ORNEK_KARAKTER) -> list[dict]:
    """Her bölümden: başındaki anlatım + sistem satırı taşıyan paragraflar (sistem dili oradadır)."""
    pay = max(BOLUM_BASI, toplam // max(1, len(bolumler)))
    out = []
    for b in bolumler:
        paragraflar = [p.strip() for p in b["source"].split("\n\n") if p.strip()]
        sistemli = {s["paragraf"] for s in genel.sistem_satirlari(b["source"])}
        secilen, boy = [], 0
        for i, p in enumerate(paragraflar):
            if boy < BOLUM_BASI or i in sistemli:
                if boy + len(p) > pay:
                    break
                secilen.append(p)
                boy += len(p)
        out.append({"chapter_no": b["chapter_no"], "text": "\n\n".join(secilen)})
    return out


def _norm(s: str) -> str:
    return sozluk_tarama._norm(s)


def _sozcuk(deger: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(deger) + r"(?!\w)")


# ---------- doğrulama ----------
class _Dogrulayici:
    """Model önerisini örnek ve ilk bölümlerle sınar. Her `kabul` bir kanıt kaydı döner, yoksa None."""

    def __init__(self, ornek: list[dict], bolumler: list[dict]):
        self.ornek = [(p["chapter_no"], _norm(p["text"])) for p in ornek]
        self.birlesik = "\n".join(t for _n, t in self.ornek)
        self.kaynak = "\n".join(b["source"] for b in bolumler)
        self.bolumler = bolumler

    def alinti(self, deger: str, kanit) -> dict | None:
        k = _norm(str(kanit or ""))
        if not k or not deger or deger not in k:
            return None
        bolum = next((no for no, t in self.ornek if k in t), None)
        return {"deger": deger, "alinti": k, "bolum": bolum} if bolum is not None else None

    def sayi(self, deger: str) -> int:
        return len(_sozcuk(deger).findall(self.kaynak))

    def ornekte(self, deger: str) -> bool:
        return bool(_sozcuk(deger).search(self.birlesik))


def _tek(veri, alan):
    x = veri.get(alan)
    return x if isinstance(x, dict) else None


def _liste(veri, alan):
    return [x for x in (veri.get(alan) or []) if isinstance(x, dict)] if isinstance(veri.get(alan), list) else []


def _dizi_adi(ad: str, sira: int) -> str:
    ad = re.sub(r"\W+", "_", (ad or "").casefold()).strip("_")
    return ad or f"dizi_{sira}"


def dogrula(veri: dict, ornek: list[dict], bolumler: list[dict]) -> dict[str, dict]:
    """Modelin JSON'u -> {alan: {"deger", "kanit": [...], "elenen": [...]}}. Yalnız tutan alanlar döner."""
    d = _Dogrulayici(ornek, bolumler)
    out: dict[str, dict] = {}
    if not isinstance(veri, dict):
        return out

    x = _tek(veri, "kitap_turu")
    if x and str(x.get("deger") or "").strip() in TURLER:
        k = _norm(str(x.get("kanit") or ""))
        bolum = next((no for no, t in d.ornek if k and k in t), None)
        if bolum is not None:
            out["kitap_turu"] = {"deger": x["deger"].strip(), "kanit": [{"deger": x["deger"].strip(), "alinti": k,
                                                                         "bolum": bolum}]}

    x = _tek(veri, "ana_karakter")
    if x:
        ad = str(x.get("deger") or "").strip()
        k = d.alinti(ad, x.get("kanit"))
        if k and d.sayi(ad) >= ANA_KARAKTER_MIN:
            out["ana_karakter"] = {"deger": ad, "kanit": [{**k, "sayi": d.sayi(ad)}]}

    sesler, ses_kanit = [], []
    for x in _liste(veri, "sistem_sesi"):
        ad = str(x.get("deger") or "").strip()
        k = d.alinti(ad, x.get("kanit"))
        if not k or ad in sesler:
            continue
        acan = sum(1 for b in bolumler for s in genel.sistem_satirlari(b["source"], (ad,)) if s["tur"] == "ses")
        if acan >= 2:
            sesler.append(ad)
            ses_kanit.append({**k, "sayi": acan})
    if sesler:
        out["sistem_sesi"] = {"deger": sesler, "kanit": ses_kanit}

    # Anahtarlar YEREL sayımdır (model önermez): onaylı sesle bulunan sistem bloklarındaki
    # "Anahtar: değer" satırları. Profilde anahtar listesi varsa genel algılayıcı anlatıma gömülü
    # satırları da yakalar (RSSG ölçümü: 26 "Cooldown"dan 20'si ancak böyle).
    sayac, ilk = Counter(), {}
    for b in bolumler:
        for s in genel.sistem_satirlari(b["source"], tuple(sesler)):
            if s["anahtar"]:
                sayac[s["anahtar"]] += 1
                ilk.setdefault(s["anahtar"], {"deger": s["anahtar"], "alinti": s["satir"], "bolum": b["chapter_no"]})
    anahtarlar = [a for a, n in sayac.most_common(ANAHTAR_EN_COK) if n >= ANAHTAR_MIN and a not in sesler]
    if anahtarlar:
        out["sistem_anahtarlari"] = {"deger": anahtarlar,
                                     "kanit": [{**ilk[a], "sayi": sayac[a]} for a in anahtarlar]}

    diziler, dizi_kanit, elenen = {}, [], []
    for i, x in enumerate(_liste(veri, "diziler"), 1):
        sira = [str(s).strip() for s in (x.get("deger") or []) if str(s).strip()] if isinstance(x.get("deger"), list) else []
        k = _norm(str(x.get("kanit") or ""))
        bolum = next((no for no, t in d.ornek if k and k in t), None)
        eksik = [s for s in sira if not d.ornekte(s)]
        if len(sira) < 3 or len(set(sira)) != len(sira) or eksik or bolum is None or not any(s in k for s in sira):
            elenen.append({"deger": sira, "neden": "örnekte yok: " + ", ".join(eksik) if eksik else "kanıt/uzunluk"})
            continue
        ad = _dizi_adi(str(x.get("ad") or ""), i)
        diziler[ad] = sira
        dizi_kanit.append({"deger": ad, "alinti": k, "bolum": bolum})
    if diziler:
        out["diziler"] = {"deger": diziler, "kanit": dizi_kanit, "elenen": elenen}

    terimler, terim_kanit = [], []
    for x in _liste(veri, "kategori_terimleri"):
        t = str(x.get("deger") or "").strip()
        k = d.alinti(t, x.get("kanit"))
        if k and t not in terimler and d.sayi(t) >= 2:
            terimler.append(t)
            terim_kanit.append({**k, "sayi": d.sayi(t)})
    if terimler:
        out["kategori_terimleri"] = {"deger": terimler, "kanit": terim_kanit}

    x = _tek(veri, "gercek_ad_sozcugu")
    if x and x.get("deger"):
        s = str(x["deger"]).strip()
        k = d.alinti(s, x.get("kanit"))
        if k:
            out["gercek_ad_sozcugu"] = {"deger": [s], "kanit": [{**k, "sayi": d.sayi(s)}]}
    return out


# ---------- çıkarım ----------
def _yazilabilir(book_slug: str) -> set[str]:
    """Modelin yazabileceği alanlar: koddaki kayıtta yok, elle satırı yok, model satırı karara bağlanmamış."""
    kod = varlik_grafigi.KITAP_PROFILLERI.get(book_slug) or {}
    kilitli = {r["alan"] for r in kitap_profili.satirlar(book_slug)
               if r["origin"] == "manual" or r["durum"] in ("onayli", "reddedildi")}
    return {a for a in ALANLAR if a not in kod and a not in kilitli}


def profil_oner(book_slug: str, bolumler: list[dict] | None = None, api_key: str = "", yaz: bool = True,
                cagir=None) -> dict:
    """İlk bölümlerden profil adayları (bir model isteği). `yaz` ise aday satırları yazılır."""
    bolumler = bolumler if bolumler is not None else ilk_bolumler(book_slug)
    if not bolumler:
        return {"bolumler": [], "alanlar": {}, "yazilan": [], "model": None}
    ornek = ornek_kur(bolumler)
    user = "\n\n".join(f"[PARÇA — bölüm {p['chapter_no']}]\n{p['text']}" for p in ornek)
    ham, model = (cagir or sozluk_tarama.ucretsiz_cagir)(user, PROFIL_INSTRUCTION, api_key)
    alanlar = dogrula(sozluk_tarama.json_coz(ham) or {}, ornek, bolumler)
    yazilan = []
    if yaz:
        izinli = _yazilabilir(book_slug)
        for alan, v in alanlar.items():
            if alan in izinli:
                kitap_profili.yaz(book_slug, alan, v["deger"], origin="model", durum="aday", kanit=v["kanit"])
                yazilan.append(alan)
    return {"bolumler": [b["chapter_no"] for b in bolumler], "alanlar": alanlar, "yazilan": yazilan, "model": model}


def on_tarama_acik() -> bool:
    """Sözlük ön taraması çeviriyi (doğrulanan adaylar prompt'a girince) etkiler: ölçülmeden açılmaz."""
    return os.getenv("SOZLUK_ON_TARAMA", "0") == "1"


def cikar(book_slug: str, on_tarama: bool | None = None, api_key: str = "", cagir=None) -> dict:
    """Profil önerisi + (açıksa) sözlük ön taraması; sonuç iş kaydına yazılır."""
    bolumler = ilk_bolumler(book_slug)
    sonuc: dict = {"bolumler": [b["chapter_no"] for b in bolumler]}
    try:
        p = profil_oner(book_slug, bolumler, api_key, cagir=cagir)
        sonuc.update(model=p["model"], profil=p["yazilan"],
                     elenen={a: v["elenen"] for a, v in p["alanlar"].items() if v.get("elenen")})
        if on_tarama_acik() if on_tarama is None else on_tarama:
            t = sozluk_tarama.on_tara(book_slug, bolumler, api_key, cagir=cagir)
            sonuc["on_tarama"] = {"oneri": t["oneri"], "yazilan": t["yazilan"],
                                  "elenen": sum(1 for a in t["adaylar"] if a["durum"] == "elendi")}
    except Exception as hata:  # noqa: BLE001 — kayıt hatayı taşır; çağıran (arka plan) düşmez
        sonuc["hata"] = str(hata)[:300]
    _kaydet(book_slug, sonuc)
    return sonuc


# ---------- karar ve ekran ----------
def deger_dogrula(alan: str, deger):
    """Elle düzeltilen değer: alan biçimine uymazsa ValueError. Temizlenmiş değer döner."""
    def sozcukler(v):
        if not isinstance(v, list):
            raise ValueError("Liste bekleniyor")
        out = [str(x).strip() for x in v if str(x).strip()]
        if not out:
            raise ValueError("En az bir değer gerekli")
        return out

    if alan == "kitap_turu":
        if deger not in TURLER:
            raise ValueError(f"Tür şunlardan biri olmalı: {', '.join(TURLER)}")
        return deger
    if alan == "ana_karakter":
        if not isinstance(deger, str) or not deger.strip():
            raise ValueError("Ad boş olamaz")
        return deger.strip()
    if alan == "diziler":
        if not isinstance(deger, dict) or not deger:
            raise ValueError("En az bir dizi gerekli")
        out = {}
        for ad, sira in deger.items():
            sira = sozcukler(sira)
            if len(sira) < 2:
                raise ValueError(f"'{ad}' dizisinde en az iki basamak olmalı")
            out[_dizi_adi(str(ad), len(out) + 1)] = sira
        return out
    if alan in ALANLAR:
        return sozcukler(deger)
    raise ValueError(f"Bilinmeyen profil alanı: {alan!r}")


def karar_ver(book_slug: str, alan: str, karar: str, deger=None) -> bool:
    """onayla / reddet: modelin aday satırı (yoksa False). duzelt: elle değer, onaylı yazılır."""
    if alan not in ALANLAR:
        raise ValueError(f"Bilinmeyen profil alanı: {alan!r}")
    if karar == "duzelt":
        kitap_profili.yaz(book_slug, alan, deger_dogrula(alan, deger), origin="manual", durum="onayli")
        return True
    if karar not in ("onayla", "reddet"):
        raise ValueError(f"Geçersiz karar: {karar!r}")
    return kitap_profili.durum_yaz(book_slug, alan, "model", "onayli" if karar == "onayla" else "reddedildi")


def ekran(book_slug: str) -> dict:
    """Kitap profili kartının verisi. `etkin`: istemlere/denetimlere fiilen giren değer."""
    from . import karakter_defteri

    kod = varlik_grafigi.KITAP_PROFILLERI.get(book_slug) or {}
    etkin = varlik_grafigi.profil(book_slug) or {}
    satirlar = kitap_profili.satirlar(book_slug)
    alanlar = []
    for alan in ALANLAR:
        model = next((r for r in satirlar if r["alan"] == alan and r["origin"] == "model"), None)
        elle = next((r for r in satirlar if r["alan"] == alan and r["origin"] == "manual"), None)
        alanlar.append({"alan": alan, "kod": alan in kod, "etkin": etkin.get(alan), "model": model, "elle": elle})
    return {"alanlar": alanlar, "kod_profili": bool(kod), "profil_var": bool(etkin),
            "defter_acik": karakter_defteri.kitap_acik(book_slug),
            "cikarim": {"calisiyor": calisiyor(book_slug), "son": son_cikarim(book_slug),
                        "on_tarama_varsayilan": on_tarama_acik()}}


# ---------- arka plan ----------
_KILIT = threading.Lock()
_CALISAN: set[str] = set()


def otomatik_acik() -> bool:
    return os.getenv("KITAP_PROFIL_OTOMATIK", "1") != "0"


def calisiyor(book_slug: str) -> bool:
    return book_slug in _CALISAN


def arka_planda(book_slug: str, on_tarama: bool | None = None) -> bool:
    """Tek-uçuşlu arka plan çıkarımı. Başladıysa True."""
    from . import translate

    if not translate.ceviri_anahtari_var_mi(os.getenv("GEMINI_API_KEY", "")):
        return False
    with _KILIT:
        if book_slug in _CALISAN:
            return False
        _CALISAN.add(book_slug)

    def is_():
        try:
            with api_durum.islem("profil_cikarim"):
                cikar(book_slug, on_tarama)
        finally:
            with _KILIT:
                _CALISAN.discard(book_slug)

    threading.Thread(target=is_, name=f"profil-cikarim-{book_slug}", daemon=True).start()
    return True


def gerekirse_baslat(book_slug: str) -> bool:
    """Bölüm önbelleğe girince (`pipeline`): yeni kitapta ilk kez, kendiliğinden."""
    if not otomatik_acik() or book_slug in varlik_grafigi.KITAP_PROFILLERI or calisiyor(book_slug):
        return False
    if not OTOMATIK_MIN <= _kaynakli_bolum_sayisi(book_slug) <= OTOMATIK_UST or son_cikarim(book_slug) is not None:
        return False
    return arka_planda(book_slug)
