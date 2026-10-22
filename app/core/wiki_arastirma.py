"""WİKİ ARAŞTIRMASI: yeni kitapta İLK iş, kitabın hayran wikisini bulup karakter sayfalarını
bölüm dipnotlarıyla saklamak (2026-10-22, kullanıcı isteği "yeni kitap okumaya başladığımda ilk
önce wiki araştırması yapsın").

Neden: defter kitabı yalnız okunan bölümlerden kurar; rün ekranı seyrek açıldığı için Sunny'nin
1090'daki Tiran sınıfı, kaybedilen anılar ve evrimleşen nitelikler kaçıyordu. Wiki DIŞ bir kontrol
kaynağıdır — doğruluğun tek kaynağı değil (hayran yazımı): kartta "wikiye göre" notu ve
"wikide olup defterde olmayan" adlar olarak görünür, defteri kendiliğinden DEĞİŞTİRMEZ.

SPOILER: Fandom sayfaları kitabın sonuna kadar her şeyi anlatır. Yalnız bölüm DİPNOTU olan
cümle saklanır (`<ref>Chapter 1090 Tyrant</ref>`); cümle, dipnotlarındaki EN BÜYÜK bölüm okuma
konumunu geçmiyorsa gösterilir. Dipnotsuz cümle hiç alınmaz (ne zaman olduğu bilinmez).

Erişim: Fandom MediaWiki API'si düz HTTP ile (ücretsiz, anahtarsız; sunucudan 200 ölçüldü).
Fandom'un arama API'si Cloudflare'e takılıyor (403); wiki adresi kitap adından tahmin edilir
(`shadowslave`, `solo-leveling` yönlendirmesi, `reincarnationofthestrongestswordgod`),
bulunamazsa elle verilir (`adres_yaz`)."""
from __future__ import annotations

import json
import os
import re
import threading
import time

from . import cache, db, glossary

UA = {"User-Agent": "NovelLink/1.0 (kisisel roman okuyucu; wiki dipnot denetimi)"}
ZAMAN_ASIMI = 20
SAYFA_LISTESI_EN_COK = 20000
ALT_SAYFA_EN_COK = 12        # "Sunny/Runes", "Sunny/Memories"…
BEKLEME = 0.5                # istekler arası (Fandom'a nazik ol)
YENIDEN_DENE_SN = 24 * 3600  # bulunamayan/hatalı wiki bir gün sonra yeniden aranır

SEMA = """
CREATE TABLE IF NOT EXISTS wiki_kaynak (
    book_slug TEXT PRIMARY KEY,
    adres TEXT,
    site_adi TEXT,
    durum TEXT NOT NULL,
    sayfalar TEXT,
    elle INTEGER NOT NULL DEFAULT 0,
    hata TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wiki_sayfa (
    book_slug TEXT NOT NULL,
    sayfa TEXT NOT NULL,
    cekildi REAL NOT NULL,
    PRIMARY KEY (book_slug, sayfa)
);
CREATE TABLE IF NOT EXISTS wiki_bilgi (
    book_slug TEXT NOT NULL,
    sayfa TEXT NOT NULL,
    sira INTEGER NOT NULL,
    metin TEXT NOT NULL,
    bolumler TEXT NOT NULL,
    en_buyuk INTEGER NOT NULL,
    PRIMARY KEY (book_slug, sayfa, sira)
);
CREATE INDEX IF NOT EXISTS wiki_bilgi_sayfa ON wiki_bilgi (book_slug, sayfa);
"""

_CALISAN: set[str] = set()
_KILIT = threading.Lock()


def _connect():
    conn = db.connect()
    conn.executescript(SEMA)
    return conn


def _getir(url: str, params: dict) -> dict | None:
    """MediaWiki API çağrısı; JSON değilse (404 sayfası, Cloudflare) None."""
    import requests

    r = requests.get(url, params={**params, "format": "json"}, headers=UA, timeout=ZAMAN_ASIMI)
    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        return None
    return r.json()


