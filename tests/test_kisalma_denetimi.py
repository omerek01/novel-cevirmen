"""KISALMA (özetleme) denetimi + tek turluk onarım.

Arıza (2026-09-28, kullanıcı bildirimi): shadow-slave #787'de model çevirmek
yerine ÖZETLEDİ. Bunu MEVCUT denetimlerin hiçbiri göremiyordu ve sebebi
yapısaldı — `_split_by_markers` yalnız YAPIYI, `sozluk_ihlalleri` yalnız KAYITLI
terimleri, `ingilizce_kalinti` yalnız İngilizce kalıntıyı denetliyor. Üçü de
"metnin yarısı gitti mi" diye SORMUYORDU.

Daha kötüsü arıza KENDİ denetimini kapatıyordu: özetleme hizalamayı öldürüyor
(`aligned = False`) ve `translate_chapter` içindeki iki onarım dalı da o bayrağa
bağlı. Yani en bozuk bölüm, hiç denetlenmeyen bölümdü. Bu yüzden kısalma ölçütü
bilerek HİZALAMADAN BAĞIMSIZ (düz karakter sayısı).
"""
import pytest

from core import translate


# ---------------------------------------------------------------- ölçüt

def test_oran_karakter_uzerinden_olculur():
    assert translate.uzunluk_orani("a" * 97, "b" * 100) == pytest.approx(0.97)


def test_kaynaksiz_bolumde_oran_YOK():
    """Kaynak yoksa oran ölçülemez. 0.0 dönmek "her şey kısa" demek olurdu ve
    kaynaksız her bölüme sahte uyarı bastırırdı."""
    assert translate.uzunluk_orani("bir çeviri", "") is None
    assert translate.uzunluk_orani("bir çeviri", "   ") is None


def test_olculemeyen_oran_KISALMA_SAYILMAZ():
    """None = "ölçülmedi". Eksik bilgiyi arıza saymak, eski önbellek satırlarının
    tamamını ⚠ ile işaretler ve rozeti gürültüye boğardı."""
    assert translate.kisalmis_mi(None) is False


def test_ozetleyen_model_yakalanir():
    """Ölçülen gerçek değer: `gemini-3-flash-preview` 0,436'da kaldı."""
    assert translate.kisalmis_mi(0.436) is True


def test_mesru_ceviri_yakalanmaz():
    """Ölçülen en kötü MEŞRU model mistral-medium 0,914; üretim medyanları
    0,932-0,985. Eşik bu aralığın belirgin ALTINDA durmalı, yoksa her bölüm
    boşuna bir onarım turu (ve ücretli modelde PARA) yakardı."""
    for oran in (0.914, 0.932, 0.966, 0.972, 0.985, 1.05):
        assert translate.kisalmis_mi(oran) is False, oran


def test_esik_olculen_bosluga_oturur():
    """Tel tuzağı: eşik 0,436 (özetleyen) ile 0,914 (en kötü meşru) ARASINDA
    kalmalı. Dışına taşarsa ya arızayı kaçırır ya sahte alarm üretir."""
    assert 0.436 < translate.KISALMA_ORANI < 0.914


# ---------------------------------------------------------------- prompt

def test_prompt_ozetlemeyi_ACIKCA_yasaklar():
    """İşaretçi maddesi paragraf DÜZENİNİ şart koşuyordu ama içeriğin
    KORUNMASINI istemiyordu: model her [[n]] işaretini doğru yerine koyup her
    paragrafı tek cümleye indirdiğinde hiçbir kural çiğnenmiyordu. Bu, 2026-09-05
    İngilizce-kalıntı boşluğunun birebir aynısıdır."""
    p = translate.SYSTEM_INSTRUCTION
    assert "ÖZET DEĞİL" in p
    assert "AYNI UZUNLUKTA" in p


# ---------------------------------------------------------------- onarım

class _SahteParca:
    """`_translate_chunk` yerine geçer; her çağrıda sıradaki çıktıyı döndürür."""

    def __init__(self, *ciktilar):
        self.ciktilar = list(ciktilar)
        self.cagri = 0

    def __call__(self, factory, models, chunk_en, glossary, prev_tail, kosullar):
        self.cagri += 1
        metin = self.ciktilar.pop(0) if self.ciktilar else ""
        return {
            "translation": metin,
            "detected_names": [],
            "detected_terms": {},
            "model": f"sahte-{self.cagri}",
        }


def _kaynak(n=3, uzunluk=400):
    return "\n\n".join(f"P{i} " + "x" * uzunluk for i in range(n))


def _ceviri(kaynak, oran=1.0):
    """Kaynağı [[n]] işaretli bir 'çeviri'ye çevirir; `oran` kadarını tutar."""
    return "\n\n".join(
        f"[[{i + 1}]] " + p[: max(1, int(len(p) * oran))]
        for i, p in enumerate(kaynak.split("\n\n"))
    )


def test_kisalmis_parca_TEK_kez_yeniden_denenir(monkeypatch):
    """Zincir bunu kurtaramaz: düşme yalnız HATADA olur (429/503/404), başarılı
    ama kötü bir yanıtta olmaz. Onarım buradan tetiklenmeli."""
    kaynak = _kaynak()
    sahte = _SahteParca(_ceviri(kaynak, 0.30), _ceviri(kaynak, 0.98))
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])

    sonuc = translate.translate_chapter(kaynak, "anahtar", models=("m",))

    assert sahte.cagri == 2  # bir kez yeniden denendi
    assert sonuc["uzunluk_orani"] > translate.KISALMA_ORANI
    assert not translate.kisalmis_mi(sonuc["uzunluk_orani"])


