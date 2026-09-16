"""Çevrilen bölümlerin kalıcı önbelleği (SQLite).

Bir bölüm bir kez çevrildikten sonra burada saklanır; tekrar açıldığında
API'ye gidilmeden anında döner. Tarayıcıdan bağımsızdır (PC + telefon paylaşır).
"""
from __future__ import annotations

import json
import sqlite3
import time

from . import db


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chapters (
            url TEXT PRIMARY KEY,
            book_slug TEXT,
            book_title TEXT,
            title TEXT,
            chapter_no INTEGER,
            translation TEXT,
            next_url TEXT,
            detected_names TEXT,
            chunk_count INTEGER,
            created_at REAL,
            prev_url TEXT,
            source_text TEXT
        )
        """
    )
    # Eski DB'ler için idempotent migration'lar.
    db.ensure_column(conn, "chapters", "prev_url", "prev_url TEXT")
    # source_text: çeviriyle paragraf-hizalı İngilizce kaynak (iki-dilli okuma).
    db.ensure_column(conn, "chapters", "source_text", "source_text TEXT")
    # raw_source (E-18): içe aktarımın DEĞİŞMEZ ham kaynağı. source_text hizalı
    # iki-dilli metindir ve hizalama tutmayınca bilerek NULL olur — ikisi
    # birbirinin yerine geçemez. Sentetik refresh/¶-yeniden-çevir buradan okur.
    db.ensure_column(conn, "chapters", "raw_source", "raw_source TEXT")
    # content_type (E-10): NULL/"text" = düz metin bölüm (web/paste). "html" = görsel
    # içerik (PDF çevrilmiş sayfa <img> / EPUB yerinde-çevrili HTML) — okuyucu
    # translation'ı paragraf yerine innerHTML olarak render eder; iki-dilli/¶-yeniden-
    # çevir/arama devre dışı.
    db.ensure_column(conn, "chapters", "content_type", "content_type TEXT")
    # KÜNYE (okuyucudaki rozet): bu bölümü hangi motor çevirdi ve o çeviride sözlüğe
    # hangi terimler EKLENDİ. Sözlüğe otomatik ekleme sessiz çalışıyor ve hatalı bir
    # karşılığı kalıcılaştırabiliyor (gerçek bulgu: kaynak sitenin yazım hatası
    # "Ore Empire" sözlüğe "Maden İmparatorluğu" diye girmişti — doğrusu ork ırkı,
    # "Ork İmparatorluğu"); görünür olması gerekiyor. Cache'te saklanır, yoksa ikinci açılışta
    # (önbellek isabeti) künyesini kaybederdi.
    db.ensure_column(conn, "chapters", "engine", "engine TEXT")
    db.ensure_column(conn, "chapters", "added_terms", "added_terms TEXT")  # JSON eşleme
    # Motorun İÇİNDEKİ model: `engine` yalnız "gemini" der, oysa zincirin hangi halkası
    # çevirdi (3.6 mı flash-lite mı) kalite sorularının cevabı orada. Bu bilgi daha önce
    # yalnız çalışma zamanında vardı ve kayboluyordu → "bunu hangi model çevirdi"
    # tahminle cevaplanıyordu. Eski satırlarda NULL; rozet yalnız motoru gösterir.
    db.ensure_column(conn, "chapters", "model", "model TEXT")
    # SÖZLÜK UYUM BAYRAĞI: bu çeviride, Türkçe karşılığı sözlükte KAYITLI olduğu
    # hâlde İngilizce kalan terimler (JSON eşleme). Zincir yalnız erişilebilirliğe
    # bakarak iniyor ve kaliteyi hiçbir yerde ölçmüyordu; ölçüm (2026-08-30, Shadow
    # Slave 110 bölüm) halkaların sözlüğe EŞİT uymadığını gösterdi: 3.6-flash 60
    # bölümde 5 ihlal, flash-lite 4 bölümde 36. Lite'ın çevirisi sessizce kalıcı
    # önbelleğe yazılıp bir daha kontrol edilmiyordu. NULL = hiç denetlenmedi (eski
    # satır), "{}" = denetlendi ve temiz — ikisi AYRI, rozet yalnız ikincisine güvenir.
    db.ensure_column(conn, "chapters", "glossary_leaks", "glossary_leaks TEXT")
    # İNGİLİZCE KALINTI BAYRAĞI: onarım turundan SONRA hâlâ çevrilmemiş paragraflar
    # (JSON, indeks -> metin). Ölçüm (2026-09-05, 392 hizalı bölüm): hizalama
    # tuttuğu hâlde 6 paragraf İngilizce dönmüştü ve hiçbir denetim bunu görmüyordu
    # — `_split_by_markers` yalnız YAPIYI, `glossary_leaks` yalnız KAYITLI terimleri
    # denetliyor. NULL = hiç denetlenmedi (eski satır), "{}" = denetlendi ve temiz.
    db.ensure_column(conn, "chapters", "ingilizce_kalinti", "ingilizce_kalinti TEXT")
    # SÖZLÜK SÜRÜMÜ (2026-09-16): bölüm çevrilirken kitabın sözlüğü hangi
    # sürümdeydi (`glossary.kitap_surumu`). `first_chapter` bunu söyleyemiyordu —
    # eski bir bölüm sonradan yeniden çevrilmiş olabilir. NULL = bilinmiyor.
    db.ensure_column(conn, "chapters", "sozluk_surumu", "sozluk_surumu INTEGER")
    # ÇEVİRİ ARŞİVİ: yeniden çeviri (sözlük düzeltmesi sonrası) eski çeviriyi
    # sessizce eziyordu; yeni çeviri daha kötü çıkarsa (hizalama kaybı, kalıntı)
    # geri dönüş yoktu. Metin değişen HER yazımda eski hâl buraya düşer, url
    # başına son `ARSIV_MAX` tutulur.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ceviri_arsivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            translation TEXT NOT NULL,
            source_text TEXT,
            engine TEXT,
            model TEXT,
            glossary_leaks TEXT,
            ingilizce_kalinti TEXT,
            sozluk_surumu INTEGER,
            ceviri_zamani REAL,
            arsiv_zamani REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ceviri_arsivi_url ON ceviri_arsivi (url, id)")
    return conn


ARSIV_MAX = 3
_ARSIV_SUTUNLARI = (
    "translation", "source_text", "engine", "model", "glossary_leaks", "ingilizce_kalinti",
    "sozluk_surumu",
)


def _arsivle(conn: sqlite3.Connection, url: str, yeni_ceviri: str | None) -> None:
    """Satırın ŞU ANKİ çevirisi yenisinden farklıysa arşive koy (aynı bağlantıda).

    Künye-yalnız güncellemeler (çeviri metni None ya da aynı) arşivlenmez: arşiv
    "geri dönülebilecek çeviriler" listesidir, gürültü değil."""
    if yeni_ceviri is None:
        return
    satir = conn.execute(
        f"SELECT {', '.join(_ARSIV_SUTUNLARI)}, created_at FROM chapters WHERE url = ?", (url,)
    ).fetchone()
    if not satir or not satir[0] or satir[0] == yeni_ceviri:
        return
    conn.execute(
        f"INSERT INTO ceviri_arsivi (url, {', '.join(_ARSIV_SUTUNLARI)}, ceviri_zamani, "
        f"arsiv_zamani) VALUES (?, {', '.join('?' for _ in _ARSIV_SUTUNLARI)}, ?, ?)",
        (url, *satir, time.time()),
    )
    conn.execute(
        "DELETE FROM ceviri_arsivi WHERE url = ? AND id NOT IN "
        "(SELECT id FROM ceviri_arsivi WHERE url = ? ORDER BY id DESC LIMIT ?)",
        (url, url, ARSIV_MAX),
    )


def arsiv_listesi(url: str) -> list[dict]:
    """Bölümün arşivlenmiş çevirileri, yeniden eskiye (metin YOK — yalnız künye)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, model, engine, sozluk_surumu, ceviri_zamani, arsiv_zamani, "
            "length(translation), glossary_leaks, ingilizce_kalinti, source_text IS NOT NULL "
            "FROM ceviri_arsivi WHERE url = ? ORDER BY id DESC",
            (url,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0], "model": r[1], "engine": r[2], "sozluk_surumu": r[3],
            "ceviri_zamani": r[4], "arsiv_zamani": r[5], "uzunluk": r[6],
            "ihlal": len(json.loads(r[7] or "{}")), "kalinti": len(json.loads(r[8] or "{}")),
            "hizali": bool(r[9]),
        }
        for r in rows
    ]


