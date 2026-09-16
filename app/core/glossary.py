"""Kitap başına sözlük (glossary) — terim tutarlılığı için kalıcı eşleme.

Eşleme: kaynak (İngilizce terim) -> karşılık (nasıl yazılsın). Karakter isimleri
çeviri sırasında otomatik eklenir; kullanıcı kendi terimlerini ekleyip düzenler.
chapters.db ile aynı dosyada ayrı bir tabloda tutulur.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid

from . import db


def _connect() -> sqlite3.Connection:
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS glossary (
            book_slug TEXT,
            source TEXT,
            target TEXT,
            PRIMARY KEY (book_slug, source)
        )
        """
    )
    # Köken sütunları — kayıt hakkında "ne zaman, nereden, hangi bölümde" sorusu
    # eskiden CEVAPSIZDI (tablo 3 sütundu). Somut bedeli: yanlış bir karşılık
    # görüldüğünde ("Uyuyan Merkezi", doğrusu "Uyuyanlar Merkezi") onu kullanıcının
    # mı modelin mi yazdığı bilinemiyordu — düzeltilir mi, korunur mu belirsizdi.
    # Eski satırlarda NULL; künye alanlarındaki (chapters.engine/model) kabul
    # edilmiş desen. `hit_count` BİLEREK yok: okumanın gövdesi önbellek isabetinden
    # geldiği için sayaç sistematik olarak eksik sayardı; "hiç eşleşmeyen kayıt"
    # sorusunu `scripts/sozluk_gozden_gecir.py --olu` doğrudan kaynak metinden
    # yanıtlıyor (sayaç tutmadan, daha doğru).
    db.ensure_column(conn, "glossary", "created_at", "created_at REAL")
    db.ensure_column(conn, "glossary", "origin", "origin TEXT")
    db.ensure_column(conn, "glossary", "first_chapter", "first_chapter INTEGER")
    # KOŞUL: karşılığın HANGİ BAĞLAMDA geçerli olduğunu anlatan serbest metin.
    # Sözlük düz bir `kaynak -> karşılık` eşlemesiydi ve aynı İngilizce sözcüğün
    # bağlama göre iki farklı Türkçe karşılığı olduğu durumu İFADE EDEMİYORDU.
    # Ölçülen vaka (2026-09-06, Shadow Slave): `Great` bir Kabus Yaratığı rütbesi
    # ("Ulu") ama önbellekteki 32 geçişin ~12'si gündelik İngilizce ("Great!",
    # "Great job"). Sözlük karşılığı prompt'ta KURAL olduğu için düz bir
    # `Great -> Ulu` kaydı o on ikisini de "Ulu!" yapardı — bir sorunu çözerken
    # on ikisini açardı.
    #
    # Koşul karşılığın YERİNE GEÇMEZ, yanına iliştirilir ve YALNIZ prompt'a çıkar:
    # `sozluk_ihlalleri`, `_terim_metinde` ve terim eşleştirme karşılığı olduğu
    # gibi görmeye devam eder. Eski satırlarda NULL.
    db.ensure_column(conn, "glossary", "kosul", "kosul TEXT")
    # Kaydin cikti CUMLE. `first_chapter` (bolum no) tek basina "bu karsilik
    # nereden geldi" sorusunu cevaplamiyordu: sozluk karsiligi prompt'ta KURAL
    # olarak uygulaniyor ve garip bir cikti gorulunce kaynagini gormek gerekiyor.
    db.ensure_column(conn, "glossary", "kaynak_cumle", "kaynak_cumle TEXT")
    # SÜRÜM VE KİMLİK (2026-09-16, belge "Sürüm ve geçmiş"). Telefon ve PC aynı
    # sözlüğü düzenliyor; eski bir görüntü üzerinden yapılan düzenleme öteki
    # cihazın yeni kaydını SESSİZCE eziyordu. `surum` yalnız PROMPT'u etkileyen
    # alanlar (karşılık, koşul) değişince artar — köken doldurmak artırmaz.
    # `kimlik` kaydın ömür boyu adıdır: silinip geri alınan kayıt geçmişini korur.
    # Tablo YENİDEN KURULMADI (eklemeli göç): canlı veritabanında satır kopyalamak
    # gereksiz risk, sütun eklemek geri alınabilir.
    db.ensure_column(conn, "glossary", "kimlik", "kimlik TEXT")
    db.ensure_column(conn, "glossary", "surum", "surum INTEGER")
    db.ensure_column(conn, "glossary", "updated_at", "updated_at REAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sozluk_gecmis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_slug TEXT NOT NULL,
            kimlik TEXT,
            source TEXT NOT NULL,
            islem TEXT NOT NULL,
            onceki TEXT,
            sonraki TEXT,
            yol TEXT,
            zaman REAL NOT NULL,
            kitap_surumu INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS sozluk_gecmis_kitap ON sozluk_gecmis (book_slug, kimlik, id)"
    )
    # Kitabın SÖZLÜK SÜRÜMÜ: prompt'u etkileyen her değişiklikte bir artar. Çeviri
    # kaydı bunu künyede taşır (`chapters.sozluk_surumu`) — "bu bölüm hangi sözlükle
    # çevrildi" sorusu `first_chapter`la cevaplanamıyordu (eski bölüm sonradan
    # yeniden çevrilmiş olabilir).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sozluk_surumu "
        "(book_slug TEXT PRIMARY KEY, surum INTEGER NOT NULL)"
    )
    # Eski satırlar bir kez doldurulur. Önce OKUNUR: eşleşmeyen bir UPDATE bile
    # yazma kilidi alır ve her bağlantıda çeviri yoluyla yarışırdı.
    if conn.execute(
        "SELECT 1 FROM glossary WHERE kimlik IS NULL OR surum IS NULL LIMIT 1"
    ).fetchone():
        conn.execute(
            "UPDATE glossary SET kimlik = lower(hex(randomblob(8))) WHERE kimlik IS NULL"
        )
        conn.execute(
            "UPDATE glossary SET surum = 1, updated_at = COALESCE(updated_at, created_at) "
            "WHERE surum IS NULL"
        )
        conn.commit()
    return conn


