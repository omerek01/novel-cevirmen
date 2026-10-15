"""DEFTER KAYITLARI: rün mesajlarından anılar, efsunlar, nitelikler, gölgeler, yankılar,
öldürülen yaratıklar ve karakterin rün listesi — ve kullanıcının bunlara ELLE düzeltmeleri.

NEDEN AYRI TABLO (2026-10-15, kullanıcı isteği "bunlar da tutulsun", elle düzeltme/ekleme):
`varlik_grafigi.bolumden_sistem_baglari` aynı rünleri `varlik_bag`a yazıyor ama yalnız iki ucu
da SÖZLÜKTE kayıtlı olan bağları; sunucu kopyasında 990 bölümden 297 sistem bağı kaldı, sözlükte
olmayan anılar (Puppeteer's Shroud…) hiç tutulmadı. Defter sözlüğe otomatik kayıt AÇMAZ (karar
kullanıcının), bu yüzden kayıtlar burada ADIYLA tutulur; sözlükte karşılığı varsa okunurken eklenir.

Ayrıştırıcı yeniden yazılmadı: `varlik_grafigi.sistem_baglarini_bul` dörtlülerini kayda çevirir.
Kayıt kimliği `anahtar` = tür|sahip|ad|değer (katlanmış). İki köken: `sistem` (rünlerden,
`cikar` her koşuda baştan kurar) ve `elle` (kullanıcı). Aynı anahtarda elle kayıt sistem kaydını
gölgeler; `silindi=1` elle kayıt "kaldırıldı" demektir ve çıkarım onu diriltmez.

Spoiler: kayıt `ilk_bolum` ≤ konumda görünür; alanların (rütbe, kademe…) GEÇMİŞİ tutulur ve
konumdaki son değer gösterilir (Memory Tier sonradan yükseliyor)."""
from __future__ import annotations

import json
import re
import time

from . import cache, db, glossary, varlik_grafigi

TURLER = ("ani", "efsun", "nitelik", "golge", "yanki", "yaratik", "alan")
# Rün listesi satırları (`Name: X` bloğu) -> alan adı. Tekil alanlarda konumdaki son değer,
# çoklu alanlarda (yetenekler) hepsi gösterilir.
RUN_ALANLARI = ("gercek_adi", "rutbesi", "sinifi", "gorunusu", "kusuru", "ruya_capasi", "yetenegi")
COKLU_ALANLAR = frozenset({"yetenegi"})
LISTE_ALANLARI = frozenset({"nitelikler"})
_SAHIPLI = {"anisi": "ani", "golgesi": "golge", "yanki": "yanki"}
_ESYA_ALANI = {"rutbesi": "rutbe", "sinifi": "sinif", "esya_turu": "tur"}
_ACIKLAMA = re.compile(r"Enchantment Description:\s*\[?([^\]]+?)\]?\.?\s*$")
_TIRNAK = "\"'“”‘’ "


def _temiz(ad: str) -> str:
    """Rün değerinin kenar artıkları: "Cloud.." (yarım kalan mesaj), tırnaklar."""
    return (ad or "").strip().strip(_TIRNAK).rstrip(".…").strip()

SEMA = """
CREATE TABLE IF NOT EXISTS defter_kayit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_slug TEXT NOT NULL,
    anahtar TEXT NOT NULL,
    tur TEXT NOT NULL,
    sahip TEXT NOT NULL DEFAULT '',
    ad TEXT NOT NULL,
    deger TEXT NOT NULL DEFAULT '',
    alanlar TEXT,
    ilk_bolum INTEGER,
    kanit TEXT,
    origin TEXT NOT NULL,
    silindi INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    UNIQUE (book_slug, anahtar, origin)
);
CREATE INDEX IF NOT EXISTS defter_kayit_kitap ON defter_kayit (book_slug, tur);
"""


def _connect():
    conn = db.connect()
    conn.executescript(SEMA)
    return conn


def anahtar(tur: str, sahip: str, ad: str, deger: str = "") -> str:
    return "|".join((tur, glossary.fold_term(sahip or ""), glossary.fold_term(ad or ""),
                     glossary.fold_term(deger or "")))


