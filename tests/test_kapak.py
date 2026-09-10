"""Kitap kapağı: bölüm sayfasından çıkarma + kütüphanede saklama.

Kapak YALNIZ kütüphane ızgarasında kullanılır (kullanıcı kararı 2026-09-10);
roman detayında büyük kart, puan/yazar/tür/özet alanları BİLEREK yok — bu
projede o alanların kaynağı hiç olmadı ve boş kutu göstermek yanlış vaat olurdu.

ÖLÇÜM (2026-09-10, freewebnovel/shadow-slave): kapak URL'si BÖLÜM sayfasının
`og:image`'ında zaten duruyor ve KİTAP sayfasındakiyle birebir aynı. Yani kapak
için ikinci bir sayfa çekmeye — Cloudflare'e bir kez daha inmeye — gerek yok;
mevcut çekimden bedavaya gelir. Bu yüzden çıkarma `_parse` içindedir.
"""
import pytest

from core import fetch, library

SITE = {"content": "#article", "title": [".t"], "next": [], "prev": [],
        "slug_mode": "after_novel"}


def _html(head: str = "", govde: str = "<p>Metin.</p>") -> str:
    return f"<html><head>{head}</head><body><div id='article'>{govde}</div></body></html>"


def test_kapak_og_image_den_okunur():
    h = '<meta property="og:image" content="https://site.test/files/1991s.jpg">'
    d = fetch._parse(_html(h), "https://site.test/novel/x/chapter-1", SITE)
    assert d["cover"] == "https://site.test/files/1991s.jpg"


def test_og_image_yoksa_twitter_image_e_dusulur():
    """freewebnovel ikisini de veriyor ama her site vermiyor; ikinci ölçüt ucuz."""
    h = '<meta name="twitter:image" content="https://site.test/kapak.jpg">'
    d = fetch._parse(_html(h), "https://site.test/novel/x/chapter-1", SITE)
    assert d["cover"] == "https://site.test/kapak.jpg"


def test_goreli_kapak_adresi_MUTLAKA_cevrilir():
    """Göreli adres olduğu gibi saklanırsa okuyucu onu KENDİ kökünde arar ve
    kapak sessizce kırık çıkar."""
    h = '<meta property="og:image" content="/files/article/1991s.jpg">'
    d = fetch._parse(_html(h), "https://site.test/novel/x/chapter-1", SITE)
    assert d["cover"] == "https://site.test/files/article/1991s.jpg"


def test_kapak_yoksa_None():
    """Kapağı olmayan site/bölüm akışı BOZMAMALI — kapak süslemedir, içerik değil."""
    d = fetch._parse(_html(), "https://site.test/novel/x/chapter-1", SITE)
    assert d["cover"] is None


def test_kutuphane_kapagi_saklar_ve_dondurur():
    library.upsert_book("kitap", "Kitap", "https://s.test/c1", "Bölüm 1", 1)
    library.set_cover("kitap", "https://s.test/kapak.jpg")
    kitap = next(b for b in library.list_books() if b["slug"] == "kitap")
    assert kitap["cover"] == "https://s.test/kapak.jpg"


def test_kapak_yazimi_MEVCUDU_EZMEZ():
    """Kapak bir kez oturunca her bölümde yeniden yazılmamalı: site kapağı
    değiştirse bile kullanıcının gördüğü görsel bölüm bölüm zıplamamalı."""
    library.upsert_book("kitap", "Kitap", "https://s.test/c1", "Bölüm 1", 1)
    library.set_cover("kitap", "https://s.test/ilk.jpg")
    library.set_cover("kitap", "https://s.test/ikinci.jpg")
    kitap = next(b for b in library.list_books() if b["slug"] == "kitap")
    assert kitap["cover"] == "https://s.test/ilk.jpg"


def _fonksiyon_govdesi(kaynak: str, ad: str) -> str:
    """`def ad(` satirindan bir sonraki modul duzeyi `def`e kadar."""
    bas = kaynak.index(f"def {ad}(")
    sonraki = kaynak.find("\ndef ", bas + 1)
    return kaynak[bas: sonraki if sonraki > 0 else len(kaynak)]


def test_kapagi_yazan_IKI_YOL_da_guncel():
    """Kapağı web'den alan İKİ yol var; biri unutulursa o yoldan eklenen kitap
    sessizce kapaksız kalır.

    Bu projede aynı sınıf hata `model` künyesinde yaşandı: alan bir süre yalnız
    tek yolda yazıldı, URL ile eklenen bölüm "GEMINI ile çevrildi" deyip hangi
    halkanın çevirdiğini söylemiyordu. Statik tel tuzağı ayrışmayı erken yakalar.
    """
    from pathlib import Path
    kaynak = Path(__file__).resolve().parent.parent.joinpath(
        "app", "core", "pipeline.py").read_text(encoding="utf-8")
    for fn in ("_do_fetch_translate_save", "fetch_into_book"):
        assert "set_cover" in _fonksiyon_govdesi(kaynak, fn), (
            f"{fn} kapağı kaydetmiyor — o yoldan gelen kitap kapaksız kalır"
        )