# ---------- wiki bulma ----------
def _sozcukler(metin: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (metin or "").casefold()) if w]


def aday_alt_alanlar(baslik: str, slug: str) -> list[str]:
    """Kitap adından Fandom alt alan adı adayları, olasılık sırasıyla."""
    sozcuk = _sozcukler(baslik) or _sozcukler(slug.replace("-", " "))
    adaylar = ["".join(sozcuk), "-".join(sozcuk), slug.lower(), "".join(_sozcukler(slug))]
    if len(sozcuk) >= 3:
        adaylar.append("".join(w[0] for w in sozcuk))  # "rotssg"
    out = []
    for a in adaylar:
        if a and a not in out:
            out.append(a)
    return out


def _site_uyar_mi(site_adi: str, baslik: str) -> bool:
    """Bulunan wiki gerçekten bu kitabın mı: site adı başlığın anlamlı sözcüklerini taşımalı."""
    dolgu = {"the", "of", "a", "an", "wiki", "and", "in", "to"}
    beklenen = {w for w in _sozcukler(baslik) if w not in dolgu}
    site = set(_sozcukler(site_adi))
    return bool(beklenen) and len(beklenen & site) >= max(1, (len(beklenen) + 1) // 2)


def wiki_bul(baslik: str, slug: str, getir=_getir) -> dict | None:
    """{"adres": ".../api.php", "site_adi": ...} ya da None."""
    for alt in aday_alt_alanlar(baslik, slug):
        adres = f"https://{alt}.fandom.com/api.php"
        try:
            veri = getir(adres, {"action": "query", "meta": "siteinfo"})
        except Exception:  # noqa: BLE001 — ağ hatası: sıradaki aday
            veri = None
        genel = ((veri or {}).get("query") or {}).get("general") or {}
        if genel.get("sitename") and _site_uyar_mi(genel["sitename"], baslik):
            # Yönlendirme (sololeveling -> solo-leveling) `server` alanında görünür.
            sunucu = genel.get("server") or f"https://{alt}.fandom.com"
            if sunucu.startswith("//"):
                sunucu = "https:" + sunucu
            return {"adres": f"{sunucu.rstrip('/')}{genel.get('scriptpath', '')}/api.php",
                    "site_adi": genel["sitename"]}
    return None


def sayfa_listesi(adres: str, getir=_getir) -> list[str]:
    sayfalar, devam = [], {}
    while len(sayfalar) < SAYFA_LISTESI_EN_COK:
        veri = getir(adres, {"action": "query", "list": "allpages", "aplimit": "500", **devam}) or {}
        sayfalar += [s["title"] for s in ((veri.get("query") or {}).get("allpages") or [])]
        devam = (veri.get("continue") or {})
        devam = {"apcontinue": devam["apcontinue"]} if "apcontinue" in devam else {}
        if not devam:
            break
    return sayfalar


# ---------- wikitext ayıklama ----------
_BOLUM = re.compile(r"\b(?:Chapter|Chapters|Ch\.?|Bölüm)\s*(\d{1,5})", re.IGNORECASE)
_REF = re.compile(r"<ref(?:\s+name\s*=\s*\"?([^\">/]+?)\"?)?\s*(?:/>|>(.*?)</ref>)", re.IGNORECASE | re.DOTALL)
_SABLON = re.compile(r"\{\{([^{}]*)\}\}")
_BAG = re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]]*)\]\]")
_ETIKET = re.compile(r"</?[a-zA-Z][^>]*>")
_SATIR_ETIKETI = re.compile(r"^\s*\|?\s*'''(.{1,60}?):?'''")


def _sablon(m: re.Match) -> str:
    """{{Color|#E3BE00|Aspect}} -> "Aspect"; argümansız şablon (TabViews) atılır."""
    parcalar = m.group(1).split("|")
    return parcalar[-1] if len(parcalar) > 1 else ""


