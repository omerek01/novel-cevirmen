"""Bölüm SIRASI: numara ataması + zincir bütünlüğü.

Ölçülen gerçek vaka (Shadow Slave, 2026-09-02): `fetch_into_book` sayfanın KENDİ
bölüm numarasını yok sayıp kuyruk sayacı (`tail+1`) veriyordu. Kuyruk 140'tayken
eklenen `chapter-137` 141 numarasını, sonra eklenen `chapter-141` 142'yi aldı;
üstelik her ekleme kuyruğun `next`'ini yeni bölüme çevirdiği için zincir de koptu
(140 -> 137 -> 141). Okuyucuda bölüm sırası ve adı kaydı.

Düzeltme İKİ YÖNLÜ olmak zorundaydı ve testler ikisini de tutuyor:
  * WEB kitabında (numaralandırma kaynağın URL'lerini izliyor) sayfanın numarası
    kazanır — kayma buradan çıkmıştı.
  * PASTE kitabını web'e köprülerken tail+1 KORUNUR — oradaki web sayfasının
    numarası başka bir numaralandırma evreninden gelir (paste kitabın 2. bölümü,
    sitenin 1704. bölümü olabilir).
"""
from core import cache, library, pipeline, synthetic


def _sahte_cevir(monkeypatch):
    monkeypatch.setattr(
        pipeline, "translate_chapter",
        lambda t, api_key=None, glossary=None, **kw: {
            "translation": "çeviri", "source": None,
            "detected_names": [], "chunk_count": 1,
        },
    )


def _sahte_sayfa(monkeypatch, *, no, next_url, prev_url, baslik="Web B"):
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **k: {
        "book_slug": "host", "book_title": "Host", "title": baslik,
        "chapter_no": no, "text": "metin",
        "next_url": next_url, "prev_url": prev_url,
    })


def _web_bolumu(url, slug, no, next_url=None, prev_url=None):
    """Kaynağın numaralandırmasını izleyen bir web bölümü önbelleğe yaz."""
    cache.save_chapter(url, {
        "book_slug": slug, "book_title": "K", "title": f"Chapter {no}",
        "chapter_no": no, "translation": "ç", "next_url": next_url,
        "prev_url": prev_url, "detected_names": [], "chunk_count": 1,
    })


# ---------- WEB kitabı: sayfanın kendi numarası kazanır ----------

def test_aradan_eklenen_bolum_KENDI_numarasini_alir(monkeypatch):
    """Shadow Slave vakasının ta kendisi: kuyruk 140'tayken 137 eklenmesi.

    Eskiden 141 numarası verilirdi (tail+1) ve okuyucuda sıra kayardı."""
    _web_bolumu("https://s/novel/k/chapter-136", "k", 136)
    _web_bolumu("https://s/novel/k/chapter-140", "k", 140)
    library.upsert_book("k", "K", "https://s/novel/k/chapter-140", "Chapter 140", 140)
    _sahte_sayfa(monkeypatch, no=137, next_url="https://s/novel/k/chapter-138",
                 prev_url="https://s/novel/k/chapter-136")
    _sahte_cevir(monkeypatch)

    out = pipeline.fetch_into_book("https://s/novel/k/chapter-137", "k", "anahtar")
    assert out["chapter_no"] == 137  # tail+1 (=141) DEĞİL


def test_aradan_ekleme_kuyrugun_zincirini_KOPARMAZ(monkeypatch):
    """Kuyruğun `next`'i yeni bölüme çevrilirse okuma 140'tan 137'ye geri atardı."""
    _web_bolumu("https://s/novel/k/chapter-136", "k", 136)
    _web_bolumu("https://s/novel/k/chapter-140", "k", 140,
                next_url="https://s/novel/k/chapter-141")
    library.upsert_book("k", "K", "https://s/novel/k/chapter-140", "Chapter 140", 140)
    _sahte_sayfa(monkeypatch, no=137, next_url="https://s/novel/k/chapter-138",
                 prev_url="https://s/novel/k/chapter-136")
    _sahte_cevir(monkeypatch)

    pipeline.fetch_into_book("https://s/novel/k/chapter-137", "k", "anahtar")

    kuyruk = cache.get_chapter("https://s/novel/k/chapter-140")
    assert kuyruk["next_url"] == "https://s/novel/k/chapter-141"  # DOKUNULMADI
    yeni = cache.get_chapter("https://s/novel/k/chapter-137")
    # Araya eklenen bölümün prev'i SAYFANIN kendi prev'idir, kuyruk değil.
    assert yeni["prev_url"] == "https://s/novel/k/chapter-136"


