"""Kitap sayfası: işlem hiyerarşisi ve çevrimdışı durum kartı (belge 2026-09-16)."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _kitaba_gir(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#bookView")).to_be_visible()


def test_sik_islemler_gorunur_seyrekler_diger_altinda(sayfa):
    tohum.kitap()
    _kitaba_gir(sayfa)
    for dugme in ("#openGlossaryBtn", "#offlineBtn", "#bulkBtn"):
        expect(sayfa.locator(dugme)).to_be_visible()
    for dugme in ("#mergeBtn", "#deleteBookBtn", "#epubBtn"):
        expect(sayfa.locator(dugme)).to_be_hidden()
    sayfa.locator("#bookMore > summary").click()
    expect(sayfa.locator("#deleteBookBtn")).to_be_visible()


def test_cevrimdisi_kart_telefondaki_bolumleri_sayar(sayfa):
    urller = tohum.kitap(bolum_sayisi=2)
    _kitaba_gir(sayfa)
    kart = sayfa.locator("#offlineCardOzet")
    expect(kart).to_contain_text("Telefonda 0/2 çevrilmiş bölüm")
    # Bir bölümü SW önbelleğine elle koy (testlerde SW kapalı; Cache API açık).
    sayfa.evaluate(
        """async (url) => {
          const c = await caches.open('novellink-data');
          const anahtar = new URL('/api/chapter', location.origin);
          anahtar.searchParams.set('url', url);
          await c.put(anahtar.toString(), new Response('{}', {
            headers: { 'content-length': '3072', 'date': new Date().toUTCString() },
          }));
        }""",
        urller[0],
    )
    sayfa.locator("#bookBackBtn").click()
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(kart).to_contain_text("Telefonda 1/2 çevrilmiş bölüm")
    expect(kart).to_contain_text("3 KB")
    expect(kart).to_contain_text("son indirme")