def temizle(metin: str) -> str:
    for _ in range(3):  # iç içe şablon
        metin = _SABLON.sub(_sablon, metin)
    metin = _BAG.sub(lambda m: m.group(1), metin)
    metin = metin.replace("'''", "").replace("''", "")
    metin = re.sub(r"<br\s*/?>", " ", metin, flags=re.IGNORECASE)
    metin = _ETIKET.sub("", metin)
    metin = re.sub(r"&#91;|&lsqb;", "[", metin)
    metin = re.sub(r"&#93;|&rsqb;", "]", metin)
    metin = re.sub(r"^[|!{}\-\s]+", "", metin)          # tablo sözdizimi
    metin = re.sub(r"\s*\|\|\s*|\s*!!\s*", " · ", metin)
    metin = re.sub(r"\[\s+", "[", re.sub(r"\s+\]", "]", metin))
    return re.sub(r"\s+", " ", metin).strip(" ·")


def ayikla(wikitext: str) -> list[tuple[str, list[int]]]:
    """Dipnotlu cümleler: [(metin, [bölümler])]. Satır dipnot işaretlerinde bölünür; her parça
    kendisinden SONRA gelen dipnotların bölümlerini taşır, dipnotsuz kuyruk atılır. Satır bir
    etiketle başlıyorsa ("'''Shadow Cores:''' [2/7]<ref/> → [3/7]<ref/>") sonraki parçalar da
    etiketi taşır: "Shadow Cores: [3/7]"."""
    adlar: dict[str, list[int]] = {}
    for m in _REF.finditer(wikitext):
        if m.group(1) and m.group(2):
            adlar[m.group(1).strip()] = [int(x) for x in _BOLUM.findall(m.group(2))]
    out = []
    for satir in wikitext.split("\n"):
        if "<ref" not in satir.lower():
            continue
        e = _SATIR_ETIKETI.match(satir)
        etiket = temizle(e.group(1)).rstrip(":").strip() if e else ""
        parcalar, konum = [], 0
        for m in _REF.finditer(satir):
            bolumler = ([int(x) for x in _BOLUM.findall(m.group(2))] if m.group(2)
                        else adlar.get((m.group(1) or "").strip(), []))
            metin = temizle(satir[konum:m.start()])
            if metin or not parcalar:
                parcalar.append([metin, []])
            parcalar[-1][1] += bolumler  # art arda dipnotlar aynı parçanın
            konum = m.end()
        for i, (metin, bolumler) in enumerate(parcalar):
            if not metin or not bolumler:
                continue
            if i and etiket and not metin.startswith(etiket):
                metin = f"{etiket}: {metin.lstrip('→ ').strip()}"
            out.append((metin, sorted(set(bolumler))))
    return out


def sayfa_cek(book_slug: str, sayfa: str, getir=_getir, conn=None) -> int:
    """Sayfanın dipnotlu cümlelerini yaz (önceki satırlar yenilenir). Döner: cümle sayısı."""
    kendi = conn is None
    conn = conn or _connect()
    try:
        adres = (conn.execute("SELECT adres FROM wiki_kaynak WHERE book_slug = ?", (book_slug,)).fetchone()
                 or (None,))[0]
        if not adres:
            return 0
        veri = getir(adres, {"action": "parse", "page": sayfa, "prop": "wikitext", "redirects": "1"}) or {}
        wikitext = (((veri.get("parse") or {}).get("wikitext") or {}).get("*")) or ""
        cumleler = ayikla(wikitext)
        conn.execute("DELETE FROM wiki_bilgi WHERE book_slug = ? AND sayfa = ?", (book_slug, sayfa))
        conn.executemany(
            "INSERT INTO wiki_bilgi (book_slug, sayfa, sira, metin, bolumler, en_buyuk) VALUES (?, ?, ?, ?, ?, ?)",
            [(book_slug, sayfa, i, metin, json.dumps(b), max(b)) for i, (metin, b) in enumerate(cumleler)])
        conn.execute("INSERT INTO wiki_sayfa (book_slug, sayfa, cekildi) VALUES (?, ?, ?) "
                     "ON CONFLICT(book_slug, sayfa) DO UPDATE SET cekildi = excluded.cekildi",
                     (book_slug, sayfa, time.time()))
        conn.commit()
        return len(cumleler)
    finally:
        if kendi:
            conn.close()


