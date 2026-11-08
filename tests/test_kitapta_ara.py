"""Kitap içi metin arama: bütün çevrilmiş bölümler, Türkçe büyük/küçük harf kuralı."""
from core import cache


def _bolum(no, metin, slug="k", content_type=None):
    veri = {
        "book_slug": slug, "book_title": "K", "title": f"Chapter {no}",
        "chapter_no": no, "translation": metin, "detected_names": [], "chunk_count": 1,
    }
    if content_type:
        veri["content_type"] = content_type
    cache.save_chapter(f"https://x/{slug}/{no}", veri)


def test_butun_bolumlerde_turkce_kurallarla_bulur_sirali_ve_parcali():
    _bolum(2, "Quentin kalkanını onardı. IŞIK söndü. Işık yine yandı.")
    _bolum(1, "Sunny gölgesine baktı.")
    _bolum(3, "Hiçbir ışık yoktu.")
    _bolum(4, "Başka kitap değil.", slug="baska")
    s = cache.kitapta_ara("k", "ışık")["sonuclar"]
    assert [r["chapter_no"] for r in s] == [2, 3]
    assert s[0]["adet"] == 2  # "IŞIK" (I→ı) ve "Işık"
    assert s[0]["eslesme"] == "IŞIK" and s[0]["once"].endswith("onardı. ")
    assert s[0]["sonra"].startswith(" söndü.")
    # Büyük İ de i'ye iner; büyük harfli İngilizce ad (I→ı) da bulunur.
    _bolum(5, "QUENTIN geldi.")
    assert [r["chapter_no"] for r in cache.kitapta_ara("k", "quentin")["sonuclar"]] == [2, 5]
    assert [r["chapter_no"] for r in cache.kitapta_ara("k", "hİÇBİR")["sonuclar"]] == [3]


def test_gorsel_icerik_ve_bos_sorgu_atlanir_sinir_kesildi_der():
    _bolum(1, "<p>ejderha</p>", content_type="html")
    _bolum(2, "ejderha")
    _bolum(3, "ejderha")
    assert cache.kitapta_ara("k", "  ") == {"sonuclar": [], "kesildi": False}
    r = cache.kitapta_ara("k", "ejderha", sinir=1)
    assert [x["chapter_no"] for x in r["sonuclar"]] == [2] and r["kesildi"] is True