def test_kuyruga_ekleme_zinciri_kurar(monkeypatch):
    """Gerçekten SONA eklerken eski davranış sürer: kuyruk yeni bölüme bağlanır."""
    _web_bolumu("https://s/novel/k/chapter-140", "k", 140)
    library.upsert_book("k", "K", "https://s/novel/k/chapter-140", "Chapter 140", 140)
    _sahte_sayfa(monkeypatch, no=141, next_url="https://s/novel/k/chapter-142",
                 prev_url="https://s/novel/k/chapter-140")
    _sahte_cevir(monkeypatch)

    out = pipeline.fetch_into_book("https://s/novel/k/chapter-141", "k", "anahtar")
    assert out["chapter_no"] == 141
    kuyruk = cache.get_chapter("https://s/novel/k/chapter-140")
    assert kuyruk["next_url"] == "https://s/novel/k/chapter-141"


# ---------- PASTE köprüsü: tail+1 KORUNUR ----------

def test_paste_koprusunde_sayfa_numarasi_KULLANILMAZ(monkeypatch):
    """Paste kitabında web sayfasının numarası BAŞKA bir evrenden gelir.

    Kitabın kuyruğu `paste://…` — URL'de bölüm numarası yok, yani kitap kaynağın
    numaralandırmasını izlemiyor. Sayfanın 1704'ünü almak, 2 bölümlük bir kitabın
    ikinci bölümünü 1704 yapardı."""
    synthetic.append_chapter("paste-k", "K", "B1", "one")
    library.upsert_book("paste-k", "K", "paste://paste-k/1", "B1", 1)
    _sahte_sayfa(monkeypatch, no=1704, next_url="https://s/3", prev_url="https://s/1")
    _sahte_cevir(monkeypatch)

    out = pipeline.fetch_into_book("https://s/2", "paste-k", "anahtar")
    assert out["chapter_no"] == 2  # kuyruk + 1
    assert cache.get_chapter("https://s/2")["prev_url"] == "paste://paste-k/1"


def test_acik_numara_her_seyi_ezer(monkeypatch):
    """Kullanıcının verdiği numara en üstün kaynak (uçtaki `chapter_no` alanı)."""
    _web_bolumu("https://s/novel/k/chapter-140", "k", 140)
    library.upsert_book("k", "K", "https://s/novel/k/chapter-140", "Chapter 140", 140)
    _sahte_sayfa(monkeypatch, no=137, next_url=None, prev_url=None)
    _sahte_cevir(monkeypatch)

    out = pipeline.fetch_into_book("https://s/novel/k/chapter-137", "k", "anahtar", 55)
    assert out["chapter_no"] == 55


# ---------- bakım aracı: numara düzeltmesi İKİ kaynak ister ----------

def test_numara_duzeltmesi_url_ve_baslik_UYUSUNCA_yapilir():
    """Tek kaynağa dayanıp numara değiştirmek doğru satırı bozabilirdi.

    Gerçek yanlış-pozitifler: manga sayfaları tek `chapter-0` URL'si altında
    duruyor, "Chapter 0" adlı ön sözler var. İkisi de tek kaynağa bakan bir kuralla
    "düzeltilirdi"."""
    from bolum_sirasi_denetle import _numara_duzeltmeleri

    bolumler = [
        # URL ve başlık AYNI numarayı söylüyor, kayıt farklı → düzeltilir
        {"url": "https://s/k/chapter-137", "title": "Chapter 137: X", "no": 141},
        # URL ve başlık ÇELİŞİYOR → dokunulmaz (hangisi doğru bilinmiyor)
        {"url": "https://s/k/chapter-1", "title": "Chapter 0", "no": 1},
        # Başlıkta numara yok → dokunulmaz (manga sayfası)
        {"url": "https://s/manga-chapter-0/36", "title": "Sayfa 36", "no": 36},
        # Zaten tutarlı → dokunulmaz
        {"url": "https://s/k/chapter-138", "title": "Chapter 138: Y", "no": 138},
    ]
    assert _numara_duzeltmeleri(bolumler) == [(bolumler[0], 137)]


