"""Bölüm künyesi: hangi motor çevirdi + o bölümde sözlüğe ne eklendi.

Künye cache'te SAKLANIR; yoksa bölüm ikinci açılışta (önbellek isabeti) künyesini
kaybederdi — o an sözlükte her şey zaten kayıtlı olduğu için `merge_*` boş döner.

Cache testlerinde `engine="claude"` bilinçli: bugün tek motor (gemini) çeviriyor
ama DB'de Claude motoru kaldırılmadan ÖNCE yazılmış satırlar duruyor. Sütun serbest
metindir ve okuyucu o eski kayıtları da gösterebilmeli.
"""
from core import cache, glossary, pipeline


def _kaydet(url, **ek):
    veri = {
        "book_slug": "k", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "ç", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    }
    veri.update(ek)
    cache.save_chapter(url, veri)


# ---------- cache: yazma / okuma ----------

def test_kunye_roundtrip():
    _kaydet("u1", engine="claude",
            added_terms={"Lightshadow City": "Işıkgölge Şehri", "Zero Wing": "Zero Wing"})
    row = cache.get_chapter("u1")
    assert row["engine"] == "claude"
    assert row["added_terms"] == {
        "Lightshadow City": "Işıkgölge Şehri", "Zero Wing": "Zero Wing",
    }


def test_kunyesiz_eski_satir_patlamaz():
    """Sütunlar sonradan eklendi; eski satırlarda NULL. Okuyucu bunu 'rozet çizme'
    olarak yorumlar."""
    _kaydet("u2")
    row = cache.get_chapter("u2")
    assert row["engine"] is None
    assert row["added_terms"] == {}


def test_kunyesiz_yazim_mevcut_kunyeyi_silmez():
    """E-16 sınıfı regresyon: künye TAŞIMAYAN bir payload (örn. görsel içerik yolu)
    aynı satırı güncellediğinde motor bilgisi NULL'a düşmemeli — COALESCE."""
    _kaydet("u3", engine="claude", added_terms={"Zero Wing": "Zero Wing"})
    _kaydet("u3", translation="yeni çeviri")          # künye alanları YOK
    row = cache.get_chapter("u3")
    assert row["engine"] == "claude"
    assert row["added_terms"] == {"Zero Wing": "Zero Wing"}
    assert row["translation"] == "yeni çeviri"        # asıl güncelleme geçmiş olmalı


def test_yeni_kunye_eskisini_ezer():
    """Bölüm yeniden çevrildiğinde künye TAZELENİR (COALESCE yalnız None'ı korur)."""
    _kaydet("u4", engine="gemini", added_terms={"A": "A"})
    _kaydet("u4", engine="claude", added_terms={"B": "B"})
    row = cache.get_chapter("u4")
    assert row["engine"] == "claude" and row["added_terms"] == {"B": "B"}


def test_bos_eklenen_listesi_saklanir():
    """"Hiçbir şey eklenmedi" ile "bilgi yok" AYRI: ilki boş dict, ikincisi None."""
    _kaydet("u5", engine="gemini", added_terms={})
    row = cache.get_chapter("u5")
    assert row["engine"] == "gemini" and row["added_terms"] == {}


# ---------- glossary: ne eklendiğini bildir ----------

def test_merge_terms_eklenenleri_dondurur():
    eklenen = glossary.merge_terms("k", {"Lightshadow City": "Işıkgölge Şehri"})
    assert eklenen == {"Lightshadow City": "Işıkgölge Şehri"}


def test_ikinci_kez_eklenmez_ve_bos_doner():
    glossary.merge_terms("k", {"Zero Wing": "Zero Wing"})
    assert glossary.merge_terms("k", {"Zero Wing": "Zero Wing"}) == {}


def test_kullanici_kaydi_eklendi_diye_raporlanmaz():
    """Kullanıcının elle yazdığı kayıt ne ezilir ne de künyede 'eklendi' görünür."""
    glossary.set_term("k", "Lightshadow City", "Lightshadow City")
    assert glossary.merge_terms("k", {"Lightshadow City": "Işıkgölge Şehri"}) == {}
    assert glossary.get_glossary("k")["Lightshadow City"] == "Lightshadow City"


def test_merge_names_x_to_x_dondurur():
    assert glossary.merge_names("k", ["Zero Wing"]) == {"Zero Wing": "Zero Wing"}


def test_kismi_ekleme_yalniz_yenileri_bildirir():
    glossary.merge_terms("k", {"A": "A"})
    assert glossary.merge_terms("k", {"A": "A", "B": "Bee"}) == {"B": "Bee"}