# ---------- rünlerden kayıt ----------
class _Toplayici:
    """Dörtlüleri kayda çevirir; bölümler arasında anı/gölge adlarını hatırlar."""

    def __init__(self, esyalar: dict[str, str] | None = None):
        self.kayitlar: dict[str, dict] = {}
        self.esyalar = dict(esyalar or {})  # katlanmış ad -> ani|golge|yanki
        self.gorunusler: dict[str, str] = {}  # katlanmış Görünüş (Aspect) adı -> sahibi

    def _kayit(self, tur, sahip, ad, bolum, kanit, deger=""):
        a = anahtar(tur, sahip, ad, deger)
        k = self.kayitlar.get(a)
        if k is None:
            k = self.kayitlar[a] = {"anahtar": a, "tur": tur, "sahip": sahip, "ad": ad, "deger": deger,
                                    "alanlar": {}, "ilk_bolum": bolum, "kanit": kanit}
        elif bolum is not None and (k["ilk_bolum"] is None or bolum < k["ilk_bolum"]):
            k["ilk_bolum"], k["kanit"] = bolum, kanit
        return k

    def _esya(self, ad):
        """Daha önce sahiplik bloğuyla görülmüş anı/gölge/yankının kaydı (sahibiyle)."""
        tur = self.esyalar.get(glossary.fold_term(ad))
        if not tur:
            return None
        for k in self.kayitlar.values():
            if k["tur"] == tur and glossary.fold_term(k["ad"]) == glossary.fold_term(ad):
                return k
        return None

    def bolum(self, no: int | None, metin: str, ana: str, ana_adlar: tuple[str, ...]) -> None:
        dortluler = varlik_grafigi.sistem_baglarini_bul(metin, ana, ana_adlar)
        olduruldu: dict[str, dict] = {}
        for ozne, iliski, nesne, kanit in dortluler:
            if iliski in ("_evrim", "donustu", "turu") or not nesne:
                continue
            ozne = _temiz(ozne)
            if iliski != varlik_grafigi.DEGER:
                nesne = _temiz(nesne)
            if iliski == "gorunusu":
                self.gorunusler[glossary.fold_term(nesne)] = ozne
            elif iliski == "rutbesi" and glossary.fold_term(ozne) in self.gorunusler:
                # "Aspect Rank: Divine" Görünüşün rütbesidir; sahibinin rün listesine gider.
                sahip = self.gorunusler[glossary.fold_term(ozne)]
                self._kayit("alan", sahip, "gorunus_rutbesi", no, kanit, nesne)
                continue
            if iliski in _SAHIPLI:
                tur = _SAHIPLI[iliski]
                self.esyalar[glossary.fold_term(nesne)] = tur
                self._kayit(tur, ozne, nesne, no, kanit)
                continue
            if iliski == "oldurdu":
                olduruldu[glossary.fold_term(nesne)] = {"sahip": ozne, "ad": nesne, "kanit": kanit, "alan": {}}
                continue
            esya = self._esya(ozne)
            if iliski == varlik_grafigi.DEGER:
                ad, deger = nesne.split("\t", 1)
                if esya is not None and ad == "Memory Tier":
                    _alan_ekle(esya, "kademe", deger, no)
                elif esya is None:
                    _alan_ekle(self._kayit("alan", ozne, ad, no, kanit, deger), "deger", deger, no)
                continue
            if esya is not None:
                if iliski == "efsunu":
                    e = self._kayit("efsun", esya["ad"], nesne, no, kanit)
                    m = _ACIKLAMA.search(kanit or "")
                    if m:
                        _alan_ekle(e, "aciklama", m.group(1).strip().strip(_TIRNAK), no)
                elif iliski == "niteligi":
                    _alan_ekle(esya, "nitelikler", nesne, no)
                elif iliski in _ESYA_ALANI:
                    _alan_ekle(esya, _ESYA_ALANI[iliski], nesne, no)
                continue
            hedef = olduruldu.get(glossary.fold_term(ozne))
            if hedef is not None and iliski in ("rutbesi", "sinifi"):
                hedef["alan"]["rutbe" if iliski == "rutbesi" else "sinif"] = nesne
                continue
            if iliski == "niteligi":
                self._kayit("nitelik", ozne, nesne, no, kanit)
            elif iliski in RUN_ALANLARI:
                self._kayit("alan", ozne, iliski, no, kanit, nesne)
        for o in olduruldu.values():
            # İnsan öldürmek yaratık kaydı değildir (War Maiden Hilde, Solvane…).
            if (o["alan"].get("sinif") or "").casefold() == "human":
                continue
            k = self._kayit("yaratik", o["sahip"], o["ad"], no, o["kanit"])
            for alan, deger in o["alan"].items():
                _alan_ekle(k, alan, deger, no)