# ---------- sürüm, kimlik, geçmiş ----------
_SATIR_ALANLARI = (
    "source", "target", "created_at", "origin", "first_chapter", "kosul", "kaynak_cumle",
    "kimlik", "surum", "updated_at",
)
_SATIR_SUTUNLARI = ", ".join(_SATIR_ALANLARI)
# PROMPT'u etkileyen alanlar: yalnız bunlar değişince kayıt/kitap sürümü artar.
_PROMPT_ALANLARI = ("target", "kosul")
# `terimi_yaz`da "koşul verilmedi" işareti (None "temizle" ile karışmasın diye ayrı).
KORU = object()
GECMIS_MAX = 100  # geçmiş ucu kayıt başına en çok bu kadar döndürür


class SurumCakismasi(Exception):
    """İstemcinin gördüğü sürüm sunucudakiyle uyuşmuyor. `guncel`: sunucudaki
    kayıt (silinmişse None). Öteki cihazın düzeltmesi SESSİZCE ezilmesin diye
    yazma yapılmaz; karar kullanıcıya bırakılır."""

    def __init__(self, guncel: dict | None):
        super().__init__("Kayıt başka bir cihazda değişti.")
        self.guncel = guncel


def _bul(conn: sqlite3.Connection, book_slug: str, source: str) -> dict | None:
    """Kaydı yazım varyantından bağımsız bul (`fold_term`)."""
    anahtar = fold_term(source)
    for r in conn.execute(
        f"SELECT {_SATIR_SUTUNLARI} FROM glossary WHERE book_slug = ?", (book_slug,)
    ):
        if fold_term(r[0]) == anahtar:
            return dict(zip(_SATIR_ALANLARI, r))
    return None


def _tabani_denetle(mevcut: dict | None, taban_surum: int | None) -> None:
    """None = denetleme yok (eski istemci, bakım aracı). 0 = "kayıt YOK sanıyorum"."""
    if taban_surum is None:
        return
    gercek = (mevcut or {}).get("surum") or (1 if mevcut else 0)
    if gercek != taban_surum:
        raise SurumCakismasi(mevcut)


def _kitap_surumunu_artir(conn: sqlite3.Connection, book_slug: str) -> int:
    conn.execute(
        "INSERT INTO sozluk_surumu (book_slug, surum) VALUES (?, 1) "
        "ON CONFLICT(book_slug) DO UPDATE SET surum = surum + 1",
        (book_slug,),
    )
    return conn.execute(
        "SELECT surum FROM sozluk_surumu WHERE book_slug = ?", (book_slug,)
    ).fetchone()[0]


def kitap_surumu(book_slug: str) -> int:
    """Kitabın sözlük sürümü (hiç değişmediyse 0). Çeviri künyesine yazılır."""
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT surum FROM sozluk_surumu WHERE book_slug = ?", (book_slug,)
        ).fetchone()
    finally:
        conn.close()
    return r[0] if r else 0


def _ozet(satir: dict | None) -> str | None:
    if satir is None:
        return None
    return json.dumps(
        {"target": satir.get("target"), "kosul": satir.get("kosul"), "surum": satir.get("surum"),
         "origin": satir.get("origin")},
        ensure_ascii=False,
    )


def _gecmise_yaz(conn, book_slug, islem, onceki, sonraki, yol, kitap_surumu) -> None:
    """Değişikliği geçmişe yaz. Sözlüğe YAZAN her yol bunu çağırır
    (`tests/test_sozluk_surum.py` statik tel tuzağıyla tutar)."""
    satir = sonraki or onceki
    conn.execute(
        "INSERT INTO sozluk_gecmis (book_slug, kimlik, source, islem, onceki, sonraki, yol, "
        "zaman, kitap_surumu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (book_slug, satir.get("kimlik"), satir["source"], islem, _ozet(onceki), _ozet(sonraki),
         yol, time.time(), kitap_surumu),
    )


def _satir_ekle(conn: sqlite3.Connection, book_slug: str, satir: dict) -> dict:
    """Yeni satır: kimlik/sürüm/zaman eksikse doldurulur. Yazılan satırı döndürür."""
    yeni = {a: satir.get(a) for a in _SATIR_ALANLARI}
    yeni["kimlik"] = yeni["kimlik"] or uuid.uuid4().hex[:16]
    yeni["surum"] = yeni["surum"] or 1
    yeni["created_at"] = yeni["created_at"] or time.time()
    yeni["updated_at"] = time.time()
    conn.execute(
        f"INSERT INTO glossary (book_slug, {_SATIR_SUTUNLARI}) "
        f"VALUES (?, {', '.join('?' for _ in _SATIR_ALANLARI)})",
        (book_slug, *(yeni[a] for a in _SATIR_ALANLARI)),
    )
    return yeni


def _satiri_guncelle(conn, book_slug, mevcut, degisen, yol, kitap_surumu_al) -> dict:
    """Var olan satırı güncelle. Prompt alanı değiştiyse sürüm artar ve geçmişe
    yazılır; yalnız köken/origin değiştiyse sürüm artmaz, geçmiş yazılmaz."""
    yeni = {**mevcut, **degisen}
    prompt_degisti = any(yeni.get(a) != mevcut.get(a) for a in _PROMPT_ALANLARI)
    if prompt_degisti:
        yeni["surum"] = (mevcut.get("surum") or 1) + 1
        yeni["updated_at"] = time.time()
    alanlar = [a for a in _SATIR_ALANLARI if a != "source" and yeni.get(a) != mevcut.get(a)]
    if alanlar:
        conn.execute(
            f"UPDATE glossary SET {', '.join(a + ' = ?' for a in alanlar)} "
            "WHERE book_slug = ? AND source = ?",
            (*(yeni[a] for a in alanlar), book_slug, mevcut["source"]),
        )
    if prompt_degisti:
        _gecmise_yaz(conn, book_slug, "guncelle", mevcut, yeni, yol, kitap_surumu_al())
    return yeni


