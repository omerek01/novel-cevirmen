"""3. aşama kabul ölçütleri gerçek tarayıcıda: sürüm çakışması, geçmiş, çeviri
arşivine dönüş, telefondaki bayat bölüm kopyasının tazelenmesi."""
from __future__ import annotations

import json
import sqlite3
import time

import pytest
from playwright.sync_api import expect

import tohum
from yardimci import js_bekle

SLUG = "gumus-kule"


def _sozluge_git(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()


def _sunucu_terimleri(sayfa):
    return sayfa.evaluate("async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms")


def test_baska_cihazin_degisikligi_ezilmez_kullanici_karar_verir(sayfa):
    from core import glossary

    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Aziz"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    expect(sayfa.locator("#terimKarsilik")).to_have_value("Aziz")
    # Panel açıkken başka bir cihaz aynı terimi değiştirdi.
    glossary.set_term(SLUG, "Saint", "Evliya")
    sayfa.locator("#terimKarsilik").fill("Ermiş")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Gönderilemedi", timeout=10000)
    assert _sunucu_terimleri(sayfa)["Saint"] == "Evliya", "öteki cihazın değeri ezildi"
    sayfa.keyboard.press("Escape")
    not_ = sayfa.locator("#glossPending .gloss-pending-hata")
    expect(not_).to_contain_text("Başka bir cihazda değişti")
    expect(not_).to_contain_text("sunucuda şu an: Evliya")
    not_.get_by_role("button", name="Benimkini yaz").click()
    js_bekle(sayfa, "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Saint === 'Ermiş'"
    )
    expect(sayfa.locator("#glossPending")).to_be_hidden()


def test_cakismada_sunucudakini_kullanmak_yerel_degeri_birakir(sayfa):
    from core import glossary

    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Aziz"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    glossary.set_term(SLUG, "Saint", "Evliya")
    sayfa.locator("#terimKarsilik").fill("Ermiş")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Gönderilemedi", timeout=10000)
    sayfa.keyboard.press("Escape")
    sayfa.locator("#glossPending").get_by_role("button", name="Sunucudakini kullan").click()
    expect(sayfa.locator("#glossList .gloss-row .gloss-target-metin")).to_have_text("Evliya")
    expect(sayfa.locator("#glossPending")).to_be_hidden()


def test_ardisik_iki_kayit_kendi_kendiyle_cakismaz(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Aziz"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimKarsilik").fill("Ermiş")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Sunucuya kaydedildi", timeout=10000)
    sayfa.locator("#terimKarsilik").fill("Evliya")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Sunucuya kaydedildi", timeout=10000)
    assert _sunucu_terimleri(sayfa)["Saint"] == "Evliya"


def test_gecmis_listelenir_onceki_hal_forma_alinir(sayfa):
    from core import glossary

    tohum.kitap()
    glossary.merge_terms(SLUG, {"Great": "Ulu"}, "auto", 2)
    glossary.set_term(SLUG, "Great", "Yüce")
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimGecmisBtn").click()
    satirlar = sayfa.locator("#terimGecmis .terim-gecmis-satir")
    expect(satirlar).to_have_count(2)
    expect(satirlar.first).to_contain_text("Ulu → Yüce")
    expect(satirlar.nth(1)).to_contain_text("otomatik")
    satirlar.first.get_by_role("button", name="Bu hâli forma al").click()
    expect(sayfa.locator("#terimKarsilik")).to_have_value("Ulu")


def test_yeniden_ceviri_sonucu_eski_ceviriye_donulebilir(sayfa):
    urller = tohum.kitap(bolum_sayisi=1)
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    geri = []
    sayfa.route("**/api/book/*/retranslate", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"job_id": "is-2"}'))
    sayfa.route("**/api/bulk/is-2", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"state": "done", "message": "Bitti", "params": {"sonuclar": {
            urller[0]: {"durum": "tamam", "hizali": False, "ihlal": 0, "kalinti": 0,
                        "model": "gemini-2.5-flash", "arsiv_id": 7}}}})))

    def arsiv_geri(route):
        geri.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    sayfa.route("**/api/chapter/arsiv/geri", arsiv_geri)
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimEtkiBtn").click()
    sayfa.get_by_role("button", name="Seçilenleri yeniden çevir").click()
    sonuc = sayfa.locator("#terimEtki .terim-etki-sonuc")
    expect(sonuc).to_contain_text("hizalama tutmadı")
    sonuc.get_by_role("button", name="Eski çeviriye dön").click()
    expect(sonuc).to_have_text("ESKİ ÇEVİRİYE DÖNÜLDÜ")
    assert geri == [{"url": urller[0], "id": 7}]


@pytest.mark.sw_acik
def test_sunucuda_yeniden_cevrilen_bolumun_telefondaki_kopyasi_tazelenir(sayfa):
    from core import db

    urller = tohum.kitap(bolum_sayisi=2)
    sayfa.goto(sayfa.taban + "/")
    sayfa.evaluate("navigator.serviceWorker.ready.then(() => true)")
    sayfa.reload()
    sayfa.wait_for_function("() => !!navigator.serviceWorker.controller")
    ICERIK = """async (url) => {
      for (const k of await caches.keys()) {
        const c = await caches.open(k);
        for (const r of await c.keys()) {
          const u = new URL(r.url);
          if (u.pathname === '/api/chapter' && u.searchParams.get('url') === url) {
            return (await (await c.match(r)).json()).translation;
          }
        }
      }
      return null;
    }"""
    # İKİ bölüm de önbellekte ve tarama durulmuş olmalı: yeniden çeviri ilk ısıtma
    # sürerken yazılırsa telefon YENİ metni ilk seferde alır ve test tazelemeyi
    # hiç sınamaz (mutasyonla ölçüldü: bayatlık denetimi kapalıyken test geçiyordu).
    for url in urller:
        js_bekle(sayfa, f"async () => !!(await ({ICERIK})({json.dumps(url)}))", timeout=20000)
    sayfa.wait_for_timeout(1500)
    assert sayfa.evaluate(ICERIK, urller[0]) != "YENİ ÇEVİRİ"
    # Sunucuda yeniden çevrildi (başka bir cihazdan): çeviri zamanı kopyadan SONRA.
    conn = sqlite3.connect(db.db_path())
    conn.execute(
        "UPDATE chapters SET translation = ?, created_at = ? WHERE url = ?",
        ("YENİ ÇEVİRİ", time.time() + 30, urller[0]),
    )
    conn.commit()
    conn.close()
    sayfa.reload()  # kütüphane taraması yeniden koşar
    js_bekle(sayfa, f"async () => (await ({ICERIK})({json.dumps(urller[0])})) === 'YENİ ÇEVİRİ'", timeout=20000
    )