def _alan_ekle(kayit: dict, alan: str, deger: str, bolum: int | None) -> None:
    gecmis = kayit["alanlar"].setdefault(alan, [])
    if alan in LISTE_ALANLARI:
        if all(d != deger for d, _b in gecmis):
            gecmis.append([deger, bolum or 0])
        return
    if not gecmis or gecmis[-1][0] != deger:
        gecmis.append([deger, bolum or 0])


def _profil(book_slug: str) -> dict | None:
    p = varlik_grafigi.profil(book_slug)
    return p if p and p.get("runler") else None


def _yaz_sistem(conn, book_slug: str, kayitlar, birlestir: bool) -> None:
    simdi = time.time()
    for k in kayitlar:
        eski = None
        if birlestir:
            eski = conn.execute(
                "SELECT alanlar, ilk_bolum, kanit FROM defter_kayit WHERE book_slug = ? AND anahtar = ? "
                "AND origin = 'sistem'", (book_slug, k["anahtar"]),
            ).fetchone()
        alanlar, ilk, kanit = k["alanlar"], k["ilk_bolum"], k["kanit"]
        if eski is not None:
            alanlar = _gecmis_birlestir(json.loads(eski[0] or "{}"), alanlar)
            if eski[1] is not None and (ilk is None or eski[1] <= ilk):
                ilk, kanit = eski[1], eski[2]
        conn.execute(
            "INSERT INTO defter_kayit (book_slug, anahtar, tur, sahip, ad, deger, alanlar, ilk_bolum, kanit, "
            "origin, silindi, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sistem', 0, ?) "
            "ON CONFLICT(book_slug, anahtar, origin) DO UPDATE SET alanlar = excluded.alanlar, "
            "ilk_bolum = excluded.ilk_bolum, kanit = excluded.kanit, updated_at = excluded.updated_at",
            (book_slug, k["anahtar"], k["tur"], k["sahip"], k["ad"], k["deger"],
             json.dumps(alanlar, ensure_ascii=False), ilk, kanit, simdi),
        )


def _gecmis_birlestir(a: dict, b: dict) -> dict:
    out = {}
    for alan in set(a) | set(b):
        satirlar = sorted({(d, bo) for d, bo in (a.get(alan, []) + b.get(alan, []))}, key=lambda x: (x[1], x[0]))
        temiz: list[list] = []
        for d, bo in satirlar:
            if alan in LISTE_ALANLARI:
                if all(d != t[0] for t in temiz):
                    temiz.append([d, bo])
            elif not temiz or temiz[-1][0] != d:
                temiz.append([d, bo])
        out[alan] = temiz
    return out


def cikar(book_slug: str) -> dict:
    """Kitabın bütün bölümlerinden sistem kayıtlarını BAŞTAN kurar (API'siz, idempotent).
    Elle kayıtlara dokunmaz. Döner: {"kayit": sayı, "bolum": sayı}."""
    p = _profil(book_slug)
    if p is None:
        return {"kayit": 0, "bolum": 0}
    t = _Toplayici()
    bolumler = sorted(cache.kaynak_bolumleri(book_slug), key=lambda b: b["chapter_no"] or 0)
    for b in bolumler:
        t.bolum(b["chapter_no"], b["source"] or "", p["ana_karakter"], tuple(p.get("ana_karakter_adlari", ())))
    conn = _connect()
    try:
        conn.execute("DELETE FROM defter_kayit WHERE book_slug = ? AND origin = 'sistem'", (book_slug,))
        _yaz_sistem(conn, book_slug, t.kayitlar.values(), birlestir=False)
        conn.commit()
    finally:
        conn.close()
    return {"kayit": len(t.kayitlar), "bolum": len(bolumler)}


