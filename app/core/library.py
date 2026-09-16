"""Kitap listesi + okuma konumu — cihazlar arası paylaşılır (sunucu tarafı).

Daha önce kütüphane tarayıcıda (localStorage) tutuluyordu; bu yüzden PC'de
eklenen kitap telefonda görünmüyordu. Artık sunucuda (chapters.db ile aynı
dosyada) tutulur, böylece tüm cihazlar aynı kütüphaneyi ve son okuma konumunu
paylaşır.
"""
from __future__ import annotations

import sqlite3
import time

from . import db, glossary


def _connect() -> sqlite3.Connection:
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            slug TEXT PRIMARY KEY,
            title TEXT,
            current_url TEXT,
            current_title TEXT,
            chapter_no INTEGER,
            updated_at REAL,
            current_ratio REAL
        )
        """
    )
    # Aynı kitabın farklı sitelerdeki slug'larını tek kanonik slug'a bağlar
    # (örn. only-i-level-up-wn -> solo-leveling).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, canonical TEXT)"
    )
    # Eski (current_ratio'suz) DB'ler için idempotent migration. Bölüm-içi okuma
    # oranı (0..1) burada tutulur → cihazlar arası "kaldığın yer" paylaşılır.
    db.ensure_column(conn, "books", "current_ratio", "current_ratio REAL")
    # Kitap yaşam durumu: okunuyor/beklemede/bitti (NULL = okunuyor). Rafta
    # filtre + kitap görünümünde düzenleme; sırtta gösterilmez (D-B2v2).
    db.ensure_column(conn, "books", "status", "status TEXT")
    # Manga sonsuz devam: son çekilen bölümün site URL'i + sonraki bölümün URL'i.
    # Okuyucu manga bölümünün sonuna gelince next_source_url'i çekip ekler (novel
    # sonsuz okumanın manga karşılığı). Yalnız web'den çekilen manga'da dolu.
    # Kapak adresi (kutuphane izgarasinda gosterilir). Cevirinin hicbir asamasi
    # buna bagli DEGIL: bos kalirsa izgara renkli sirt gorunumune duser.
    db.ensure_column(conn, "books", "cover", "cover TEXT")
    db.ensure_column(conn, "books", "manga_source_url", "manga_source_url TEXT")
    db.ensure_column(conn, "books", "manga_next_url", "manga_next_url TEXT")
    return conn


BOOK_STATUSES = ("okunuyor", "beklemede", "bitti")


def resolve_slug(slug: str) -> str:
    """Bir slug alias ise kanonik karşılığını, değilse kendisini döndürür."""
    if not slug:
        return slug
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE alias = ?", (slug,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else slug


def set_alias(alias: str, canonical: str) -> None:
    """`alias` slug'ını `canonical`'a yönlendir (resolve_slug bunu okur).

    Paste+web köprüsü: web devamı bir web bölümü çekildiğinde host-türevli slug
    (örn. renegade-immortal) hedef paste kitabına çözülsün → AYRI kitap açılmaz
    (bölünme fix). Boş/kendine yönlendirme yok sayılır; hedef başka bir alias ise
    kanonik köke iner (alias zinciri olmaz)."""
    alias = (alias or "").strip()
    canonical = (canonical or "").strip()
    if not alias or not canonical or alias == canonical:
        return
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE alias = ?", (canonical,)
        ).fetchone()
        if row:
            canonical = row[0]
        if alias == canonical:
            return
        conn.execute(
            "INSERT OR REPLACE INTO aliases (alias, canonical) VALUES (?, ?)",
            (alias, canonical),
        )
        conn.commit()
    finally:
        conn.close()


def merge_books(source: str, target: str) -> str:
    """`source` kitabını `target` kitabıyla birleştirir.

    Bölümler ve sözlük target'a taşınır, source kitabı listeden kalkar ve bundan
    sonra source slug'ından gelen her şey target'a yönlenir. Kanonik slug döner.
    """
    source = (source or "").strip()
    target = (target or "").strip()
    if not source or not target or source == target:
        return target or source
    # NOT (eski E-8 kaldırıldı): sentetik (paste-/…) kitaplar da birleştirilebilir.
    # Kullanıcı ch1'i yapıştırıp gerisini web'den çekince oluşan paste+web bölünmesini
    # tek seride toplayabilmeli. Merge yalnız book_slug'ı gruplar; next/prev URL
    # bazlı olduğundan zincir korunur. Bölüm no çakışması olursa liste ikisini de
    # gösterir (kişisel kullanım; kullanıcı bilinçli birleştirir).
    # Sözlük şeması işlem AÇILMADAN hazırlanır: tembel göç ikinci bir bağlantıda
    # ALTER TABLE yapar ve açık yazma işleminin içinden çağrılırsa kilitlenir.
    glossary.semayi_hazirla()
    conn = _connect()
    try:
        # Hedef kendisi bir alias'sa kanonik köke in (alias zinciri olmasın).
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE alias = ?", (target,)
        ).fetchone()
        if row:
            target = row[0]
        if target == source:
            return target
        # Bölümleri taşı (url PK olduğu için çakışma olmaz).
        try:
            conn.execute(
                "UPDATE chapters SET book_slug = ? WHERE book_slug = ?", (target, source)
            )
        except sqlite3.OperationalError:
            pass
        # Sözlüğü TAM kayıtlarıyla taşı (koşul + köken); hedefteki kayıt ve onun
        # yazım varyantı kazanır. Eskiden yalnız (kaynak, karşılık) kopyalanıyordu.
        glossary.kitaba_tasi(conn, source, target)
        # source'a bağlı eski alias'ları target'a yönlendir, sonra source->target ekle.
        conn.execute(
            "UPDATE aliases SET canonical = ? WHERE canonical = ?", (target, source)
        )
        conn.execute(
            "INSERT OR REPLACE INTO aliases (alias, canonical) VALUES (?, ?)",
            (source, target),
        )
        conn.execute("DELETE FROM books WHERE slug = ?", (source,))
        conn.commit()
    finally:
        conn.close()
    return target


def konum_adini_duzelt(slug: str, current_title: str | None, chapter_no: int | None) -> bool:
    """Okuma konumunun ADINI/NUMARASINI `current_url` ile tutarlı hâle getir.

    `current_url`'e ve `current_ratio`'ya DOKUNMAZ: kullanıcı nerede kaldıysa orada
    kalır, yalnız o bölümü ANLATAN türetilmiş alanlar düzeltilir.

    `upsert_book(update_position=False)` bu iş için KULLANILAMAZ — o, var olan
    satıra bilerek hiç dokunmuyor (`INSERT OR IGNORE`), çünkü amacı arka plan
    işlerinin konumu ilerletmesini önlemek. Bakım aracının ihtiyacı tam tersi:
    konumu ilerletmeden var olan satırı düzeltmek.

    Gerçek vaka (Shadow Slave, 2026-09-02): `current_url` 141. bölümü gösterirken
    `current_title` "Chapter 138" diyordu — okuyucu "kaldığın yer"de yanlış bölüm
    adı gösteriyordu. Satır yoksa False.
    """
    if not slug:
        return False
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE books SET current_title = ?, chapter_no = ? WHERE slug = ?",
            (current_title, chapter_no, slug),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def upsert_book(
    slug: str,
    title: str,
    current_url: str,
    current_title: str | None,
    chapter_no: int | None,
    update_position: bool = True,
) -> None:
    """Bir bölüm okununca kitabı + son okuma konumunu güncelle (paylaşılır).

    current_ratio yalnızca (url, ratio) çifti tutarlı kalsın diye yönetilir: yeni
    bir bölüme geçilince (url değişince) oran 0'a sıfırlanır; aynı bölüm tekrar
    açılınca (resume) korunur, böylece bölüm-içi konum geri yüklenebilir.

    update_position=False (toplu çeviri işi): kitap zaten kütüphanedeyse hiçbir
    şeye dokunma — arka planda hazırlanan bölüm "kaldığın yer"i İLERLETMEZ.
    Kitap henüz yoksa normal eklenir (kütüphanede görünsün).
    """
    if not slug:
        return
    conn = _connect()
    try:
        if not update_position:
            # Atomik: kitap yoksa ekle, varsa HİÇBİR şeye dokunma. SELECT-sonra-yaz
            # yapılsaydı, arada okuyucunun yazdığı gerçek konum INSERT OR REPLACE
            # ile ezilebilirdi (TOCTOU).
            conn.execute(
                """
                INSERT OR IGNORE INTO books
                    (slug, title, current_url, current_title, chapter_no,
                     updated_at, current_ratio)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (slug, title, current_url, current_title, chapter_no, time.time()),
            )
            conn.commit()
            return
        prev = conn.execute(
            "SELECT current_url, current_ratio FROM books WHERE slug = ?", (slug,)
        ).fetchone()
        # url değiştiyse (veya yeni kitap) oranı sıfırla; aynıysa mevcut oranı koru.
        ratio = 0.0
        if prev and prev[0] == current_url and prev[1] is not None:
            ratio = prev[1]
        # ON CONFLICT (INSERT OR REPLACE DEĞİL): REPLACE satırı siler ve yeniden
        # yazar — burada ADI GEÇMEYEN sütunlar (status, ileride has_new/
        # auto_translate/...) sessizce NULL'a sıfırlanırdı (E-16). Adlandırılmış
        # güncelleme yalnız konum alanlarına dokunur.
        conn.execute(
            """
            INSERT INTO books
                (slug, title, current_url, current_title, chapter_no, updated_at,
                 current_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                current_url = excluded.current_url,
                current_title = excluded.current_title,
                chapter_no = excluded.chapter_no,
                updated_at = excluded.updated_at,
                current_ratio = excluded.current_ratio
            """,
            (slug, title, current_url, current_title, chapter_no, time.time(), ratio),
        )
        conn.commit()
    finally:
        conn.close()