def terimi_yaz(
    book_slug: str,
    source: str,
    target: str | None,
    kosul=KORU,
    origin: str | None = "manual",
    taban_surum: int | None = None,
) -> dict | None:
    """Terimi TEK işlemde ekle/güncelle; yazılan satırı döndürür.

    * `kosul`: KORU = dokunma, "" / None = temizle, metin = yaz.
    * `origin`: None = mevcut kökeni koru (koşul düzenlemesi kaydın sahibini değiştirmez).
    * `taban_surum`: istemcinin gördüğü sürüm; uyuşmazsa `SurumCakismasi`.

    Koşul ve köken TAŞINIR: okuyucunun kuyruğu çoğu zaman yalnız {source, target}
    gönderir ve sıradan bir karşılık düzeltmesinin bağlam kuralını ya da "ilk
    nerede geçti" bilgisini silmesi, sebebi hiçbir yerde görünmeyen bir arızaydı.
    """
    source = normalize_source(source)
    if not source:
        return None
    target = (target or "").strip() or source  # boş karşılık = aynen koru
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        mevcut = _bul(conn, book_slug, source)
        _tabani_denetle(mevcut, taban_surum)
        kitap_surumu = None

        def surum_al() -> int:
            nonlocal kitap_surumu
            if kitap_surumu is None:
                kitap_surumu = _kitap_surumunu_artir(conn, book_slug)
            return kitap_surumu

        if mevcut is None:
            satir = _satir_ekle(conn, book_slug, {
                "source": source, "target": target, "origin": origin or "manual",
                "kosul": None if kosul is KORU else ((kosul or "").strip() or None),
            })
            _gecmise_yaz(conn, book_slug, "ekle", None, satir, origin or "manual", surum_al())
        else:
            degisen: dict = {"target": target}
            if origin is not None:
                degisen["origin"] = origin
            if kosul is not KORU:
                degisen["kosul"] = (kosul or "").strip() or None
            satir = _satiri_guncelle(conn, book_slug, mevcut, degisen, origin or "manual", surum_al)
        conn.commit()
        return satir
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def gecmis(book_slug: str, source: str) -> list[dict]:
    """Bir kaydın değişiklik geçmişi, yeniden eskiye.

    Kayıt duruyorsa KİMLİĞİYLE aranır (yeniden adlandırma/yazım varyantı kopmaz);
    silinmişse yazımdan (fold) bulunur."""
    conn = _connect()
    try:
        mevcut = _bul(conn, book_slug, normalize_source(source) or source)
        if mevcut and mevcut.get("kimlik"):
            rows = conn.execute(
                "SELECT id, source, islem, onceki, sonraki, yol, zaman, kitap_surumu "
                "FROM sozluk_gecmis WHERE book_slug = ? AND kimlik = ? ORDER BY id DESC LIMIT ?",
                (book_slug, mevcut["kimlik"], GECMIS_MAX),
            ).fetchall()
        else:
            anahtar = fold_term(source)
            rows = [
                r for r in conn.execute(
                    "SELECT id, source, islem, onceki, sonraki, yol, zaman, kitap_surumu "
                    "FROM sozluk_gecmis WHERE book_slug = ? ORDER BY id DESC",
                    (book_slug,),
                )
                if fold_term(r[1]) == anahtar
            ][:GECMIS_MAX]
    finally:
        conn.close()
    return [
        {
            "id": r[0], "source": r[1], "islem": r[2],
            "onceki": json.loads(r[3]) if r[3] else None,
            "sonraki": json.loads(r[4]) if r[4] else None,
            "yol": r[5], "zaman": r[6], "kitap_surumu": r[7],
        }
        for r in rows
    ]


def get_kosullar(book_slug: str) -> dict[str, str]:
    """Koşulu OLAN kayıtlar: {kaynak: koşul}. Koşulsuzlar listeye girmez.

    Ayrı fonksiyon: `get_glossary` sade eşlemeyi döndürmeye devam etmeli — çeviri
    yolu yalnız onu istiyor ve sözleşmesini değiştirmek `translate_chapter`'a
    kadar sızardı (`get_glossary_rows` aynı gerekçeyle ayrı durur).
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT source, kosul FROM glossary "
            "WHERE book_slug = ? AND kosul IS NOT NULL AND TRIM(kosul) <> '' "
            "ORDER BY source COLLATE NOCASE",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: r[1] for r in rows}


def set_kosul(book_slug: str, source: str, kosul: str | None) -> bool:
    """Bir kaydın koşulunu yaz ya da (boş verilirse) temizle. Kayıt yoksa False.

    `set_term`'den AYRI tutulur, çünkü ikisinin "verilmedi" anlamı zıttır:
    `set_term` koşulu almadığında onu KORUMALI (okuyucunun kuyruğu yalnız
    {source,target} gönderir ve koşulu sessizce silmesi, alanı görünmez bir
    tuzağa çevirirdi); bu fonksiyon ise boş değeri "temizle" diye okur.
    """
    source = normalize_source(source)
    if not source:
        return False
    conn = _connect()
    try:
        mevcut = _bul(conn, book_slug, source)
        if mevcut is None:
            return False
    finally:
        conn.close()
    terimi_yaz(book_slug, mevcut["source"], mevcut["target"], kosul=kosul or "", origin=None)
    return True


def get_glossary(book_slug: str) -> dict[str, str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT source, target FROM glossary WHERE book_slug = ? "
            "ORDER BY source COLLATE NOCASE",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: row[1] for row in rows}


def bolumdeki_sozluk(book_slug: str, chapter_no: int | None) -> dict[str, str]:
    """Bu bölüm çevrilirken sözlükte DURAN kayıtlar (köken sütununa göre).

    Geriye dönük uyum denetimi (`scripts/uyum_denetle.py`) için. Denetim BUGÜNKÜ
    sözlüğe göre ölçerse yalan söyler: 200. bölümde kaydedilmiş bir terim, 50.
    bölüm çevrilirken prompt'ta YOKTU — model onu ihlal edemezdi. Ölçülen etki
    gerçek DB'de büyük: en eski bölümler (henüz `model` sütunu yokken çevrilenler)
    kitabın bugün 200+ kayıtlık sözlüğüne göre denetlenince ihlal sayısı şişiyor.

    `first_chapter` None olan kayıtlar KAPSANIR: elle eklenenler ve köken
    sütunlarından önceki satırlar öyledir, dışlamak kullanıcının kendi yazdığı
    kayıtları denetim dışı bırakırdı — oysa asıl önemsenen kayıtlar onlar.
    Eşitlik de kapsanır: terim o bölümde algılandıysa karşılığı modelin KENDİ
    seçimidir, metin içinde tutarlı kullanmış olması beklenir.

    `chapter_no` bilinmiyorsa süzme yapılmaz (sözlüğün tamamı döner).
    """
    if chapter_no is None:
        return get_glossary(book_slug)
    return {
        r["source"]: r["target"]
        for r in get_glossary_rows(book_slug)
        if r["first_chapter"] is None or r["first_chapter"] <= chapter_no
    }


def get_glossary_rows(book_slug: str) -> list[dict]:
    """Sözlük satırları KÖKEN bilgisiyle (sözlük ekranı + künye rozeti için).

    `get_glossary` sade eşlemeyi döndürmeye devam eder — çeviri yolu yalnız onu
    ister ve sözleşmesini değiştirmek `translate_chapter`'a kadar sızardı.
    Eski satırlarda köken alanları None'dır. `surum` istemcinin çakışma tabanıdır.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT {_SATIR_SUTUNLARI} FROM glossary WHERE book_slug = ? "
            "ORDER BY source COLLATE NOCASE",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    # Koşul ve köken cümlesi ekranda GÖRÜNMELİ: görünmeyen bir kural, terim yanlış
    # çevrildiğinde hata ayıklanamaz hâle gelir.
    return [dict(zip(_SATIR_ALANLARI, r)) for r in rows]


