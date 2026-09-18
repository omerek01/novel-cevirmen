"""Gemini API gözlem kaydı: her gerçek istek, her soğuma atlaması, her model geçişi.

Neden var: "3.6 seçiliyken neden 3.5 ile çevrildi?" sorusu bir dönem TAHMİNLE
cevaplanıyordu. Veritabanında yalnız bölümü FİİLEN çeviren model duruyordu, zincirin
neden aşağı indiği hiçbir yerde yoktu ve çeviri yolunda tek satır log bile yoktu.
Gerçek vaka (2026-09-18): sunucu kayıtlarında iki ayrı desen vardı. Biri tek tük düşüp
dakikalar içinde geri dönen düşüşlerdi (503 dalgası ya da boş yanıt olmalı), öteki gece
yarısı sekiz bölüm üst üste süren bir düşüştü (günlük kotaya benziyor ama o gün yalnız
~25 bölüm çevrilmişti). Elimizdeki veriyle ikisini ayırmak imkânsızdı.

Üç kayıt tutulur:
  * ``api_gunluk`` — anahtar x model x Pasifik günü sayaçları. Kota Pasifik gece
    yarısında sıfırlandığı için gün de ORADAN sayılır; TSİ günü kotayla hizalanmazdı.
  * ``api_son``    — anahtar x model son gözlem ve varsa soğuma bitişi (UTC epoch).
    Soğuma yeniden başlatmada buradan GERİ YÜKLENİR (`translate._sogumalari_geri_yukle`).
  * ``api_olay``   — sınırlı ayrıntı geçmişi: istek, atlama, model geçişi.

Üç kural load-bearing:
  * **Anahtar DEĞERİ hiçbir yere yazılmaz.** Kimlik SHA-256 özetinin ilk 16
    karakteridir. Sıra (``.env``'deki numara) kimlik DEĞİLDİR: anahtarlar yeniden
    sıralanınca eski kullanım yanlış anahtara taşınırdı.
  * **Kayıt hatası çeviriyi ASLA başarısız kılmaz.** Bu bir göstergedir; sayaç
    yazılamadı diye bölümü kaybetmek, ölçmeye çalıştığımız şeyden pahalıdır.
  * **Ham istem, çeviri metni, ham hata gövdesi saklanmaz.** Yalnız sınıf, HTTP kodu
    ve yapılandırılmış kota alanları (quotaId, quotaValue, retryDelay).

İşlem bağlamı (amaç, bölüm URL'si, aşama) ``contextvars`` ile taşınır: aynı anda
koşan okuma, prefetch ve toplu çeviri birbirinin kaydına karışmaz. Uvicorn'un iş
parçacığı havuzu bağlamı kopyalar; ``threading.Thread`` KOPYALAMAZ, bu yüzden elle
açılan iş parçacıkları (prefetch, jobs) bağlamı kendi içinde kurar.
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

from . import db

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sonuç sınıfları — panel ve özet aynı adları kullanır
# ---------------------------------------------------------------------------
BASARI = "basari"
KOTA_GUNLUK = "kota_gunluk"
KOTA_DAKIKALIK = "kota_dakikalik"
KOTA_BELIRSIZ = "kota_belirsiz"
GECICI = "gecici"  # 500/503
BAGLANTI = "baglanti"  # taşıma katmanı (httpx)
ERISIM = "erisim"  # 404: bu anahtarın projesi modeli görmüyor
ANAHTAR = "anahtar"  # 401/403 ya da 400 API_KEY_INVALID
BOS = "bos"  # 200 ama boş/engellenmiş yanıt
DIGER = "diger"  # beklenmeyen HTTP kodu
SOGUMA = "soguma"  # istek ATILMADI: anahtar bu modelde soğumada

ETIKET = {
    BASARI: "başarılı",
    KOTA_GUNLUK: "günlük kota",
    KOTA_DAKIKALIK: "dakikalık kota",
    KOTA_BELIRSIZ: "kota (türü belirsiz)",
    GECICI: "geçici hata",
    BAGLANTI: "bağlantı hatası",
    ERISIM: "model erişilemiyor (404)",
    ANAHTAR: "anahtar/izin hatası",
    BOS: "boş/engellenmiş yanıt",
    DIGER: "beklenmeyen hata",
    SOGUMA: "soğumada, atlandı",
}
KOTA_SINIFLARI = frozenset({KOTA_GUNLUK, KOTA_DAKIKALIK, KOTA_BELIRSIZ})

# Saklama: ayrıntı 30 gün / 10.000 kayıt, günlük özet 90 gün. Temizlik her yazımda
# DEĞİL, süreç başına saatte bir — sık yazılan bir tabloda her istekte DELETE
# koşturmak, ölçtüğümüz çeviri yolunu yavaşlatırdı.
OLAY_GUN = 30
OLAY_TAVAN = 10_000
GUNLUK_GUN = 90
TEMIZLIK_ARALIGI_SN = 3600.0

# ---------------------------------------------------------------------------
# Anahtar kimliği ve Pasifik günü
# ---------------------------------------------------------------------------


def anahtar_kimligi(deger: str) -> str:
    """Anahtarın kalıcı kimliği: değer değil, SHA-256 özetinin başı.

    API anahtarı yüksek entropili olduğu için özetinden geri çıkarılamaz; tuz
    gerekmez. 16 onaltılık hane (64 bit) beş anahtarlık bir havuzda çakışmaz.
    """
    return hashlib.sha256((deger or "").strip().encode("utf-8")).hexdigest()[:16]


@functools.lru_cache(maxsize=1)
def _pasifik_tz():
    # Windows'ta sistem saat dilimi veritabanı yok; `tzdata` paketi olmadan
    # ZoneInfo patlar. O durumda sabit UTC-8'e düşülür — yazın bir saat şaşar,
    # ama sunucu Linux'ta ve orada sistem veritabanı var.
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Los_Angeles")
        except Exception:  # noqa: BLE001
            pass
    return timezone(timedelta(hours=-8))


def pasifik_gunu(ts: float | None = None) -> str:
    """Kota gününün adı (YYYY-MM-DD, America/Los_Angeles)."""
    an = datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc)
    return an.astimezone(_pasifik_tz()).date().isoformat()


def sonraki_sifirlama(ts: float | None = None) -> float:
    """Günlük kotanın bir sonraki sıfırlanma anı (UTC epoch)."""
    an = datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc)
    pas = an.astimezone(_pasifik_tz())
    ertesi = (pas + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return ertesi.timestamp()


# ---------------------------------------------------------------------------
# İşlem bağlamı
# ---------------------------------------------------------------------------
_BAGLAM: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "api_durum_baglam", default=None
)
# Bir `_generate_with_fallback` çağrısının denemeleri: model geçişinin NEDENİ
# buradan kurulur. Ortak bir "son hata" değişkeni paralel işlemleri karıştırırdı.
_CAGRI: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "api_durum_cagri", default=None
)


def _yeni_kimlik() -> str:
    return uuid.uuid4().hex[:12]


def mevcut_baglam() -> dict:
    return dict(_BAGLAM.get() or {})


@contextlib.contextmanager
def islem(amac: str, url: str | None = None):
    """YENİ bir işlem başlat (okuma, prefetch, toplu, sözlük önerisi…)."""
    token = _BAGLAM.set({"islem": _yeni_kimlik(), "amac": amac, "url": url, "asama": None})
    try:
        yield
    finally:
        _BAGLAM.reset(token)


@contextlib.contextmanager
def baglam(**alanlar):
    """Mevcut işleme alan ekle (url, asama); işlem yoksa kimlik üretir.

    `None` verilen alan mevcut değeri EZMEZ: pipeline URL'yi her durumda geçirir,
    ama giriş noktasının koyduğu amaç korunmalı.
    """
    simdiki = _BAGLAM.get() or {"islem": _yeni_kimlik(), "amac": "diger", "url": None,
                                 "asama": None}
    yeni = {**simdiki, **{k: v for k, v in alanlar.items() if v is not None}}
    token = _BAGLAM.set(yeni)
    try:
        yield
    finally:
        _BAGLAM.reset(token)


@contextlib.contextmanager
def cagri():
    """Tek bir yedek-zinciri çağrısının denemelerini topla.

    Döner: denemeler listesi — her öge ``{"model", "sira", "sonuc", "kod"}``.
    """
    kayit = {"kimlik": _yeni_kimlik(), "denemeler": []}
    token = _CAGRI.set(kayit)
    try:
        yield kayit["denemeler"]
    finally:
        _CAGRI.reset(token)


def _cagriya_ekle(model: str, sira: int, sonuc: str, kod: int | None) -> str | None:
    kayit = _CAGRI.get()
    if kayit is None:
        return None
    kayit["denemeler"].append({"model": model, "sira": sira, "sonuc": sonuc, "kod": kod})
    return kayit["kimlik"]


# ---------------------------------------------------------------------------
# Depo
# ---------------------------------------------------------------------------
_KURULAN: set[str] = set()
_KURULUM_KILIDI = threading.Lock()
_SON_TEMIZLIK: dict[str, float] = {}


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    yol = str(db.db_path())
    if yol in _KURULAN:
        return conn
    with _KURULUM_KILIDI:
        # Çift kontrol: kilidi bekleyen ikinci iş parçacığı kurulumu YENİDEN
        # yapmasın (ölçüldü: iki eşzamanlı ilk yazımdan biri "database is locked"
        # alıp kaydı kaybediyordu).
        if yol in _KURULAN:
            return conn
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_gunluk (
                anahtar TEXT NOT NULL,
                model TEXT NOT NULL,
                gun TEXT NOT NULL,
                deneme INTEGER NOT NULL DEFAULT 0,
                basari INTEGER NOT NULL DEFAULT 0,
                hata INTEGER NOT NULL DEFAULT 0,
                kota INTEGER NOT NULL DEFAULT 0,
                giris_token INTEGER NOT NULL DEFAULT 0,
                cikis_token INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (anahtar, model, gun)
            );
            CREATE TABLE IF NOT EXISTS api_son (
                anahtar TEXT NOT NULL,
                model TEXT NOT NULL,
                sira INTEGER,
                son_deneme REAL,
                son_basari REAL,
                son_hata REAL,
                sonuc TEXT,
                hata_sinifi TEXT,
                http_kodu INTEGER,
                kota_turu TEXT,
                kota_sinir INTEGER,
                kota_kimligi TEXT,
                yeniden_sn REAL,
                soguma_bitis REAL,
                PRIMARY KEY (anahtar, model)
            );
            CREATE TABLE IF NOT EXISTS api_olay (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zaman REAL NOT NULL,
                islem TEXT,
                cagri TEXT,
                amac TEXT,
                asama TEXT,
                url TEXT,
                tur TEXT NOT NULL,
                anahtar TEXT,
                sira INTEGER,
                model TEXT,
                hedef TEXT,
                sonuc TEXT,
                http_kodu INTEGER,
                sure_ms INTEGER,
                ayrinti TEXT
            );
            CREATE INDEX IF NOT EXISTS api_olay_zaman ON api_olay (zaman);
            CREATE INDEX IF NOT EXISTS api_olay_url ON api_olay (url, tur);
            CREATE TABLE IF NOT EXISTS api_meta (
                ad TEXT PRIMARY KEY,
                deger TEXT
            );
            """
        )
        with _yazim(conn):
            conn.execute(
                "INSERT OR IGNORE INTO api_meta (ad, deger) VALUES ('baslangic', ?)",
                (str(time.time()),),
            )
        _KURULAN.add(yol)
    return conn