# ---------- kaynak kaydı ----------
def kaynak(book_slug: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute("SELECT adres, site_adi, durum, sayfalar, elle, hata, updated_at FROM wiki_kaynak "
                         "WHERE book_slug = ?", (book_slug,)).fetchone()
    finally:
        conn.close()
    if r is None:
        return None
    return {"adres": r[0], "site_adi": r[1], "durum": r[2], "sayfalar": json.loads(r[3] or "[]"),
            "elle": bool(r[4]), "hata": r[5], "updated_at": r[6]}


def _kaynak_yaz(conn, book_slug: str, **alan) -> None:
    alan.setdefault("updated_at", time.time())
    sutunlar = ", ".join(alan)
    conn.execute(
        f"INSERT INTO wiki_kaynak (book_slug, {sutunlar}) VALUES (?, {', '.join('?' for _ in alan)}) "
        f"ON CONFLICT(book_slug) DO UPDATE SET {', '.join(f'{k} = excluded.{k}' for k in alan)}",
        (book_slug, *alan.values()))
    conn.commit()


def _baslik(book_slug: str) -> str:
    conn = cache._connect()
    try:
        r = conn.execute("SELECT book_title FROM chapters WHERE book_slug = ? AND book_title IS NOT NULL "
                         "AND book_title != '' ORDER BY chapter_no LIMIT 1", (book_slug,)).fetchone()
    finally:
        conn.close()
    return r[0] if r else book_slug.replace("-", " ")


def _kisi_adlari(book_slug: str) -> list[str]:
    """Sözlükteki kişi adları, en çok geçenden (defter iddialarından) başlayarak."""
    satirlar = [r for r in glossary.get_glossary_rows(book_slug) if r.get("tur") == "kisi"]
    conn = db.connect()
    try:
        sayi = dict(conn.execute(
            "SELECT ozne_kimlik, COUNT(DISTINCT bolum) FROM defter_iddia WHERE book_slug = ? AND tur = 'varlik' "
            "AND gecerli = 1 GROUP BY ozne_kimlik", (book_slug,)).fetchall())
    except Exception:  # noqa: BLE001 — defter tablosu henüz yoksa sıra sözlük sırasıdır
        sayi = {}
    finally:
        conn.close()
    satirlar.sort(key=lambda r: -sayi.get(r.get("kimlik"), 0))
    return [r["source"] for r in satirlar]


def karakter_sayfalari(sayfalar: list[str], adlar: list[str]) -> list[str]:
    """Adın kendi sayfası ve alt sayfaları ("Sunny", "Sunny/Runes"); Fandom büyük harfle başlatır."""
    katli = {glossary.fold_term(a) for a in adlar if a}
    ana = [s for s in sayfalar if glossary.fold_term(s.split("/")[0]) in katli]
    kok = [s for s in ana if "/" not in s]
    alt = [s for s in ana if "/" in s][:ALT_SAYFA_EN_COK * max(1, len(kok))]
    return kok + alt


def arastir(book_slug: str, getir=_getir, kisi_sayisi: int = 40, bekleme: float = BEKLEME) -> dict:
    """Wikiyi bul, sayfa listesini al, en çok geçen kişilerin sayfalarını dipnotlarıyla çek."""
    conn = _connect()
    try:
        mevcut = conn.execute("SELECT adres, site_adi, elle FROM wiki_kaynak WHERE book_slug = ?",
                              (book_slug,)).fetchone()
        if mevcut and mevcut[2] and mevcut[0]:
            bulunan = {"adres": mevcut[0], "site_adi": mevcut[1]}
        else:
            bulunan = wiki_bul(_baslik(book_slug), book_slug, getir)
        if bulunan is None:
            _kaynak_yaz(conn, book_slug, durum="yok", adres=None, site_adi=None, hata=None)
            return {"durum": "yok"}
        sayfalar = sayfa_listesi(bulunan["adres"], getir)
        _kaynak_yaz(conn, book_slug, durum="bulundu", adres=bulunan["adres"], site_adi=bulunan["site_adi"],
                    sayfalar=json.dumps(sayfalar, ensure_ascii=False), hata=None)
        cekilecek = karakter_sayfalari(sayfalar, _kisi_adlari(book_slug)[:kisi_sayisi])
        cumle = 0
        for s in cekilecek:
            cumle += sayfa_cek(book_slug, s, getir, conn)
            time.sleep(bekleme)
        return {"durum": "bulundu", "site_adi": bulunan["site_adi"], "sayfa": len(cekilecek), "cumle": cumle}
    except Exception as hata:  # noqa: BLE001 — ağ/ayrıştırma hatası kayda düşer, okuma etkilenmez
        _kaynak_yaz(conn, book_slug, durum="hata", hata=f"{type(hata).__name__}: {hata}"[:300])
        return {"durum": "hata", "hata": str(hata)[:300]}
    finally:
        conn.close()


def adres_yaz(book_slug: str, adres: str) -> None:
    """Elle wiki adresi ("https://x.fandom.com" ya da ".../api.php"): tahmin bulamadığında."""
    adres = adres.strip().rstrip("/")
    if not re.match(r"^https://[a-z0-9.-]+(/[^\s]*)?$", adres):
        raise ValueError("Geçersiz wiki adresi")
    if not adres.endswith("api.php"):
        adres += "/api.php"
    conn = _connect()
    try:
        _kaynak_yaz(conn, book_slug, durum="bekliyor", adres=adres, elle=1, hata=None)
    finally:
        conn.close()


# ---------- arka plan ----------
def _arka_planda(book_slug: str, is_) -> bool:
    with _KILIT:
        if book_slug in _CALISAN:
            return False
        _CALISAN.add(book_slug)

    def calis():
        try:
            is_()
        finally:
            with _KILIT:
                _CALISAN.discard(book_slug)

    threading.Thread(target=calis, name=f"wiki-{book_slug}", daemon=True).start()
    return True


def arka_planda_arastir(book_slug: str) -> bool:
    """Tek uçuşlu arka plan araştırması (elle tetik: `/api/book/{slug}/wiki`). Başladıysa True."""
    return _arka_planda(book_slug, lambda: arastir(book_slug))


def acik_mi() -> bool:
    return os.getenv("WIKI_ARASTIRMA", "1") != "0"


def gerekirse_baslat(book_slug: str) -> bool:
    """Bölüm önbelleğe girince (`pipeline`): kitabın wikisi hiç aranmadıysa — ya da bir gün önce
    bulunamadı/hata verdiyse — arka planda ara. Yeni kitapta İLK bölümde çalışır, profil
    çıkarımından (3. bölüm) önce. Ücretsiz; model çağrısı yok."""
    if not acik_mi():
        return False
    k = kaynak(book_slug)
    if k is not None and (k["durum"] == "bulundu" or time.time() - (k["updated_at"] or 0) < YENIDEN_DENE_SN) \
            and k["durum"] != "bekliyor":
        return False
    return arka_planda_arastir(book_slug)


def sayfa_gerekirse(book_slug: str, adlar: list[str]) -> bool:
    """Kart açılınca: kişinin wikide sayfası var ama henüz çekilmediyse arka planda çek."""
    if not acik_mi():
        return False
    k = kaynak(book_slug)
    if not k or k["durum"] != "bulundu":
        return False
    sayfalar = karakter_sayfalari(k["sayfalar"], adlar)
    if not sayfalar:
        return False
    conn = _connect()
    try:
        cekilmis = {r[0] for r in conn.execute("SELECT sayfa FROM wiki_sayfa WHERE book_slug = ?", (book_slug,))}
    finally:
        conn.close()
    eksik = [s for s in sayfalar if s not in cekilmis]
    if not eksik:
        return False

    def is_():
        for s in eksik:
            sayfa_cek(book_slug, s)
            time.sleep(BEKLEME)
    return _arka_planda(f"{book_slug}#sayfa", is_)


# ---------- kart ----------
_KOSELI_AD = re.compile(r"\[([A-Z][^\[\]]{1,60}?)\]")
_BAGLACLAR = frozenset({"of", "the", "a", "an", "and", "in", "from", "to", "with", "on", "for"})


def notlar(book_slug: str, adlar: list[str], konum: int | None) -> dict:
    """Kişinin wiki sayfalarından konuma kadar dipnotlu cümleler (spoiler yok). `durum`:
    yok | aranmadi | yukleniyor | hazir."""
    k = kaynak(book_slug)
    if k is None:
        return {"durum": "aranmadi", "notlar": []}
    if k["durum"] != "bulundu":
        return {"durum": k["durum"], "notlar": []}
    sayfalar = karakter_sayfalari(k["sayfalar"], adlar)
    if not sayfalar:
        return {"durum": "sayfa_yok", "site_adi": k["site_adi"], "notlar": []}
    conn = _connect()
    try:
        yer = ", ".join("?" for _ in sayfalar)
        cekilmis = {r[0] for r in conn.execute(
            f"SELECT sayfa FROM wiki_sayfa WHERE book_slug = ? AND sayfa IN ({yer})", (book_slug, *sayfalar))}
        satirlar = conn.execute(
            f"SELECT sayfa, metin, bolumler, en_buyuk FROM wiki_bilgi WHERE book_slug = ? AND sayfa IN ({yer}) "
            "AND en_buyuk <= ? ORDER BY en_buyuk, sayfa, sira",
            (book_slug, *sayfalar, konum if konum is not None else 10**9)).fetchall()
    finally:
        conn.close()
    # Yönlendirme sayfası ("Sunless" -> "Sunny") aynı cümleleri ikinci kez getirir.
    sonuc, gorulen = [], set()
    for s, m, b, e in satirlar:
        if (m, e) not in gorulen:
            gorulen.add((m, e))
            sonuc.append({"sayfa": s, "metin": m, "bolumler": json.loads(b), "bolum": e})
    return {"durum": "hazir" if cekilmis >= set(sayfalar) else "yukleniyor", "site_adi": k["site_adi"],
            "notlar": sonuc}


def eksik_adlar(notlar_: list[dict], bilinen: set[str]) -> list[dict]:
    """Wiki notlarında köşeli ad ([Shadow Lantern]) olup defterde hiç geçmeyenler: defterin
    kaçırdığını gösteren ucuz bir kontrol. Uzun köşeli metin (rün açıklaması) ad değildir."""
    gorulen: dict[str, dict] = {}
    for n in notlar_:
        for ad in _KOSELI_AD.findall(n["metin"]):
            ad = ad.strip().rstrip(".")
            # Ad başlık biçimindedir ("Feather of Truth"); "You cannot lie", "Blood Weave has
            # evolved" rün cümlesidir (gerçek sayfada ölçüldü).
            if len(ad.split()) > 6 or not all(w[:1].isupper() or w in _BAGLACLAR for w in ad.split()):
                continue
            if glossary.fold_term(ad) not in bilinen and ad not in gorulen:
                gorulen[ad] = {"ad": ad, "bolum": n["bolum"], "metin": n["metin"]}
    return list(gorulen.values())
