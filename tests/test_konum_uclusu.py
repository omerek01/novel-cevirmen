"""Okuma konumu (url, ad, numara) ÜÇLÜ olarak taşınır — ikisi ayrışamaz.

Gerçek arıza (2026-09-12, telefonda görüldü): kullanıcı 391. bölümdeyken ana
sayfadaki "DEVAM ET" fişi ve raf sırtı "BÖL. 390 · Chapter 390: ..." diyordu;
okuyucuya girip çıkınca düzeliyordu. Sunucudaki canlı satır kanıtı:

    current_url  : .../chapter-392
    chapter_no   : 391
    current_title: Chapter 391: Dreamscape

Yani satır KENDİ İÇİNDE tam bir bölüm tutarsızdı. Sebep `set_position`'ın yalnız
`current_url` + `current_ratio` + `updated_at` yazması, `chapter_no`/`current_title`'ı
olduğu yerde bırakmasıydı. İki katmanlı zarar:

  1. Satır yanlış: ad/numara BAŞKA bir bölümü anlatıyor.
  2. `updated_at` de tazelendiği için okuyucunun DOĞRU yerel kaydı (`LS_LASTREAD`,
     `resolveResume`'un `local.ts >= serverTs` ölçütü) "bayat" sayılıp tümden
     atılıyor ve ekrana bayat SUNUCU değeri çiziliyordu.

Adı doğru yazan yol (`upsert_book`) devreye girmiyordu: indirilmiş bölüm Service
Worker önbelleğinden geliyor, `GET /api/chapter` sunucuya HİÇ ulaşmıyor.

Bu dosya üçlünün birlikte taşındığını ve "ad verilmedi" hâlinin bayat ad
bırakmadığını tutar.
"""
from core import library


def _kitap():
    """390. bölümde duran bir kitap."""
    library.upsert_book("s", "K", "u390", "Chapter 390", 390)


def test_yeni_bolume_gecince_ad_ve_numara_da_tasinir():
    _kitap()
    library.set_position("s", "u391", 0.1, current_title="Chapter 391", chapter_no=391)
    book = library.get_book("s")
    assert book["current_url"] == "u391"
    assert book["chapter_no"] == 391
    assert book["current_title"] == "Chapter 391"


def test_ayni_bolumde_kaydirinca_ad_korunur():
    """Bölüm İÇİ kaydırma en sık çağrı — adı silmesi kabul edilemez."""
    _kitap()
    library.set_position("s", "u390", 0.5)
    book = library.get_book("s")
    assert book["chapter_no"] == 390
    assert book["current_title"] == "Chapter 390"
    assert abs(book["current_ratio"] - 0.5) < 1e-9


def test_ad_verilmeden_bolum_degisirse_bayat_ad_temizlenir():
    """Eski istemci (önbellekteki app.js) üçlüyü göndermez.

    O durumda eski adı KORUMAK, adın artık BAŞKA bir bölümü anlatması demek ve
    okuyucu güvenle YANLIŞ bir numara çizer — düzeltmeye çalıştığımız arızanın ta
    kendisi. NULL'da fiş "SON BÖLÜM"e, sırt "OKU"ya düşer: eksik bilgi, yanlış
    bilgiden iyidir. İstemcinin yerel kaydı varsa zaten o doldurur.
    """
    _kitap()
    library.set_position("s", "u391", 0.1)
    book = library.get_book("s")
    assert book["current_url"] == "u391"
    assert book["chapter_no"] is None
    assert book["current_title"] is None


def test_bilinmeyen_kitap_noop():
    library.set_position("yok", "u1", 0.5, current_title="B", chapter_no=1)  # patlamamalı


def test_uc_ucu_endpointten_yazilir():
    """`POST /api/book/{slug}/position` üçlüyü kabul eder."""
    from fastapi.testclient import TestClient
    import server

    _kitap()
    c = TestClient(server.app)
    r = c.post(
        "/api/book/s/position",
        json={"url": "u391", "ratio": 0.2, "title": "Chapter 391", "chapter_no": 391},
    )
    assert r.status_code == 200
    book = library.get_book("s")
    assert book["chapter_no"] == 391
    assert book["current_title"] == "Chapter 391"


def test_endpoint_eski_istemciyi_reddetmez():
    """Ad/numara taşımayan eski gövde 422 vermemeli — alanlar OPSİYONEL."""
    from fastapi.testclient import TestClient
    import server

    _kitap()
    c = TestClient(server.app)
    r = c.post("/api/book/s/position", json={"url": "u391", "ratio": 0.2})
    assert r.status_code == 200
    assert library.get_book("s")["current_url"] == "u391"
