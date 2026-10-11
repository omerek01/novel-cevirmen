"""Bölümde bulunan otomatik kayıt künyede durumuyla görünür (shadow-slave 965, Carin)."""
import sqlite3

from core import db, glossary
from playwright.sync_api import expect
import tohum


def test_dogrulanan_ve_bekleyen_yeni_kayit_kunyede_gorunur(sayfa):
    urller = tohum.kitap(bolum_sayisi=1)
    with sqlite3.connect(db.db_path()) as c:
        slug, no = c.execute("SELECT book_slug, chapter_no FROM chapters WHERE url=?",
                             (urller[0],)).fetchone()
    glossary.merge_names(slug, ["Carin"], "auto", no)
    glossary.merge_terms(slug, {"Erebus Field": "Erebus Sahası"}, "auto", no)
    with sqlite3.connect(db.db_path()) as c:  # doğrulamadan geçti → kural
        c.execute("UPDATE glossary SET inceleme=NULL, durum=NULL WHERE book_slug=? AND source=?",
                  (slug, "Carin"))
    sayfa.set_viewport_size({"width": 375, "height": 812})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    kart = sayfa.locator("#readerBody .kunye").first
    expect(kart.locator("summary")).to_contain_text("2 yeni kayıt bulundu (1 doğrulandı, 1 bekliyor)")
    kart.locator("summary").click()
    carin = kart.locator(".kunye-yeni-liste li", has_text="Carin")
    expect(carin.locator(".kunye-yeni-durum")).to_have_text("doğrulandı")
    erebus = kart.locator(".kunye-yeni-liste li", has_text="Erebus Field")
    expect(erebus.locator(".kunye-yeni-durum")).to_have_text("bekliyor")
    expect(kart.get_by_role("button", name="Bekleyenleri incele →")).to_be_visible()
    genislik = sayfa.evaluate("document.documentElement.scrollWidth")
    assert genislik <= 375, "künye dar ekranda yatay taşma yapıyor"