def all_terms(book_slug: str | None = None) -> list[tuple[str, str, str]]:
    """Tüm kitapların (ya da tek kitabın) kayıtları: (slug, kaynak, karşılık).

    Bakım aracı için (`scripts/sozluk_gozden_gecir.py`): kitap-başına `get_glossary`
    slug listesini bilmeyi gerektirirdi, sözlükte ise kütüphanede artık olmayan
    slug'lar da bulunabiliyor.
    """
    conn = _connect()
    try:
        sorgu = "SELECT book_slug, source, target FROM glossary"
        parametre: tuple = ()
        if book_slug:
            sorgu += " WHERE book_slug = ?"
            parametre = (book_slug,)
        rows = conn.execute(sorgu + " ORDER BY book_slug, source", parametre).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def set_term(
    book_slug: str, source: str, target: str | None, origin: str = "manual"
) -> None:
    """Terimi elle ekle/güncelle (sözlük ekranı, okurken hızlı ekleme, bakım aracı).

    Otomatik yolla (`merge_terms`) AYNI iki sertleştirmeyi uygular; eskiden yalnız
    `.strip()` vardı ve iki yol ayrışıyordu:

    * **`normalize_source`** — çekim eki/noktalama atılır. Kullanıcı "Sunny's"
      seçip eklediğinde anahtar "Sunny" olur.
    * **`fold_term` ile mevcut satırı bul** — yazım varyantı İKİNCİ SATIR AÇMAZ.
      Sözlükte "Ore Empire" varken "OreEmpire" eklenirse yeni kayıt açılmaz,
      mevcut kaydın karşılığı güncellenir.

    Kayıtlı YAZIM korunur; değişen yalnız karşılıktır. Kullanıcı iradesi üstündür:
    otomatik algılamanın aksine mevcut karşılığı bilerek ezer. Koşul ve köken
    TAŞINIR (bkz. `terimi_yaz`).
    """
    terimi_yaz(book_slug, source, target, origin=origin)


# ---------- yedek: tam kayıt dışa/içe aktarma ----------
# Dışa aktarma eskiden yalnız `kaynak -> karşılık` taşıyordu: boş bir veritabanına
# geri yüklenen "yedek" KOŞULLARI (prompt'ta kural olan bağlam bilgisi) ve kökeni
# sessizce kaybediyordu. Biçim artık sürümlüdür; eski biçim (`terms` eşlemesi)
# okunmaya devam eder ve yeni yedek de onu taşır — önbellekteki eski bir okuyucu
# yeni dosyayı tümden reddetmesin.
YEDEK_BICIMI = "novellink-sozluk"
YEDEK_SURUMU = 2
# Kayıt başına taşınan alanlar (kaynak hariç). Sıra dosyada okunaklılık içindir.
YEDEK_ALANLARI = ("target", "kosul", "origin", "created_at", "first_chapter", "kaynak_cumle")
IMPORT_STRATEJILERI = ("mevcut", "dosya")
_METIN_SINIRI = {"source": 200, "target": 500, "kosul": 2000, "origin": 40, "kaynak_cumle": 2000}


def disa_aktar(book_slug: str) -> dict:
    """Kitabın sözlüğünü TAM kayıtlarıyla yedek sözlüğüne çevir (JSON'a hazır)."""
    satirlar = get_glossary_rows(book_slug)
    return {
        "bicim": YEDEK_BICIMI,
        "surum": YEDEK_SURUMU,
        "book_slug": book_slug,
        "disa_aktarim_zamani": time.time(),
        "kayit_sayisi": len(satirlar),
        "kayitlar": satirlar,
        # GERİYE UYUM: eski okuyucu yalnız bu eşlemeyi okur.
        "terms": {r["source"]: r["target"] for r in satirlar},
    }


def _yedek_kaydi(ham) -> dict | None:
    """Dosyadan gelen tek kaydı doğrula; yalnız DOSYADA OLAN alanları döndür.

    "Alan yok" ile "alan null" AYRIDIR: `dosya` stratejisinde yok olan alan mevcut
    değeri korur, null olan temizler. Tip hatalı kayıt bütünüyle geçersizdir —
    yarım doğru bir kaydı yazmak, dosyanın geri kalanının da doğru olduğu
    izlenimini verirdi.
    """
    if not isinstance(ham, dict):
        return None
    kaynak = ham.get("source")
    if not isinstance(kaynak, str) or len(kaynak) > _METIN_SINIRI["source"]:
        return None
    kaynak = normalize_source(kaynak)
    if not kaynak:
        return None
    kayit: dict = {"source": kaynak}
    for alan in ("target", "kosul", "origin", "kaynak_cumle"):
        if alan in ham:
            deger = ham[alan]
            if deger is not None and (not isinstance(deger, str) or len(deger) > _METIN_SINIRI[alan]):
                return None
            kayit[alan] = deger.strip() if isinstance(deger, str) else None
    if "created_at" in ham:
        deger = ham["created_at"]
        if deger is not None and (isinstance(deger, bool) or not isinstance(deger, (int, float))):
            return None
        kayit["created_at"] = float(deger) if deger is not None else None
    for alan in ("first_chapter", "surum"):
        if alan in ham:
            deger = ham[alan]
            if deger is not None and (isinstance(deger, bool) or not isinstance(deger, int)):
                return None
            kayit[alan] = deger
    # Kimlik yalnız BİÇİMİ doğruysa taşınır; bozuk bir kimlik yenisiyle değişir.
    kimlik = ham.get("kimlik")
    if isinstance(kimlik, str) and re.fullmatch(r"[0-9a-f]{8,32}", kimlik):
        kayit["kimlik"] = kimlik
    return kayit