@contextlib.contextmanager
def _yazim(conn: sqlite3.Connection):
    """Yazma işlemi: BEGIN IMMEDIATE ile.

    Python'un örtük ERTELENMİŞ işlemi WAL kipinde paralel yazarlar arasında
    "database is locked" verebilir: okuma anlık görüntüsü alındıktan sonra başka
    bir yazar işlem bitirirse yükseltme BEKLEMEDEN reddedilir (busy_timeout
    devreye girmez). Okuma, prefetch ve toplu çeviri aynı anda istek kaydettiği
    için bu yol gerçekten paralel — ölçüldü: iki eşzamanlı istekten birinin
    kaydı kayboluyordu. IMMEDIATE yazma kilidini BAŞTA alır ve beklemeyi
    busy_timeout'a bırakır.
    """
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _sessiz(fn):
    """Yazma yolunu korur: kayıt hatası çeviriye SIZMAZ, yalnız log'a düşer."""

    @functools.wraps(fn)
    def sarici(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — gösterge, çeviri yolunun parçası değil
            _log.warning("api_durum.%s yazılamadı: %s", fn.__name__, exc)
            return None

    return sarici


def _olay_yaz(conn, tur: str, **alanlar) -> None:
    ctx = _BAGLAM.get() or {}
    conn.execute(
        "INSERT INTO api_olay (zaman, islem, cagri, amac, asama, url, tur, anahtar, sira,"
        " model, hedef, sonuc, http_kodu, sure_ms, ayrinti)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            alanlar.get("zaman", time.time()),
            ctx.get("islem"),
            alanlar.get("cagri"),
            ctx.get("amac") or "diger",
            ctx.get("asama"),
            ctx.get("url"),
            tur,
            alanlar.get("anahtar"),
            alanlar.get("sira"),
            alanlar.get("model"),
            alanlar.get("hedef"),
            alanlar.get("sonuc"),
            alanlar.get("kod"),
            alanlar.get("sure_ms"),
            alanlar.get("ayrinti"),
        ),
    )


