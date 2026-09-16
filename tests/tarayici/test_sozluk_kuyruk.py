"""Sözlük kuyruğu v2 — kabul ölçütleri gerçek tarayıcıda.

Belge (2026-09-16) P0 bulguları:
* A gönderilirken B yazıldığında B kuyrukta kalır ve sunucuya ulaşır.
* Kaydedilmemiş değer hiçbir zaman kaydedilmiş gibi görünmez (depolama hatası,
  reddedilen istek).
"""
from __future__ import annotations

import json

from playwright.sync_api import expect

import tohum

SLUG = "gumus-kule"
GECIKTIR = """(() => {
  const asil = window.fetch.bind(window);
  window.fetch = (url, opts = {}) =>
    (opts.method || 'GET') !== 'GET' && String(url).includes('/glossary')
      ? new Promise((r) => setTimeout(r, %d)).then(() => asil(url, opts))
      : asil(url, opts);
})()"""


def _sozluge_git(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()


def _sunucu_terimleri(sayfa):
    return sayfa.evaluate(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms"
    )


def test_yaris_gonderim_surerken_yazilan_yeni_deger_sunucuya_ulasir(sayfa):
    sayfa.add_init_script(GECIKTIR % 1500)
    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Sen"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    alan = sayfa.locator("#terimKarsilik")
    expect(alan).to_have_value("Sen")
    alan.fill("Aziz")
    sayfa.locator("#terimKaydet").click()
    sayfa.wait_for_timeout(300)  # A uçuşta
    alan.fill("Ermiş")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Cihazda bekliyor")
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Saint === 'Ermiş'",
        timeout=15000,
    )
    sayfa.wait_for_function("() => !document.querySelector('.gloss-row-pending')", timeout=15000)
    assert _sunucu_terimleri(sayfa)["Saint"] == "Ermiş"


def test_eklenen_terim_gonderimden_sonra_suzgecte_kaybolmaz(sayfa):
    sayfa.add_init_script(GECIKTIR % 800)
    tohum.kitap()
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossSource").fill("Mira")
    sayfa.locator("#glossAddBtn").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Mira === 'Mira'"
    )
    sayfa.wait_for_function("() => !document.querySelector('#glossList .gloss-row-pending')")
    sayfa.locator("#glossSearch").fill("x")
    sayfa.locator("#glossSearch").fill("")
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(2)


def test_depolama_yazilamazsa_uyari_gorunur_ve_kayit_yine_gider(sayfa):
    sayfa.add_init_script(
        """(() => {
          const asil = Storage.prototype.setItem;
          Storage.prototype.setItem = function (k, v) {
            if (String(k).startsWith('novellink:glossQueue')) {
              throw new DOMException('dolu', 'QuotaExceededError');
            }
            return asil.call(this, k, v);
          };
        })()"""
    )
    sayfa.add_init_script(GECIKTIR % 1200)
    tohum.kitap()
    _sozluge_git(sayfa)
    sayfa.locator("#glossSource").fill("Kaan")
    sayfa.locator("#glossAddBtn").click()
    expect(sayfa.locator("#glossPending")).to_contain_text("YAZILAMADI")
    expect(sayfa.locator("#glossList .gloss-durum").first).to_have_text("KAYDEDİLMEDİ")
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Kaan === 'Kaan'"
    )


def test_reddedilen_istek_silinmez_sebebiyle_gorunur_vazgecilebilir(sayfa):
    tohum.kitap()
    _sozluge_git(sayfa)
    sayfa.route(
        "**/api/book/*/glossary",
        lambda route: route.fulfill(
            status=422, content_type="application/json",
            body=json.dumps({"detail": "geçersiz terim"}),
        ) if route.request.method == "POST" else route.continue_(),
    )
    sayfa.locator("#glossSource").fill("Bozuk")
    sayfa.locator("#glossAddBtn").click()
    satir = sayfa.locator("#glossPending .gloss-pending-hata")
    expect(satir).to_contain_text("Gönderilemedi")
    expect(satir).to_contain_text("geçersiz terim")
    expect(sayfa.locator("#glossList .gloss-row-hata")).to_have_count(1)
    satir.get_by_role("button", name="Vazgeç").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(0)
    expect(sayfa.locator("#glossPending")).to_be_hidden()


def test_429_kaydi_bekletir_sonra_gonderir(sayfa):
    tohum.kitap()
    _sozluge_git(sayfa)
    durum = {"red": True}
    sayfa.route(
        "**/api/book/*/glossary",
        lambda route: route.fulfill(status=429, body="{}")
        if route.request.method == "POST" and durum["red"] else route.continue_(),
    )
    sayfa.locator("#glossSource").fill("Kaan")
    sayfa.locator("#glossAddBtn").click()
    expect(sayfa.locator("#glossPending")).to_contain_text("sunucu 429")
    expect(sayfa.locator("#glossList .gloss-durum").first).to_have_text("CİHAZDA BEKLİYOR")
    durum["red"] = False
    # Otomatik yeniden deneme (5 sn) beklenmeden bağlantı olayı da tetikler.
    sayfa.evaluate("window.dispatchEvent(new Event('online'))")
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Kaan === 'Kaan'"
    )


def test_silme_geri_alinir_kosul_ve_koken_korunur(sayfa):
    tohum.kitap()
    from core import glossary

    glossary.merge_terms(SLUG, {"Great": "Ulu"}, "auto", 2, {"Great": "Ulu yaratık."})
    glossary.set_kosul(SLUG, "Great", "rütbe")
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    expect(sayfa.locator("#terimKosul")).to_have_value("rütbe")
    sayfa.locator("#terimSil").click()
    sayfa.wait_for_function(
        "async () => !('Great' in (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms)"
    )
    sayfa.locator("#bildirim .bildirim-eylem").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).kosullar.Great === 'rütbe'"
    )
    satir = {r["source"]: r for r in glossary.get_glossary_rows(SLUG)}["Great"]
    assert satir["origin"] == "auto" and satir["first_chapter"] == 2
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