def son_arsiv_id(url: str) -> int | None:
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT MAX(id) FROM ceviri_arsivi WHERE url = ?", (url,)
        ).fetchone()
    finally:
        conn.close()
    return r[0] if r else None


def arsivden_geri_yukle(url: str, arsiv_id: int) -> bool:
    """Arşivdeki çeviriyi geri koy; şu anki çeviri de arşive düşer (geri alma da
    geri alınabilir). `created_at` TAZELENİR: telefonun önbelleği bu zamana
    bakarak kopyasının bayat olduğunu anlar. Kayıt yoksa False."""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        satir = conn.execute(
            f"SELECT {', '.join(_ARSIV_SUTUNLARI)} FROM ceviri_arsivi WHERE id = ? AND url = ?",
            (arsiv_id, url),
        ).fetchone()
        if satir is None or conn.execute(
            "SELECT 1 FROM chapters WHERE url = ?", (url,)
        ).fetchone() is None:
            conn.rollback()
            return False
        conn.execute("DELETE FROM ceviri_arsivi WHERE id = ?", (arsiv_id,))
        _arsivle(conn, url, satir[0])
        conn.execute(
            f"UPDATE chapters SET {', '.join(a + ' = ?' for a in _ARSIV_SUTUNLARI)}, "
            "created_at = ? WHERE url = ?",
            (*satir, time.time(), url),
        )
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_chapter(url: str) -> dict | None:
    """Önbellekte varsa ÇEVRİLMİŞ bölümü döndürür (cached=True), yoksa None.

    E-17: sahneli satırlar (translation IS NULL — içe aktarım işi henüz
    çevirmedi) okuma yolunda cache MISS sayılır; yalnız iş yolu onları gezer
    (get_staged). Aksi halde okuyucu boş bölüm alırdı."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT book_slug, book_title, title, chapter_no, translation, "
            "next_url, detected_names, chunk_count, prev_url, source_text, content_type, "
            "engine, added_terms, model, glossary_leaks, ingilizce_kalinti, sozluk_surumu, "
            "created_at "
            "FROM chapters WHERE url = ? AND translation IS NOT NULL",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "book_slug": row[0],
        "book_title": row[1],
        "title": row[2],
        "chapter_no": row[3],
        "translation": row[4],
        "next_url": row[5],
        "detected_names": json.loads(row[6] or "[]"),
        "chunk_count": row[7],
        "prev_url": row[8],
        "source": row[9],
        "content_type": row[10] or "text",
        # Künye: eski satırlarda NULL (sütun sonradan eklendi) → okuyucu rozeti çizmez.
        "engine": row[11],
        "added_terms": json.loads(row[12] or "{}"),
        "model": row[13],
        # NULL (hiç denetlenmedi) da "{}" (denetlendi, temiz) de okuyucuya boş gelir;
        # ayrım DB'de duruyor ve bakım aracı oradan "hangi bölüm hiç denetlenmedi"
        # sorusunu cevaplayabiliyor.
        "glossary_leaks": json.loads(row[14] or "{}"),
        # Aynı kural: NULL da "{}" da okuyucuya boş gelir; ayrım DB'de durur.
        "ingilizce_kalinti": json.loads(row[15] or "{}"),
        "sozluk_surumu": row[16],
        "ceviri_zamani": row[17],
        "cached": True,
    }


def list_chapters(book_slug: str) -> list[dict]:
    """Bir kitabın bölümleri, numaraya göre sıralı. `translated` = çevirisi HAZIR mı.

    Satırlar SAHNELENMİŞ de olabilir (`translation` NULL): içe aktarılan PDF/EPUB/
    manga sayfaları çeviriden ÖNCE bu tabloya yazılır ve okundukça çevrilir. Liste
    onları da içerir — okuyucu bölüm listesinde görünmeleri gerekiyor.

    `translated` bayrağı bu yüzden LOAD-BEARING: bir bölümü GET'lemek çevirisi
    yoksa ÇEVİRİ TETİKLER, yani ücretli model seçiliyken PARA harcar. Toplu indirme
    yolları (elle "çevrimdışı indir" ve otomatik tarama) yalnız `translated` olanları
    ister; ikisi de "indir" diyor, "çevir" demiyor. Bayrak olmadan otomatik tarama,
    içe aktarılan bir kitabı sessizce baştan sona çevirtirdi.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT url, title, chapter_no, "
            "       (translation IS NOT NULL AND trim(translation) <> ''), created_at "
            "  FROM chapters WHERE book_slug = ? "
            " ORDER BY chapter_no IS NULL, chapter_no",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    # `ceviri_zamani`: satırın son yazıldığı an (`save_chapter` her yazımda tazeler).
    # Telefonun önbelleğindeki kopyanın bayat olup olmadığı buna bakılarak anlaşılır:
    # başka cihazdan yeniden çevrilen bölüm, telefona kendiliğinden inmez.
    return [
        {"url": r[0], "title": r[1], "chapter_no": r[2], "translated": bool(r[3]),
         "ceviri_zamani": r[4]}
        for r in rows
    ]