def _gerekirse_temizle(conn, simdi: float) -> None:
    yol = str(db.db_path())
    if simdi - _SON_TEMIZLIK.get(yol, 0.0) < TEMIZLIK_ARALIGI_SN:
        return
    _SON_TEMIZLIK[yol] = simdi
    conn.execute("DELETE FROM api_olay WHERE zaman < ?", (simdi - OLAY_GUN * 86400,))
    conn.execute(
        "DELETE FROM api_olay WHERE id <= ("
        " SELECT id FROM api_olay ORDER BY id DESC LIMIT 1 OFFSET ?)",
        (OLAY_TAVAN,),
    )
    conn.execute(
        "DELETE FROM api_gunluk WHERE gun < ?",
        (pasifik_gunu(simdi - GUNLUK_GUN * 86400),),
    )


@_sessiz
def istek_kaydet(
    anahtar: str,
    sira: int,
    model: str,
    sonuc: str,
    kod: int | None = None,
    sure_ms: int | None = None,
    giris: int = 0,
    cikis: int = 0,
    kota: dict | None = None,
    soguma_sn: float | None = None,
) -> None:
    """GERÇEK bir sağlayıcı çağrısının sonucunu kaydet (sayaç + son durum + olay).

    ``soguma_sn`` çeviri yolunun anahtara FİİLEN uyguladığı soğuma süresidir;
    bitiş UTC epoch olarak saklanır ki yeniden başlatmada geri yüklenebilsin.
    """
    simdi = time.time()
    kota = kota or {}
    cagri_kimligi = _cagriya_ekle(model, sira, sonuc, kod)
    basari = sonuc == BASARI
    conn = _connect()
    try:
        with _yazim(conn):
            conn.execute(
                "INSERT INTO api_gunluk (anahtar, model, gun, deneme, basari, hata, kota,"
                " giris_token, cikis_token) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)"
                " ON CONFLICT(anahtar, model, gun) DO UPDATE SET"
                "  deneme = deneme + 1,"
                "  basari = basari + excluded.basari,"
                "  hata = hata + excluded.hata,"
                "  kota = kota + excluded.kota,"
                "  giris_token = giris_token + excluded.giris_token,"
                "  cikis_token = cikis_token + excluded.cikis_token",
                (
                    anahtar, model, pasifik_gunu(simdi),
                    int(basari), int(not basari), int(sonuc in KOTA_SINIFLARI),
                    int(giris or 0), int(cikis or 0),
                ),
            )
            if basari:
                # Başarı soğumayı KALDIRIR ama son hatanın ayrıntısını silmez:
                # "en son ne zaman ve neden hata aldı" bilgisi başarıdan sonra da
                # anlamlıdır.
                conn.execute(
                    "INSERT INTO api_son (anahtar, model, sira, son_deneme, son_basari,"
                    " sonuc, soguma_bitis) VALUES (?, ?, ?, ?, ?, ?, NULL)"
                    " ON CONFLICT(anahtar, model) DO UPDATE SET"
                    "  sira = excluded.sira, son_deneme = excluded.son_deneme,"
                    "  son_basari = excluded.son_basari, sonuc = excluded.sonuc,"
                    "  soguma_bitis = NULL",
                    (anahtar, model, sira, simdi, simdi, sonuc),
                )
            else:
                bitis = simdi + soguma_sn if soguma_sn else None
                conn.execute(
                    "INSERT INTO api_son (anahtar, model, sira, son_deneme, son_hata, sonuc,"
                    " hata_sinifi, http_kodu, kota_turu, kota_sinir, kota_kimligi,"
                    " yeniden_sn, soguma_bitis) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(anahtar, model) DO UPDATE SET"
                    "  sira = excluded.sira, son_deneme = excluded.son_deneme,"
                    "  son_hata = excluded.son_hata, sonuc = excluded.sonuc,"
                    "  hata_sinifi = excluded.hata_sinifi, http_kodu = excluded.http_kodu,"
                    "  kota_turu = excluded.kota_turu, kota_sinir = excluded.kota_sinir,"
                    "  kota_kimligi = excluded.kota_kimligi,"
                    "  yeniden_sn = excluded.yeniden_sn,"
                    # Soğuma yalnız KOTADA yazılır; geçici hata var olan bir kota
                    # soğumasını SİLMEMELİ (anahtar hâlâ kotada).
                    "  soguma_bitis = COALESCE(excluded.soguma_bitis, soguma_bitis)",
                    (
                        anahtar, model, sira, simdi, simdi, sonuc, sonuc, kod,
                        kota.get("tur"), kota.get("sinir"), kota.get("kimlik"),
                        kota.get("yeniden_sn"), bitis,
                    ),
                )
            _olay_yaz(
                conn, "istek", zaman=simdi, cagri=cagri_kimligi, anahtar=anahtar,
                sira=sira, model=model, sonuc=sonuc, kod=kod, sure_ms=sure_ms,
            )
            _gerekirse_temizle(conn, simdi)
    finally:
        conn.close()


