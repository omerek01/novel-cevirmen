"""Çeviri modeli SEÇİMİ: ayar deposu, zincir kurulumu ve uçlar.

Seçim zincirin YERİNİ ALMAZ, BAŞINA geçer. Ölçüldü (2026-09-02) ki 3.7 ve 3.8 bu
projenin uzunluktaki isteklerini sık sık 503 ile reddediyor; seçim "yalnız bunu
kullan" diye yorumlansaydı o modeli seçen kullanıcının okuması modelin kapasitesi
daraldığı anda TÜMDEN dururdu.
"""
import pytest
from fastapi.testclient import TestClient

import server
from core import kullanim, settings, translate


@pytest.fixture(autouse=True)
def _varsayilana_don():
    """Ayar DB'de kalıcı; testler arası sızarsa iddialar sıraya bağımlı olur."""
    settings.set(translate.MODEL_AYAR_ANAHTARI, translate.VARSAYILAN_MODEL)
    yield
    settings.set(translate.MODEL_AYAR_ANAHTARI, translate.VARSAYILAN_MODEL)


def _client() -> TestClient:
    return TestClient(server.app)


# ---------- ayar deposu ----------

def test_ayar_yazilir_ve_okunur():
    settings.set("deneme", "bir")
    assert settings.get("deneme") == "bir"
    settings.set("deneme", "iki")  # UPSERT: ikinci yazma satırı günceller
    assert settings.get("deneme") == "iki"


def test_olmayan_ayar_varsayilani_doner():
    assert settings.get("hic-yazilmadi", "varsayilan") == "varsayilan"


# ---------- zincir kurulumu ----------

def test_secilen_model_zincirin_basina_gecer():
    zincir = translate.zincir_kur("gemini-3.8-flash")
    assert zincir[0] == "gemini-3.8-flash"
    # Gerisi YEDEK olarak korunur: seçilen model 503 verirse okuma durmamalı.
    assert zincir[1:] == translate.DEFAULT_MODELS


def test_zincirde_ayni_model_iki_kez_denenmez():
    """Zaten zincirde olan bir model seçilirse başa alınır ama TEKRAR ETMEZ —
    yoksa o model kotasını iki kez yakar ve alt halkalara geç inilirdi."""
    zincir = translate.zincir_kur("gemini-3.5-flash")
    assert zincir[0] == "gemini-3.5-flash"
    assert len(zincir) == len(set(zincir))
    assert set(zincir) == set(translate.DEFAULT_MODELS)


def test_varsayilan_secim_zinciri_degistirmez():
    """Ayara hiç dokunulmamışsa davranış birebir eskisi gibi kalmalı."""
    assert translate.zincir_kur(translate.VARSAYILAN_MODEL) == translate.DEFAULT_MODELS


@pytest.mark.parametrize("bozuk", ["", None, "gpt-5", "gemini-3.6-flash-lite"])
def test_taninmayan_secim_sessizce_varsayilana_duser(bozuk):
    """Ayar tablosunda elle bozulmuş bir değer, her isteği 404'e çarpan bir BİRİNCİ
    halka yaratırdı ve arıza "model meşgul" kılığına girerdi."""
    assert translate.zincir_kur(bozuk) == translate.DEFAULT_MODELS


def test_secilebilir_modeller_kullanicinin_istedikleri():
    """Kullanıcı kararı: altı Gemini + iki Claude seçilebilir.

    2026-09-06'da `gemini-2.5-flash` eklendi. Sıra SÜRÜM sırasıdır (yeniden
    eskiye); okuyucu listeyi olduğu gibi çiziyor, karıştırmak kullanıcıyı "hangisi
    daha yeni" sorusuyla baş başa bırakırdı.
    """
    assert translate.SECILEBILIR_ADLAR == (
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "claude-haiku-4-5",
        "claude-sonnet-5",
    )
    for m in translate.SECILEBILIR_MODELLER:
        assert m["etiket"] and m["not"], m  # etiket ve ölçüm notu okuyucuya çıkıyor