def ice_aktar(book_slug: str, kayitlar: list, strateji: str = "mevcut") -> dict:
    """Yedek kayıtlarını kitabın sözlüğüne yaz; sayımları döndür.

    `mevcut`: kayıtlı terim (yazım varyantı dahil) HİÇ değişmez, yalnız eksikler
    eklenir — sözlük kullanıcınındır. `dosya`: dosyadaki alanlar kayıtlı terimin
    üzerine yazılır (masaüstünde toplu düzeltip geri yüklemenin yolu); dosyada
    OLMAYAN alan korunur. Kayıtlı yazım korunur, değişen yalnız alanlardır.

    Kayıttaki `kimlik` kitapta boştaysa korunur: silinip GERİ ALINAN terim aynı
    kimlikle döner ve geçmişi kopmaz.

    Tek bağlantı ve tek işlem: yüzlerce kayıtlık bir yedek yarım yazılmasın.
    """
    if strateji not in IMPORT_STRATEJILERI:
        raise ValueError(f"Bilinmeyen strateji: {strateji!r}")
    sonuc = {"gelen": len(kayitlar), "eklenen": 0, "guncellenen": 0, "atlanan": 0, "gecersiz": 0}
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        mevcut = {
            fold_term(r["source"]): r
            for r in (
                dict(zip(_SATIR_ALANLARI, s))
                for s in conn.execute(
                    f"SELECT {_SATIR_SUTUNLARI} FROM glossary WHERE book_slug = ?", (book_slug,)
                )
            )
        }
        kimlikler = {r["kimlik"] for r in mevcut.values()}
        kitap_surumu = None

        def surum_al() -> int:
            nonlocal kitap_surumu
            if kitap_surumu is None:
                kitap_surumu = _kitap_surumunu_artir(conn, book_slug)
            return kitap_surumu

        dosyada: set[str] = set()
        for ham in kayitlar:
            kayit = _yedek_kaydi(ham)
            if kayit is None:
                sonuc["gecersiz"] += 1
                continue
            anahtar = fold_term(kayit["source"])
            if anahtar in dosyada:
                sonuc["atlanan"] += 1  # dosyada aynı terimin ikinci yazımı: ilki kazanır
                continue
            dosyada.add(anahtar)
            kayitli = mevcut.get(anahtar)
            if kayitli is None:
                yeni = {
                    "source": kayit["source"],
                    "target": kayit.get("target") or kayit["source"],  # boş = aynen koru
                    "created_at": kayit.get("created_at") or time.time(),
                    "origin": kayit.get("origin") or "import",
                    "first_chapter": kayit.get("first_chapter"),
                    "kosul": kayit.get("kosul") or None,
                    "kaynak_cumle": kayit.get("kaynak_cumle") or None,
                    "kimlik": kayit.get("kimlik") if kayit.get("kimlik") not in kimlikler else None,
                    "surum": (kayit.get("surum") or 0) + 1,
                }
                yeni = _satir_ekle(conn, book_slug, yeni)
                kimlikler.add(yeni["kimlik"])
                _gecmise_yaz(conn, book_slug, "ekle", None, yeni, "import", surum_al())
                mevcut[anahtar] = yeni
                sonuc["eklenen"] += 1
            elif strateji == "dosya":
                degisen = {}
                for a in YEDEK_ALANLARI:
                    if a not in kayit:
                        continue
                    deger = kayit[a]
                    if a == "target":
                        deger = deger or kayitli["source"]
                    elif a in ("kosul", "kaynak_cumle", "origin"):
                        deger = deger or None
                    degisen[a] = deger
                if degisen:
                    _satiri_guncelle(conn, book_slug, kayitli, degisen, "import", surum_al)
                sonuc["guncellenen"] += 1
            else:
                sonuc["atlanan"] += 1
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return sonuc


def semayi_hazirla() -> None:
    """Sözlük tablosunu ve sütunlarını oluştur/göç et (başka modülün işleminden önce)."""
    _connect().close()


def kitaba_tasi(conn: sqlite3.Connection, kaynak_slug: str, hedef_slug: str) -> None:
    """Bir kitabın sözlüğünü başka kitaba TAŞI (birleştirme), çağıranın bağlantısında.

    Eskiden `INSERT OR IGNORE ... SELECT source, target` idi: koşul ve köken
    sütunları kopyalanmıyordu, ve `(kitap, kaynak)` anahtarı birebir aynı olmayan
    bir YAZIM VARYANTI hedefte ikinci satır açıyordu. Hedefteki kayıt her zaman
    kazanır (kullanıcının oradaki düzenlemesi bozulmaz). Kimlik ve sürüm taşınır;
    kaynağın GEÇMİŞİ de hedefe geçer.

    Commit ETMEZ: birleştirme bölümleri, alias'ları ve kitap satırını aynı işlemde
    değiştiriyor; sözlük taşıması onun parçasıdır. ÖN KOŞUL: çağıran, işlemi
    açmadan ÖNCE `semayi_hazirla()` çağırmış olmalı — tembel göç (ALTER TABLE)
    açık bir yazma işleminin içinden ikinci bağlantıyla yapılırsa kilitlenir.
    """
    hedefte = {
        fold_term(r[0])
        for r in conn.execute("SELECT source FROM glossary WHERE book_slug = ?", (hedef_slug,))
    }
    satirlar = [
        dict(zip(_SATIR_ALANLARI, r))
        for r in conn.execute(
            f"SELECT {_SATIR_SUTUNLARI} FROM glossary WHERE book_slug = ? "
            "ORDER BY created_at IS NULL, created_at",
            (kaynak_slug,),
        )
    ]
    conn.execute(
        "UPDATE sozluk_gecmis SET book_slug = ? WHERE book_slug = ?", (hedef_slug, kaynak_slug)
    )
    tasinan = [s for s in satirlar if fold_term(s["source"]) not in hedefte]
    kitap_surumu = _kitap_surumunu_artir(conn, hedef_slug) if tasinan else None
    for satir in tasinan:
        hedefte.add(fold_term(satir["source"]))
        _satir_ekle(conn, hedef_slug, satir)
        _gecmise_yaz(conn, hedef_slug, "tasi", None, satir, "merge", kitap_surumu)
    conn.execute("DELETE FROM glossary WHERE book_slug = ?", (kaynak_slug,))
    conn.execute("DELETE FROM sozluk_surumu WHERE book_slug = ?", (kaynak_slug,))