@_sessiz
def atlama_kaydet(anahtar: str, sira: int, model: str) -> None:
    """Soğumada olduğu için İSTEK ATILMADAN geçilen anahtar. Sayaçlara GİRMEZ."""
    cagri_kimligi = _cagriya_ekle(model, sira, SOGUMA, None)
    conn = _connect()
    try:
        with _yazim(conn):
            _olay_yaz(
                conn, "atlama", cagri=cagri_kimligi, anahtar=anahtar, sira=sira,
                model=model, sonuc=SOGUMA,
            )
    finally:
        conn.close()


def _kisa(model: str | None) -> str:
    return (model or "?").removeprefix("gemini-")


def gecis_ozeti(tercih: str, kullanilan: str | None, denemeler: list[dict]) -> str:
    """İnsan okuyacak tek satır: "3.6-flash → 3.5-flash: 3.6-flash'ta 3 anahtarda …".

    Anahtar başına SON sonuç sayılır: geçici hatada aynı anahtar birden çok turda
    denenir, her turu ayrı saymak "5 anahtarda hata" yerine "15" yazdırırdı.
    """
    modeller: dict[str, dict[int, str]] = {}
    for d in denemeler:
        if d.get("model") == kullanilan:
            continue
        modeller.setdefault(d["model"], {})[d["sira"]] = d["sonuc"]
    parcalar = []
    for model, anahtarlar in modeller.items():
        sayim: dict[str, int] = {}
        for sonuc in anahtarlar.values():
            sayim[sonuc] = sayim.get(sonuc, 0) + 1
        dokum = ", ".join(
            f"{n} anahtarda {ETIKET.get(s, s)}"
            for s, n in sorted(sayim.items(), key=lambda x: -x[1])
        )
        parcalar.append(f"{_kisa(model)}: {dokum}")
    bas = f"{_kisa(tercih)} → {_kisa(kullanilan) if kullanilan else 'çeviri yapılamadı'}"
    return bas + (": " + "; ".join(parcalar) if parcalar else "")


