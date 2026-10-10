"""Kalite şüphesi telefonda görünür; kaynak alıntısı HTML olarak çalışmaz."""
import json
import sqlite3

from core import db
from playwright.sync_api import expect
import tohum


def test_dusuk_guvenli_bulgu_okuyucuda_gorunur(sayfa):
    urller = tohum.kitap(bolum_sayisi=1)
    rapor = {"durum": "supheli", "supheli": [{"paragraf": 0, "tur": "dilbilgisi",
              "aciklama": "<script>hata</script> Cümle kuruluşu şüpheli.", "guven": .88}]}
    with sqlite3.connect(db.db_path()) as c:
        c.execute("UPDATE chapters SET ceviri_kalitesi=? WHERE url=?", (json.dumps(rapor), urller[0]))
    sayfa.set_viewport_size({"width": 375, "height": 812})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    kart = sayfa.locator("#readerBody .kunye").first
    expect(kart.locator("summary")).to_contain_text("1 çeviri şüphesi")
    kart.locator("summary").click()
    expect(kart).to_contain_text("Paragraf 1")
    expect(kart).to_contain_text("Cümle kuruluşu şüpheli")
    expect(kart.locator("script")).to_have_count(0)
