"""KARAKTER DEFTERİ: kitabın kim-kimdir kaydı — sözlüğe ve çeviriye hizmet eden yalın grafik.

NEDEN AYRI BİR HAT (2026-10-14, kullanıcı kararı): v11 bilgi grafiği (arşiv: `faz2a` dalı,
`0245b53`) bölüm başına ~67 sn, ~0,067 $ harcıyordu ve 25–30. bölümlerde TEK bağ kabul
etmedi (23 inceleme). Kararı regex kapısı veriyordu (diyalog/"said" -> inceleme), inceleme
kayıtları bölümler arasında birikmiyordu (Sunny -> Julius dört bölümde önerildi, hiç
kabul edilmedi) ve çeviriye hiç bağlı değildi.

Buradaki yol (araştırma: KGGen, LightRAG, BookNLP, DelTA, TransGraph):
  * Bölüm başına TEK çağrı, arka planda; girdi hizalı EN+TR paragraflar (BİRER kez) ve
    bölümde geçen kayıtlı adlar. Bölümler birbirinden bağımsızdır (N−1 zinciri YOK), bu
    yüzden geriye dönük doldurma paralel koşar.
  * Doğrulama DETERMİNİSTİK ve yalnız biçimseldir: alıntı paragrafta birebir var mı, ad
    orada geçiyor mu, hitap beyanı kendi Türkçe alıntısıyla çelişiyor mu. Anlamsal regex
    kapısı yok — o kapı iki yönde de hata yaptı.
  * Kabul BİRİKİMLE gelir (`uzlastir`): aynı iddia farklı bölümlerde tekrar ettikçe güven
    artar. Bağlar `varlik_grafigi.bag_ekle` ile `varlik_bag`a `aday` olarak yazılır;
    `onaylandi` yalnız kullanıcıyla olur (model bağı incelenmeden onaylanmaz).
  * HİTAP (sen/siz) ayrı tutulur: konuşan -> muhatap çifti başına çevirinin FİİLEN kullandığı
    biçim. LLM hakemleri hitap hatasını çoğu zaman kaçırır (arXiv 2412.01340), bu tablo
    tutarlılığı ölçülebilir kılar. Tablo geçmiş çeviriyi yansıtır, doğruyu değil: elle
    karar (`defter_hitap_karar`) her zaman üstündür.

Bu modül sözlüğü DEĞİŞTİRMEZ; sözlüğe katkısı inceleme listesine giden önerilerdir.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter, defaultdict

from . import api_durum, budget, db, glossary, translate, varlik_grafigi
from .varlik_cikarim import _normal, ad_temizle

# v2 (2026-10-14, pilot elle denetimi): çoğul hitap ayrı (`cogul`), rütbe yalnız rütbe
# dizisinden, Gerçek Ad yalnız "True Name" kanıtıyla, ad en az bir kez büyük harfle.
ISTEM_SURUMU = "defter-v2"
VARSAYILAN_MODEL = "vertex/gemini-3.8-flash"
# Düşünme tokenları da bu tavandan düşer. Pilot (2026-10-14, 20 SS bölümü, model varsayılan
# düşünmesi): düşünme bölüm başına 1,3k–6,5k token; 8000'lik tavanda 14 bölümün 5'i yarıda
# kesildi (STOP yok). Tavan geniş, düşünme varsayılanı `low`.
CIKIS_TAVANI = 16000
VARSAYILAN_DUSUNME = "low"
EN_COK_KAYIT = 60
EN_COK_HITAP_ADAYI = 40
EN_COK_DENEME = 3
# Çeviriye yararlı küçük ilişki kümesi (hepsi `varlik_grafigi.ILISKILER`de); yeni tür AÇILMAZ.
DEFTER_ILISKILERI = (
    "akrabasi", "lideri", "ogretmeni", "yoldasi", "dusmani", "klani", "grubu",
    "rutbesi", "takma_adi", "gercek_adi", "unvani",
)
# `cogul`: birden çok kişiye hitap. Türkçede çoğul "siz" resmiyet DEĞİLDİR; tabloya girerse
# "Sunny -> Kai: siz" gibi sahte bir resmiyet üretir (pilotta 50 hitabın ~5'i böyleydi).
HITAP_BICIMLERI = ("sen", "siz", "cogul", "belirsiz")
# Sistem sesi: sözlükte kayıtlı olmasa da konuşan olabilir (Spell'in rün mesajları).
SISTEM_KONUSANLARI = frozenset({"spell"})
_YER_TUTUCULAR = frozenset({
    "", "?", "-", "—", "unknown", "someone", "somebody", "he", "she", "they", "him", "her",
    "it", "you", "i", "we", "narrator", "anlatıcı", "bilinmiyor",
})
# Takma adı asla kesin sayılmayan kayıt türleri; yalnız aday + inceleme (BookNLP dersi:
# cins ad ile özel ad birleştirilmez).
_BIRLESEBILIR_TURLER = frozenset({"kisi", "orgut", "yer", None, ""})

SEMA = """
CREATE TABLE IF NOT EXISTS defter_isleme (
    book_slug TEXT NOT NULL,
    bolum INTEGER NOT NULL,
    durum TEXT NOT NULL,
    istem_surumu TEXT,
    model TEXT,
    giris_token INTEGER,
    cikis_token INTEGER,
    dusunme_token INTEGER,
    sure_sn REAL,
    deneme INTEGER NOT NULL DEFAULT 0,
    hata TEXT,
    metrik TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (book_slug, bolum)
);
CREATE TABLE IF NOT EXISTS defter_iddia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_slug TEXT NOT NULL,
    bolum INTEGER NOT NULL,
    tur TEXT NOT NULL,
    ozne_ad TEXT,
    ozne_kimlik TEXT,
    iliski TEXT,
    nesne_ad TEXT,
    nesne_kimlik TEXT,
    deger TEXT,
    paragraf INTEGER,
    en_alinti TEXT,
    tr_alinti TEXT,
    anlatim TEXT,
    gecerli INTEGER NOT NULL,
    red_nedeni TEXT,
    istem_surumu TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS defter_iddia_bolum ON defter_iddia (book_slug, bolum);
CREATE INDEX IF NOT EXISTS defter_iddia_tur ON defter_iddia (book_slug, tur, gecerli);
CREATE TABLE IF NOT EXISTS defter_hitap_karar (
    book_slug TEXT NOT NULL,
    konusan TEXT NOT NULL,
    muhatap TEXT NOT NULL,
    hitap TEXT NOT NULL,
    ilk_bolum INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (book_slug, konusan, muhatap, ilk_bolum)
);
"""

DEFTER_TALIMATI = """Bir web romanının TEK bölümünden "karakter defteri" kaydı çıkarıyorsun.
Girdi: İngilizce kaynak paragrafları ve Türkçe çevirileri (aynı numara = aynı paragraf), bu
bölümde geçen kayıtlı adlar (`kayitli`; kimlikleri e1, e2…) ve hitap aranacak paragraf
numaraları (`hitap_adaylari`).

Yalnız JSON döndür: {"v":[...],"g":[...],"b":[...],"h":[...]}

v — bu bölümde AD olarak geçen varlıklar (kişi, yer, örgüt/klan/grup, rütbe/unvan, yetenek, nesne):
 Yalnız BÜYÜK HARFLE yazılan özel adlar; küçük harfli cins sözcükler (beast, cohort, dark sea) girmez.
 {"ad":"kayıtlıysa id (e3), değilse kaynaktaki ad aynen","tr":"Türkçe çeviride bu ad nasıl yazılmış (aynen)",
  "t":"kisi|yer|orgut|rutbe|yetenek|nesne|diger","asil":"bu ad başka bir varlığın takma adı, lakabı ya da
  kısaltmasıysa o varlığın id'si ya da adı; değilse null","p":paragraf_no,
  "a":"İngilizce paragraftan AYNEN, adı içeren, en çok 12 sözcük"}
 Her varlık bir kez. Cins adlar (the man, a girl, the Echo, the creature) varlık değildir.

g — `kayitli` listesinde olup bu bölümde AD olarak değil SIRADAN SÖZCÜK olarak geçen kayıtların
 id'leri (örnek: kayıtlı "Hollow" burada "a hollow tree" olarak geçiyor).