# ---------- pipeline: künye payload'da ----------

def _pipeline_kur(monkeypatch, sonuc):
    monkeypatch.setattr(pipeline, "translate_chapter",
                        lambda text, api_key=None, glossary=None, **kw: sonuc)
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: {
        "book_slug": "kitap", "book_title": "K", "title": "B1", "chapter_no": 1,
        "text": "t", "next_url": None, "prev_url": None,
    })


def test_payload_kunyeyi_tasir(monkeypatch):
    _pipeline_kur(monkeypatch, {
        "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
        "detected_names": ["Wang Lin"],
        "detected_terms": {
            "Zero Wing": "Sıfır Kanat",
            "Lightshadow City": "Işıkgölge Şehri",
        },
    })
    payload = pipeline.get_or_translate("p1", "anahtar")
    assert payload["engine"] == "gemini"
    assert payload["added_terms"] == {
        "Wang Lin": "Wang Lin",
        "Zero Wing": "Sıfır Kanat",
        "Lightshadow City": "Işıkgölge Şehri",
    }


def test_kunye_onbellek_isabetinde_de_gelir(monkeypatch):
    """Asıl gerekçe: ikinci açılışta sözlük zaten dolu olduğu için merge boş döner;
    künye DB'den okunmazsa kaybolurdu."""
    _pipeline_kur(monkeypatch, {
        "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
        "detected_names": [],
        "detected_terms": {"Cold Wind City": "Soğuk Rüzgar Şehri"},
    })
    pipeline.get_or_translate("p3", "anahtar")          # ilk çeviri
    tekrar = pipeline.get_or_translate("p3", "anahtar")  # önbellekten
    assert tekrar["cached"] is True
    assert tekrar["engine"] == "gemini"
    assert tekrar["added_terms"] == {"Cold Wind City": "Soğuk Rüzgar Şehri"}


# ---------- künyede MODEL adı (motorun içindeki halka) ----------


def test_kaydedilen_model_geri_okunur():
    _kaydet("m-1", engine="gemini", model="gemini-3.7-flash")
    assert cache.get_chapter("m-1")["model"] == "gemini-3.7-flash"


def test_eski_satirda_model_none():
    """Sütun sonradan eklendi: eski bölümlerde NULL, okuyucu model satırını çizmez."""
    _kaydet("m-2", engine="gemini")
    assert cache.get_chapter("m-2")["model"] is None


def test_model_tasimayan_payload_mevcut_modeli_silmez():
    """E-16 sınıfı: künye TAŞIMAYAN bir payload (ör. çevrilecek metni olmayan görsel
    sayfa) aynı satırı güncelliyor. COALESCE olmasaydı model NULL'a düşer, künye
    sessizce kaybolurdu."""
    _kaydet("m-3", engine="gemini", model="gemini-3.5-flash-lite")
    _kaydet("m-3", translation="<img>", content_type="html")  # künyesiz güncelleme
    assert cache.get_chapter("m-3")["model"] == "gemini-3.5-flash-lite"


def test_payload_model_adini_tasir(monkeypatch):
    _pipeline_kur(monkeypatch, {
        "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
        "model": "gemini-3.7-flash",
        "detected_names": [], "detected_terms": {},
    })
    payload = pipeline.get_or_translate("m-4", "anahtar")
    assert payload["model"] == "gemini-3.7-flash"
    assert pipeline.get_or_translate("m-4", "anahtar")["model"] == "gemini-3.7-flash"  # cache


def test_url_ile_eklenen_bolum_de_model_tasir(monkeypatch):
    """Kitaba URL ile bölüm ekleme ("web'den devam"): URL ile bölüm ekleme) künyeye modeli YAZMIYORDU:
    bölüm "GEMINI ile çevrildi" diyor ama hangi halkanın çevirdiği (3.7 mi 3.6 mı)
    görünmüyordu; akışın KENDİ çektiği bölümde (get_or_translate) görünüyordu."""
    _pipeline_kur(monkeypatch, {
        "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
        "model": "gemini-3.7-flash",
        "detected_names": [], "detected_terms": {},
    })
    payload = pipeline.fetch_into_book("https://site/b1", "kitap", "anahtar")
    assert payload["model"] == "gemini-3.7-flash"
    # Cache'e de yazılmalı: bölüm ikinci açılışta künyesini DB'den okur.
    assert cache.get_chapter("https://site/b1")["model"] == "gemini-3.7-flash"