def test_yeni_modeller_zinciri_DEGISTIRMEZ():
    """Ekleme YALNIZ seçilebilir listeye; `DEFAULT_MODELS` aynı kalır.

    Ayrım load-bearing: seçilebilir liste bir TEKLİFTİR, zincir ise hiç kimse
    seçim yapmadığında herkesin düştüğü yoldur. Ölçülmemiş bir modeli zincire
    koymak, ayarı hiç açmamış bir kullanıcının çevirisini sessizce değiştirirdi.
    """
    assert translate.DEFAULT_MODELS == (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    )
    assert "gemini-2.5-flash" in translate.SECILEBILIR_ADLAR
    assert "gemini-2.5-flash" not in translate.DEFAULT_MODELS


def test_yeni_model_zincirin_basina_gecebilir():
    """Seçilince zincirin başına geçer, yedekler ALTTA kalır (ücretsiz kural)."""
    zincir = translate.zincir_kur("gemini-2.5-flash")
    assert zincir[0] == "gemini-2.5-flash"
    assert zincir[1:] == translate.DEFAULT_MODELS


def test_gemini_3_onizleme_LISTEDE_DEGIL():
    """Tel tuzağı: `gemini-3-flash-preview` ölçülerek ELENDİ, geri gelmemeli.

    Ölçüm (2026-09-06): hizalamayı 3/3 kaybetti, uzunluk oranı 0,436 — metnin
    yarısını atıp özetliyor. Zincir bunu kurtaramaz (düşme yalnız HATADA olur,
    başarılı ama kötü yanıtta olmaz), yani seçilseydi iki dilli okuma ve
    İngilizce-kalıntı denetimi o bölümlerde tümden ölürdü.

    `gemini-3-flash` / `gemini-3.0-flash` adları da API'de YOK (404).
    """
    for ad in ("gemini-3-flash-preview", "gemini-3-flash", "gemini-3.0-flash"):
        assert ad not in translate.SECILEBILIR_ADLAR
        assert ad not in translate.DEFAULT_MODELS


def test_flash_lite_SECILEBILIR_LISTEDE_DEGIL():
    """Lite yalnız zincirden değil, TEKLİF listesinden de çıktı.

    Seçenek listesi bir TEKLİFTİR: kaliteyi ölçülerek en kötü çıkan halkayı
    teklif etmek, `gemini-3-flash-preview` kararıyla aynı hatayı tekrarlamak
    olurdu. Zincirden çıkarıp listede bırakmak da tutarsız olurdu — kullanıcı
    seçer, zincir onu ilk halka yapar ve kaldırılmış model geri gelirdi.
    """
    assert "gemini-3.5-flash-lite" not in translate.SECILEBILIR_ADLAR
    assert translate.zincir_kur("gemini-3.5-flash-lite") == translate.DEFAULT_MODELS


def test_ucretli_modeller_isaretli():
    """Okuyucu ücretliyi ücretsizden AYIRT edebilmeli: rozetsiz bir liste,
    kullanıcının farkında olmadan para harcayan bir model seçmesine yol açardı."""
    ucretli = {m["ad"] for m in translate.SECILEBILIR_MODELLER if m.get("ucretli")}
    assert ucretli == set(translate.CLAUDE_MODELLER)
    for m in translate.SECILEBILIR_MODELLER:
        if m.get("ucretli"):
            assert "ÜCRETLİ" in m["not"], m  # not da açıkça söylemeli


def test_varsayilan_model_secilebilirler_arasinda():
    """Aksi hâlde okuyucu hiçbir düğmeyi basılı gösteremez ve kullanıcı seçili
    modeli göremezdi."""
    assert translate.VARSAYILAN_MODEL in translate.SECILEBILIR_ADLAR


# ---------- Claude: ÜCRETLİ, yalnız açıkça seçilince, yedeksiz ----------

def test_claude_secilince_zincir_TEK_HALKA():
    """İşin emniyet kilidi. Ücretli bir halkanın ALTINA ücretsiz yedek koymak cazip
    ama iki şeyi birden bozardı: künye "Claude" derken bölümü Gemini çevirmiş
    olabilirdi, ve daha kötüsü tersi yönde "Gemini'nin altına Claude koyalım"
    demenin önü açılırdı — sessiz harcamanın kapısı."""
    for ad in translate.CLAUDE_MODELLER:
        assert translate.zincir_kur(ad) == (ad,), ad