def delete_term(
    book_slug: str,
    source: str,
    taban_surum: int | None = None,
    yol: str = "manual",
) -> dict | None:
    """Terimi sil; silinen satırı TAM hâliyle döndür (yoksa None).

    Dönüş değeri GERİ ALMA içindir: okuyucu silinen kaydı içe aktarma ucuyla
    (dosya stratejisi) geri yazar ve koşul + köken + KİMLİK kaybolmaz. Yalnız
    karşılık geri gelseydi geri alınan kayıt "elle, şimdi eklendi" görünür ve
    prompt'taki bağlam kuralı sessizce yok olurdu.

    Eşleştirme `fold_term` ile: "OreEmpire" silme isteği "Ore Empire" kaydını
    bulur — `set_term` de aynı kuralla yazıyor. `taban_surum` verilirse ve kayıt
    o sürümde değilse `SurumCakismasi` fırlar (öteki cihazın düzeltmesi sessizce
    silinmesin).
    """
    anahtar = normalize_source(source) or source
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        bulunan = _bul(conn, book_slug, anahtar)
        _tabani_denetle(bulunan, taban_surum)
        if bulunan is None:
            conn.rollback()
            return None
        conn.execute(
            "DELETE FROM glossary WHERE book_slug = ? AND source = ?",
            (book_slug, bulunan["source"]),
        )
        _gecmise_yaz(conn, book_slug, "sil", bulunan, None, yol, _kitap_surumunu_artir(conn, book_slug))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return bulunan


# Yazım varyantı ayırıcıları. Aynı özel ad metinde "Ore Empire", "OreEmpire",
# "Ore-Empire" diye geçebiliyor; bunlar TEK terimdir.
_FOLD_SEP_RE = re.compile(r"[\s\-_'’.·]+")


def fold_term(name: str) -> str:
    """Terimi yazım varyantından bağımsız KARŞILAŞTIRMA anahtarına indirger.

    ``Ore Empire`` · ``OreEmpire`` · ``ore-empire`` · ``ORE  EMPIRE`` → ``oreempire``.

    Yalnız karşılaştırma içindir; sözlükte SAKLANAN anahtar `normalize_source`
    çıktısıdır (kullanıcı ekranda okunaklı yazımı görmeli). Bu ayrım olmadan aynı
    ad iki satır olur ve karşılıkları ayrışır.
    """
    return _FOLD_SEP_RE.sub("", (name or "").strip()).casefold()


def normalize_source(name: str) -> str:
    """Terimi sözlük anahtarı hâline getir: çevresel noktalama + iyelik eki atılır.

    Model bazen ismi cümledeki çekimli hâliyle döndürüyor (``Sunny's``, ``"Nephis"``).
    Kök hâle indirgemezsek aynı karakter sözlükte iki satır olur ve karşılıkları
    ayrışır. Çeviri tarafı eki kendisi getirdiğinden anahtar kök olmalı.
    """
    term = (name or "").strip().strip("\"'“”‘’()[]{}.,;:!?")
    for suffix in ("'s", "’s", "s'", "s’"):
        if len(term) > len(suffix) + 1 and term.endswith(suffix):
            return term[: -len(suffix)].strip()
    return term