def test_zincir_duzeltmesi_ONBELLEK_DISINA_dokunmaz():
    """Zincirin uçları önbellek dışını gösterir ve bizim kararımız değildir:
    ilk bölümün prev'i sitenin dizin sayfası, son bölümün next'i henüz
    indirilmemiş bölüm. Ayrıca önbellek BOŞLUKLU olabilir (gerçek veri: 1.
    bölümden sonra 1704) — orada "sıradaki önbellekli bölüm" gerçek komşu
    değildir."""
    from bolum_sirasi_denetle import _zincir_duzeltmeleri

    bolumler = [
        {"url": "u1", "no": 1, "prev": "https://s/novel/k", "next": "u2"},
        {"url": "u2", "no": 2, "prev": "u1", "next": "https://s/k/chapter-3"},
    ]
    # Hiçbiri bozuk değil: u1'in prev'i dizin (önbellekte yok), u2'nin next'i
    # indirilmemiş bölüm (önbellekte yok).
    assert _zincir_duzeltmeleri(bolumler) == []


def test_zincir_duzeltmesi_KITAP_ICI_yanlis_bagi_onarir():
    """Onarılan bozukluğun imzası dar: aynı kitap içindeki bağlantı yanlış satırı
    gösteriyor (140 -> 137 gibi)."""
    from bolum_sirasi_denetle import _zincir_duzeltmeleri

    bolumler = [
        {"url": "u136", "no": 136, "prev": None, "next": "u137"},
        {"url": "u137", "no": 137, "prev": "u140", "next": "u141"},
        {"url": "u140", "no": 140, "prev": "u139", "next": "u137"},
        {"url": "u141", "no": 141, "prev": "u137", "next": "u142"},
    ]
    duzeltmeler = {b["url"]: (p, n) for b, p, n in _zincir_duzeltmeleri(bolumler)}
    assert duzeltmeler["u137"] == ("u136", "u140")  # sıradaki önbellekli bölüm
    assert duzeltmeler["u140"] == ("u139", "u141")
    assert duzeltmeler["u141"] == ("u140", "u142")  # next önbellek dışı → korunur
    assert "u136" not in duzeltmeler  # prev None, next zaten doğru


# ---------- çevrimdışı indirme: SAHNELENMİŞ bölüm ELENİR ----------

def test_list_chapters_ceviri_hazir_mi_bayragi_verir():
    """`translated` bayrağı PARA güvenliğidir, süs değil.

    İçe aktarılan PDF/EPUB/manga sayfaları çeviriden ÖNCE `chapters` tablosuna
    yazılır (`translation` NULL) ve okundukça çevrilir. Bir bölümü GET'lemek
    çevirisi yoksa ÇEVİRİ TETİKLER — ücretli model seçiliyken para harcar.
    Otomatik çevrimdışı tarama tüm kitapları geziyor; bayrak olmasa içe aktarılan
    bir kitabı sessizce baştan sona çevirtirdi.
    """
    cache.save_chapter("u-hazir", {
        "book_slug": "k", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "çeviri", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    cache.save_chapter("u-sahne", {
        "book_slug": "k", "book_title": "K", "title": "B2", "chapter_no": 2,
        "translation": None, "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    bayrak = {c["url"]: c["translated"] for c in cache.list_chapters("k")}
    assert bayrak == {"u-hazir": True, "u-sahne": False}


def test_bos_ceviri_de_hazir_sayilmaz():
    """NULL değil ama BOŞ çeviri de indirilebilir sayılmamalı — GET'i yine
    çeviriye düşerdi."""
    cache.save_chapter("u-bos", {
        "book_slug": "k2", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "   ", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    assert cache.list_chapters("k2")[0]["translated"] is False


def test_chapters_ucu_bayragi_tasir():
    """Okuyucu bayrağı UÇTAN alıyor; payload'dan düşerse süzgeç sessizce açılır."""
    from fastapi.testclient import TestClient
    import server

    cache.save_chapter("u-uc", {
        "book_slug": "k3", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "ç", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    data = TestClient(server.app).get("/api/book/k3/chapters").json()
    assert data["chapters"][0]["translated"] is True