def bolumden(book_slug: str, bolum: int | None, metin: str) -> int:
    """Yeni kaydedilen TEK bölümün rünlerini mevcut kayıtlara katar (çeviri akışı)."""
    p = _profil(book_slug)
    if p is None or not metin:
        return 0
    conn = _connect()
    try:
        esyalar = {glossary.fold_term(ad): tur for ad, tur in conn.execute(
            "SELECT ad, tur FROM defter_kayit WHERE book_slug = ? AND tur IN ('ani', 'golge', 'yanki')",
            (book_slug,))}
        t = _Toplayici(esyalar)
        # Önceki bölümlerde görülen anının sahibini bilmek için mevcut kayıtlar tohumlanır.
        for satir in conn.execute(
            "SELECT anahtar, tur, sahip, ad, deger FROM defter_kayit WHERE book_slug = ? AND origin = 'sistem' "
            "AND tur IN ('ani', 'golge', 'yanki')", (book_slug,)):
            t.kayitlar[satir[0]] = {"anahtar": satir[0], "tur": satir[1], "sahip": satir[2], "ad": satir[3],
                                    "deger": satir[4], "alanlar": {}, "ilk_bolum": None, "kanit": None,
                                    "_tohum": True}
        t.bolum(bolum, metin, p["ana_karakter"], tuple(p.get("ana_karakter_adlari", ())))
        # Tohum kaydı yalnız bu bölümde alan kazandıysa yazılır; ilk bölümü eski kayıttan kalır.
        yeni = [k for k in t.kayitlar.values() if not k.get("_tohum") or k["alanlar"] or k["ilk_bolum"]]
        _yaz_sistem(conn, book_slug, yeni, birlestir=True)
        conn.commit()
        return len(yeni)
    finally:
        conn.close()


# ---------- elle düzenleme ----------
def _dogrula(kayit: dict) -> dict:
    tur = (kayit.get("tur") or "").strip()
    ad = (kayit.get("ad") or "").strip()
    if tur not in TURLER:
        raise ValueError(f"Bilinmeyen kayıt türü: {tur!r}")
    if not ad:
        raise ValueError("Ad boş olamaz")
    ilk = kayit.get("ilk_bolum")
    if ilk is not None and (not isinstance(ilk, int) or ilk < 0):
        raise ValueError("Bölüm numarası geçersiz")
    alanlar = kayit.get("alanlar") or {}
    if not isinstance(alanlar, dict):
        raise ValueError("Alanlar sözlük olmalı")
    return {"tur": tur, "ad": ad, "sahip": (kayit.get("sahip") or "").strip(),
            "deger": (kayit.get("deger") or "").strip(), "ilk_bolum": ilk, "alanlar": alanlar,
            "kanit": kayit.get("kanit")}


def _gorunen_satir(conn, book_slug: str, a: str):
    satirlar = {r[0]: r for r in conn.execute(
        "SELECT origin, ilk_bolum, silindi FROM defter_kayit WHERE book_slug = ? AND anahtar = ?",
        (book_slug, a))}
    return satirlar.get("elle") or satirlar.get("sistem")


def elle_yaz(book_slug: str, kayit: dict, yerine: str | None = None) -> str:
    """Elle kayıt ekle ya da düzelt. `yerine` düzeltilen kaydın anahtarı: anahtar değiştiyse
    (ad/sahip/değer düzeldi) eski kayıt kaldırılır. Bölüm verilmezse eski kaydınki korunur.
    Döner: yeni anahtar."""
    k = _dogrula(kayit)
    a = anahtar(k["tur"], k["sahip"], k["ad"], k["deger"])
    conn = _connect()
    try:
        if k["ilk_bolum"] is None and yerine:
            eski = _gorunen_satir(conn, book_slug, yerine)
            k["ilk_bolum"] = eski[1] if eski is not None else None
        alanlar = {ad: ([[x, k["ilk_bolum"] or 0] for x in deger] if ad in LISTE_ALANLARI and isinstance(deger, list)
                        else [[str(deger), k["ilk_bolum"] or 0]])
                   for ad, deger in k["alanlar"].items() if deger not in (None, "", [])}
        conn.execute(
            "INSERT INTO defter_kayit (book_slug, anahtar, tur, sahip, ad, deger, alanlar, ilk_bolum, kanit, "
            "origin, silindi, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'elle', 0, ?) "
            "ON CONFLICT(book_slug, anahtar, origin) DO UPDATE SET sahip = excluded.sahip, ad = excluded.ad, "
            "deger = excluded.deger, alanlar = excluded.alanlar, ilk_bolum = excluded.ilk_bolum, "
            "kanit = COALESCE(excluded.kanit, defter_kayit.kanit), silindi = 0, updated_at = excluded.updated_at",
            (book_slug, a, k["tur"], k["sahip"], k["ad"], k["deger"], json.dumps(alanlar, ensure_ascii=False),
             k["ilk_bolum"], k["kanit"], time.time()),
        )
        if yerine and yerine != a:
            _kaldir(conn, book_slug, yerine)
        conn.commit()
    finally:
        conn.close()
    return a