def merge_terms(
    book_slug: str,
    mapping: dict[str, str] | None,
    origin: str = "auto",
    chapter_no: int | None = None,
    cumleler: dict[str, str] | None = None,
) -> dict[str, str]:
    """Otomatik algılanan terimleri (kaynak -> karşılık) ekle.

    Kayıtlı terime DOKUNULMAZ: kullanıcının elle yazdığı karşılık ASLA ezilmez —
    sözlük kullanıcınındır, otomatik algılama yalnız BOŞLUĞU doldurur. Anahtar
    `normalize_source` ile kök hâline indirilir (çekim eki/noktalama atılır) ve
    "zaten kayıtlı mı" kararı `fold_term` ile verilir (yazım varyantı sayılmaz),
    yoksa aynı terim iki satır olur ve karşılıkları ayrışır.

    Döner: FİİLEN eklenenler (zaten kayıtlı olanlar hariç) — okuyucudaki bölüm
    künyesi bunu gösterir.

    `origin`/`chapter_no` köken sütunlarına yazılır: "bu karşılığı model mi yazdı,
    hangi bölümde" sorusu eskiden cevapsızdı ve yanlış bir otomatik karşılık
    görüldüğünde kaynağı izlenemiyordu. Her ekleme geçmişe de yazılır.
    """
    if not mapping:
        return {}
    seen: dict[str, str] = {}
    gorulen: set[str] = set()
    for raw_kaynak, raw_hedef in mapping.items():
        term = normalize_source(raw_kaynak)
        hedef = (raw_hedef or "").strip() or term  # boş karşılık = aynen koru
        if not term:
            continue
        anahtar = fold_term(term)
        if anahtar not in gorulen:  # aynı yanıtta "Ore Empire" + "OreEmpire" gelebilir
            gorulen.add(anahtar)
            seen[term] = hedef
    if not seen:
        return {}
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Karşılaştırma `fold_term` üzerinden: kayıtlı terimin YAZIM VARYANTI yeni
        # satır açmamalı. Okuma yazma kilidi ALINDIKTAN sonra yapılır: eşzamanlı
        # iki çeviri aynı terimi iki kez eklemesin.
        mevcut = {
            fold_term(r[0])
            for r in conn.execute(
                "SELECT source FROM glossary WHERE book_slug = ?", (book_slug,)
            )
        }
        eklenecek = {k: h for k, h in seen.items() if fold_term(k) not in mevcut}
        if eklenecek:
            simdi = time.time()
            kitap_surumu = _kitap_surumunu_artir(conn, book_slug)
            for k, h in eklenecek.items():
                # Köken cümlesi ILK görülen hâlinde kalır — "ilk nerede geçti"
                # sorusunun cevabı sonraki bölümlerde değişmemeli.
                satir = _satir_ekle(conn, book_slug, {
                    "source": k, "target": h, "created_at": simdi, "origin": origin,
                    "first_chapter": chapter_no, "kaynak_cumle": (cumleler or {}).get(k),
                })
                _gecmise_yaz(conn, book_slug, "ekle", None, satir, origin, kitap_surumu)
        conn.commit()
        return eklenecek
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ornek_doldur(book_slug: str, source: str, cumle: str | None, bolum: int | None) -> bool:
    """Okurken eklenen terimin KÖKENİNİ (cümle + bölüm) YALNIZ boşsa yaz.

    Elle eklenen kayıtta köken hiç yoktu: sözlük ekranındaki "BÖLÜM N" bağlantısı
    ve köken cümlesi yalnız otomatik kayıtlarda çıkıyordu. Okuma panelinden
    eklenen terimin geldiği bölüm ve cümle bilinir; kaydedilmemesi bilgi kaybıdır.
    "İlk boş olana yaz" kuralı `merge_terms` ile aynı: köken "ilk nerede görüldü"
    sorusunun cevabıdır, sonraki düzeltmeler onu değiştirmez. Eşleştirme
    `fold_term` ile (yazım varyantı aynı kayıttır).
    """
    anahtar = fold_term(normalize_source(source) or source)
    cumle = (cumle or "").strip()[: _METIN_SINIRI["kaynak_cumle"]]
    conn = _connect()
    try:
        bulunan = next(
            (
                r[0]
                for r in conn.execute("SELECT source FROM glossary WHERE book_slug = ?", (book_slug,))
                if fold_term(r[0]) == anahtar
            ),
            None,
        )
        if bulunan is None:
            return False
        degisen = 0
        if cumle:
            degisen += conn.execute(
                "UPDATE glossary SET kaynak_cumle = ? WHERE book_slug = ? AND source = ? "
                "AND (kaynak_cumle IS NULL OR kaynak_cumle = '')",
                (cumle, book_slug, bulunan),
            ).rowcount
        if isinstance(bolum, int) and not isinstance(bolum, bool):
            degisen += conn.execute(
                "UPDATE glossary SET first_chapter = ? WHERE book_slug = ? AND source = ? "
                "AND first_chapter IS NULL",
                (bolum, book_slug, bulunan),
            ).rowcount
        conn.commit()
        return degisen > 0
    finally:
        conn.close()


def set_kaynak_cumle(book_slug: str, source: str, cumle: str | None) -> bool:
    """Kaydın köken cümlesini YALNIZ boşsa yazar; doldurulduysa döner True.

    "İlk boş olana yaz" kuralı `merge_terms`in `INSERT OR IGNORE` davranışıyla
    aynı: köken "ilk nerede gördük" sorusunun cevabıdır ve sonradan gelen bir
    geçiş onu değiştirmemeli.
    """
    cumle = (cumle or "").strip()
    if not cumle:
        return False
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE glossary SET kaynak_cumle = ? WHERE book_slug = ? AND source = ? "
            "AND (kaynak_cumle IS NULL OR kaynak_cumle = '')",
            (cumle, book_slug, source),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def merge_names(
    book_slug: str,
    names: list[str] | None,
    origin: str = "auto",
    chapter_no: int | None = None,
    cumleler: dict[str, str] | None = None,
) -> dict[str, str]:
    """Otomatik algılanan İNGİLİZCE KALACAK adları ekle (yalnız KARAKTER adları).

    Lonca/yer gibi diğer özel adlar Türkçe'ye çevrilir ve `merge_terms` ile
    karşılığıyla yazılır — İngilizce kalan tek sınıf kişi adlarıdır.


    Karşılık = kaynağın kendisi (`X -> X`): çeviride İngilizce yazımıyla durur,
    yalnız Türkçe eki alır. Döner: fiilen eklenenler.
    """
    return merge_terms(
        book_slug, {ad: ad for ad in (names or []) if ad}, origin, chapter_no,
        cumleler,
    )


# ---------- yakın terim uyarısı (yazım hatası olabilecek çiftler) ----------
# Gerçek vaka: aynı varlık kaynak sitede bazı bölümlerde `Orc Empire`, bazılarında
# `Ore Empire` yazılmıştı; yalnız yanlış yazım sözlükte kayıtlı olduğu için 157
# geçişin olduğu 29 bölümde sözlük hiç devreye girmemişti.
#
# OTOMATİK BİRLEŞTİRME YOK — aynı örnek neden birleştirilmemesi gerektiğini de
# gösteriyor: `ore` (maden damarı) romanda gerçek anlamıyla da geçiyor, tek harf
# farkı gerçek bir anlam farkı olabilir. Karar kullanıcınındır; bu yalnız uyarı.


def _fark_yeri(a: str, b: str) -> tuple[int, str] | None:
    """İki dizi arasında TEK karakterlik fark varsa (indis, tür); yoksa None."""
    if a == b or abs(len(a) - len(b)) > 1:
        return None
    if len(a) == len(b):
        farklar = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return (farklar[0], "degisim") if len(farklar) == 1 else None
    kisa, uzun = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(kisa) and kisa[i] == uzun[i]:
        i += 1
    return (i, "ekleme") if kisa[i:] == uzun[i + 1:] else None