def prev_translation(
    book_slug: str, prev_url: str | None, chapter_no: int | None
) -> str:
    """Bir önceki bölümün Türkçe metni — yeni bölümün çeviri bağlamı için.

    Önce `prev_url` denenir (zincir doğrudan bağlıysa kesin sonuç); yoksa aynı
    kitapta bu bölümden KÜÇÜK en büyük numaralı bölüme düşülür (elle eklenen ya da
    zinciri kopuk bölümlerde de bağlam bulunsun). Görsel bölümler (`content_type`
    "html") atlanır: içlerinde çeviri bağlamı olarak kullanılabilecek düz metin yok.
    Bulunamazsa boş string.
    """
    if prev_url:
        row = get_chapter(prev_url)
        if row and row.get("content_type") != "html" and (row.get("translation") or "").strip():
            return row["translation"]
    if not book_slug or chapter_no is None:
        return ""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT translation FROM chapters WHERE book_slug = ? AND chapter_no < ? "
            "AND translation IS NOT NULL AND IFNULL(content_type, 'text') != 'html' "
            "ORDER BY chapter_no DESC LIMIT 1",
            (book_slug, chapter_no),
        ).fetchone()
    finally:
        conn.close()
    return (row[0] or "") if row else ""


def kaynak_kapsamasi(book_slug: str) -> tuple[int, int, str]:
    """(toplam bölüm, kaynak metni OLAN bölüm, birleşik kaynak metin).

    Sözlük bakım aracının "ölü kayıt" raporu için: bir terimin kitabın hiçbir
    bölümünde geçmediğini ancak kaynak metin kapsaması YÜKSEKSE söyleyebiliriz.
    Kapsama düşükken (ör. 61 bölümün 2'sinde kaynak var) "geçmiyor" demek
    yanıltıcıdır ve meşru bir kaydı sildirebilir — çağıran oranı görüp karar verir.
    """
    conn = _connect()
    try:
        toplam = conn.execute(
            "SELECT COUNT(*) FROM chapters WHERE book_slug = ?", (book_slug,)
        ).fetchone()[0]
        satirlar = conn.execute(
            "SELECT source_text FROM chapters "
            "WHERE book_slug = ? AND source_text IS NOT NULL",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return toplam, len(satirlar), "\n".join(r[0] for r in satirlar)


def kaynak_bolumleri(book_slug: str) -> list[dict]:
    """Kaynak metni OLAN bölümler: (url, chapter_no, title, source).

    "Bu terimi düzeltirsem hangi bölümler etkilenir" sorusu için. Eşleştirme
    ÇEVİRİ metninde değil KAYNAK metinde yapılır: sözlük kaynağı görünce devreye
    giriyor, dolayısıyla etkilenecek bölümler kaynağında terim geçenlerdir.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT url, chapter_no, title, source_text, translation, created_at FROM chapters "
            "WHERE book_slug = ? AND source_text IS NOT NULL "
            "ORDER BY chapter_no",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"url": r[0], "chapter_no": r[1], "title": r[2], "source": r[3],
         "translation": r[4], "ceviri_zamani": r[5]}
        for r in rows
    ]


def bolum_kaynagi(url: str) -> str | None:
    """Bölümün hizalı İngilizce kaynağı (yoksa None) — "bu bölümde geçen terimler" için."""
    conn = _connect()
    try:
        row = conn.execute("SELECT source_text FROM chapters WHERE url = ?", (url,)).fetchone()
    finally:
        conn.close()
    return row[0] if row and (row[0] or "").strip() else None


def delete_chapter(url: str) -> bool:
    """Bölümü önbellekten sil (listeden kalkar). Kayıt silindiyse True döner."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM ceviri_arsivi WHERE url = ?", (url,))
        cur = conn.execute("DELETE FROM chapters WHERE url = ?", (url,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def denetim_bolumleri(book_slug: str | None = None) -> list[dict]:
    """Sözlük uyum denetimine girebilecek satırlar: kaynağı DA çevirisi DE olanlar.

    `kaynak_bolumleri` çeviriyi ve künyeyi taşımıyor; denetim ikisini de ister
    (ölçüm modele göre ayrıştırılabilsin diye `model` de gelir). Kaynağı olmayan
    bölüm (hizalama tutmamış) ölçülemez ve listeye girmez.

    `book_slug` verilmezse TÜM kitaplar taranır — araç varsayılan olarak her şeye
    bakar, süzgeç isteğe bağlıdır.
    """
    kosul = "translation IS NOT NULL AND source_text IS NOT NULL"
    parametreler: tuple = ()
    if book_slug:
        kosul += " AND book_slug = ?"
        parametreler = (book_slug,)
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT url, book_slug, chapter_no, title, source_text, translation, "
            f"model, glossary_leaks, ingilizce_kalinti FROM chapters WHERE {kosul} "
            "ORDER BY book_slug, chapter_no",
            parametreler,
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "url": r[0], "book_slug": r[1], "chapter_no": r[2], "title": r[3],
            "source": r[4], "translation": r[5], "model": r[6],
            # None = hiç denetlenmedi (araç bunu "işaretlenecek" sayar).
            "glossary_leaks": json.loads(r[7]) if r[7] else None,
            "ingilizce_kalinti": json.loads(r[8]) if r[8] else None,
        }
        for r in rows
    ]


