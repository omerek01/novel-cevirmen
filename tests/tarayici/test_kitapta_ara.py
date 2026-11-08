"""Kitap içi metin arama: kitap sayfasından bütün bölümlerin metninde ara (2026-11-08)."""
from playwright.sync_api import expect
import pytest
import tohum
from core import cache

SLUG = "gumus-kule"
pytestmark = pytest.mark.parametrize("sayfa", [{"width": 375, "height": 812}], indirect=True)


def test_metinde_ara_sonuca_gider_vurgular_ve_geri_donunce_sonuclar_kalir(sayfa):
    urller = tohum.kitap(bolum_sayisi=3)
    cache.save_chapter(urller[1], {
        "book_slug": SLUG, "book_title": "Gumus Kule", "title": "Chapter 2", "chapter_no": 2,
        # Okuyucu 50 karakterden kısa çeviriyi boş bölüm sayar.
        "translation": "Quentin hasar gören kalkanını sabırla onardı.\n\n"
                       "Sonra QUENTIN, Dorn ile birlikte yüksek sesle güldü.",
        "next_url": urller[2], "prev_url": urller[0], "detected_names": [], "chunk_count": 1,
    })
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterSearch").fill("quentin")
    expect(sayfa.locator("#chapterList")).to_contain_text("Eşleşen bölüm yok")
    sayfa.locator("#metinAraBtn").click()

    sonuc = sayfa.locator("#chapterList .metin-sonuc")
    expect(sonuc).to_have_count(1)
    expect(sonuc.locator(".chapter-no")).to_have_text("2")
    expect(sonuc.locator("mark")).to_have_text("Quentin")
    expect(sonuc.locator(".metin-sonuc-adet")).to_have_text("×2")

    sonuc.click()
    expect(sayfa.locator("#findBar")).to_be_visible()
    expect(sayfa.locator("#findInput")).to_have_value("quentin")
    expect(sayfa.locator("#findCount")).to_have_text("1/2")

    sayfa.go_back()
    expect(sayfa.locator("#chapterSearch")).to_have_value("quentin")
    expect(sayfa.locator("#chapterList .metin-sonuc")).to_have_count(1)
