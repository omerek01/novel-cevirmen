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
    def sahte(client_factory, models, user, system=None, max_tokens=None):
        if promptlar is not None:
            promptlar.append(user)
        # Fiilen çeviren model AÇIKÇA gemini: `models[0]` döndürmek sahteyi zincirin
        # ilk halkasına bağlıyordu ve o halka artık Mistral — yardımcının adı
        # `_gemini_kur` olduğu hâlde künye "mistral" çıkıyordu.
        return _GeminiYanit(), "gemini-3.6-flash"

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())


# ---------- prompt bütünlüğü ----------

def test_prompt_sozluk_ve_baglami_tasir(monkeypatch):
    """Üçü de TEK prompt'ta buluşur; biri düşerse çevirinin karakteri değişir."""
    promptlar = []
    _gemini_kur(monkeypatch, promptlar)

    translate.translate_chapter(
        "Blackwater attacked.", api_key="k",
        glossary={"Blackwater": "Blackwater"},
        prev_context="Önceki bölümün sonu.",
    )

    p = promptlar[0]
    assert "Blackwater" in p
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

def _fetch_yasakla(monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: (_ for _ in ()).throw(
        AssertionError("anahtarsız çağrı fetch'e indi")
    ))


def test_hicbir_anahtar_yoksa_ceviri_reddedilir(monkeypatch):
    """Kapı, fetch'e İNMEDEN erken hata verir (boşuna Cloudflare turu atılmasın).

    Ölçüt tek bir değişken DEĞİL, anahtar HAVUZU: ikinci anahtar yalnız `.env`'de
    duruyor olabilir. Anahtar değişkenleri `gemini_anahtar_degiskenleri` ile
    TÜRETİLEREK siliniyor — adları tek tek yazmak, üçüncü bir anahtar eklendiğinde
    testi sessizce geliştiricinin `.env`ine bağımlı kılardı (`server` importu onu
    pytest sürecine yüklüyor)."""
    for _ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(_ad, raising=False)
    _fetch_yasakla(monkeypatch)
    with pytest.raises(translate.TranslateError):
        pipeline.get_or_translate("u-anahtarsiz", None, background=False)