def test_tam_ceviride_onarim_TETIKLENMEZ(monkeypatch):
    """Sahte alarm PARA demek: ücretli model seçiliyken her bölüm bir fazladan
    istek yakardı."""
    kaynak = _kaynak()
    sahte = _SahteParca(_ceviri(kaynak, 0.97))
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])

    sonuc = translate.translate_chapter(kaynak, "anahtar", models=("m",))

    assert sahte.cagri == 1
    assert not translate.kisalmis_mi(sonuc["uzunluk_orani"])


def test_onarim_DAHA_KOTU_gelirse_ilki_korunur(monkeypatch):
    """İkinci tur da kısa gelebilir (aynı model, aynı dikkat kayması). Onu
    körlemesine kabul etmek DAHA ÇOK içerik kaybettirirdi."""
    kaynak = _kaynak()
    sahte = _SahteParca(_ceviri(kaynak, 0.50), _ceviri(kaynak, 0.10))
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])

    sonuc = translate.translate_chapter(kaynak, "anahtar", models=("m",))

    assert sahte.cagri == 2
    # 0,50'lik ilk tur korundu; 0,10'luk ikinci tur ATILDI.
    assert sonuc["uzunluk_orani"] > 0.4


def test_onarim_TEK_TURDUR_dongu_kurmaz(monkeypatch):
    """Israrla kısa dönen bir modelde döngü kurmak maliyeti — ücretli modelde
    PARAYI — katlar. `_kalintiyi_onar` de aynı gerekçeyle tek turdur. Bölüm
    onarılamazsa bayrakla işaretlenir, sonsuza dek denenmez."""
    kaynak = _kaynak()
    sahte = _SahteParca(*[_ceviri(kaynak, 0.20)] * 6)
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])

    sonuc = translate.translate_chapter(kaynak, "anahtar", models=("m",))

    assert sahte.cagri == 2  # 1 asıl + 1 onarım, DAHA FAZLA DEĞİL
    assert translate.kisalmis_mi(sonuc["uzunluk_orani"])  # bayrak kalır


def test_olcum_HIZALAMA_KAYBINDA_da_yapilir(monkeypatch):
    """Load-bearing: özetleme hizalamayı ÖLDÜRÜR ve öteki iki onarım `if aligned`
    ardında duruyor. Kısalma ölçütü hizalamaya bağlansaydı, tam da gerekli
    olduğu anda susardı."""
    kaynak = _kaynak()
    # İşaretçisiz çıktı -> `_split_by_markers` None döner -> aligned False.
    sahte = _SahteParca("kisa ozet", "kisa ozet")
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])

    sonuc = translate.translate_chapter(kaynak, "anahtar", models=("m",))

    assert sonuc["source"] is None  # hizalama gerçekten kayboldu
    assert sonuc["uzunluk_orani"] is not None  # ölçüm YİNE de yapıldı
    assert translate.kisalmis_mi(sonuc["uzunluk_orani"])


# ---------------------------------------------------------------- künye taşıma

def _payload(**ek):
    temel = {
        "book_slug": "k", "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "çeviri", "next_url": None, "detected_names": [],
        "chunk_count": 1, "prev_url": None, "source": "source",
    }
    temel.update(ek)
    return temel


def test_oran_onbellekte_YASAR():
    """Künye alanı DB'ye yazılıp geri okunmalı. Bu projede `model` alanı bir süre
    yalnız tek noktada yazıldı ve önbellek isabetinde sessizce kayboldu."""
    from core import cache

    cache.save_chapter("http://s/1", _payload(uzunluk_orani=0.42))
    assert cache.get_chapter("http://s/1")["uzunluk_orani"] == pytest.approx(0.42)


def test_kunyesiz_guncelleme_orani_SILMEZ():
    """E-16 sınıfı: künye TAŞIMAYAN bir payload aynı satırı güncellediğinde
    mevcut ölçüm NULL'a düşmemeli (`COALESCE(excluded.x, x)`)."""
    from core import cache

    cache.save_chapter("http://s/2", _payload(uzunluk_orani=0.42))
    cache.save_chapter("http://s/2", _payload())  # oran YOK
    assert cache.get_chapter("http://s/2")["uzunluk_orani"] == pytest.approx(0.42)


def test_karar_ESIKTEN_turetilir_DB_de_saklanmaz(monkeypatch):
    """Ölçüm saklanır, KARAR türetilir. Eşik kalibre edilirse eski satırlar da
    kendiliğinden doğru değerlendirilmeli — kaydedilmiş bir karar o gün sessizce
    yanlışa dönerdi (aynı ayrım `kullanim.py`de token/maliyet olarak var)."""
    from core import cache, pipeline

    cache.save_chapter("http://s/3", _payload(uzunluk_orani=0.60))
    assert pipeline._finalize_cached(cache.get_chapter("http://s/3"), "http://s/3")["kisalmis"]

    # Eşik düşerse AYNI satır artık kısalmış sayılmamalı.
    monkeypatch.setattr(translate, "KISALMA_ORANI", 0.50)
    assert not pipeline._finalize_cached(
        cache.get_chapter("http://s/3"), "http://s/3"
    )["kisalmis"]