@_sessiz
def gecis_kaydet(tercih: str, kullanilan: str | None, denemeler: list[dict]) -> None:
    """Zincirin ilk halkası dışında bir modele inildi (ya da zincir tükendi).

    ``kullanilan`` None = hiçbir model çeviremedi (tur ``tukendi``).
    """
    ozet = gecis_ozeti(tercih, kullanilan, denemeler)
    kayit = _CAGRI.get()
    conn = _connect()
    try:
        with _yazim(conn):
            _olay_yaz(
                conn, "gecis" if kullanilan else "tukendi",
                cagri=kayit["kimlik"] if kayit else None,
                model=tercih, hedef=kullanilan,
                ayrinti=json.dumps({"ozet": ozet, "denemeler": denemeler},
                                   ensure_ascii=False),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


def aktif_sogumalar(simdi: float | None = None) -> list[tuple[str, str, float]]:
    """Bitişi GELECEKTE olan soğumalar: ``[(anahtar, model, bitis_utc)]``.

    Geçmiş bitişler aktif engel sayılmaz. Okunamazsa boş liste: soğuma geri
    yüklenemedi diye çeviri durmamalı, en kötü ihtimalle bir boş istek atılır.
    """
    simdi = time.time() if simdi is None else simdi
    try:
        conn = _connect()
    except sqlite3.Error:
        return []
    try:
        return [
            (r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT anahtar, model, soguma_bitis FROM api_son WHERE soguma_bitis > ?",
                (simdi,),
            )
        ]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def kayit_baslangici() -> float | None:
    conn = _connect()
    try:
        r = conn.execute("SELECT deger FROM api_meta WHERE ad = 'baslangic'").fetchone()
        return float(r[0]) if r else None
    finally:
        conn.close()


def gunluk_sayaclar(gun: str | None = None) -> list[dict]:
    gun = gun or pasifik_gunu()
    conn = _connect()
    try:
        satirlar = conn.execute(
            "SELECT anahtar, model, deneme, basari, hata, kota, giris_token, cikis_token"
            " FROM api_gunluk WHERE gun = ? ORDER BY anahtar, model",
            (gun,),
        ).fetchall()
    finally:
        conn.close()
    adlar = ("anahtar", "model", "deneme", "basari", "hata", "kota", "giris_token",
             "cikis_token")
    return [dict(zip(adlar, r)) for r in satirlar]


def son_durumlar() -> list[dict]:
    conn = _connect()
    try:
        imlec = conn.execute("SELECT * FROM api_son ORDER BY sira, model")
        adlar = [c[0] for c in imlec.description]
        return [dict(zip(adlar, r)) for r in imlec.fetchall()]
    finally:
        conn.close()


def son_olaylar(limit: int = 50, turler: tuple[str, ...] | None = None,
                url: str | None = None, once: int | None = None) -> list[dict]:
    """En yeniden eskiye olaylar. ``once``: bu id'den KÜÇÜK olanlar (sayfalama)."""
    kosul, deger = [], []
    if turler:
        kosul.append(f"tur IN ({', '.join('?' * len(turler))})")
        deger += list(turler)
    if url:
        kosul.append("url = ?")
        deger.append(url)
    if once is not None:
        kosul.append("id < ?")
        deger.append(once)
    where = (" WHERE " + " AND ".join(kosul)) if kosul else ""
    conn = _connect()
    try:
        imlec = conn.execute(
            f"SELECT * FROM api_olay{where} ORDER BY id DESC LIMIT ?",
            (*deger, max(1, min(int(limit), 500))),
        )
        adlar = [c[0] for c in imlec.description]
        sonuc = []
        for r in imlec.fetchall():
            satir = dict(zip(adlar, r))
            if satir.get("ayrinti"):
                try:
                    satir["ayrinti"] = json.loads(satir["ayrinti"])
                except ValueError:
                    pass
            sonuc.append(satir)
        return sonuc
    finally:
        conn.close()


def bolum_gecisleri(url: str, limit: int = 5) -> list[dict]:
    """Bir bölüm için kaydedilmiş model geçişleri (künye rozeti "neden bu model?")."""
    return son_olaylar(limit, turler=("gecis", "tukendi"), url=url)


def sifirla_temizlik_zamani() -> None:
    """Testler için: saatlik temizlik kilidini kaldır."""
    _SON_TEMIZLIK.clear()


# ---------------------------------------------------------------------------
# Panel (salt okunur): kartlar, geçiş listesi, "neden bu model?"
# ---------------------------------------------------------------------------
# Kart durumu planın tablosundan gelir ve ASLA yalnız renkle anlatılmaz: her
# durumun metni var, renk (`ton`) yalnız destekler.
YENIDEN_DENENEBILIR = "yeniden_denenebilir"
GOZLENMEDI = "gozlenmedi"
BASARILI = "basarili"

DURUM = {
    GOZLENMEDI: ("Henüz gözlenmedi", "notr"),
    BASARILI: ("Son istek başarılı", "iyi"),
    KOTA_DAKIKALIK: ("Dakikalık kota", "bekle"),
    KOTA_GUNLUK: ("Günlük kota", "bekle"),
    KOTA_BELIRSIZ: ("Kota türü belirsiz", "bekle"),
    YENIDEN_DENENEBILIR: ("Yeniden denenebilir", "notr"),
    GECICI: ("Geçici hata", "uyari"),
    ERISIM: ("Model erişilemiyor", "hata"),
    ANAHTAR: ("Anahtar/izin hatası", "hata"),
    BOS: ("Son yanıt boş/engellenmiş", "notr"),
    DIGER: ("Beklenmeyen hata", "hata"),
}

AMAC = {
    "okuma": "okuma",
    "prefetch": "ön yükleme",
    "toplu": "toplu çeviri",
    "yeniden_ceviri": "yeniden çeviri",
    "webden_ekle": "web'den ekleme",
    "sozluk_onerisi": "sözlük önerisi",
    "diger": "diğer",
}

# Türkiye 2016'dan beri kalıcı UTC+3: sabit ofset TAM doğrudur ve Windows'ta
# `tzdata` olmadan da çalışır.
_TSI = timezone(timedelta(hours=3))


def tsi(ts: float | None, bicim: str = "%d.%m %H:%M") -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, _TSI).strftime(bicim)