def _cogul_cifti(a: str, b: str) -> bool:
    """`evilbeast` / `evilbeasts` gibi tekil-çoğul çifti mi (MEŞRU, uyarı değil)?"""
    kisa, uzun = (a, b) if len(a) < len(b) else (b, a)
    return uzun in (kisa + "s", kisa + "e")


def yakin_terimler(book_slug: str) -> list[tuple[str, str]]:
    """Yazım hatası olabilecek terim çiftleri (tek karakter farklı), gürültü elenmiş.

    Ham "tek karakter farkı" ölçütü KULLANILAMAZ: gerçek sözlükte 21 çift buldu
    ve 14'ü meşrudu — tekil/çoğul (`Evil Beast` / `Evil Beasts`, ki desen zaten
    çoğulu yakalıyor) ve rakam farkı (`Tier 2` / `Tier 3`). Uyaran her şeye
    uyaran bir kapı görmezden gelinir, o yüzden ikisi de elenir; geriye 376
    kayıtta 7 uyarı kalıyor ve hepsi insan gözü istiyor (`Orc`/`Ore`,
    `Yan Ya`/`Yaya`, `Song`/`Seong`).

    Karşılaştırma `fold_term` üzerinden — yazım varyantı zaten tek terimdir ve
    `merge_terms`/`set_term` onu ayrı satır açtırmaz; buraya düşmemeli.
    """
    satirlar = [(s, fold_term(s)) for s in get_glossary(book_slug)]
    ciftler: list[tuple[str, str]] = []
    for i, (kaynak_a, fa) in enumerate(satirlar):
        for kaynak_b, fb in satirlar[i + 1:]:
            yer = _fark_yeri(fa, fb)
            if not yer or _cogul_cifti(fa, fb):
                continue
            idx = yer[0]
            if fa[idx:idx + 1].isdigit() or fb[idx:idx + 1].isdigit():
                continue  # "Tier 2" / "Tier 3" — meşru ayrı kayıtlar
            ciftler.append((kaynak_a, kaynak_b))
    return ciftler


# ---------- bakım raporları (scripts/sozluk_gozden_gecir.py) ----------
# Hepsi ÇEVRİMDIŞI: saf SQLite sorgusu, model çağrısı yok. Hiçbiri otomatik
# değiştirmez — sözlük kullanıcınındır, bunlar yalnız "şuraya bak" der.

# Ortak kelime gruplamasında anlam taşımayan kelimeler.
_DURAK_KELIMELER = {"of", "the", "a", "an", "and", "de", "da", "ve"}


def _kelimeler(terim: str) -> list[str]:
    """Terimi karşılaştırılabilir kelimelere ayırır (`fold_term` ile aynı ayırıcılar).

    `translate._term_parts` daha zengin (CamelCase de böler) ama translate bu
    modülden import ediyor — ters yönde bağımlılık döngü yaratırdı. Buradaki
    sezgisel için basit bölme yeterli.
    """
    return [p for p in _FOLD_SEP_RE.split((terim or "").strip()) if p]


def karsilik_cakismalari(book_slug: str) -> list[tuple[str, list[str]]]:
    """Aynı Türkçe karşılığa giden FARKLI kaynaklar.

    Kasıtlı olabilir (`Orc Empire` ve `Ore Empire` aynı varlığın iki yazımı,
    ikisi de `Ork İmparatorluğu`ya bağlandı) ya da hata olabilir — iki ayrı
    şeyin aynı karşılığı alması onları çeviride ayırt edilemez kılar. Karar
    kullanıcınındır; bu yalnız rapordur.

    İngilizce korunan kayıtlar (`X -> X`) DIŞARIDA: karşılıkları zaten kaynağın
    kendisi olduğu için çakışma kavramı onlar için anlamsız.
    """
    gruplar: dict[str, list[str]] = {}
    for kaynak, hedef in get_glossary(book_slug).items():
        if fold_term(kaynak) == fold_term(hedef or ""):
            continue
        gruplar.setdefault(fold_term(hedef or ""), []).append(kaynak)
    return [(h, sorted(k)) for h, k in gruplar.items() if len(k) > 1]


def kardes_tutarsizliklari(book_slug: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Ortak kaynak kelimesi taşıyan terimlerde büyük-harf stili AYRIŞMASI.

    Vaka: `Star-Moon Kingdom -> Yıldız-Ay Krallığı` yanında
    `Star-Moon City -> yıldız ay şehri` (küçük harf, tiresiz). Aynı ad ailesi,
    farklı yazım — cümle içinde biri özel ad gibi, öteki cins isim gibi okunur.

    Tel tuzağıdır: yazılmış hatayı bulur, ama asıl işi otomatik eklemenin
    ileride yenisini yazmasını GÖRÜNÜR kılmaktır. Ölçüm günü (2026-08-23) gerçek
    sözlükte 0 bulgu verdi — o gün vakalar zaten elle temizlenmişti.
    """
    sozluk = get_glossary(book_slug)
    gruplar: dict[str, list[tuple[str, str]]] = {}
    for kaynak, hedef in sozluk.items():
        if not hedef or fold_term(kaynak) == fold_term(hedef):
            continue  # İngilizce korunanda büyük-harf stili kaynağın kendisidir
        for kelime in _kelimeler(kaynak):
            anahtar = kelime.casefold()
            if len(anahtar) >= 3 and anahtar not in _DURAK_KELIMELER:
                gruplar.setdefault(anahtar, []).append((kaynak, hedef))
    # Aynı terim ailesi birden çok ortak kelime altında görünür ("Star-Moon
    # Kingdom" / "Star-Moon City" hem `star` hem `moon` grubunda). Aynı bulguyu
    # iki kez söyleyen rapor gürültüdür; üye kümesi başına TEK kayıt tutulur.
    out: list[tuple[str, list[tuple[str, str]]]] = []
    gorulen: set[frozenset[str]] = set()
    for kelime, uyeler in sorted(gruplar.items()):
        if len(uyeler) < 2:
            continue
        if len({u[1][:1].isupper() for u in uyeler}) < 2:
            continue
        imza = frozenset(u[0] for u in uyeler)
        if imza in gorulen:
            continue
        gorulen.add(imza)
        out.append((kelime, sorted(uyeler)))
    return out

