"""Okuma hızı ölçümü (hızlı okuma planı Adım A, 2026-11-08): bölüm oturumu ve kalan süre."""
from playwright.sync_api import expect

import tohum
from core import cache, db, reading_log

PARAGRAF = 12  # tohum metni ×12: kaydırılabilir, 1500 harften uzun


def _uzun_kitap():
    urller = tohum.kitap(bolum_sayisi=1)
    metin = "\n\n".join(tohum.TR * PARAGRAF)
    cache.save_chapter(urller[0], {
        "book_slug": "gumus-kule", "book_title": "Gumus Kule", "title": "Chapter 1",
        "chapter_no": 1, "translation": metin, "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1})
    return metin


def _satirlar():
    conn = db.connect()
    try:
        return conn.execute(
            "SELECT url, mode, chars, words, active_ms FROM reading_speed").fetchall()
    except Exception:
        return []
    finally:
        conn.close()


def _ac(sayfa):
    sayfa.set_viewport_size({"width": 390, "height": 600})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(
        len(tohum.TR) * PARAGRAF)


def test_bolum_sonuna_okununca_oturum_harf_sayisiyla_kaydedilir(sayfa):
    metin = _uzun_kitap()
    _ac(sayfa)
    sayfa.wait_for_timeout(1500)  # birkaç saniyelik tık birikimi
    # Okur gibi küçük adımlarla aşağı (tek adımda %20'den fazla atlama sayılır).
    for _ in range(80):
        sayfa.mouse.wheel(0, 120)
        sayfa.wait_for_timeout(40)
        if sayfa.evaluate("document.querySelector('#readerBody article.chapter')"
                          ".getBoundingClientRect().bottom <= innerHeight"):
            break
    harf = len("".join(metin.split()))
    for _ in range(50):
        if _satirlar():
            break
        sayfa.wait_for_timeout(100)
    satir = _satirlar()
    assert len(satir) == 1, satir
    url, mod, chars, words, ms = satir[0]
    assert mod == "serbest" and chars == harf and 0 < words <= chars and ms > 0
    # Birkaç saniyelik okuma 60 sn'den kısa: hıza girmez, pratik dakikası olarak kalır.
    assert reading_log.speed_stats(sayfa.evaluate(
        "(() => { const d = new Date(), p = n => String(n).padStart(2, '0');"
        " return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; })()"
    ))["oturum_sayisi"] == 0


def test_kalan_sure_kisisel_hizla_hesaplanir(sayfa):
    metin = _uzun_kitap()
    for i in range(10):  # 3000 harf/dk okuyan biri
        reading_log.log_speed(f"tohum-oturum-{i:02d}", "2026-11-01", "gumus-kule", f"u{i}",
                              "serbest", 6000, 900, 120_000, True)
    harf = len("".join(metin.split()))
    beklenen = max(1, round(harf / 3000))
    _ac(sayfa)
    sayfa.wait_for_function(
        "JSON.parse(localStorage.getItem('novellink:okuma-hizi') || 'null')?.kisisel_hiz?.hdk === 3000")
    sayfa.mouse.wheel(0, 10)  # kalan süre kaydırmayla tazelenir
    expect(sayfa.locator("#altKalan")).to_have_text(f"{beklenen} dk")


def test_tempo_yoklamasi_seridi_ve_zorlandim_hizi_dusurur(sayfa):
    sayfa.add_init_script(
        "localStorage.setItem('novellink:settings', JSON.stringify({kaydirmaHizi: 2000}))")
    _uzun_kitap()
    _ac(sayfa)
    serit = sayfa.locator("#yoklama")
    expect(serit).to_be_hidden()
    # İki tempo bölümü bitti (ölçüm modülünün haberi): ikincide şerit çıkar.
    sayfa.evaluate("""async () => {
        const m = await import('/js/yoklama.js');
        m.tempoBolumuBitti(true, true);
        m.tempoBolumuBitti(true, true);
    }""")
    expect(serit).to_be_visible()
    expect(serit).to_contain_text("Takip edebildin mi?")
    sayfa.locator("#yoklamaDugmeler [data-cevap='zorlandim']").click()
    expect(serit).to_be_hidden()
    assert sayfa.evaluate("JSON.parse(localStorage.getItem('novellink:settings')).kaydirmaHizi") == 1920


def test_ayarlarda_okuma_hizi_karti(sayfa):
    _uzun_kitap()
    for i in range(10):
        reading_log.log_speed(f"kart-oturum-{i:02d}", "2026-11-01", "gumus-kule", f"u{i}",
                              "serbest", 3000, 460, 120_000, True)
    _ac(sayfa)
    sayfa.locator("#settingsBtn").click()
    kart = sayfa.locator("#hizKarti")
    expect(kart).to_contain_text("kel/dk")
    expect(kart).to_contain_text("bugün okudun")
    expect(kart).to_contain_text("10 bölüm")