def kart_durumu(son: dict | None, soguma_bitis: float | None, simdi: float) -> str:
    """Anahtar x model kartının durumu.

    Soğuma bitince kota durumu "yeniden denenebilir"e döner, "başarılı"ya DEĞİL:
    başarılı bir istek olmadan anahtar çalışıyor sayılmaz. Geçici hata son
    gözlemdir, kalıcı bir etiket değil.
    """
    if not son or not son.get("sonuc"):
        return GOZLENMEDI
    sonuc = son["sonuc"]
    if sonuc in KOTA_SINIFLARI:
        return sonuc if soguma_bitis and soguma_bitis > simdi else YENIDEN_DENENEBILIR
    if sonuc == BASARI:
        return BASARILI
    if sonuc in (GECICI, BAGLANTI):
        return GECICI
    return sonuc if sonuc in DURUM else DIGER


def panel_verisi(
    kimlikler: list[str],
    zincir: tuple[str, ...] | list[str],
    sogumalar: dict[tuple[str, str], float],
    simdi: float | None = None,
) -> dict:
    """`GET /api/settings/api-status` gövdesi. Google'a istek ATMAZ.

    ``kimlikler`` bugünkü `.env` sırasıyla anahtar kimlikleri; arayüze yalnız
    "Anahtar N" etiketi gider. ``sogumalar`` çeviri yolunun KENDİ bellek
    soğumasıdır (`translate.aktif_soguma_bitisleri`): panel ile çeviri yolu
    aynı kaynağa bakar, ikinci bir kural doğmaz.
    """
    simdi = time.time() if simdi is None else simdi
    gun = pasifik_gunu(simdi)
    son = {(d["anahtar"], d["model"]): d for d in son_durumlar()}
    sayac = {(s["anahtar"], s["model"]): s for s in gunluk_sayaclar(gun)}
    tercih = zincir[0] if zincir else None
    kartlar = []
    for i, kimlik in enumerate(kimlikler):
        modeller = []
        for model in zincir:
            d = son.get((kimlik, model))
            bitis = sogumalar.get((kimlik, model))
            durum = kart_durumu(d, bitis, simdi)
            etiket, ton = DURUM[durum]
            s = sayac.get((kimlik, model)) or {}
            d = d or {}
            modeller.append({
                "model": model,
                "durum": durum,
                "etiket": etiket,
                "ton": ton,
                "son_deneme": d.get("son_deneme"),
                "son_basari": d.get("son_basari"),
                "son_hata": d.get("son_hata"),
                "hata_etiketi": ETIKET.get(d["hata_sinifi"]) if d.get("hata_sinifi") else None,
                "http_kodu": d.get("http_kodu"),
                "kota_turu": d.get("kota_turu"),
                "kota_sinir": d.get("kota_sinir"),
                "soguma_bitis": bitis if bitis and bitis > simdi else None,
                "bugun": {k: s.get(k, 0) for k in ("deneme", "basari", "hata", "kota")},
            })
        kartlar.append({"etiket": f"Anahtar {i + 1}", "sira": i + 1, "modeller": modeller})
    toplam = {
        k: sum(s[k] for s in sayac.values() if s["model"] in zincir)
        for k in ("deneme", "basari", "hata")
    }
    return {
        "guncelleme": simdi,
        "kayit_baslangici": kayit_baslangici(),
        "gun": gun,
        "sifirlama": sonraki_sifirlama(simdi),
        "tercih": tercih,
        "zincir": list(zincir),
        "rotasyon": "Her istekte sonraki anahtar",
        "anahtar_sayisi": len(kimlikler),
        "sogumada": sum(1 for k in kimlikler if (sogumalar.get((k, tercih)) or 0) > simdi),
        "bugun_toplam": toplam,
        "anahtarlar": kartlar,
    }


