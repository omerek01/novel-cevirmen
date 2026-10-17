"""Okuyucuda paragraf önerisi (Ö2/Ö4, kabul/atla) ve künyede sözlük damgası (Ö3).

Öneri ucu model çağırdığı için `page.route` ile taklit edilir; kaydetme GERÇEK uçtur
(sunucu metni değiştirir, okuyucu bölümü tazeler)."""
import json
import sqlite3

from core import db, glossary
from playwright.sync_api import expect
import tohum


def _hazirla(sayfa):
    urller = tohum.kitap(bolum_sayisi=1)
    url = urller[0]
    with sqlite3.connect(db.db_path()) as c:
        slug, tr = c.execute("SELECT book_slug, translation FROM chapters WHERE url=?",
                             (url,)).fetchone()
        c.execute(
            "UPDATE chapters SET ceviri_kalitesi=?, sozluk_damgasi=? WHERE url=?",
            (json.dumps({"durum": "supheli", "supheli": [
                {"paragraf": 0, "tur": "anlam", "aciklama": "deneme şüphesi"}]}),
             json.dumps({"Silver Tower": "Eski Kule"}), url))
    glossary.set_term(slug, "Silver Tower", "Gümüş Kule")
    return url, tr.split("\n\n")


def _oneri_taklidi(sayfa, mevcut, aday):
    def cevap(route):
        govde = json.loads(route.request.post_data)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "sira": govde["sira"], "mevcut": mevcut[govde["sira"]], "aday": aday,
            "model": "deneme", "kalan": [], "mod": govde["mod"]}))
    sayfa.route("**/api/chapter/paragraf/oneri", cevap)


def _bolumu_ac(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody p[data-idx='0']")).to_be_visible()


def test_kunyeden_onarim_onerisi_kabul_edilince_paragraf_degisir(sayfa):
    url, tr = _hazirla(sayfa)
    _oneri_taklidi(sayfa, tr, "Onarılmış deneme paragrafı.")
    _bolumu_ac(sayfa)
    kart = sayfa.locator("#readerBody .kunye").first
    expect(kart.locator("summary")).to_contain_text("1 terim bu çeviriden sonra değişti")
    kart.locator("summary").click()
    expect(kart.locator(".kunye-damga-liste li")).to_have_text(
        "Silver Tower: “Eski Kule” → “Gümüş Kule”")
    kart.get_by_role("button", name="Onarım önerisi al").click()
    panel = kart.locator(".paragraf-oneri-panel")
    expect(panel.locator(".aday p")).to_have_text("Onarılmış deneme paragrafı.")
    expect(panel.locator(".mevcut p")).to_have_text(tr[0])
    panel.get_by_role("button", name="Kabul et").click()
    expect(sayfa.locator("#readerBody p[data-idx='0']")).to_contain_text(
        "Onarılmış deneme paragrafı.")
    with sqlite3.connect(db.db_path()) as c:
        yeni = c.execute("SELECT translation FROM chapters WHERE url=?", (url,)).fetchone()[0]
    assert yeni.split("\n\n")[0] == "Onarılmış deneme paragrafı."
    assert sayfa.evaluate("document.documentElement.scrollWidth") <= 390


def test_kaynak_satirindan_yeniden_ceviri_atlaninca_metin_degismez(sayfa):
    url, tr = _hazirla(sayfa)
    _oneri_taklidi(sayfa, tr, "Bambaşka bir çeviri.")
    _bolumu_ac(sayfa)
    p = sayfa.locator("#readerBody p[data-idx='1']")
    p.dblclick()
    expect(sayfa.locator("#readerBody .source-line").first).to_have_text(tohum.EN[1])
    kaynak = sayfa.locator("#readerBody .paragraf-oneri-kaynak").first
    kaynak.get_by_role("button", name="Bu paragrafı yeniden çevir").click()
    panel = kaynak.locator(".paragraf-oneri-panel")
    expect(panel.locator(".aday p")).to_have_text("Bambaşka bir çeviri.")
    expect(panel.locator(".mevcut")).to_have_count(0)  # paragraf zaten görünüyor
    panel.get_by_role("button", name="Atla").click()
    expect(panel).to_have_count(0)
    expect(p).to_have_text(tr[1])
    p.dblclick()  # ikinci çift dokunuş kaynakla birlikte öneri düğmesini de kapatır
    expect(sayfa.locator("#readerBody .paragraf-oneri-kaynak")).to_have_count(0)
    with sqlite3.connect(db.db_path()) as c:
        assert c.execute("SELECT translation FROM chapters WHERE url=?",
                         (url,)).fetchone()[0].split("\n\n")[1] == tr[1]
