"""Sözlük satırlarının KÖKEN bilgisi: göç + yazma yolları + uç sözleşmesi.

Neden var: tablo uzun süre 3 sütundu (`book_slug, source, target`) ve bir satır
hakkında "ne zaman, hangi yoldan, hangi bölümde girdi" sorusu CEVAPSIZDI. Somut
bedeli: yanlış bir otomatik karşılık görüldüğünde onu kullanıcının mı modelin mi
yazdığı bilinemiyor, düzeltilir mi korunur mu belirsiz kalıyordu.

Hepsi çevrimdışı: SQLite roundtrip + ağ gerektirmeyen endpoint.
"""
import sqlite3

from fastapi.testclient import TestClient

import server
from core import cache, db, glossary


def _eski_sema_db():
    """Köken sütunlarından ÖNCEKİ sözlük tablosu + bir satır."""
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE glossary (
            book_slug TEXT, source TEXT, target TEXT,
            PRIMARY KEY (book_slug, source)
        )
        """
    )
    conn.execute("INSERT INTO glossary VALUES ('kitap', 'Nephis', 'Nephis')")
    conn.commit()
    conn.close()


# ---------- göç ----------


def test_goc_koken_sutunlarini_ekler_ve_idempotenttir():
    _eski_sema_db()
    glossary._connect().close()  # 1. çağrı: ALTER
    glossary._connect().close()  # 2. çağrı: patlamamalı
    conn = sqlite3.connect(db.db_path())
    cols = {r[1] for r in conn.execute("PRAGMA table_info(glossary)")}
    conn.close()
    assert {"created_at", "origin", "first_chapter"} <= cols


def test_eski_satirda_koken_none():
    """Eski satırlar geçmişe dönük doldurulmaz — künye alanlarındaki kabul edilmiş desen."""
    _eski_sema_db()
    (satir,) = glossary.get_glossary_rows("kitap")
    assert satir["source"] == "Nephis"
    assert (satir["created_at"], satir["origin"], satir["first_chapter"]) == (None, None, None)


def test_eski_satir_ceviri_yolunu_bozmaz():
    """`get_glossary` sözleşmesi DEĞİŞMEDİ: çeviri yolu sade eşleme bekliyor."""
    _eski_sema_db()
    assert glossary.get_glossary("kitap") == {"Nephis": "Nephis"}


# ---------- otomatik yol ----------


def test_merge_terms_kokeni_yazar():
    glossary.merge_terms("kitap", {"Zero Wing": "Sıfır Kanat"}, "auto", 42)
    (satir,) = glossary.get_glossary_rows("kitap")
    assert satir["origin"] == "auto"
    assert satir["first_chapter"] == 42
    assert satir["created_at"] > 0


def test_merge_names_kokeni_tasir():
    glossary.merge_names("kitap", ["Nephis"], "auto", 7)
    (satir,) = glossary.get_glossary_rows("kitap")
    assert (satir["origin"], satir["first_chapter"]) == ("auto", 7)


# ---------- elle yol ----------


def test_set_term_manual_yazar():
    glossary.set_term("kitap", "Aspect", "Görünüş")
    (satir,) = glossary.get_glossary_rows("kitap")
    assert satir["origin"] == "manual"
    assert satir["created_at"] > 0


def test_set_term_giris_anini_ve_bolumu_korur():
    """`INSERT OR REPLACE` satırı silip yeniden yazar — köken taşınmazsa kaybolurdu.

    Otomatik eklenmiş bir kaydı kullanıcı düzeltince satır artık kullanıcınındır
    (`origin` -> manual), ama "ne zaman/hangi bölümde girdi" bilgisi durmalı.
    """
    glossary.merge_terms("kitap", {"Sleeper Center": "Uyuyan Merkezi"}, "auto", 12)
    (once,) = glossary.get_glossary_rows("kitap")
    glossary.set_term("kitap", "Sleeper Center", "Uyuyanlar Merkezi")
    (sonra,) = glossary.get_glossary_rows("kitap")
    assert sonra["target"] == "Uyuyanlar Merkezi"
    assert sonra["origin"] == "manual"          # artık kullanıcının
    assert sonra["created_at"] == once["created_at"]   # giriş anı korunur
    assert sonra["first_chapter"] == 12                # giriş bölümü korunur


def test_set_term_varyanti_kokeni_bozmadan_gunceller():
    """Varyantla gelen düzeltme yeni satır açmaz; köken de sıfırlanmaz."""
    glossary.merge_terms("kitap", {"Ore Empire": "Maden İmparatorluğu"}, "auto", 3)
    glossary.set_term("kitap", "OreEmpire", "Ork İmparatorluğu")
    satirlar = glossary.get_glossary_rows("kitap")
    assert len(satirlar) == 1
    assert satirlar[0]["source"] == "Ore Empire"       # kayıtlı YAZIM korunur
    assert satirlar[0]["first_chapter"] == 3


# ---------- uç sözleşmesi ----------


def test_uc_hem_terms_hem_rows_dondurur():
    """`terms` geriye dönük uyum için duruyor: çevrimdışı kuyruklu okuyucu onu bekliyor."""
    glossary.merge_terms("kitap", {"Zero Wing": "Sıfır Kanat"}, "auto", 5)
    with TestClient(server.app) as client:
        veri = client.get("/api/book/kitap/glossary").json()
    assert veri["terms"] == {"Zero Wing": "Sıfır Kanat"}
    assert veri["rows"][0]["origin"] == "auto"
    assert veri["rows"][0]["first_chapter"] == 5


# ---------- yakın terim uyarısı ----------
# Ham "tek karakter farkı" ölçütü gerçek sözlükte 21 çift buldu ve 14'ü MEŞRUDU.
# Uyaran her şeye uyaran bir kapı görmezden gelinir; gürültü elenmezse özellik ölür.


def test_yakin_terim_yazim_hatasi_ciftini_bulur():
    """Gerçek vaka: aynı varlık kaynak sitede `Orc Empire` ve `Ore Empire` yazılmıştı."""
    glossary.set_term("kitap", "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term("kitap", "Ore Empire", "Ork İmparatorluğu")
    assert glossary.yakin_terimler("kitap") == [("Orc Empire", "Ore Empire")]


def test_yakin_terim_cogul_tekil_ciftini_saymaz():
    """`Evil Beast` / `Evil Beasts` MEŞRU — desen zaten çoğulu yakalıyor."""
    glossary.set_term("kitap", "Evil Beast", "Kötü Canavar")
    glossary.set_term("kitap", "Evil Beasts", "Kötü Canavarlar")
    assert glossary.yakin_terimler("kitap") == []


def test_yakin_terim_rakam_farkini_saymaz():
    """`Tier 2` / `Tier 3` ayrı ve meşru kayıtlar."""
    glossary.set_term("kitap", "Tier 2", "Kademe 2")
    glossary.set_term("kitap", "Tier 3", "Kademe 3")
    assert glossary.yakin_terimler("kitap") == []


def test_yakin_terim_yazim_varyantini_saymaz():
    """Varyant zaten TEK terimdir; `set_term` ikinci satır açtırmaz, buraya düşmemeli."""
    glossary.set_term("kitap", "Ore Empire", "Ork İmparatorluğu")
    glossary.set_term("kitap", "OreEmpire", "Ork İmparatorluğu")
    assert glossary.yakin_terimler("kitap") == []


def test_yakin_terim_uzak_terimleri_eslestirmez():
    glossary.set_term("kitap", "Nephis", "Nephis")
    glossary.set_term("kitap", "Zero Wing", "Sıfır Kanat")
    assert glossary.yakin_terimler("kitap") == []


def test_uc_yakin_terim_uyarisini_dondurur():
    glossary.set_term("kitap", "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term("kitap", "Ore Empire", "Ork İmparatorluğu")
    with TestClient(server.app) as client:
        veri = client.get("/api/book/kitap/glossary").json()
    assert veri["warnings"] == [["Orc Empire", "Ore Empire"]]


# ---------- bakım raporları (çevrimdışı, model çağrısı YOK) ----------


def test_cakisan_ayni_karsiliga_giden_kaynaklari_bulur():
    """İki ayrı şeyin aynı karşılığı alması onları çeviride ayırt edilemez kılar."""
    glossary.set_term("kitap", "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term("kitap", "Ore Empire", "Ork İmparatorluğu")
    (_anahtar, kaynaklar), = glossary.karsilik_cakismalari("kitap")
    assert kaynaklar == ["Orc Empire", "Ore Empire"]


def test_cakisan_ingilizce_korunanlari_saymaz():
    """`X -> X` kayıtlarında karşılık zaten kaynağın kendisi — çakışma anlamsız."""
    glossary.set_term("kitap", "Nephis", "Nephis")
    glossary.set_term("kitap", "Sunny", "Sunny")
    assert glossary.karsilik_cakismalari("kitap") == []


def test_kardes_buyuk_harf_ayrismasini_bulur():
    """Vaka: `Star-Moon Kingdom -> Yıldız-Ay Krallığı` yanında küçük harfli kardeşi."""
    glossary.set_term("kitap", "Star-Moon Kingdom", "Yıldız-Ay Krallığı")
    glossary.set_term("kitap", "Star-Moon City", "yıldız ay şehri")
    (kelime, uyeler), = glossary.kardes_tutarsizliklari("kitap")
    assert kelime in {"star", "moon"}
    assert len(uyeler) == 2


def test_kardes_tutarli_aileyi_bildirmez():
    glossary.set_term("kitap", "Star-Moon Kingdom", "Yıldız-Ay Krallığı")
    glossary.set_term("kitap", "Star-Moon City", "Yıldız-Ay Şehri")
    assert glossary.kardes_tutarsizliklari("kitap") == []


def test_kardes_durak_kelimeyi_gruplamaz():
    """`of`/`the` ortaklığı ad ailesi DEĞİLDİR; gruplarsa her şey kardeş olur."""
    glossary.set_term("kitap", "Sword of Dawn", "Şafak Kılıcı")
    glossary.set_term("kitap", "Crown of Night", "gece tacı")
    assert glossary.kardes_tutarsizliklari("kitap") == []


def test_kaynak_kapsamasi_orani_bildirir():
    """Rapor 'ölü kayıt' derken kapsamayı görmeli — düşükken meşru kayıt silinir."""
    cache.save_chapter(
        "u1", {"book_slug": "k", "book_title": "K", "title": "B1", "chapter_no": 1,
               "translation": "ç", "source": "Nephis walked.", "next_url": None,
               "prev_url": None, "detected_names": [], "chunk_count": 1},
    )
    cache.save_chapter(
        "u2", {"book_slug": "k", "book_title": "K", "title": "B2", "chapter_no": 2,
               "translation": "ç", "source": None, "next_url": None,
               "prev_url": None, "detected_names": [], "chunk_count": 1},
    )
    toplam, kapsanan, metin = cache.kaynak_kapsamasi("k")
    assert (toplam, kapsanan) == (2, 1)
    assert "Nephis" in metin


# ---------- dışa/içe aktarma + etkilenen bölümler ----------


def _bolum(url, no, kaynak):
    cache.save_chapter(
        url, {"book_slug": "k", "book_title": "K", "title": f"B{no}", "chapter_no": no,
              "translation": "ç", "source": kaynak, "next_url": None, "prev_url": None,
              "detected_names": [], "chunk_count": 1},
    )


def test_export_sozlugu_json_olarak_verir():
    glossary.set_term("k", "Zero Wing", "Sıfır Kanat")
    with TestClient(server.app) as client:
        r = client.get("/api/book/k/glossary/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.json()["terms"] == {"Zero Wing": "Sıfır Kanat"}


def test_import_varsayilan_mevcut_kaydi_ezmez():
    """Sözlük kullanıcınındır — varsayılan strateji yalnız BOŞLUĞU doldurur."""
    glossary.set_term("k", "Zero Wing", "Benim Karşılığım")
    with TestClient(server.app) as client:
        veri = client.post(
            "/api/book/k/glossary/import",
            json={"terms": {"Zero Wing": "Sıfır Kanat", "Nephis": "Nephis"}},
        ).json()
    assert veri["terms"]["Zero Wing"] == "Benim Karşılığım"  # korundu
    assert veri["terms"]["Nephis"] == "Nephis"               # eksik olan eklendi
    assert (veri["gelen"], veri["eklenen"]) == (2, 1)


def test_import_dosya_stratejisi_bilerek_ezer():
    """Masaüstünde toplu düzeltip geri yüklemenin yolu budur."""
    glossary.set_term("k", "Zero Wing", "Eski Karşılık")
    with TestClient(server.app) as client:
        veri = client.post(
            "/api/book/k/glossary/import",
            json={"terms": {"Zero Wing": "Sıfır Kanat"}, "strateji": "dosya"},
        ).json()
    assert veri["terms"]["Zero Wing"] == "Sıfır Kanat"


def test_import_bos_kaynagi_atar():
    with TestClient(server.app) as client:
        veri = client.post(
            "/api/book/k/glossary/import", json={"terms": {"  ": "x", "Nephis": "Nephis"}}
        ).json()
    assert veri["gelen"] == 1


def test_impact_terimin_gectigi_bolumleri_sayar():
    _bolum("u1", 1, "The Zero Wing guild advanced.")
    _bolum("u2", 2, "Nothing relevant here.")
    _bolum("u3", 3, "Zero-Wing again.")   # yazım varyantı da sayılmalı
    with TestClient(server.app) as client:
        veri = client.get("/api/book/k/glossary/impact", params={"source": "Zero Wing"}).json()
    assert veri["count"] == 2
    assert [b["chapter_no"] for b in veri["chapters"]] == [1, 3]


def test_impact_kaynak_kapsamasini_bildirir():
    """Kapsama düşükken '0 bölüm' yanıltıcı okunmasın diye oran da döner."""
    _bolum("u1", 1, "Zero Wing.")
    _bolum("u2", 2, None)
    with TestClient(server.app) as client:
        veri = client.get("/api/book/k/glossary/impact", params={"source": "Nephis"}).json()
    assert veri["count"] == 0
    assert veri["kapsama"] == [1, 2]


# ---------- "o bölüm çevrilirken sözlükte ne vardı" ----------
#
# Geriye dönük uyum denetimi (`scripts/uyum_denetle.py`) BUGÜNKÜ sözlüğe göre
# ölçerse yalan söyler: 200. bölümde kaydedilmiş bir terim, 50. bölüm çevrilirken
# prompt'ta YOKTU — model onu ihlal edemezdi. Köken sütunu (`first_chapter`) tam
# olarak bu sorunun cevabı ve zaten yazılıyordu; okuyan yoktu.


def test_bolumdeki_sozluk_sonra_kaydedilen_terimi_dislar():
    glossary.merge_terms("k", {"Erken": "Erkenci"}, "auto", 5)
    glossary.merge_terms("k", {"Sonra": "Sonraki"}, "auto", 90)
    assert glossary.bolumdeki_sozluk("k", 10) == {"Erken": "Erkenci"}


def test_bolumdeki_sozluk_ayni_bolumde_kaydedileni_kapsar():
    """Terim o bölümde algılandıysa çeviri sırasında prompt'ta yoktu ama karşılığı
    modelin KENDİ seçimidir — metinde tutarlı kullanmış olması beklenir."""
    glossary.merge_terms("k", {"Tam": "Tamı"}, "auto", 7)
    assert glossary.bolumdeki_sozluk("k", 7) == {"Tam": "Tamı"}


def test_bolumdeki_sozluk_kokeni_bilinmeyeni_kapsar():
    """Elle eklenen ve köken sütunlarından ÖNCEKİ satırlarda `first_chapter` None.
    Dışlamak, kullanıcının kendi yazdığı kayıtları denetim dışı bırakırdı —
    oysa asıl önemsenen kayıtlar onlar."""
    glossary.merge_terms("k", {"Kokensiz": "Kökensiz"}, "manual", None)
    assert glossary.bolumdeki_sozluk("k", 3) == {"Kokensiz": "Kökensiz"}


def test_bolumdeki_sozluk_bolum_no_yoksa_tamamini_verir():
    glossary.merge_terms("k", {"Erken": "Erkenci"}, "auto", 5)
    glossary.merge_terms("k", {"Sonra": "Sonraki"}, "auto", 90)
    assert glossary.bolumdeki_sozluk("k", None) == {
        "Erken": "Erkenci", "Sonra": "Sonraki",
    }