def set_glossary_leaks(url: str, leaks: dict[str, str]) -> bool:
    """Cache satırının YALNIZ sözlük uyum bayrağını güncelle.

    Geriye dönük denetim (`scripts/uyum_denetle.py`) bunu kullanır: bayrak yalnız
    YENİ çevrilen bölümlerde doluyor, oysa bozukluk zaten önbellekteki eski
    bölümlerde duruyor (ölçüm: Shadow Slave 16, 18, 109, 110 — hepsi flash-lite).
    Denetim deterministik ve API'siz olduğu için eski satırlar da bedavaya
    işaretlenebilir.

    `save_chapter` tam payload ister; oradan geçmek çeviriyi/künyeyi yeniden yazma
    riski taşırdı. Boş dict "denetlendi, temiz" demektir ve NULL'dan (hiç
    denetlenmedi) AYRIDIR. Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET glossary_leaks = ? WHERE url = ?",
            (json.dumps(leaks or {}, ensure_ascii=False), url),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_ingilizce_kalinti(url: str, kalinti: dict) -> bool:
    """Cache satırının YALNIZ İngilizce-kalıntı bayrağını güncelle.

    `set_glossary_leaks` ile aynı gerekçe: bayrak yalnız YENİ çevrilen bölümlerde
    doluyor, oysa bozukluk zaten önbellekteki eski bölümlerde duruyor (ölçüm:
    shadow-slave 58, 177, 179, 181, 188, 194). Denetim deterministik ve API'siz
    olduğu için eski satırlar da bedavaya işaretlenebilir.

    Boş dict "denetlendi, temiz" demektir ve NULL'dan (hiç denetlenmedi) AYRIDIR.
    Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET ingilizce_kalinti = ? WHERE url = ?",
            (json.dumps(kalinti or {}, ensure_ascii=False), url),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_translation(
    url: str,
    translation: str,
    model: str | None = None,
    engine: str | None = None,
) -> bool:
    """Cache satırının çeviri metnini (ve isteğe bağlı künyesini) güncelle.

    Geriye dönük onarım (`scripts/kalinti_onar.py`) bunu kullanır. `save_chapter`
    tam payload ister; oradan geçmek gezinme alanlarını ve kaynağı yeniden yazma
    riski taşırdı — onarım YALNIZ sızan paragrafları düzeltip metni geri yazar.

    `model`/`engine` verilirse künye de tazelenir. Verilmesi ŞART değil ama
    verilmediğinde rozet, paragrafı fiilen onaran halkayı gizler: bu projede
    künyenin sabit yazılması bir kez doğrudan yanlış bilgiye dönüşmüştü (Mistral'in
    çevirdiği bölüm "GEMINI ile çevrildi" diyordu). Satır yoksa False."""
    alanlar = ["translation = ?"]
    degerler: list = [translation]
    if model:
        alanlar.append("model = ?")
        degerler.append(model)
    if engine:
        alanlar.append("engine = ?")
        degerler.append(engine)
    degerler.append(url)
    conn = _connect()
    try:
        _arsivle(conn, url, translation)  # onarım da geri alınabilir
        cur = conn.execute(
            f"UPDATE chapters SET {', '.join(alanlar)} WHERE url = ?", degerler
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_nav(url: str, next_url: str | None, prev_url: str | None) -> bool:
    """Cache satırının YALNIZ gezinme alanlarını güncelle (E-3, refresh_metadata).

    translation/source'a dokunmaz — gece kontrolü çeviri yakmadan ve ¶-yamalarını
    ezmeden yeni bölüm bağlantısını işleyebilsin. Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET next_url = ?, prev_url = ? WHERE url = ?",
            (next_url, prev_url, url),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_chapter_no(url: str, chapter_no: int) -> bool:
    """Cache satırının YALNIZ bölüm numarasını düzelt (bakım aracı).

    `update_nav` gibi dar tutuldu: çeviri/kaynak metne DOKUNMAZ. Numara okuyucudaki
    sıralamanın anahtarı, ama uydurulabilir bir alan — `fetch_into_book` bir dönem
    sayfanın kendi numarasını yok sayıp kuyruk sayacı veriyordu ve ARADAN eklenen
    bölüm yanlış numara alıyordu. Bu yardımcı, o dönemden kalan satırları
    `scripts/bolum_sirasi_denetle.py` ile düzeltmek için var. Satır yoksa False.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET chapter_no = ? WHERE url = ?", (chapter_no, url)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def tail_chapter(book_slug: str) -> dict | None:
    """Kitabın en yüksek numaralı (kuyruk) bölümü — zincire sona ekleme için."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT url, chapter_no FROM chapters WHERE book_slug = ? "
            "ORDER BY chapter_no IS NULL, chapter_no DESC LIMIT 1",
            (book_slug,),
        ).fetchone()
    finally:
        conn.close()
    return {"url": row[0], "chapter_no": row[1]} if row else None


def set_next(url: str, next_url: str | None) -> bool:
    """Yalnız bir satırın next_url'ünü güncelle (prev_url'e DOKUNMAZ). Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET next_url = ? WHERE url = ?", (next_url, url)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_staged(url: str) -> dict | None:
    """Satırı çeviri durumundan bağımsız döndür (İŞ YOLU — okuma yolu değil).

    İçe aktarım işi sahneli (translation NULL) satırları bununla gezer;
    raw_source (E-18) ham kaynağı taşır."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT book_slug, book_title, title, chapter_no, translation, "
            "next_url, prev_url, raw_source, content_type FROM chapters WHERE url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "book_slug": row[0], "book_title": row[1], "title": row[2],
        "chapter_no": row[3], "translation": row[4], "next_url": row[5],
        "prev_url": row[6], "raw_source": row[7], "content_type": row[8] or "text",
    }


def save_chapter(url: str, data: dict) -> None:
    """Çevrilen bölümü önbelleğe yaz (varsa üzerine).

    E-16: ON CONFLICT (REPLACE değil) — adı geçmeyen raw_source her çeviri
    yazımında sessizce silinmesin (içe aktarımın ham kaynağı değişmezdir).

    Künye alanları (engine/added_terms/model) COALESCE ile yazılır: bu alanları TAŞIMAYAN
    bir payload (örn. `_render_import_page`) aynı satırı güncellediğinde mevcut künye
    NULL'a düşmesin. Aynı E-16 sınıfı hata, farklı sütunlar."""
    conn = _connect()
    try:
        _arsivle(conn, url, data.get("translation"))
        conn.execute(
            """
            INSERT INTO chapters
                (url, book_slug, book_title, title, chapter_no,
                 translation, next_url, detected_names, chunk_count, created_at,
                 prev_url, source_text, content_type, engine, added_terms, model,
                 glossary_leaks, ingilizce_kalinti, sozluk_surumu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                book_slug = excluded.book_slug, book_title = excluded.book_title,
                title = excluded.title, chapter_no = excluded.chapter_no,
                translation = excluded.translation, next_url = excluded.next_url,
                detected_names = excluded.detected_names,
                chunk_count = excluded.chunk_count, created_at = excluded.created_at,
                prev_url = excluded.prev_url, source_text = excluded.source_text,
                content_type = excluded.content_type,
                engine = COALESCE(excluded.engine, engine),
                added_terms = COALESCE(excluded.added_terms, added_terms),
                model = COALESCE(excluded.model, model),
                glossary_leaks = COALESCE(excluded.glossary_leaks, glossary_leaks),
                ingilizce_kalinti = COALESCE(
                    excluded.ingilizce_kalinti, ingilizce_kalinti),
                sozluk_surumu = COALESCE(excluded.sozluk_surumu, sozluk_surumu)
            """,
            (
                url,
                data.get("book_slug"),
                data.get("book_title"),
                data.get("title"),
                data.get("chapter_no"),
                data.get("translation"),
                data.get("next_url"),
                json.dumps(data.get("detected_names") or [], ensure_ascii=False),
                data.get("chunk_count"),
                time.time(),
                data.get("prev_url"),
                data.get("source"),
                data.get("content_type"),
                data.get("engine"),
                # None bırakılır (boş dict DEĞİL): COALESCE'in eski künyeyi koruyabilmesi
                # için "bilgi yok" ile "bu bölümde hiçbir şey eklenmedi" ayrışmalı.
                json.dumps(data["added_terms"], ensure_ascii=False)
                if data.get("added_terms") is not None
                else None,
                data.get("model"),
                # added_terms ile aynı kural: None bırakılır (boş dict DEĞİL) ki
                # "hiç denetlenmedi" ile "denetlendi, temiz" ayrışsın ve COALESCE
                # künyesiz bir güncellemede eski bayrağı koruyabilsin.
                json.dumps(data["glossary_leaks"], ensure_ascii=False)
                if data.get("glossary_leaks") is not None
                else None,
                # glossary_leaks ile AYNI kural (None vs boş dict ayrımı).
                json.dumps(data["ingilizce_kalinti"], ensure_ascii=False)
                if data.get("ingilizce_kalinti") is not None
                else None,
                data.get("sozluk_surumu"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
