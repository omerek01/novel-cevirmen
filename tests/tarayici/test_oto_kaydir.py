"""Okuyucu: otomatik kaydırma ve ayarlanabilir hız (2026-11-01, kullanıcı isteği).

Yalnız okur başlatır; kumanda alt çubuğun yerini alır; duraklatınca durur; hız
seviyesi saklanır; kapatınca alt çubuk geri gelir.
"""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _okuyucu(sayfa):
    sayfa.set_viewport_size({"width": 390, "height": 420})  # kısa tohum metni kaydırılabilsin
    tohum.kitap(bolum_sayisi=3)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(len(tohum.TR))


def _baslat(sayfa):
    sayfa.locator("#altHap").click()
    sayfa.locator("#altKaydir").click()
    expect(sayfa.locator("#otoKaydir")).to_be_visible()


def test_kendiliginden_baslamaz_kaydir_ile_akar(sayfa):
    _okuyucu(sayfa)
    expect(sayfa.locator("#otoKaydir")).to_be_hidden()
    y0 = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(400)
    assert sayfa.evaluate("scrollY") == y0
    _baslat(sayfa)
    expect(sayfa.locator("#okuyucuAlt")).to_be_hidden()  # kumanda çubuğun yerini alır
    sayfa.wait_for_function(f"scrollY > {y0 + 5}")