def set_position(
    slug: str,
    current_url: str,
    ratio: float,
    current_title: str | None = None,
    chapter_no: int | None = None,
) -> None:
    """Okuma konumunu kaydet (kaydırdıkça frontend çağırır).

    Konum bir ÜÇLÜDÜR: (url, ad, numara). Üçü birlikte yazılır, çünkü ad ve numara
    `current_url`i ANLATIR — ayrı yazılırlarsa satır kendi içinde tutarsızlaşır.

    Gerçek arıza (2026-09-12): burası yalnız `current_url`i ilerletiyordu ve ad/numara
    bir önceki bölümde kalıyordu (canlı satır: `current_url` 392'yi gösterirken
    `chapter_no` 391). İki katmanlı zarar veriyordu: (1) satır yanlış, (2) `updated_at`
    de tazelendiği için okuyucunun DOĞRU yerel kaydı (`resolveResume`, `local.ts >=
    serverTs` ölçütü) "bayat" sayılıp atılıyor ve ekrana bayat SUNUCU değeri
    çiziliyordu. Kullanıcı 391'deyken ana sayfa "BÖL. 390" diyordu; okuyucuya girip
    çıkınca yerel kayıt tazelenip düzeliyordu. Adı doğru yazan yol (`upsert_book`)
    devreye girmiyordu: indirilmiş bölüm Service Worker önbelleğinden geliyor,
    `GET /api/chapter` sunucuya hiç ulaşmıyor.

    Ad/numara VERİLMEDİYSE davranış URL'e bakar ve bilerek asimetriktir:
      * aynı bölümde kaydırma (url değişmedi) → mevcut ad KORUNUR. En sık çağrı bu;
        silmek her kaydırmada adı düşürürdü.
      * bölüm değişti (eski istemci üçlüyü göndermiyor) → ad/numara TEMİZLENİR.
        Eski adı korumak, adın artık BAŞKA bir bölümü anlatması demek ve okuyucu
        güvenle YANLIŞ bir numara çizer — düzeltmeye çalıştığımız arızanın kendisi.
        NULL'da fiş "SON BÖLÜM"e, sırt "OKU"ya düşer; eksik bilgi yanlıştan iyidir.

    Karar TEK bir UPDATE içinde SQL'le verilir: SET sağ tarafları satırın ESKİ
    değerleriyle hesaplanır, yani `current_url` karşılaştırması aynı deyimde
    güvenle yapılır. SELECT-sonra-yaz yapılsaydı arada gelen bir yazım ezilirdi
    (`upsert_book`taki TOCTOU gerekçesinin aynısı). Kitap yoksa sessizce yok sayılır.
    """
    if not slug or not current_url:
        return
    try:
        ratio = max(0.0, min(1.0, float(ratio)))
    except (TypeError, ValueError):
        return
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE books SET
                current_title = CASE
                    WHEN :title IS NOT NULL THEN :title
                    WHEN current_url = :url THEN current_title
                    ELSE NULL END,
                chapter_no = CASE
                    WHEN :no IS NOT NULL THEN :no
                    WHEN current_url = :url THEN chapter_no
                    ELSE NULL END,
                current_url = :url,
                current_ratio = :ratio,
                updated_at = :now
            WHERE slug = :slug
            """,
            {
                "title": current_title,
                "no": chapter_no,
                "url": current_url,
                "ratio": ratio,
                "now": time.time(),
                "slug": slug,
            },
        )
        conn.commit()
    finally:
        conn.close()


def clear_position_if(slug: str, url: str) -> None:
    """Kitabın 'kaldığın yer' işareti silinen bölümü gösteriyorsa temizle.

    Aksi halde 'devam et' düğmesi artık var olmayan bölüme götürür ve bölüm
    yeniden çekilip çevrilir (silme amacının tersi).
    """
    if not slug or not url:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE books SET current_url = NULL, current_title = NULL, "
            "chapter_no = NULL, current_ratio = 0, updated_at = ? "
            "WHERE slug = ? AND current_url = ?",
            (time.time(), slug, url),
        )
        conn.commit()
    finally:
        conn.close()


def set_status(slug: str, status: str) -> bool:
    """Kitabın yaşam durumunu değiştir (okunuyor/beklemede/bitti).

    Geçersiz durum veya bilinmeyen kitap → False (yazılmaz)."""
    if not slug or status not in BOOK_STATUSES:
        return False
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE books SET status = ? WHERE slug = ?", (status, slug)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_manga_source(slug: str, source_url: str | None, next_url: str | None) -> None:
    """Manga kitabının son çekilen bölüm URL'i + sonraki bölüm URL'ini kaydet.

    Web'den manga çekilince/devam edilince çağrılır; okuyucu next_url ile sonraki
    bölümü çeker. Kitap yoksa sessizce yok sayılır."""
    if not slug:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE books SET manga_source_url = ?, manga_next_url = ? WHERE slug = ?",
            (source_url or None, next_url or None, slug),
        )
        conn.commit()
    finally:
        conn.close()


def delete_book(slug: str) -> bool:
    """Kitabı ve ona bağlı HER ŞEYİ kalıcı sil: bölümler, sözlük, okuma günlüğü,
    alias'lar, books satırı. Bölümü olmayan (mükerrer içe aktarım kalıntısı) kitap
    da silinir. Herhangi bir satır silindiyse True. Geri alınamaz.

    Sentetik kitaplar merge'e sokulmaz (E-8) ama SİLİNEBİLİR — zincir tümüyle
    kalkar, kalan bir referans olmaz."""
    slug = (slug or "").strip()
    if not slug:
        return False
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        deleted = conn.execute("DELETE FROM books WHERE slug = ?", (slug,)).rowcount
        # chapters/glossary/reading_log/aliases tembel oluşturulur — henüz yoksa
        # OperationalError'ı yut (taze DB'de tablo olmayabilir, merge_books ile aynı desen).
        for stmt, params in (
            ("DELETE FROM chapters WHERE book_slug = ?", (slug,)),
            ("DELETE FROM glossary WHERE book_slug = ?", (slug,)),
            ("DELETE FROM reading_log WHERE slug = ?", (slug,)),
            ("DELETE FROM aliases WHERE alias = ? OR canonical = ?", (slug, slug)),
        ):
            try:
                deleted += conn.execute(stmt, params).rowcount
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return deleted > 0
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_cover(slug: str, cover: str | None) -> None:
    """Kitabin kapak adresini YALNIZ bos ise yazar.

    Kapak her bolumde yeniden yazilsaydi site kapagini degistirdigi gun kullanicinin
    gordugu gorsel bolum bolum ziplardi; kapak kitabin kimligidir, bolumun degil.
    Sozluge otomatik terim yaziminda oldugu gibi burada da kural "ilk yazan kazanir"
    ve elle duzeltme (bakim araci) bunu acikca ezer.
    """
    if not (cover or "").strip():
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE books SET cover = ? WHERE slug = ? "
            "AND (cover IS NULL OR cover = '')",
            (cover.strip(), slug),
        )
        conn.commit()
    finally:
        conn.close()


def list_books() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT slug, title, current_url, current_title, chapter_no, current_ratio, "
            "updated_at, status, cover FROM books ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "slug": r[0],
            "title": r[1],
            "current_url": r[2],
            "current_title": r[3],
            "chapter_no": r[4],
            "current_ratio": r[5] or 0.0,
            # updated_at: sunucu konumunun son yazılma zamanı (saniye). Frontend bunu
            # yerel "son okunan" işaretinin zaman damgasıyla kıyaslar (çevrimdışı resume).
            "updated_at": r[6] or 0.0,
            "status": r[7] or "okunuyor",  # NULL = okunuyor (eski satırlar)
            # Kapak: yalnız kütüphane ızgarasında kullanılır. NULL kalması
            # normaldir (içe aktarılan/paste kitapların kaynağı yok) ve
            # okuyucu o durumda renkli sırt görünümüne düşer.
            "cover": r[8],
        }
        for r in rows
    ]


def get_book(slug: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT slug, title, current_url, current_title, chapter_no, current_ratio, "
            "updated_at, status, manga_source_url, manga_next_url "
            "FROM books WHERE slug = ?",
            (slug,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "slug": row[0],
        "title": row[1],
        "current_url": row[2],
        "current_title": row[3],
        "chapter_no": row[4],
        "current_ratio": row[5] or 0.0,
        "updated_at": row[6] or 0.0,
        "status": row[7] or "okunuyor",
        "manga_source_url": row[8],
        "manga_next_url": row[9],
    }


def backfill_from_cache() -> None:
    """Önbellekte olup books tablosunda olmayan kitapları ekle (bir kez, var olanı bozmaz)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO books
                (slug, title, current_url, current_title, chapter_no, updated_at)
            SELECT c.book_slug, c.book_title, c.url, c.title, c.chapter_no, c.created_at
            FROM chapters c
            JOIN (
                SELECT book_slug, MAX(created_at) AS mc
                FROM chapters GROUP BY book_slug
            ) m ON c.book_slug = m.book_slug AND c.created_at = m.mc
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # chapters tablosu henüz yoksa (taze kurulum) sorun değil
    finally:
        conn.close()