def test_ucretsiz_zincir_ASLA_claude_a_inmez():
    """Sürpriz harcama YAPISAL olarak imkânsız olmalı: Gemini seçiliyken kota
    dolsa bile ücretli halkaya inilmez. Bu projede bir kez ödenmiş ders —
    OpenRouter'ın `:free` soneki düştüğünde istek 200 dönüyor, çeviri çalışıyor,
    hiçbir hata görünmüyor, yalnız fatura işliyordu."""
    assert not any(translate._claude_modeli(m) for m in translate.DEFAULT_MODELS)
    for ad in translate.SECILEBILIR_ADLAR:
        if translate._claude_modeli(ad):
            continue
        zincir = translate.zincir_kur(ad)
        assert not any(translate._claude_modeli(m) for m in zincir), zincir


def test_claude_kunyede_kendi_adiyla_gorunur():
    """Rozet "GEMINI" deseydi hangi motorun para harcadığı gizlenmiş olurdu."""
    assert translate.motor_adi("claude-haiku-4-5") == "claude"
    assert translate.motor_adi("claude-sonnet-5") == "claude"
    assert translate.motor_adi("gemini-3.6-flash") == "gemini"


def test_claude_ornekleme_parametresi_TASIMAZ():
    """Gemini yolundaki `temperature=0.3` Claude'a KOPYALANMAZ.

    İki bağımsız sebep: SDK'nın akış yardımcısı örnekleme parametrelerini hiç
    kabul etmiyor (`stream()` imzasında yok — ilk gerçek çağrı `TypeError` ile
    patladı) ve Sonnet 5 onları zaten 400 ile reddediyor."""
    for bilgi in translate.CLAUDE_MODELLER.values():
        assert "temperature" not in bilgi, bilgi


def test_sonnet5_dusunmeyi_ACIKCA_kapatir():
    """Sonnet 5'te `thinking` HİÇ verilmezse adaptif düşünme AÇIK gelir ve düşünme
    çıktısı da ÇIKIŞ tokenı olarak faturalanır ($10/M). Çeviri mekanik bir iş:
    kazanç belirsiz, maliyet düzenli."""
    assert translate.CLAUDE_MODELLER["claude-sonnet-5"]["dusunme"] == {
        "type": "disabled"
    }


def test_claude_anahtari_iki_adi_da_kabul_eder(monkeypatch):
    """`CLAUDE_API_KEY` kullanıcının bu projede yazdığı ad, `ANTHROPIC_API_KEY`
    SDK'nın kanonik adı. Birini dayatmak, diğerini yazan kurulumu sessizce
    anahtarsız gösterirdi."""
    for ad in translate.CLAUDE_ANAHTAR_ENVLERI:
        monkeypatch.delenv(ad, raising=False)
    assert translate.claude_anahtari() == ""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert translate.claude_anahtari() == "a"
    monkeypatch.setenv("CLAUDE_API_KEY", "c")
    assert translate.claude_anahtari() == "c"  # proje adı öncelikli


def test_claude_anahtari_yoksa_kapi_gemini_ile_acilir(monkeypatch):
    """Claude anahtarı olmayan kurulum (telefon, ikinci makine) bozulmamalı."""
    for ad in translate.CLAUDE_ANAHTAR_ENVLERI:
        monkeypatch.delenv(ad, raising=False)
    assert translate.ceviri_anahtari_var_mi("gemini-anahtari")


# ---------- harcama göstergesi ----------

def test_kullanim_TOKEN_saklar_maliyeti_TURETIR():
    """Fiyat sağlayıcının elinde ve değişir. Doları kaydetseydik, fiyat değiştiği
    gün geçmiş kayıtlar sessizce yanlışa dönerdi ve "bu ay ne harcadım" sorusunun
    cevabı iki farklı fiyatın karışımı olurdu."""
    kullanim.ekle("claude-haiku-4-5", 8284, 4952, gun="2026-09-02")
    o = kullanim.ozet("2026-09")
    assert o["istek"] == 1
    # 8284 * $1/1M + 4952 * $5/1M = 0,008284 + 0,024760
    assert abs(o["maliyet"] - 0.033044) < 1e-4
    assert o["modeller"][0]["giris_token"] == 8284


def test_kullanim_ayni_gun_ve_modelde_birikir():
    kullanim.ekle("claude-sonnet-5", 1000, 1000, gun="2026-09-02")
    kullanim.ekle("claude-sonnet-5", 1000, 1000, gun="2026-09-02")
    o = kullanim.ozet("2026-09")
    assert o["istek"] == 2
    assert o["modeller"][0]["giris_token"] == 2000