b — metnin AÇIKÇA söylediği ilişkiler; tahmin yok:
 {"o":"özne","r":"akrabasi|lideri|ogretmeni|yoldasi|dusmani|klani|grubu|rutbesi|takma_adi|gercek_adi|unvani",
  "n":"nesne","p":paragraf_no,"a":"ilişkiyi gösteren İngilizce alıntı, AYNEN","s":"anlatici|konusma"}
 Yön: "o r n" = "o'nun r'si n". Örnekler: Sunny ogretmeni Julius (Julius, Sunny'nin öğretmeni);
 Nephis klani Immortal Flame; Sunny rutbesi Master; Nephis takma_adi Changing Star; Kai lideri Nephis
 (Nephis, Kai'nin lideri ya da amiri). s: ilişkiyi anlatıcı mı söylüyor, bir karakterin sözünde mi geçiyor.
 rutbesi YALNIZ resmî rütbe/basamak adı içindir (Sleeper, Awakened, Master, Saint…); görev ya da rol
 (archer, healer), yaratık sınıfı ve betimleme ("the ruthless tyrant") rütbe değildir. gercek_adi YALNIZ
 metin "True Name" dediğinde; başka ad ya da lakap takma_adi'dir.

h — yalnız `hitap_adaylari` paragraflarında, konuşanın karşısındakine DOĞRUDAN hitabı:
 {"p":paragraf_no,"ko":"konuşan","mu":"muhatap","f":"sen|siz|cogul|belirsiz",
  "tra":"TÜRKÇE paragraftan hitabı gösteren AYNEN alıntı (Türkçe harfleriyle), en çok 8 sözcük",
  "en":"İngilizce hitap sözcüğü varsa (sir, Lady Nephis, Master, Captain), yoksa boş"}
 f: Türkçe çevirinin FİİLEN kullandığı biçim (sen/siz zamiri ya da kişi eki). Konuşan BİRDEN ÇOK kişiye
 hitap ediyorsa ("both of you", gruba konuşma) f="cogul" ve mu o kişilerden biri. Konuşan ya da muhatap
 metinden kesin anlaşılmıyorsa o paragrafı ATLA. Sistemin (Spell) mesajlarında konuşan "Spell".

Kurallar: ad/o/n/ko/mu alanlarında kayıtlı id varsa id'yi yaz. Her öğenin paragraf numarası ve
alıntısı o paragraftan BİREBİR olmalı. Emin olmadığını yazma; boş liste geçerli bir cevaptır.
Açıklama yazma, yalnız JSON."""


# ---------- ayarlar ----------
def acik_mi() -> bool:
    """Canlı kuyruk (çeviriden sonra arka plan çıkarımı). Varsayılan KAPALI."""
    return os.getenv("KARAKTER_DEFTERI", "0") == "1"


def kitaplar() -> set[str]:
    return {s.strip() for s in os.getenv("KARAKTER_DEFTERI_KITAPLAR", "shadow-slave").split(",") if s.strip()}


def model_adi() -> str:
    return (os.getenv("DEFTER_MODELI") or VARSAYILAN_MODEL).strip()


def dusunme_ayari() -> dict | None:
    """`DEFTER_DUSUNME`: boş -> `VARSAYILAN_DUSUNME`; `varsayilan` -> modelin kendi ayarı;
    low/medium/high/minimal -> düzey; sayı -> bütçe. Düşünme tokenları ÇIKIŞ fiyatından ödenir."""
    deger = (os.getenv("DEFTER_DUSUNME") or VARSAYILAN_DUSUNME).strip().lower()
    if deger == "varsayilan":
        return None
    if deger.lstrip("-").isdigit():
        return {"thinking_budget": int(deger)}
    return {"thinking_level": deger}


def _connect():
    conn = db.connect()
    conn.executescript(SEMA)
    return conn


# ---------- Türkçe hitap işaretleri ----------
def _tr_kucuk(metin: str) -> str:
    return (metin or "").replace("İ", "i").replace("I", "ı").lower()


_SIZ = re.compile(
    r"\b(?:siz|sizi|size|sizin|sizde|sizden|sizinle|sizler)\b"
    r"|\w+(?:s[ıiuü]n[ıiuü]z|[ıiuü]n[ıiuü]z|y[ıiuü]n[ıiuü]z)\b"
)
# 2. tekil: zamir, geniş/şimdiki zaman `-sın`, geçmiş zaman `-dın/-tın` (kaldın, gittin).
_SEN = re.compile(
    r"\b(?:sen|seni|sana|senin|sende|senden|seninle)\b|\b\w+(?:s|[dt])[ıiuü]n\b"
)
# `-dın/-tın` ile biten ama kişi eki OLMAYAN sık sözcükler.
_SEN_DEGIL = frozenset({"kadın", "altın", "yakın", "akın", "kalın", "ilkin", "yüzdün"})
_EFENDIM = re.compile(r"\befendim\b")


def hitap_isaretleri(tr: str) -> tuple[bool, bool]:
    """(sen işareti var mı, siz işareti var mı) — Türkçe metinde. Kaba bir eleyicidir:
    model biçimi söyler, bu yalnız aday seçer ve modelin kendi alıntısıyla çelişkisini yakalar."""
    k = _tr_kucuk(tr)
    sen = any(m.group(0) not in _SEN_DEGIL for m in _SEN.finditer(k))
    return sen, bool(_SIZ.search(k))


_TIRNAK = re.compile(r"[\"“”]")


def hitap_adaylari(en_paras: list[str], tr_paras: list[str]) -> list[int]:
    """Hitap aranacak paragraflar (1 tabanlı): konuşma ya da rün mesajı VE Türkçede 2. kişi
    işareti. Model yalnız bunlara bakar: çıkışı kısaltır, hitabı da gözden kaçırmaz."""
    out = []
    for i, (en, tr) in enumerate(zip(en_paras, tr_paras), 1):
        if not (_TIRNAK.search(en or "") or (en or "").lstrip().startswith("[")):
            continue
        sen, siz = hitap_isaretleri(tr)
        if sen or siz or _EFENDIM.search(_tr_kucuk(tr)):
            out.append(i)
    return out[:EN_COK_HITAP_ADAYI]


# ---------- bölüm ve kayıt defteri ----------
def bolum_metni(book_slug: str, bolum: int, conn=None) -> tuple[list[str], list[str]] | str:
    """Hizalı (EN, TR) paragraflar; yoksa neden: 'yok' (kaynak/çeviri yok) | 'hizasiz'."""
    kendi = conn is None
    conn = conn or db.connect()
    try:
        satir = conn.execute(
            "SELECT source_text, translation FROM chapters WHERE book_slug = ? AND chapter_no = ? "
            "AND IFNULL(content_type, 'text') != 'html' ORDER BY created_at DESC LIMIT 1",
            (book_slug, bolum),
        ).fetchone()
    finally:
        if kendi:
            conn.close()
    if not satir or not satir[0] or not satir[1]:
        return "yok"
    en_p = [p.strip() for p in satir[0].split("\n\n")]
    tr_p = [p.strip() for p in satir[1].split("\n\n")]
    if len(en_p) != len(tr_p):
        return "hizasiz"
    return en_p, tr_p


def _sozluk_gorunumu(book_slug: str) -> tuple[list[dict], dict[str, list[str]]]:
    satirlar = glossary.get_glossary_rows(book_slug)
    yazimlar = {k: e["yazimlar"] for k, e in glossary.ekler(book_slug).items()}
    return satirlar, yazimlar


_TUR_ONCELIK = {"kisi": 0, "orgut": 1, "yer": 2, "rutbe": 3}


def kayit_defteri(
    book_slug: str, bolum: int, en_metin: str,
    satirlar: list[dict] | None = None, yazimlar: dict[str, list[str]] | None = None,
    takma: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Bu bölümün EN metninde geçen sözlük kayıtları (en çok `EN_COK_KAYIT`).

    SPOILER (geriye dönük doldurmada önemli): `first_chapter` bu bölümden SONRA olan kayıt
    girmez — 300. bölümü işlerken 900'de öğrenilen bir adı modele vermek, bilgiyi geriye
    taşır. `takma`: kimlik -> o bölüme kadar bilinen takma adlar."""
    if satirlar is None or yazimlar is None:
        satirlar, yazimlar = _sozluk_gorunumu(book_slug)
    takma = takma or {}
    adaylar = []
    for r in satirlar:
        ilk = r.get("first_chapter")
        if type(ilk) is int and ilk > bolum:
            continue
        adlar = [r["source"], *yazimlar.get(r["source"], [])]
        sayi = sum(len(translate._term_regex(a).findall(en_metin)) for a in adlar if a)
        if not sayi:
            continue
        adaylar.append((r, adlar[1:], sayi))
    adaylar.sort(key=lambda x: (_TUR_ONCELIK.get(x[0].get("tur"), 9), -x[2], x[0]["source"]))
    out = []
    for i, (r, diger, _sayi) in enumerate(adaylar[:EN_COK_KAYIT], 1):
        kayit = {"id": f"e{i}", "kimlik": r["kimlik"], "ad": r["source"], "tr": r.get("target") or "",
                 "tur": r.get("tur") or ""}
        diger_adlar = [*diger, *takma.get(r["kimlik"], [])]
        if diger_adlar:
            kayit["diger_adlar"] = diger_adlar
        out.append(kayit)
    return out


def _takma_adlar(book_slug: str, bolum: int, conn) -> dict[str, list[str]]:
    """kimlik -> bu bölüme kadar kurulmuş (reddedilmemiş) takma/gerçek ad kaynakları."""
    try:
        satirlar = conn.execute(
            "SELECT b.kaynak_kimlik, g.source FROM varlik_bag b JOIN glossary g "
            "ON g.book_slug = b.book_slug AND g.kimlik = b.hedef_kimlik "
            "WHERE b.book_slug = ? AND b.iliski IN ('takma_adi', 'gercek_adi') "
            "AND b.durum != 'reddedildi' AND IFNULL(b.ilk_bolum, 0) <= ?",
            (book_slug, bolum),
        ).fetchall()
    except Exception:  # noqa: BLE001 — varlik_bag henüz yoksa takma ad da yok
        return {}
    out: dict[str, list[str]] = defaultdict(list)
    for k, ad in satirlar:
        out[k].append(ad)
    return dict(out)


def istem_kur(bolum: int, kayitli: list[dict], en_p: list[str], tr_p: list[str], adaylar: list[int]) -> str:
    paragraflar = [[i, e, t] for i, (e, t) in enumerate(zip(en_p, tr_p), 1) if e and t]
    gorunur = [{a: k[a] for a in ("id", "ad", "tr", "tur", "diger_adlar") if k.get(a)} for k in kayitli]
    return json.dumps({"bolum": bolum, "kayitli": gorunur, "paragraflar": paragraflar,
                       "hitap_adaylari": adaylar}, ensure_ascii=False)


# ---------- yanıt ve doğrulama ----------
def ayristir(metin: str | None) -> dict:
    metin = (metin or "").strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```(?:json)?\s*|\s*```$", "", metin)
    veri = json.loads(metin)
    if not isinstance(veri, dict):
        raise ValueError("Yanıt nesne değil.")
    return {a: veri.get(a) if isinstance(veri.get(a), list) else [] for a in ("v", "g", "b", "h")}


class _Cozucu:
    """Yanıttaki başvuru (e3 ya da ad) -> (kimlik | None, görünen ad, bilinen adlar)."""

    def __init__(self, book_slug: str, kayitli: list[dict]):
        self.idden = {k["id"]: k for k in kayitli}
        self._dugum = varlik_grafigi.DugumCozucu(book_slug)
        # Rütbe adları: kitap profilinin dizileri + sözlükte `rutbe` türlü kayıtlar. Grafikteki
        # `rutbesi` bağlarının nesneleri BİLEREK alınmaz: eski model bağları ("Kai rutbesi
        # Archer") denetimi kendi hatasıyla beslerdi.
        p = varlik_grafigi.profil(book_slug) or {}
        self.rutbeler = {x.casefold() for dizi in p.get("diziler", {}).values() for x in dizi}
        self.rutbeler |= {x.casefold() for x in p.get("ek_rutbeler", ())}
        self.rutbeler |= {r["source"].casefold() for r in self._dugum.satirlar.values() if r.get("tur") == "rutbe"}

    def coz(self, ref) -> tuple[str | None, str, list[str]]:
        ref = ad_temizle(str(ref or "")).strip()
        if ref in self.idden:
            k = self.idden[ref]
            return k["kimlik"], k["ad"], [k["ad"], *k.get("diger_adlar", [])]
        kimlik = self._dugum.coz(ref)
        if kimlik:
            ad = self._dugum.kaynak(kimlik)
            return kimlik, ad, [ref, ad] if ref != ad else [ad]
        return None, ref, [ref]


def _geciyor(adlar: list[str], metin: str, buyuk: bool = False) -> bool:
    """Ad metinde geçiyor mu; `buyuk`: en az bir geçişi büyük harfle mi (özel ad olarak)."""
    for a in adlar:
        if not a:
            continue
        for m in translate._term_regex(a).finditer(metin or ""):
            if not buyuk or m.group(0)[:1].isupper():
                return True
    return False


def _alinti_var(alinti: str, metin: str) -> bool:
    a = _normal(alinti).strip(" .,;:!?\"'…").casefold()
    return bool(a) and a in _normal(metin).casefold()


_KATLA = str.maketrans("ığüşöçâîû", "igusocaiu")


def _katla(metin: str) -> str:
    """Türkçe harf işaretlerini düzle: model alıntıyı bazen işaretsiz yazıyor ("Oyle degil mi")."""
    return _tr_kucuk(_normal(metin)).translate(_KATLA)


def _tr_var(alinti: str, metin: str) -> bool:
    """Türkçe alıntı/ad paragrafta mı — ek ve harf işareti toleranslı (`Nephis'in` ⊃ `Nephis`)."""
    a = _katla(alinti).strip(" .,;:!?\"'…")
    m = _katla(metin)
    if not a:
        return False
    return a in m or (len(a) > 5 and a[: max(4, len(a) - 3)] in m)


def _yer_tutucu(ad: str) -> bool:
    ad = (ad or "").strip()
    return ad.casefold() in _YER_TUTUCULAR or ad == ad.lower()


def _paragraf(p, n: int) -> int | None:
    try:
        p = int(p)
    except (TypeError, ValueError):
        return None
    return p if 1 <= p <= n else None


def dogrula(tur: str, oge: dict, en_p: list[str], tr_p: list[str], cozucu: _Cozucu) -> dict:
    """Tek öğeyi kayda çevir ve biçimsel olarak doğrula. Döner: `defter_iddia` alanları.

    Red nedenleri: paragraf_yok, ad_yok, ad_kucuk, yer_tutucu, alinti_yok, tr_yok, iliski_yok,
    rutbe_degil, gercek_ad_kanitsiz, bicim_yok, hitap_celiski. Anlam yargısı yok; yalnız pilot
    denetiminde ölçülen ve metinden denetlenebilen hata sınıfları — gerisi birikime kalır."""
    n = len(en_p)
    kayit = {"tur": tur, "gecerli": 0, "red_nedeni": None, "deger": {}}

    def red(neden: str) -> dict:
        kayit["red_nedeni"] = neden
        return kayit

    p = _paragraf(oge.get("p"), n)
    kayit["paragraf"] = p
    if tur == "varlik":
        kimlik, ad, adlar = cozucu.coz(oge.get("ad"))
        asil_k, asil_ad, _ = cozucu.coz(oge.get("asil")) if oge.get("asil") else (None, None, [])
        kayit.update(ozne_ad=ad, ozne_kimlik=kimlik, nesne_ad=asil_ad, nesne_kimlik=asil_k,
                     en_alinti=str(oge.get("a") or "")[:300], tr_alinti=str(oge.get("tr") or "")[:120],
                     iliski="takma_adi" if asil_ad else None)
        t = oge.get("t") if oge.get("t") in glossary.TURLER else "diger"
        kayit["deger"] = {"tr": kayit["tr_alinti"], "t": t}
        if p is None:
            return red("paragraf_yok")
        if _yer_tutucu(ad) or (asil_ad is not None and _yer_tutucu(asil_ad)):
            return red("yer_tutucu")
        if not _geciyor(adlar, en_p[p - 1]):
            return red("ad_yok")
        if not _geciyor(adlar, en_p[p - 1], buyuk=True):
            return red("ad_kucuk")
        if not _alinti_var(kayit["en_alinti"], en_p[p - 1]):
            return red("alinti_yok")
        if kayit["tr_alinti"] and not _tr_var(kayit["tr_alinti"], tr_p[p - 1]):
            return red("tr_yok")
    elif tur == "bag":
        ok, oad, oadlar = cozucu.coz(oge.get("o"))
        nk, nad, nadlar = cozucu.coz(oge.get("n"))
        iliski = str(oge.get("r") or "")
        anlatim = oge.get("s") if oge.get("s") in ("anlatici", "konusma") else "konusma"
        kayit.update(ozne_ad=oad, ozne_kimlik=ok, nesne_ad=nad, nesne_kimlik=nk, iliski=iliski,
                     en_alinti=str(oge.get("a") or "")[:300], anlatim=anlatim)
        if iliski not in DEFTER_ILISKILERI:
            return red("iliski_yok")
        if p is None:
            return red("paragraf_yok")
        if _yer_tutucu(oad) or _yer_tutucu(nad):
            return red("yer_tutucu")
        pencere = "\n".join(en_p[max(0, p - 6): min(n, p + 1)])
        if not (_geciyor(oadlar, pencere) and _geciyor(nadlar, pencere)):
            return red("ad_yok")
        if not (_geciyor(oadlar, pencere, buyuk=True) and _geciyor(nadlar, pencere, buyuk=True)):
            return red("ad_kucuk")
        if not _alinti_var(kayit["en_alinti"], en_p[p - 1]):
            return red("alinti_yok")
        if iliski == "rutbesi" and nad.casefold() not in cozucu.rutbeler:
            return red("rutbe_degil")
        if iliski == "gercek_adi" and "true name" not in pencere.casefold():
            return red("gercek_ad_kanitsiz")
    elif tur == "hitap":
        kk, kad, kadlar = cozucu.coz(oge.get("ko"))
        mk, mad, madlar = cozucu.coz(oge.get("mu"))
        bicim = str(oge.get("f") or "").strip().lower()
        kayit.update(ozne_ad=kad, ozne_kimlik=kk, nesne_ad=mad, nesne_kimlik=mk,
                     tr_alinti=str(oge.get("tra") or "")[:200], anlatim="konusma")
        kayit["deger"] = {"f": bicim, "en": str(oge.get("en") or "")[:60]}
        if bicim not in HITAP_BICIMLERI:
            return red("bicim_yok")
        if p is None:
            return red("paragraf_yok")
        cogul = bicim == "cogul"
        if _yer_tutucu(kad) or (_yer_tutucu(mad) and not cogul):
            return red("yer_tutucu")
        # Konuşan/muhatap BÖLÜMDE geçmeli (uydurma kişi olmasın). Pencere değil: iki kişilik uzun
        # diyalogda konuşanın adı onlarca paragraf geçmeyebilir — pilotta doğru hitapları eliyordu.
        bolum = "\n".join(en_p)
        sistem = kad.casefold() in SISTEM_KONUSANLARI
        if not ((sistem or _geciyor(kadlar, bolum)) and (cogul or _geciyor(madlar, bolum))):
            return red("ad_yok")
        if not _tr_var(kayit["tr_alinti"], tr_p[p - 1]):
            return red("tr_yok")
        sen, siz = hitap_isaretleri(kayit["tr_alinti"])
        if ((bicim == "sen" and siz and not sen) or (bicim in ("siz", "cogul") and sen and not siz)):
            return red("hitap_celiski")
    kayit["gecerli"] = 1
    return kayit


def _genel_kayitlari(g: list, kayitli: list[dict]) -> list[dict]:
    idden = {k["id"]: k for k in kayitli}
    out = []
    for ref in g:
        k = idden.get(str(ref).strip())
        out.append({"tur": "genel", "ozne_ad": k["ad"] if k else str(ref)[:80],
                    "ozne_kimlik": k["kimlik"] if k else None, "deger": {},
                    "gecerli": 1 if k else 0, "red_nedeni": None if k else "ad_yok"})
    return out


# ---------- bölüm işleme ----------
class YarimYanit(translate.TranslateError):
    """Model yanıtı STOP ile bitmedi (ör. MAX_TOKENS). Harcanan tokenlar `kullanim`da: yarıda
    kalan deneme de ödenir, maliyet ölçümü onu saymazsa yanlış olur."""

    def __init__(self, mesaj: str, kullanim: dict):
        super().__init__(mesaj)
        self.kullanim = kullanim


def _bitis_nedeni(response) -> str:
    adaylar = getattr(response, "candidates", None)
    neden = getattr(adaylar[0], "finish_reason", None) if adaylar else getattr(response, "finish_reason", None)
    return str(getattr(neden, "value", neden) or "yok")


def _model_cagir(user: str, model: str) -> tuple[str, dict]:
    """TEK halka: çıkarım sessizce başka bir modele düşmemeli (ölçüm ve maliyet bozulur)."""
    jeton = translate._DUSUNME_AYARI.set(dusunme_ayari())
    try:
        response, kullanilan = translate._generate_with_fallback(
            translate._gemini_fabrikasi(os.getenv("GEMINI_API_KEY", "")), (model,), user,
            system=DEFTER_TALIMATI, max_tokens=CIKIS_TAVANI,
        )
    finally:
        translate._DUSUNME_AYARI.reset(jeton)
    meta = getattr(response, "usage_metadata", None)
    dusunme = getattr(meta, "thoughts_token_count", None) if meta is not None else None
    giris, cikis = translate._token_sayilari(response)
    kullanim = {"model": kullanilan, "giris": giris, "cikis": cikis,
                "dusunme": dusunme if isinstance(dusunme, int) else 0}
    neden = _bitis_nedeni(response)
    if neden not in ("STOP", "FinishReason.STOP", "stop"):
        raise YarimYanit(f"Defter yanıtı tamamlanmadı (bitiş: {neden}).", kullanim)
    return getattr(response, "text", None) or "", kullanim


def _isleme_yaz(conn, book_slug: str, bolum: int, durum: str, **alan) -> None:
    simdi = time.time()
    conn.execute(
        "INSERT INTO defter_isleme (book_slug, bolum, durum, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(book_slug, bolum) DO UPDATE SET durum = excluded.durum, updated_at = excluded.updated_at",
        (book_slug, bolum, durum, simdi),
    )
    for ad, deger in alan.items():
        conn.execute(f"UPDATE defter_isleme SET {ad} = ? WHERE book_slug = ? AND bolum = ?",
                     (deger, book_slug, bolum))


def _harcama_ekle(conn, book_slug: str, bolum: int, kullanim: dict) -> None:
    """Token sayaçları BİRİKİMLİDİR: yarıda kalan ve yeniden denenen çağrılar da ödenir."""
    if not kullanim:
        return
    conn.execute(
        "UPDATE defter_isleme SET model = COALESCE(?, model), giris_token = IFNULL(giris_token, 0) + ?, "
        "cikis_token = IFNULL(cikis_token, 0) + ?, dusunme_token = IFNULL(dusunme_token, 0) + ? "
        "WHERE book_slug = ? AND bolum = ?",
        (kullanim.get("model"), kullanim.get("giris") or 0, kullanim.get("cikis") or 0,
         kullanim.get("dusunme") or 0, book_slug, bolum),
    )


def bolum_isle(book_slug: str, bolum: int, *, cagir=None, kuru: bool = False, model: str | None = None) -> dict:
    """Bölümü işle: istem -> tek çağrı -> doğrulama -> `defter_iddia` (tek kısa yazma).

    `cagir(user, model) -> (metin, kullanım)` testte sahte modeli verir. `kuru`: API'siz
    yalnız istem boyutu (token tahmini ~ karakter/3,5). Model çağrısı transaction DIŞINDA:
    okuma süren veritabanını kilitlemez. Hata çeviriyi etkilemez; durum kaydına düşer."""
    model = model or model_adi()
    conn = _connect()
    try:
        metin = bolum_metni(book_slug, bolum, conn)
        if isinstance(metin, str):
            if not kuru:
                _isleme_yaz(conn, book_slug, bolum, "hizasiz" if metin == "hizasiz" else "atlandi",
                            istem_surumu=ISTEM_SURUMU)
                conn.commit()
            return {"bolum": bolum, "durum": metin}
        en_p, tr_p = metin
        satirlar, yazimlar = _sozluk_gorunumu(book_slug)
        kayitli = kayit_defteri(book_slug, bolum, "\n\n".join(en_p), satirlar, yazimlar,
                                _takma_adlar(book_slug, bolum, conn))
        adaylar = hitap_adaylari(en_p, tr_p)
        user = istem_kur(bolum, kayitli, en_p, tr_p, adaylar)
        if kuru:
            return {"bolum": bolum, "durum": "kuru", "istem_karakter": len(user) + len(DEFTER_TALIMATI),
                    "tahmini_giris": round((len(user) + len(DEFTER_TALIMATI)) / 3.5),
                    "kayitli": len(kayitli), "hitap_adayi": len(adaylar)}
        onceki = conn.execute("SELECT deneme FROM defter_isleme WHERE book_slug = ? AND bolum = ?",
                              (book_slug, bolum)).fetchone()
        deneme = (onceki[0] if onceki else 0) + 1
        _isleme_yaz(conn, book_slug, bolum, "processing", deneme=deneme, istem_surumu=ISTEM_SURUMU)
        conn.commit()
    finally:
        conn.close()

    basla = time.time()
    try:
        ham, kullanim = (cagir or _model_cagir)(user, model)
        veri = ayristir(ham)
    except Exception as hata:  # noqa: BLE001 — çıkarım hatası kayda düşer, akışı düşürmez
        conn = _connect()
        try:
            _isleme_yaz(conn, book_slug, bolum, "failed" if deneme >= EN_COK_DENEME else "pending",
                        hata=f"{type(hata).__name__}: {hata}"[:400], sure_sn=round(time.time() - basla, 2))
            _harcama_ekle(conn, book_slug, bolum, getattr(hata, "kullanim", None) or {})
            conn.commit()
        finally:
            conn.close()
        return {"bolum": bolum, "durum": "hata", "hata": str(hata)[:400], "deneme": deneme}

    cozucu = _Cozucu(book_slug, kayitli)
    kayitlar = (
        [dogrula("varlik", o, en_p, tr_p, cozucu) for o in veri["v"] if isinstance(o, dict)]
        + [dogrula("bag", o, en_p, tr_p, cozucu) for o in veri["b"] if isinstance(o, dict)]
        + [dogrula("hitap", o, en_p, tr_p, cozucu) for o in veri["h"] if isinstance(o, dict)]
        + _genel_kayitlari(veri["g"], kayitli)
    )
    sayac = Counter(k["tur"] for k in kayitlar)
    gecersiz = Counter(k["red_nedeni"] for k in kayitlar if not k["gecerli"])
    metrik = {"iddia": dict(sayac), "gecersiz": sum(gecersiz.values()), "red": dict(gecersiz),
              "kayitli": len(kayitli), "hitap_adayi": len(adaylar)}
    simdi = time.time()
    conn = _connect()
    try:
        conn.execute("DELETE FROM defter_iddia WHERE book_slug = ? AND bolum = ?", (book_slug, bolum))
        conn.executemany(
            "INSERT INTO defter_iddia (book_slug, bolum, tur, ozne_ad, ozne_kimlik, iliski, nesne_ad, "
            "nesne_kimlik, deger, paragraf, en_alinti, tr_alinti, anlatim, gecerli, red_nedeni, "
            "istem_surumu, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(book_slug, bolum, k["tur"], k.get("ozne_ad"), k.get("ozne_kimlik"), k.get("iliski"),
              k.get("nesne_ad"), k.get("nesne_kimlik"), json.dumps(k.get("deger") or {}, ensure_ascii=False),
              k.get("paragraf"), k.get("en_alinti"), k.get("tr_alinti"), k.get("anlatim"),
              k["gecerli"], k["red_nedeni"], ISTEM_SURUMU, simdi) for k in kayitlar],
        )
        _isleme_yaz(conn, book_slug, bolum, "completed", sure_sn=round(simdi - basla, 2), hata=None,
                    metrik=json.dumps(metrik, ensure_ascii=False))
        _harcama_ekle(conn, book_slug, bolum, kullanim)
        conn.commit()
    finally:
        conn.close()
    return {"bolum": bolum, "durum": "completed", **metrik, "kullanim": kullanim,
            "sure_sn": round(simdi - basla, 2)}