def test_duraklat_durdurur_surdur_devam_eder(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    dugme = sayfa.locator("#otoKaydirDurdur")
    dugme.click()
    expect(dugme).to_have_attribute("aria-label", "Kaydırmayı sürdür")
    y = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(500)
    assert sayfa.evaluate("scrollY") == y
    dugme.click()
    sayfa.wait_for_function(f"scrollY > {y + 3}")


def _ayar(sayfa, anahtar):
    return sayfa.evaluate(f"JSON.parse(localStorage.getItem('novellink:settings'))?.{anahtar} ?? null")


def test_hiz_kel_dk_gosterilir_yuzde_5_adimla_ayarlanir_ve_saklanir(sayfa):
    """Hız birimi harf/dk (hızlı okuma planı §3): kumanda kel/dk gösterir, ± %5."""
    _okuyucu(sayfa)
    _baslat(sayfa)
    deger = sayfa.locator("#otoKaydirDeger")
    expect(sayfa.locator(".ok-hiz-etiket")).to_contain_text("kel/dk")
    assert _ayar(sayfa, "kaydirmaHizi") == 1600  # ne eski seviye ne kişisel hız: başlangıç
    ilk = int(deger.inner_text())
    sayfa.locator("#otoKaydirHizli").click()
    sayfa.locator("#otoKaydirHizli").click()
    assert _ayar(sayfa, "kaydirmaHizi") == 1764  # 1600 → 1680 → 1764
    assert int(deger.inner_text()) > ilk
    expect(sayfa.locator("#otoKaydirCentik i.dolu")).to_have_count(4)
    for _ in range(40):
        if sayfa.locator("#otoKaydirYavas").is_disabled():
            break
        sayfa.locator("#otoKaydirYavas").click()
    expect(sayfa.locator("#otoKaydirYavas")).to_be_disabled()
    assert _ayar(sayfa, "kaydirmaHizi") == 700


def test_eski_seviye_ayni_kaydirma_hiziyla_harf_dk_ya_cevrilir(sayfa):
    """Kayıtlı `kaydirmaSeviyesi` ilk başlatmada o anki çizimle çevrilir: akış hızı aynı kalır."""
    sayfa.add_init_script(
        "localStorage.setItem('novellink:settings', JSON.stringify({kaydirmaSeviyesi: 4}))")
    from core import cache

    sayfa.set_viewport_size({"width": 390, "height": 420})
    urller = tohum.kitap(bolum_sayisi=1)
    # Uzun bölüm: kısa tohum metninde çevrilen hız alt sınıra (700) takılır, akış hızlanırdı.
    uzun = "\n\n".join(tohum.TR * 12)
    cache.save_chapter(urller[0], {"book_slug": "gumus-kule", "book_title": "Gumus Kule",
                                   "title": "Chapter 1", "chapter_no": 1, "translation": uzun,
                                   "next_url": None, "prev_url": None, "detected_names": [],
                                   "chunk_count": 1})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody article.chapter p[data-idx]")).to_have_count(len(tohum.TR) * 12)
    _baslat(sayfa)
    sayfa.wait_for_function(
        "JSON.parse(localStorage.getItem('novellink:settings')).kaydirmaHizi > 0")
    assert _ayar(sayfa, "kaydirmaSeviyesi") is None
    y0 = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(2000)
    hiz = (sayfa.evaluate("scrollY") - y0) / 2
    # Seviye 4 = 16 px/sn. Pay: bölüm yüksekliği başlık ve künye çizilince biraz değişir.
    assert 12 <= hiz <= 22, hiz


def test_kapat_alt_cubugu_geri_getirir(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    sayfa.locator("#otoKaydirKapat").click()
    expect(sayfa.locator("#otoKaydir")).to_be_hidden()
    expect(sayfa.locator("#altHap")).to_be_visible()
    y = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(400)
    assert sayfa.evaluate("scrollY") == y


def test_secili_sozcuk_varken_durur_secim_kalkinca_surer(sayfa):
    """Uzun basıp sözcük seçince akış seçimin altından kaymamalı (kullanıcı bulgusu)."""
    _okuyucu(sayfa)
    _baslat(sayfa)
    sayfa.evaluate("""() => {
        const p = document.querySelector('#readerBody p[data-idx]');
        const r = document.createRange();
        r.setStart(p.firstChild, 0); r.setEnd(p.firstChild, 4);
        getSelection().removeAllRanges(); getSelection().addRange(r);
    }""")
    sayfa.wait_for_timeout(150)
    y = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(500)
    assert sayfa.evaluate("scrollY") == y
    expect(sayfa.locator("#otoKaydir")).to_be_visible()
    sayfa.evaluate("getSelection().removeAllRanges()")
    sayfa.wait_for_function(f"scrollY > {y + 3}")


def test_okuyucudan_cikinca_duraklatilmis_kumanda_kapanir(sayfa):
    """Duraklatılmışken döngü koşmadığı için kapanış hiç tetiklenmiyor, eski kumanda
    sonraki her açılışta alt çubuğun yerinde kalıyordu."""
    _okuyucu(sayfa)
    _baslat(sayfa)
    sayfa.locator("#otoKaydirDurdur").click()
    sayfa.evaluate("async () => { const g = await import('/js/gezinme.js'); g.showView('library'); }")
    sayfa.evaluate("async () => { const g = await import('/js/gezinme.js'); g.showView('reader'); }")
    expect(sayfa.locator("#otoKaydir")).to_be_hidden()  # geri dönünce eski kumanda yok


def test_sayfa_sonunda_yukleme_yoksa_kendiliginden_duraklar(sayfa):
    """Son bölümün dibinde döngü her karede boşuna dönüyor, ekran kilidi tutuluyordu."""
    sayfa.set_viewport_size({"width": 390, "height": 420})
    tohum.kitap(bolum_sayisi=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody article.chapter p[data-idx]")).to_have_count(len(tohum.TR))
    _baslat(sayfa)
    sayfa.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
    expect(sayfa.locator("#otoKaydirDurdur")).to_have_attribute(
        "aria-label", "Kaydırmayı sürdür", timeout=9000)


def test_kilit_istegi_yanitlanmadan_duraklatilirsa_kilit_birakilir(sayfa):
    """Kaydır'a basıp hemen duraklatınca bekleyen kilit sonradan çözülüyor ve hiç
    bırakılmıyordu: duraklatılmış ekran kararmıyor, pil tükeniyordu."""
    sayfa.add_init_script("""
        window.__kilitler = [];
        Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: {
            request: () => new Promise((coz) => setTimeout(() => {
                const k = new EventTarget();
                k.birakildi = false;
                k.release = async () => { k.birakildi = true; k.dispatchEvent(new Event('release')); };
                window.__kilitler.push(k);
                coz(k);
            }, 400)),
        }});
    """)
    _okuyucu(sayfa)
    _baslat(sayfa)
    sayfa.locator("#otoKaydirDurdur").click()
    sayfa.wait_for_timeout(900)
    assert sayfa.evaluate("window.__kilitler.length") >= 1
    assert sayfa.evaluate("window.__kilitler.every((k) => k.birakildi)")