def test_ucretsiz_model_gostergeye_girmez():
    """"0,00 $ harcadın" satırları asıl bilgiyi gürültüye boğardı."""
    kullanim.ekle("gemini-3.6-flash", 8000, 5000, gun="2026-09-02")
    assert kullanim.ozet("2026-09")["modeller"] == []


def test_baska_ay_sizmaz():
    kullanim.ekle("claude-haiku-4-5", 1000, 1000, gun="2026-08-31")
    assert kullanim.ozet("2026-09")["istek"] == 0


def test_harcama_uctan_gorunur():
    kullanim.ekle("claude-haiku-4-5", 8284, 4952)
    data = _client().get("/api/settings/model").json()
    assert data["harcama"]["istek"] == 1
    assert data["harcama"]["maliyet"] > 0


# ---------- zincir AYARDAN çözülür (tek nokta) ----------

def test_secili_zincir_ayari_okur():
    settings.set(translate.MODEL_AYAR_ANAHTARI, "gemini-3.7-flash")
    assert translate.secili_zincir()[0] == "gemini-3.7-flash"


def test_ceviri_yolu_secilen_modeli_kullanir(monkeypatch):
    """`translate_chapter` zinciri AYARDAN çözmeli.

    Zinciri çağrı yerlerine tek tek geçirmek yerine tek noktada çözülmesinin sebebi
    somut: zinciri kullanan BEŞ yol var (okuma, prefetch, toplu çeviri, içe
    aktarılan sayfa, terim önerisi) ve biri güncellenmeyi unutulursa kullanıcı
    "modeli değiştirdim ama bazı bölümler hâlâ eskisiyle çevriliyor" derdi.
    """
    settings.set(translate.MODEL_AYAR_ANAHTARI, "gemini-3.8-flash")
    gorulen = {}

    def sahte(client_factory, models, user, system=None, max_tokens=None):
        gorulen["models"] = models
        return type("Y", (), {"text": '{"translation": "[[1]] çeviri"}'})(), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    s = translate.translate_chapter("Bir paragraf.", api_key="k")
    assert gorulen["models"][0] == "gemini-3.8-flash"
    assert s["model"] == "gemini-3.8-flash"


def test_acikca_verilen_zincir_ayari_ezer(monkeypatch):
    """Testler ve bakım araçları kendi zincirini geçebilmeli."""
    settings.set(translate.MODEL_AYAR_ANAHTARI, "gemini-3.8-flash")
    gorulen = {}

    def sahte(client_factory, models, user, system=None, max_tokens=None):
        gorulen["models"] = models
        return type("Y", (), {"text": '{"translation": "[[1]] x"}'})(), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    translate.translate_chapter("Bir paragraf.", api_key="k", models=("ozel-model",))
    assert gorulen["models"] == ("ozel-model",)


# ---------- uçlar ----------

def test_get_secili_modeli_ve_secenekleri_doner():
    res = _client().get("/api/settings/model")
    assert res.status_code == 200
    data = res.json()
    assert data["secili"] == translate.VARSAYILAN_MODEL
    # Seçenekleri SUNUCU veriyor: okuyucuda ikinci bir liste tutulsaydı model
    # eklendiğinde ayrışır ve sunucunun tanımadığı bir ad gönderilebilirdi.
    assert [m["ad"] for m in data["secenekler"]] == list(translate.SECILEBILIR_ADLAR)


def test_post_modeli_kaydeder_ve_kalici_olur():
    client = _client()
    res = client.post("/api/settings/model", json={"model": "gemini-3.5-flash"})
    assert res.status_code == 200
    assert res.json()["secili"] == "gemini-3.5-flash"
    assert res.json()["zincir"][0] == "gemini-3.5-flash"
    # Yeni bir istek (yeni istemci) aynı seçimi görmeli — telefon ve PC ortak.
    assert _client().get("/api/settings/model").json()["secili"] == "gemini-3.5-flash"
    assert translate.secili_zincir()[0] == "gemini-3.5-flash"


def test_post_bilinmeyen_modeli_reddeder():
    """Sessizce yok saymak kullanıcıya "seçtim" dedirtip hiçbir şey değiştirmezdi."""
    res = _client().post("/api/settings/model", json={"model": "gpt-5"})
    assert res.status_code == 400
    assert _client().get("/api/settings/model").json()["secili"] == (
        translate.VARSAYILAN_MODEL
    )