# ---------- birikim ----------
def _kucuk_harf_orani(book_slug: str, ad: str, bolumler: set[int], conn) -> float:
    """Adın, iddiaların geçtiği bölümlerde küçük harfle (cins ad olarak) kullanım oranı."""
    if not bolumler:
        return 0.0
    yer = ", ".join("?" for _ in bolumler)
    satirlar = conn.execute(
        f"SELECT source_text FROM chapters WHERE book_slug = ? AND chapter_no IN ({yer})",
        (book_slug, *sorted(bolumler)),
    ).fetchall()
    desen = translate._term_regex(ad)
    buyuk = kucuk = 0
    for (metin,) in satirlar:
        for m in desen.finditer(metin or ""):
            if m.group(0)[:1].islower():
                kucuk += 1
            else:
                buyuk += 1
    return kucuk / (buyuk + kucuk) if buyuk + kucuk else 0.0


def guven_hesapla(bolumler: set[int], anlatimlar: set[str]) -> float:
    if len(bolumler) >= 2:
        return 1.0
    return 0.8 if "anlatici" in anlatimlar else 0.5


def uzlastir(book_slug: str) -> dict:
    """Geçerli bağ ve takma ad iddialarını `varlik_bag`a ADAY olarak birleştir (API'siz, idempotent).

    Destek = iddianın geçtiği FARKLI bölüm sayısı. Güven 1,0 (≥2 bölüm) / 0,8 (tek bölüm,
    anlatıcı) / 0,5 (tek bölüm, konuşma). Takma adda kayıt kişi/örgüt/yer değilse ya da ad
    bölümlerde ≥%30 küçük harfle geçiyorsa (cins ad) güven 0,6'yı geçmez. `bag_ekle`
    reddedilmiş bağı diriltmez, `ilk_bolum`u yalnız küçültür."""
    conn = _connect()
    try:
        satirlar = conn.execute(
            "SELECT tur, ozne_kimlik, iliski, nesne_kimlik, bolum, anlatim, en_alinti, nesne_ad "
            "FROM defter_iddia WHERE book_slug = ? AND gecerli = 1 AND tur IN ('bag', 'varlik') "
            "AND ozne_kimlik IS NOT NULL AND nesne_kimlik IS NOT NULL AND iliski IS NOT NULL",
            (book_slug,),
        ).fetchall()
        turler = {r[0]: r[1] for r in conn.execute(
            "SELECT kimlik, tur FROM glossary WHERE book_slug = ?", (book_slug,))}
        gruplar: dict[tuple, dict] = {}
        for tur, ok, iliski, nk, bolum, anlatim, alinti, nad in satirlar:
            if tur == "varlik":  # "ad, asil'in takma adı": asıl -> takma_adi -> ad
                anahtar, anlatim = (nk, "takma_adi", ok), "anlatici"
            else:
                anahtar = (ok, iliski, nk)
            g = gruplar.setdefault(anahtar, {"bolumler": set(), "anlatim": set(), "kanit": (10**9, None)})
            g["bolumler"].add(bolum)
            g["anlatim"].add(anlatim or "konusma")
            if bolum < g["kanit"][0]:
                g["kanit"] = (bolum, alinti)
        yazilan = yeni = 0
        vconn = varlik_grafigi._connect()
        try:
            for (kaynak, iliski, hedef), g in gruplar.items():
                if kaynak == hedef:
                    continue
                guven = guven_hesapla(g["bolumler"], g["anlatim"])
                if iliski in ("takma_adi", "gercek_adi"):
                    ad = conn.execute("SELECT source FROM glossary WHERE book_slug = ? AND kimlik = ?",
                                      (book_slug, hedef)).fetchone()
                    if (turler.get(hedef) not in _BIRLESEBILIR_TURLER
                            or (ad and _kucuk_harf_orani(book_slug, ad[0], g["bolumler"], conn) >= 0.3)):
                        guven = min(guven, 0.6)
                if varlik_grafigi.bag_ekle(book_slug, kaynak, iliski, hedef, min(g["bolumler"]),
                                           g["kanit"][1], "model", guven=guven, durum="aday", conn=vconn):
                    yeni += 1
                yazilan += 1
            vconn.commit()
        finally:
            vconn.close()
    finally:
        conn.close()
    return {"grup": len(gruplar), "yazilan": yazilan, "yeni": yeni, "tur_dolan": tur_doldur(book_slug)}


