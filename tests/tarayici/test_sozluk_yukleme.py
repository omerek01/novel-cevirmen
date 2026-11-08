"""Sözlük listesi yavaş/düşen istekte (2026-11-08 canlı: 1233 kayıtlı sözlük "Henüz terim yok")."""
from playwright.sync_api import expect
import pytest
import tohum
from yardimci import js_bekle
from core import glossary

SLUG = "gumus-kule"
pytestmark = pytest.mark.parametrize("sayfa", [{"width": 375, "height": 812}], indirect=True)


def _kitabi_ac(sayfa):
    tohum.kitap()
    glossary.set_term(SLUG, "Abel", "Abel")
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()


@pytest.mark.sw_acik
def test_telefon_kopyasi_yokken_yavas_sozluk_beklenir_bos_gosterilmez(sayfa):
    _kitabi_ac(sayfa)
    js_bekle(sayfa, "() => !!navigator.serviceWorker.controller")
    bekleyen = []
    sayfa.context.route("**/api/book/gumus-kule/glossary", lambda r: bekleyen.append(r))
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.wait_for_timeout(5000)  # servis çalışanının 4 sn sınırını geç
    expect(sayfa.locator("#glossList")).not_to_contain_text("Henüz terim yok")
    assert bekleyen
    bekleyen[0].fulfill(response=bekleyen[0].fetch())
    expect(sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Abel']")).to_be_visible()


def test_dusen_istek_bos_sozluk_degil_yeniden_dene_gosterir(sayfa):
    _kitabi_ac(sayfa)
    yol = "**/api/book/gumus-kule/glossary"
    sayfa.context.route(yol, lambda r: r.abort())
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList")).to_contain_text("Sözlük yüklenemedi")
    sayfa.context.unroute(yol)
    sayfa.locator("#glossYenidenDene").click()
    expect(sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Abel']")).to_be_visible()
    expect(sayfa.locator("#glossYenidenDene")).to_have_count(0)