def _kaldir(conn, book_slug: str, a: str) -> bool:
    sistem = conn.execute(
        "SELECT tur, sahip, ad, deger FROM defter_kayit WHERE book_slug = ? AND anahtar = ? AND origin = 'sistem'",
        (book_slug, a)).fetchone()
    if sistem is None:
        n = conn.execute("DELETE FROM defter_kayit WHERE book_slug = ? AND anahtar = ? AND origin = 'elle'",
                         (book_slug, a)).rowcount
        return n > 0
    conn.execute(
        "INSERT INTO defter_kayit (book_slug, anahtar, tur, sahip, ad, deger, alanlar, ilk_bolum, kanit, origin, "
        "silindi, updated_at) VALUES (?, ?, ?, ?, ?, ?, '{}', NULL, NULL, 'elle', 1, ?) "
        "ON CONFLICT(book_slug, anahtar, origin) DO UPDATE SET silindi = 1, updated_at = excluded.updated_at",
        (book_slug, a, *sistem, time.time()),
    )
    return True


def kaldir(book_slug: str, a: str) -> bool:
    """Görünen kaydı kaldır. Rünlerden gelmişse elle bir "kaldırıldı" işareti yazılır
    (yeniden çıkarım diriltmez); yalnız elle eklenmişse tümden silinir."""
    conn = _connect()
    try:
        n = _kaldir(conn, book_slug, a)
        conn.commit()
        return n
    finally:
        conn.close()


def geri_al(book_slug: str, a: str) -> bool:
    """Elle düzeltmeyi/kaldırmayı geri al: rünlerden gelen kayıt yeniden görünür."""
    conn = _connect()
    try:
        n = conn.execute("DELETE FROM defter_kayit WHERE book_slug = ? AND anahtar = ? AND origin = 'elle'",
                         (book_slug, a)).rowcount
        conn.commit()
        return n > 0
    finally:
        conn.close()


# ---------- okuma ----------
def _duz_alanlar(gecmis: dict, konum: int | None) -> dict:
    out = {}
    for alan, satirlar in gecmis.items():
        gorunen = [d for d, b in satirlar if konum is None or (b or 0) <= konum]
        if not gorunen:
            continue
        out[alan] = gorunen if alan in LISTE_ALANLARI else gorunen[-1]
    return out


def gorunum(book_slug: str, konum: int | None) -> dict:
    """Konuma kadar görünen kayıtlar, türe göre. Sözlükte karşılığı olan adlara `tr` ve
    `kimlik` eklenir. `konum` None: süzgeç yok (spoiler açık)."""
    conn = _connect()
    try:
        satirlar = conn.execute(
            "SELECT anahtar, tur, sahip, ad, deger, alanlar, ilk_bolum, kanit, origin, silindi "
            "FROM defter_kayit WHERE book_slug = ? ORDER BY origin", (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    secili: dict[str, tuple] = {}
    for s in satirlar:  # ORDER BY origin: 'elle' < 'sistem' — elle önce gelir ve kazanır
        secili.setdefault(s[0], s)
    cozucu = varlik_grafigi.DugumCozucu(book_slug)
    hedefler = {k: r.get("target") for k, r in cozucu.satirlar.items()}
    out: dict[str, list] = {t: [] for t in TURLER}
    tekil: dict[tuple, dict] = {}
    for s in secili.values():
        (a, tur, sahip, ad, deger, alanlar, ilk, kanit, origin, silindi) = s
        if silindi or (konum is not None and (ilk or 0) > konum):
            continue
        kimlik = cozucu.coz(ad) if tur != "alan" else None
        kayit = {"anahtar": a, "tur": tur, "sahip": sahip, "sahip_kimlik": cozucu.coz(sahip),
                 "ad": ad, "deger": deger, "kimlik": kimlik, "tr": hedefler.get(kimlik) if kimlik else None,
                 "alanlar": _duz_alanlar(json.loads(alanlar or "{}"), konum), "ilk_bolum": ilk,
                 "kanit": kanit, "origin": origin}
        if tur == "alan" and ad not in COKLU_ALANLAR:
            # Tekil rün alanı (Rank…): konumdaki EN SON değer; eşitlikte elle.
            k = (glossary.fold_term(sahip), ad)
            eski = tekil.get(k)
            if eski is None or ((ilk or 0), origin == "elle") > ((eski["ilk_bolum"] or 0), eski["origin"] == "elle"):
                tekil[k] = kayit
            continue
        out[tur].append(kayit)
    out["alan"].extend(tekil.values())
    for liste in out.values():
        liste.sort(key=lambda k: ((k["ilk_bolum"] or 0), k["ad"].casefold()))
    return {"sinir": konum, "kayitlar": out}