# ---------- hitap ----------
def _uc(kimlik: str | None, ad: str | None) -> str:
    return kimlik or "ad:" + glossary.fold_term(ad or "")


KARARLI_EN_AZ = 3
KARARLI_ORAN = 0.8
HITAP_PENCERE = 15


def hitap_tablosu(book_slug: str, en_cok_bolum: int | None = None, conn=None) -> dict:
    """(konuşan, muhatap) -> çevirinin o çifte kullandığı biçim. Yalnız `en_cok_bolum`a kadar
    (dahil) — bölüm N'nin kartları N−1 ile kurulur, gelecek bilgisi sızmaz.

    Çift başına SON `HITAP_PENCERE` kayıt; ≥3 kayıt ve ≥%80 uyum "kararlı" sayılır. Elle
    karar (`defter_hitap_karar`) varsa o geçerlidir: tablo geçmiş çeviriyi ölçer, doğruyu değil."""
    kendi = conn is None
    conn = conn or _connect()
    try:
        sinir = en_cok_bolum if en_cok_bolum is not None else 10**9
        satirlar = conn.execute(
            "SELECT ozne_kimlik, ozne_ad, nesne_kimlik, nesne_ad, deger, bolum FROM defter_iddia "
            "WHERE book_slug = ? AND tur = 'hitap' AND gecerli = 1 AND bolum <= ? ORDER BY bolum DESC, id DESC",
            (book_slug, sinir),
        ).fetchall()
        kararlar = conn.execute(
            "SELECT konusan, muhatap, hitap, ilk_bolum FROM defter_hitap_karar WHERE book_slug = ? "
            "AND ilk_bolum <= ? ORDER BY ilk_bolum",
            (book_slug, sinir),
        ).fetchall()
    finally:
        if kendi:
            conn.close()
    ciftler: dict[tuple, dict] = {}
    for ok, oad, nk, nad, deger, bolum in satirlar:
        bicim = (json.loads(deger or "{}") or {}).get("f")
        c = ciftler.setdefault((_uc(ok, oad), _uc(nk, nad)), {
            "konusan": oad, "muhatap": nad, "kayitlar": [], "son_bolum": bolum})
        if bicim in ("sen", "siz") and len(c["kayitlar"]) < HITAP_PENCERE:
            c["kayitlar"].append(bicim)
    out = {}
    for anahtar, c in ciftler.items():
        sayac = Counter(c["kayitlar"])
        n = sum(sayac.values())
        bicim, adet = sayac.most_common(1)[0] if n else (None, 0)
        oran = adet / n if n else 0.0
        out[anahtar] = {"konusan": c["konusan"], "muhatap": c["muhatap"], "bicim": bicim, "n": n,
                        "oran": round(oran, 2), "son_bolum": c["son_bolum"], "elle": False,
                        "kararli": n >= KARARLI_EN_AZ and oran >= KARARLI_ORAN}
    for konusan, muhatap, hitap, ilk in kararlar:
        k = out.setdefault((konusan, muhatap), {"konusan": konusan, "muhatap": muhatap, "n": 0,
                                                "oran": 1.0, "son_bolum": ilk})
        k.update(bicim=hitap, elle=True, kararli=True)
    return out


