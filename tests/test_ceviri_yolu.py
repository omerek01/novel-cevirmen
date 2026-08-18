"""Çeviri yolu: prompt bütünlüğü + anahtar kapısı + künye alanı.

Ağa çıkmaz — `_generate_with_fallback` sahtelenir, prompt yakalanır.

Bu dosya `test_translate_engine.py`'nin yerini aldı: motor SEÇİMİ diye bir şey
kalmadı (Claude motoru kaldırıldı, tek yol Gemini), ama o dosyanın koruduğu iki
iddia hâlâ geçerli — prompt'un ne taşıdığı ve anahtarsız çevirinin reddedilmesi.
"""
import pytest

from core import pipeline, translate


class _GeminiYanit:
    text = '{"translation": "[[1]] gemini çevirisi", "detected_names": []}'


def _gemini_kur(monkeypatch, promptlar=None):
    def sahte(client, models, user, system=None, max_tokens=None):
        if promptlar is not None:
            promptlar.append(user)
        return _GeminiYanit(), models[0]  # (yanıt, fiilen çeviren model)

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())


# ---------- prompt bütünlüğü ----------

def test_prompt_sozluk_uslup_ve_baglami_tasir(monkeypatch):
    """Dördü de TEK prompt'ta buluşur; biri düşerse çevirinin karakteri değişir."""
    promptlar = []
    _gemini_kur(monkeypatch, promptlar)

    translate.translate_chapter(
        "Blackwater attacked.", api_key="k",
        glossary={"Blackwater": "Blackwater"},
        prev_context="Önceki bölümün sonu.",
        style_note="Ağır üslup.",
    )

    p = promptlar[0]
    assert "Blackwater" in p
    assert "Ağır üslup." in p
    assert "Önceki bölümün sonu." in p


def test_son_hatirlatma_sozlugun_ARDINDAN_gelir(monkeypatch):
    """Sözlük prompt'ta İKİ kez geçer ve sıra load-bearing: kısa hatırlatma
    çevrilecek METNİN ardında durur. Ölçülen sorun — 1500 kelimelik bölümde model
    baştaki sözlüğü unutup korunacak 26 adın 23'ünü Türkçeleştiriyordu; hatırlatma
    sona eklenince ihlal 0'a indi. Hatırlatmayı metnin ÖNÜNE çekme, etki yakınlıktan
    geliyor."""
    promptlar = []
    _gemini_kur(monkeypatch, promptlar)

    translate.translate_chapter(
        "Blackwater attacked.", api_key="k", glossary={"Blackwater": "Blackwater"},
    )

    p = promptlar[0]
    assert "SON HATIRLATMA" in p
    assert p.index("SON HATIRLATMA") > p.index("Blackwater attacked.")


# ---------- künye ----------

def test_donus_kunyesi_gemini_der(monkeypatch):
    _gemini_kur(monkeypatch)
    sonuc = translate.translate_chapter("Bir paragraf.", api_key="k")
    assert sonuc["engine"] == "gemini"
    assert "gemini çevirisi" in sonuc["translation"]


# ---------- anahtar kapısı ----------

def test_anahtarsiz_ceviri_reddedilir(monkeypatch):
    """Tek motor Gemini olduğundan anahtar artık koşulsuz zorunlu: pipeline fetch'e
    inmeden erken hata verir (boşuna Cloudflare turu atılmasın)."""
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: (_ for _ in ()).throw(
        AssertionError("anahtarsız çağrı fetch'e indi")
    ))
    with pytest.raises(translate.TranslateError):
        pipeline.get_or_translate("u-anahtarsiz", None, background=False)


# ---------- model zinciri: TEK ve kalite öncelikli, HER yolda aynı ----------

def _zincir_yakala(monkeypatch):
    """`_generate_with_fallback`'e giden model zincirini toplar; ağa çıkmaz."""
    zincirler = []

    def sahte(client, models, user, system=None, max_tokens=None):
        zincirler.append(models)
        return _GeminiYanit(), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: {
        "book_slug": "kitap", "book_title": "K", "title": "B1", "chapter_no": 1,
        "text": "Bir paragraf.", "next_url": None, "prev_url": None,
    })
    return zincirler


def test_zincir_kaliteden_ucuza_iner():
    """Kullanıcı kararı: en iyi modelden başla, kota/servis tökezledikçe bir alta in.
    Son halka flash-lite — en dayanıklısı, zincir tükenmesin diye orada."""
    assert translate.DEFAULT_MODELS == (
        "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
    )


def test_okuma_yolu_kaliteli_zincirle_acar(monkeypatch):
    zincirler = _zincir_yakala(monkeypatch)
    pipeline.get_or_translate("m-okuma", "anahtar")
    assert zincirler == [translate.DEFAULT_MODELS]


def test_yeniden_cevir_ayni_zinciri_kullanir(monkeypatch):
    """Yola göre AYRI zincir denendi ve kaldırıldı: `refresh` artık yalnız önbelleği
    yok sayar, model sırasını DEĞİŞTİRMEZ."""
    zincirler = _zincir_yakala(monkeypatch)
    pipeline.get_or_translate("m-refresh", "anahtar", refresh=True)
    assert zincirler == [translate.DEFAULT_MODELS]


def test_arka_plan_ceviri_de_ayni_zincirde(monkeypatch):
    """Okumanın gövdesi prefetch'ten (background) geliyor; ucuz bir zincire ayrılsaydı
    çevirinin ÇOĞUNU o belirlerdi — tam da kaldırılma sebebi."""
    zincirler = _zincir_yakala(monkeypatch)
    pipeline.get_or_translate("m-bulk", "anahtar", background=True)
    assert zincirler == [translate.DEFAULT_MODELS]


def test_ikinci_zincir_sabiti_kalmadi():
    """`REFRESH_MODELS` kaldırıldı; geri gelirse 'her yerde aynı sıra' kuralı bozulur."""
    assert not hasattr(translate, "REFRESH_MODELS")


def test_kunye_fiilen_ceviren_modeli_yazar(monkeypatch):
    """Zincirin İLK halkası değil, çeviriyi YAPAN halka künyeye geçmeli."""
    def sahte(client, models, user, system=None, max_tokens=None):
        return _GeminiYanit(), "gemini-3.6-flash"  # ilk halka tökezledi, ikinciye düşüldü

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())
    sonuc = translate.translate_chapter("Bir paragraf.", api_key="k")
    assert sonuc["model"] == "gemini-3.6-flash"
    assert sonuc["engine"] == "gemini"  # motor alanı DEĞİŞMEDİ, model onun yanında


def test_parcalar_farkli_modele_duserse_hepsi_yazilir(monkeypatch):
    """Uzun bölümde ilk parça kotayı bitirip sonrakiler alt halkaya düşebiliyor;
    tek bir 'bölümün modeli' varsayımı yanlış olurdu."""
    kullanilan = iter(["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.6-flash"])

    def sahte(client, models, user, system=None, max_tokens=None):
        return _GeminiYanit(), next(kullanilan)

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())
    # `_split_paragraphs` sahtelenir: MAX_WORDS_PER_CHUNK çalışma zamanında
    # değiştirilemez (varsayılan argüman modül yüklenirken bağlanır).
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: ["p1", "p2", "p3"])
    sonuc = translate.translate_chapter("uzun metin", api_key="k")
    # Tekrar elenir, sıra korunur.
    assert sonuc["model"] == "gemini-3.7-flash + gemini-3.6-flash"