def olaylari_disa_ver(
    olaylar: list[dict], kimlikler: list[str], bolumler: dict[str, dict] | None = None
) -> list[dict]:
    """Olayları arayüze hazırla: anahtar KİMLİĞİ çıkar, yerine etiket girer.

    Kimlik `.env`'de artık yoksa "çıkarılmış anahtar" denir: kullanımı yeni bir
    anahtara taşımak, silinen anahtarın hatasını sağlam anahtara yazardı.
    """
    etiket = {k: f"Anahtar {i + 1}" for i, k in enumerate(kimlikler)}
    bolumler = bolumler or {}
    cikti = []
    for o in olaylar:
        ayrinti = o.get("ayrinti") if isinstance(o.get("ayrinti"), dict) else {}
        denemeler = ayrinti.get("denemeler") or []
        kimlik = o.get("anahtar")
        if kimlik is None:
            anahtar = None
        else:
            anahtar = etiket.get(kimlik, "Çıkarılmış anahtar")
        url = o.get("url")
        cikti.append({
            "id": o["id"],
            "zaman": o["zaman"],
            "tur": o["tur"],
            "amac": o.get("amac"),
            "amac_etiketi": AMAC.get(o.get("amac") or "diger", o.get("amac")),
            "asama": o.get("asama"),
            "url": url,
            "bolum": bolumler.get(url) if url else None,
            "anahtar": anahtar,
            "model": o.get("model"),
            "hedef": o.get("hedef"),
            "sonuc": o.get("sonuc"),
            "sonuc_etiketi": ETIKET.get(o["sonuc"]) if o.get("sonuc") else None,
            "http_kodu": o.get("http_kodu"),
            "sure_ms": o.get("sure_ms"),
            "ozet": ayrinti.get("ozet"),
            # O ANKİ sırayla (kayıt anındaki `.env` sırası): denemeler yalnız sıra taşır.
            "denenen": sorted({d.get("sira") for d in denemeler if d.get("sira")}),
        })
    return cikti