def hitap_karari_yaz(book_slug: str, konusan: str, muhatap: str, hitap: str, ilk_bolum: int) -> None:
    if hitap not in ("sen", "siz"):
        raise ValueError(f"Bilinmeyen hitap: {hitap!r}")
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO defter_hitap_karar (book_slug, konusan, muhatap, hitap, ilk_bolum, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(book_slug, konusan, muhatap, ilk_bolum) "
            "DO UPDATE SET hitap = excluded.hitap, created_at = excluded.created_at",
            (book_slug, konusan, muhatap, hitap, int(ilk_bolum), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def hitap_sapmalari(book_slug: str, bolum: int, conn=None) -> list[dict]:
    """Bölümün hitapları, ÖNCEKİ bölümlere göre kararlı tabloyla çelişiyor mu (yalnız işaret)."""
    kendi = conn is None
    conn = conn or _connect()
    try:
        tablo = hitap_tablosu(book_slug, bolum - 1, conn)
        satirlar = conn.execute(
            "SELECT ozne_kimlik, ozne_ad, nesne_kimlik, nesne_ad, deger, paragraf, tr_alinti "
            "FROM defter_iddia WHERE book_slug = ? AND bolum = ? AND tur = 'hitap' AND gecerli = 1",
            (book_slug, bolum),
        ).fetchall()
    finally:
        if kendi:
            conn.close()
    out = []
    for ok, oad, nk, nad, deger, paragraf, tra in satirlar:
        bicim = (json.loads(deger or "{}") or {}).get("f")
        t = tablo.get((_uc(ok, oad), _uc(nk, nad)))
        if t and t["kararli"] and bicim in ("sen", "siz") and bicim != t["bicim"]:
            out.append({"konusan": oad, "muhatap": nad, "paragraf": paragraf, "bicim": bicim,
                        "beklenen": t["bicim"], "alinti": tra, "elle": t["elle"]})
    return out


def hitap_denetle(book_slug: str, bolum: int) -> list[dict]:
    """Sapmaları bölümün işleme kaydına (`metrik.hitap_sapma`) yaz. DÜZELTMEZ (Saint dersi:
    yanılabilen bir karar metni kendiliğinden değiştirmemeli)."""
    conn = _connect()
    try:
        sapma = hitap_sapmalari(book_slug, bolum, conn)
        satir = conn.execute("SELECT metrik FROM defter_isleme WHERE book_slug = ? AND bolum = ?",
                             (book_slug, bolum)).fetchone()
        if satir is not None:
            metrik = json.loads(satir[0] or "{}")
            metrik["hitap_sapma"] = sapma[:20]
            conn.execute("UPDATE defter_isleme SET metrik = ? WHERE book_slug = ? AND bolum = ?",
                         (json.dumps(metrik, ensure_ascii=False), book_slug, bolum))
            conn.commit()
        return sapma
    finally:
        conn.close()


# ---------- sözlüğe katkı (Faz 2) ----------
# Defter sözlüğü DEĞİŞTİRMEZ (tek istisna: boş `tur`, `tur_doldur`). Katkısı inceleme listesine
# giden nedenlerdir; karar kullanıcınındır. Eşikler tek bölümlük gürültüyü eler: v11'in
# inceleme listesini her iddiayla doldurması tekrarlanmasın.
GENEL_EN_AZ = 3
TAKMA_EN_AZ = 2
KARSILIK_EN_AZ = 3
KARSILIK_ORAN = 0.25
TUR_EN_AZ = 2
TUR_ORAN = 0.7
_CELISEN = ("yoldasi", "dusmani")


def _tr_govde(metin: str) -> str:
    """Türkçe adın gövdesi: kesme işaretinden sonrası (ek) atılır, harf işaretleri düzlenir."""
    return _katla(re.split(r"['’]", metin or "")[0]).strip()


def _ayni_karsilik(form: str, hedef: str) -> bool:
    if not form or not hedef:
        return True
    return form == hedef or form.startswith(hedef[: max(4, len(hedef) - 2)]) or hedef.startswith(form)


def _bolum_ornegi(bolumler) -> str:
    return ", ".join(str(b) for b in sorted(bolumler)[:4]) + ("…" if len(bolumler) > 4 else "")


def sozluk_nedenleri(book_slug: str) -> dict[str, list[dict]]:
    """{kaynak: [neden]} — `varlik_grafigi.kalite_nedenleri` üzerinden inceleme listesine girer.

    * `grafik_genel_sozcuk`: kayıt ≥3 bölümde sıradan sözcük olarak geçti, hiç ad olarak geçmedi.
    * `grafik_takma_ad`: ≥2 bölümde başka bir kaydın takma adı/lakabı olarak geçti, karar verilmedi.
    * `grafik_kosul_onerisi`: çevirilerde kayıttan farklı bir karşılık ≥3 bölümde ve ≥%25 yerleşmiş.
    * `grafik_celiski`: iki kişi ≥2 bölümde yoldaş, ≥2 bölümde düşman olarak geçti."""
    conn = _connect()
    try:
        satirlar = {r[0]: {"source": r[1], "target": r[2]} for r in conn.execute(
            "SELECT kimlik, source, target FROM glossary WHERE book_slug = ? AND kimlik IS NOT NULL", (book_slug,))}
        iddia = conn.execute(
            "SELECT tur, ozne_kimlik, iliski, nesne_kimlik, bolum, deger FROM defter_iddia "
            "WHERE book_slug = ? AND gecerli = 1 AND ozne_kimlik IS NOT NULL", (book_slug,),
        ).fetchall()
        try:
            karar = {(r[0], r[1]): r[2] for r in conn.execute(
                "SELECT kaynak_kimlik, hedef_kimlik, durum FROM varlik_bag WHERE book_slug = ? "
                "AND iliski IN ('takma_adi', 'gercek_adi') AND durum IN ('onaylandi', 'reddedildi')",
                (book_slug,))}
        except Exception:  # noqa: BLE001 — varlik_bag yoksa karar da yok
            karar = {}
    finally:
        conn.close()
    genel, ad, takma = defaultdict(set), defaultdict(set), defaultdict(set)
    formlar: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    iliski_b: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for tur, ok, iliski, nk, bolum, deger in iddia:
        if tur == "genel":
            genel[ok].add(bolum)
        elif tur == "varlik":
            ad[ok].add(bolum)
            form = _tr_govde((json.loads(deger or "{}") or {}).get("tr", ""))
            if form:
                formlar[ok][form].add(bolum)
            if nk and nk != ok:
                takma[(nk, ok)].add(bolum)
        elif tur == "bag" and iliski in _CELISEN and nk:
            iliski_b[tuple(sorted((ok, nk)))][iliski].add(bolum)
    out: dict[str, list[dict]] = defaultdict(list)

    def ekle(kimlik, neden):
        if kimlik in satirlar:
            out[satirlar[kimlik]["source"]].append(neden)

    for k, bolumler in genel.items():
        if len(bolumler) >= GENEL_EN_AZ and not ad.get(k):
            ekle(k, {"tur": "grafik_genel_sozcuk", "aciklama":
                     f"{len(bolumler)} bölümde ad olarak değil sıradan sözcük olarak geçti (bölüm "
                     f"{_bolum_ornegi(bolumler)}); hiç ad olarak geçmedi. Kural olarak kalırsa sıradan "
                     "kelimeye özel karşılık basılabilir: koşul ekle ya da kaydı kaldır."})
    for (asil, takma_k), bolumler in takma.items():
        if len(bolumler) < TAKMA_EN_AZ or (asil, takma_k) in karar or asil not in satirlar:
            continue
        ekle(takma_k, {"tur": "grafik_takma_ad", "aciklama":
                       f"'{satirlar[asil]['source']}' için takma ad/lakap olarak geçiyor ({len(bolumler)} bölüm: "
                       f"{_bolum_ornegi(bolumler)}). Aynı kişiyse 'Aynı kişi' de; değilse 'Ayrı'.",
                       "ilgili": [satirlar[asil]["source"]], "asil_kimlik": asil, "takma_kimlik": takma_k})
    for k, dagilim in formlar.items():
        if k not in satirlar:
            continue
        hedef = _tr_govde(satirlar[k]["target"] or "")
        toplam = len(set().union(*dagilim.values()))
        for form, bolumler in sorted(dagilim.items(), key=lambda x: -len(x[1])):
            if (not _ayni_karsilik(form, hedef) and len(bolumler) >= KARSILIK_EN_AZ
                    and len(bolumler) / toplam >= KARSILIK_ORAN):
                ekle(k, {"tur": "grafik_kosul_onerisi", "aciklama":
                         f"Çevirilerde kayıttaki '{satirlar[k]['target']}' yerine '{form}' de yerleşmiş "
                         f"({len(bolumler)}/{toplam} bölüm: {_bolum_ornegi(bolumler)}). Bağlama göre "
                         "değişiyorsa koşul ekle; değişmiyorsa çeviri sözlüğe uymamış olabilir."})
                break
    for (a, b), dagilim in iliski_b.items():
        if all(len(dagilim.get(r, ())) >= 2 for r in _CELISEN):
            for x, y in ((a, b), (b, a)):
                if y in satirlar:
                    ekle(x, {"tur": "grafik_celiski", "aciklama":
                             f"'{satirlar[y]['source']}' ile hem yoldaş ({len(dagilim['yoldasi'])} bölüm) hem "
                             f"düşman ({len(dagilim['dusmani'])} bölüm) olarak geçiyor; ilişki zamanla "
                             "değişmiş olabilir.", "ilgili": [satirlar[y]["source"]]})
    return dict(out)


def takma_ad_karari(book_slug: str, asil: str, takma_k: str, karar: str) -> bool:
    """Kullanıcı kararı. `ayni`: elle onaylı takma ad bağı + bağların asıl kişiye taşınması.
    `ayri`: bağ reddedilir; `bag_ekle` reddedilmiş bağı diriltmediği için bir daha önerilmez."""
    if karar not in ("ayni", "ayri"):
        raise ValueError("karar: ayni | ayri")
    if karar == "ayni":
        varlik_grafigi.bag_ekle(book_slug, asil, "takma_adi", takma_k, None, None, "manual")
        varlik_grafigi.takma_adlari_birlestir(book_slug)
        return True
    if not varlik_grafigi.bag_durumu(book_slug, asil, "takma_adi", takma_k, "reddedildi"):
        varlik_grafigi.bag_ekle(book_slug, asil, "takma_adi", takma_k, None, None, "manual", durum="reddedildi")
    return True


def tur_doldur(book_slug: str) -> int:
    """BOŞ `tur`u, ≥2 bölümde ve ≥%70 aynı tür görülmüşse doldurur (`tanim_yaz(yalniz_bossa)`:
    kullanıcının yazdığını ezmez). Tür çeviri istemine girmez; doğrulamanın yolu da budur."""
    conn = _connect()
    try:
        satirlar = {r[0]: r[1] for r in conn.execute(
            "SELECT kimlik, source FROM glossary WHERE book_slug = ? AND (tur IS NULL OR tur = '')",
            (book_slug,))}
        iddia = conn.execute(
            "SELECT ozne_kimlik, bolum, deger FROM defter_iddia WHERE book_slug = ? AND tur = 'varlik' "
            "AND gecerli = 1 AND ozne_kimlik IS NOT NULL", (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    turler: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for k, bolum, deger in iddia:
        if k in satirlar:
            turler[k][(json.loads(deger or "{}") or {}).get("t") or "diger"].add(bolum)
    yazilan = 0
    for k, dagilim in turler.items():
        tur, bolumler = max(dagilim.items(), key=lambda x: len(x[1]))
        toplam = sum(len(v) for v in dagilim.values())
        if len(bolumler) >= TUR_EN_AZ and len(bolumler) / toplam >= TUR_ORAN and tur != "diger":
            yazilan += bool(glossary.tanim_yaz(book_slug, satirlar[k], None, tur=tur, yalniz_bossa=True))
    return yazilan


def kart(book_slug: str, kimlik: str | None, en_cok_bolum: int | None = None) -> dict | None:
    """Doğrulama bağlamı için kısa kimlik kartı: tür dağılımı, takma adlar, çevirideki biçimler.
    YALNIZ BAĞLAMDIR (karar verdirmez); `baglam_hash`e girmez."""
    if not kimlik:
        return None
    conn = _connect()
    try:
        sinir = en_cok_bolum if en_cok_bolum is not None else 10**9
        iddia = conn.execute(
            "SELECT deger, nesne_ad, bolum FROM defter_iddia WHERE book_slug = ? AND tur = 'varlik' "
            "AND gecerli = 1 AND ozne_kimlik = ? AND bolum <= ?", (book_slug, kimlik, sinir),
        ).fetchall()
    finally:
        conn.close()
    if not iddia:
        return None
    turler, formlar, asil = Counter(), Counter(), Counter()
    for deger, nesne_ad, _b in iddia:
        d = json.loads(deger or "{}") or {}
        turler[d.get("t") or "diger"] += 1
        if d.get("tr"):
            formlar[_tr_govde(d["tr"])] += 1
        if nesne_ad:
            asil[nesne_ad] += 1
    return {"bolum": len({b for *_x, b in iddia}), "tur": dict(turler.most_common(3)),
            "ceviride": dict(formlar.most_common(3)), "takma_adi_oldugu": dict(asil.most_common(2))}


# ---------- ölçüm (API'siz) ----------
_CAPTAIN = re.compile(r"\bCaptain\b")


def taban_olcumu(book_slug: str) -> dict:
    """Defterden ÖNCEKİ durum, hizalı paragraflardan (API'siz): Captain'ın karşılıkları,
    konuşmalarda ve Spell mesajlarında sen/siz dağılımı. Faz 3'ün karşılaştırma tabanı."""
    conn = db.connect()
    try:
        satirlar = conn.execute(
            "SELECT chapter_no, source_text, translation FROM chapters WHERE book_slug = ? "
            "AND source_text IS NOT NULL AND translation IS NOT NULL AND IFNULL(content_type, 'text') != 'html'",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    out = {"bolum": 0, "hizasiz": 0, "captain": Counter(), "diyalog": Counter(), "spell": Counter()}
    for _no, en, tr in satirlar:
        en_p, tr_p = en.split("\n\n"), tr.split("\n\n")
        if len(en_p) != len(tr_p):
            out["hizasiz"] += 1
            continue
        out["bolum"] += 1
        for e, t in zip(en_p, tr_p):
            k = _tr_kucuk(t)
            if _CAPTAIN.search(e):
                out["captain"]["yüzbaşı" if "yüzbaşı" in k else "kaptan" if "kaptan" in k else "diğer"] += 1
            sen, siz = hitap_isaretleri(t)
            bicim = "ikisi" if sen and siz else "sen" if sen else "siz" if siz else None
            if not bicim:
                continue
            if e.lstrip().startswith("["):
                out["spell"][bicim] += 1
            elif _TIRNAK.search(e):
                out["diyalog"][bicim] += 1
    return {a: dict(v) if isinstance(v, Counter) else v for a, v in out.items()}


def metrik(book_slug: str) -> dict:
    """İşleme, iddia, maliyet, hitap tutarlılığı ve bağ adayı özeti."""
    from . import kullanim

    conn = _connect()
    try:
        isleme = conn.execute(
            "SELECT bolum, durum, model, IFNULL(giris_token, 0), IFNULL(cikis_token, 0), "
            "IFNULL(dusunme_token, 0), sure_sn FROM defter_isleme WHERE book_slug = ?", (book_slug,),
        ).fetchall()
        iddia = conn.execute(
            "SELECT tur, gecerli, red_nedeni, COUNT(*) FROM defter_iddia WHERE book_slug = ? GROUP BY 1, 2, 3",
            (book_slug,),
        ).fetchall()
        tamam = [r[0] for r in isleme if r[1] == "completed"]
        sapma = toplam_hitap = 0
        for bolum in tamam:
            tablo = hitap_tablosu(book_slug, bolum - 1, conn)
            for ok, oad, nk, nad, deger in conn.execute(
                "SELECT ozne_kimlik, ozne_ad, nesne_kimlik, nesne_ad, deger FROM defter_iddia WHERE book_slug = ? "
                "AND bolum = ? AND tur = 'hitap' AND gecerli = 1", (book_slug, bolum),
            ):
                bicim = (json.loads(deger or "{}") or {}).get("f")
                t = tablo.get((_uc(ok, oad), _uc(nk, nad)))
                if t and t["kararli"] and bicim in ("sen", "siz"):
                    toplam_hitap += 1
                    sapma += bicim != t["bicim"]
        tablo = hitap_tablosu(book_slug, None, conn)
    finally:
        conn.close()
    durumlar = Counter(r[1] for r in isleme)
    maliyet = sum(kullanim._maliyet(r[2], r[3], r[4]) for r in isleme if r[2])
    sureler = [r[6] for r in isleme if r[1] == "completed" and r[6]]
    turler: dict[str, dict] = defaultdict(lambda: {"gecerli": 0, "gecersiz": 0})
    red = Counter()
    for tur, gecerli, neden, n in iddia:
        turler[tur]["gecerli" if gecerli else "gecersiz"] += n
        if not gecerli:
            red[neden] += n
    try:
        baglar = [b for b in varlik_grafigi.baglar(book_slug, durumlar=("aday", "onaylandi", "reddedildi"))
                  if b["origin"] == "model"]
    except Exception:  # noqa: BLE001
        baglar = []
    return {
        "isleme": dict(durumlar), "tamamlanan": len(tamam),
        "token": {"giris": sum(r[3] for r in isleme), "cikis": sum(r[4] for r in isleme),
                  "dusunme": sum(r[5] for r in isleme)},
        "maliyet_usd": round(maliyet, 4),
        "bolum_basina_usd": round(maliyet / len(tamam), 5) if tamam else None,
        "ort_sure_sn": round(sum(sureler) / len(sureler), 1) if sureler else None,
        "iddia": dict(turler), "red": dict(red),
        "hitap": {"cift": len(tablo), "kararli_cift": sum(1 for t in tablo.values() if t["kararli"]),
                  "kararli_karsi_kayit": toplam_hitap, "sapma": sapma,
                  "sapma_orani": round(sapma / toplam_hitap, 3) if toplam_hitap else None},
        "model_baglari": dict(Counter(f"{b['iliski']}@{b['guven']}" for b in baglar).most_common(40)),
    }


def denetim_ornegi(book_slug: str, adet: dict[str, int], tohum: int = 7) -> list[dict]:
    """Elle kesinlik denetimi için rastgele GEÇERLİ iddialar + paragraf metni. ROMAN METNİ
    içerir: çıktısı git'e girmez (yalnız yerel/scratch)."""
    import random

    rnd = random.Random(tohum)
    conn = _connect()
    try:
        out = []
        for tur, n in adet.items():
            satirlar = conn.execute(
                "SELECT bolum, ozne_ad, iliski, nesne_ad, deger, paragraf, en_alinti, tr_alinti, anlatim "
                "FROM defter_iddia WHERE book_slug = ? AND tur = ? AND gecerli = 1 ORDER BY id",
                (book_slug, tur),
            ).fetchall()
            for r in rnd.sample(satirlar, min(n, len(satirlar))):
                metin = bolum_metni(book_slug, r[0], conn)
                en = tr = ""
                if not isinstance(metin, str) and r[5]:
                    en, tr = metin[0][r[5] - 1], metin[1][r[5] - 1]
                out.append({"tur": tur, "bolum": r[0], "ozne": r[1], "iliski": r[2], "nesne": r[3],
                            "deger": json.loads(r[4] or "{}"), "paragraf": r[5], "en_alinti": r[6],
                            "tr_alinti": r[7], "anlatim": r[8], "en": en, "tr": tr})
        return out
    finally:
        conn.close()


# ---------- canlı kuyruk ----------
_KILIT = threading.Lock()
_CALISAN: set[str] = set()
SON_DURUM: dict[str, dict] = {}
OKUMA_BEKLEME_SN = 120


def kuyruga_ekle(book_slug: str, bolum) -> bool:
    """Çevrilen (ya da yeniden çevrilen) bölümü kuyruğa al ve işçiyi uyandır. ASLA fırlatmaz:
    defter çeviriyi geri almamalı."""
    try:
        if not acik_mi() or book_slug not in kitaplar() or type(bolum) is not int:
            return False
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO defter_isleme (book_slug, bolum, durum, deneme, updated_at) "
                "VALUES (?, ?, 'pending', 0, ?) ON CONFLICT(book_slug, bolum) DO UPDATE SET "
                "durum = 'pending', deneme = 0, updated_at = excluded.updated_at",
                (book_slug, bolum, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
        arka_planda_isle(book_slug)
        return True
    except Exception:  # noqa: BLE001
        return False


def _siradaki(book_slug: str) -> int | None:
    conn = _connect()
    try:
        satir = conn.execute(
            "SELECT bolum FROM defter_isleme WHERE book_slug = ? AND durum = 'pending' "
            "AND deneme < ? ORDER BY bolum LIMIT 1", (book_slug, EN_COK_DENEME),
        ).fetchone()
        return satir[0] if satir else None
    finally:
        conn.close()


def arka_planda_isle(book_slug: str) -> bool:
    """Kitap başına tek uçuşlu işçi: bekleyen bölümleri artan sırayla işler. Okuma (etkileşimli
    çeviri) sürerken bekler — kota okuyucunundur. Başladıysa True."""
    with _KILIT:
        if book_slug in _CALISAN:
            return False
        _CALISAN.add(book_slug)

    def is_():
        islenen = 0
        try:
            while True:
                bolum = _siradaki(book_slug)
                if bolum is None:
                    break
                bitis = time.time() + OKUMA_BEKLEME_SN
                while budget.etkilesimli_var() and time.time() < bitis:
                    time.sleep(2)
                # `threading.Thread` bağlamı KOPYALAMAZ: API kaydı amacı burada kurulur.
                with budget.DEFTER_SEM, api_durum.islem("karakter_defteri"):
                    sonuc = bolum_isle(book_slug, bolum)
                if sonuc["durum"] == "completed":
                    islenen += 1
                    hitap_denetle(book_slug, bolum)
                elif sonuc["durum"] == "hata":
                    time.sleep(60)  # kota/geçici arıza: geri çekil, sonra kalan denemeyle sür
            if islenen:
                uzlastir(book_slug)
            SON_DURUM[book_slug] = {"zaman": time.time(), "islenen": islenen}
        except Exception as hata:  # noqa: BLE001 — arka plan işi çeviriyi asla düşürmez
            SON_DURUM[book_slug] = {"zaman": time.time(), "hata": str(hata)[:300]}
        finally:
            with _KILIT:
                _CALISAN.discard(book_slug)

    threading.Thread(target=is_, name=f"karakter-defteri-{book_slug}", daemon=True).start()
    return True


def durum(book_slug: str) -> dict:
    conn = _connect()
    try:
        sayim = dict(conn.execute(
            "SELECT durum, COUNT(*) FROM defter_isleme WHERE book_slug = ? GROUP BY durum", (book_slug,)
        ).fetchall())
    finally:
        conn.close()
    return {"acik": acik_mi(), "calisiyor": book_slug in _CALISAN, "son": SON_DURUM.get(book_slug),
            "bolumler": sayim}