def test_ortamdaki_ikinci_anahtar_da_kapiyi_acar(monkeypatch):
    """`api_key` argümanı boş olsa bile ortamdaki ikinci anahtar çeviriyi mümkün kılar.

    Kapı bir dönem yalnız çağrıdan gelen anahtara bakıyordu; ikinci anahtar
    `GEMINI2_API_KEY` olarak eklenince bu, pekâlâ çalışabilecek bir kurulumu
    kapıda reddederdi. Kapı geçilince fetch'e inilir; testte fetch yasak olduğu
    için AssertionError'a çarpması BEKLENEN sonuçtur (yani kapı geçildi)."""
    for _ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(_ad, raising=False)
    monkeypatch.setenv("GEMINI2_API_KEY", "ikinci-anahtar")
    _fetch_yasakla(monkeypatch)
    with pytest.raises(AssertionError, match="fetch'e indi"):
        pipeline.get_or_translate("u-ikinci-anahtar", None, background=False)


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

    2026-09-09: `gemini-3.5-flash-lite` ZİNCİRDEN ÇIKARILDI. Bir dönem son halka
    olarak duruyordu ("en dayanıklısı, zincir tükenmesin diye") ama ölçüm bunun
    bedelini gösterdi: sözlük kuralına uyumu zincirin en kötüsüydü (4 bölümde 30
    ihlal; 3.6-flash 60 bölümde 5). Son halka olması durumu ağırlaştırıyordu —
    üst halkalar elendiğinde okuma sessizce oraya iniyor ve çeviri kalıcı
    önbelleğe yazılıyordu. Daralan kapasite anahtar tarafında telafi edildi:
    503 artık sıradaki ANAHTARI deniyor ve istekler anahtarlara dönüşümlü
    dağıtılıyor.

    2026-09-02: zincir GEMINI-TEK oldu. Gemini dışı halkalar (minimax, mistral)
    zincire KOTA gerekçesiyle girmişti, kaliteyle değil; ölçüldüklerinde ikisi de
    metni kısaltıyordu (uzunluk oranı medyanı 0,949 ve 0,914; 3.6-flash 0,972).
    Kotanın yerini ANAHTAR HAVUZU aldı: kota dolunca başka bir sağlayıcıya değil,
    başka bir Gemini anahtarına geçilir — kaliteden ödün verilmeden.
    2026-09-15: ÜÇÜNCÜ halka `gemini-2.5-flash` eklendi. Zincirin iki halkası da
    3.x AİLESİNDENDİ ve o aile kullanıcının anahtarlarına 404 dönmeye başlayınca
    ayakta kalan hiçbir halka kalmadı — çeviri tümden durdu. Dayanıklılık halka
    SAYISINDAN değil, halkaların BİRLİKTE ölmemesinden gelir: aynı ailenin iki
    sürümü ortak bir kaderi paylaşır (aynı erişim politikası, yakın kota havuzu).
    2.5 farklı nesildir ve kotası ayrıdır. SONA konur — 3.6-flash ölçümde hâlâ
    daha iyi (oran 0,972 / 0,932), yani 3.x çalışırken davranış değişmez.

    Halka sırası ve gerekçesi `tests/test_gemini_anahtarlari.py` içinde."""
    assert translate.DEFAULT_MODELS == (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
    )


def test_zincir_tek_model_ailesine_bagli_degil():
    """Tel tuzağı: zincirin TAMAMI tek bir sürüm ailesinden olamaz.

    2026-09-15 arızasının kök nedeni tam buydu — `3.6-flash` ve `3.5-flash`
    ikisi de 3.x'ti, aile 404 dönünce zincirde yedek kalmadı. Bu test zincirin
    kazara yeniden tek-aileye daralmasını tutar.
    """
    aileler = {m.split("-")[1].split(".")[0] for m in translate.DEFAULT_MODELS}
    assert len(aileler) >= 2, translate.DEFAULT_MODELS


def test_zincirde_gemini_disi_saglayici_yok():
    """Gemini dışı sağlayıcılar kaldırıldı; `<sağlayıcı>:<model>` yönlendirmesi de.

    Önekli bir ad artık HİÇBİR yere yönlenmez — Gemini ucuna olduğu gibi gider ve
    404 alır, yani halka sessizce elenir. Tel tuzağı bu yüzden: zincire önekli bir
    ad geri sızarsa arıza "model meşgul" kılığına girerdi."""
    assert all(":" not in m for m in translate.DEFAULT_MODELS)
    assert all(m.startswith("gemini-") for m in translate.DEFAULT_MODELS)


def test_olculmemis_model_zincirin_basinda_durmaz():
    """`gemini-3.7-flash` 2026-08-23'te çıkarıldı: kalitesi hiç ölçülemedi ama
    reddettiğinde zincir bir alta inmeden önce 3 deneme + 6 sn uyku yakıyordu.
    Geri eklenecekse ÖNCE kalitesi ölçülmeli — bu test kazara geri gelmesini tutar."""
    assert "gemini-3.7-flash" not in translate.DEFAULT_MODELS


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
    kullanilan = iter(["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash"])

    def sahte(client, models, user, system=None, max_tokens=None):
        return _GeminiYanit(), next(kullanilan)

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    monkeypatch.setattr(translate.genai, "Client", lambda api_key=None: object())
    # `_split_paragraphs` sahtelenir: MAX_WORDS_PER_CHUNK çalışma zamanında
    # değiştirilemez (varsayılan argüman modül yüklenirken bağlanır).
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: ["p1", "p2", "p3"])
    sonuc = translate.translate_chapter("uzun metin", api_key="k")
    # Tekrar elenir, sıra korunur.
    assert sonuc["model"] == "gemini-3.6-flash + gemini-3.5-flash"