# Bir bölümün çevirisi ile o çeviriye ait geçiş kayıtlarını eşleyen pencere:
# geçiş çeviri SIRASINDA yazılır, bölüm satırı çeviri BİTİNCE. Toplu çeviride
# geçici hata beklemeleri (30 + 90 sn) ve geri-çekilme turları eklense de bir
# bölümün çevirisi yarım saati aşmaz; daha eski kayıt ÖNCEKİ bir çeviriye aittir.
NEDEN_PENCERESI_SN = 1800


def _olay_ozeti(olay: dict) -> str:
    """Geçişin insan okuyacak özeti. Kayıtta `ayrinti` (JSON) içinde durur;
    dışa verilmiş olayda (`olaylari_disa_ver`) üst düzey `ozet` alanındadır."""
    ayrinti = olay.get("ayrinti")
    if isinstance(ayrinti, dict) and ayrinti.get("ozet"):
        return ayrinti["ozet"]
    return olay.get("ozet") or ""


def _kisa_model(model: str | None) -> str:
    return " + ".join(_kisa(m) for m in (model or "").split(" + ") if m) or "?"


def model_nedeni(
    bolum: dict | None,
    tercih: str | None,
    gecisler: list[dict],
    baslangic: float | None,
) -> dict:
    """Künye rozetindeki "neden bu model?" satırının KARARI.

    Karar ve metin burada kurulur: kural tek yerde durmalı. Dört durum:
      * çeviriye ait geçiş kaydı var: nedenler listelenir;
      * bölüm tercih edilen TEK modelle çevrilmiş: söylenecek bir şey yok;
      * kayıt başlamadan önce çevrilmiş: "geçmiş neden kaydedilmemiş";
      * kayıttan sonra çevrilmiş ve geçiş YOK: o sırada tercih edilen model buydu.
    Eski bir olay GERİYE DÖNÜK uydurulmaz.
    """
    if not bolum:
        return {"durum": "yok", "aciklama": "Bu bölüm önbellekte yok.", "nedenler": []}
    model = bolum.get("model")
    zaman = bolum.get("ceviri_zamani")
    temel = {"bolum_modeli": model, "tercih": tercih, "ceviri_zamani": zaman}
    if not model:
        return {**temel, "durum": "bilinmiyor", "nedenler": [], "aciklama": (
            "Bu bölümün hangi modelle çevrildiği kaydedilmemiş (eski bölüm)."
        )}
    ilgili = sorted(
        (
            g for g in gecisler
            if g.get("tur") == "gecis" and zaman
            and zaman - NEDEN_PENCERESI_SN <= g["zaman"] <= zaman + 60
        ),
        key=lambda g: g["zaman"],
    )
    if ilgili:
        return {**temel, "durum": "gecis", "aciklama": (
            "Bu bölüm çevrilirken tercih edilen modelden inildi:"
        ), "nedenler": [f"{tsi(g['zaman'], '%H:%M')} · {_olay_ozeti(g)}" for g in ilgili]}
    parcalar = [m for m in model.split(" + ") if m]
    if tercih and parcalar == [tercih]:
        return {**temel, "durum": "tercih", "nedenler": [], "aciklama": (
            f"Bu bölüm tercih edilen modelle ({_kisa(tercih)}) çevrildi."
        )}
    ne_zaman = tsi(zaman, "%d.%m.%Y %H:%M") if zaman else "bilinmeyen bir tarihte"
    if not baslangic or not zaman or zaman < baslangic:
        kapsam = (
            f"{tsi(baslangic, '%d.%m.%Y %H:%M')} tarihinden beri" if baslangic
            else "yalnız kayıt başladıktan sonra"
        )
        return {**temel, "durum": "kayitsiz", "nedenler": [], "aciklama": (
            f"Bu bölüm daha önce ({ne_zaman}) {_kisa_model(model)} ile kaydedildi. "
            f"Geçmiş neden kaydedilmemiş: model geçişleri {kapsam} tutuluyor."
        )}
    return {**temel, "durum": "onceki_secim", "nedenler": [], "aciklama": (
        f"Bu bölüm daha önce ({ne_zaman}) {_kisa_model(model)} ile kaydedildi ve o "
        "çeviride zincirden inilmedi, yani o sırada tercih edilen model buydu. Model "
        "seçimi yalnız yeni çevrilen bölümlerde geçerli; Yeniden çevir ile güncel "
        "seçimle çevrilir."
    )}
