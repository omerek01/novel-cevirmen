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


def test_hiz_ayarlanir_ve_saklanir(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    deger = sayfa.locator("#otoKaydirDeger")
    expect(deger).to_have_text("4")
    sayfa.locator("#otoKaydirHizli").click()
    sayfa.locator("#otoKaydirHizli").click()
    expect(deger).to_have_text("6")
    expect(sayfa.locator("#otoKaydirCentik i.dolu")).to_have_count(6)
    assert sayfa.evaluate("JSON.parse(localStorage.getItem('novellink:settings')).kaydirmaSeviyesi") == 6
    for _ in range(20):
        if sayfa.locator("#otoKaydirYavas").is_disabled():
            break
        sayfa.locator("#otoKaydirYavas").click()
    expect(deger).to_have_text("1")
    expect(sayfa.locator("#otoKaydirYavas")).to_be_disabled()


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
