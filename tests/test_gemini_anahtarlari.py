"""Gemini anahtar havuzu + tek-motor zinciri.

`test_saglayicilar.py`nin yerini aldı. O dosya Gemini DIŞI sağlayıcıları
(OpenRouter/minimax, Mistral, Groq, Cerebras) ve `<sağlayıcı>:<model>`
yönlendirmesini koruyordu; hepsi 2026-09-02'de kaldırıldı. Sebep ölçüm:
zincire KOTA gerekçesiyle girmişlerdi, kaliteyle değil, ve ölçüldüklerinde
metni kısaltıyorlardı (uzunluk oranı medyanı minimax 0,949 · mistral 0,914 ·
gemini-3.6-flash 0,972).

Kotanın yerini ANAHTAR HAVUZU aldı: kota dolunca başka bir SAĞLAYICIYA değil,
başka bir GEMINI ANAHTARINA geçilir — kaliteden ödün verilmeden kota genişler.
Bu dosya o düşme kuralını ve zincirin Gemini-tek kaldığını tutar.
"""
import httpx
import pytest

from core import translate


class _SahteModeller:
    """`client.models` yüzeyinin bu yolda kullanılan asgari hâli."""

    def __init__(self, sonuclar):
        # `sonuclar`: her çağrıda sırayla tüketilir. Bir öge ya metin (başarı) ya da
        # fırlatılacak istisnadır.
        self._sonuclar = list(sonuclar)
        self.cagrilar = []

    def generate_content(self, **kw):
        self.cagrilar.append(kw.get("model"))
        sonuc = self._sonuclar.pop(0) if self._sonuclar else '{"translation": "ok"}'
        if isinstance(sonuc, Exception):
            raise sonuc
        return type("Y", (), {"text": sonuc})()


class _SahteClient:
    def __init__(self, sonuclar=()):
        self.models = _SahteModeller(sonuclar)


class _APIHatasi(Exception):
    """`genai_errors.APIError`nin bu yolda kullanılan tek alanı: `.code`."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def _kota_hatasi(gunluk: bool, retry: str | None = None):
    """Gerçek 429 gövdesinin bu yolda okunan kısmı.

    Gemini kota aşımını İKİ ayrı sınırdan verir ve ikisinin açılma süresi
    tamamen farklıdır — ayrımı yalnız `QuotaFailure.violations[].quotaId`
    söyler. Gerçek gövde (2026-09-09 ölçümü):
        quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
        quotaValue: 20
    """
    kimlik = (
        "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if gunluk
        else "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
    )
    detaylar = [{
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": kimlik, "quotaValue": "20"}],
    }]
    if retry:
        detaylar.append({
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": retry,
        })
    hata = _APIHatasi(429)
    hata.details = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                              "details": detaylar}}
    return hata


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch):
    """Her test TEMİZ anahtar ortamıyla başlar ve soğuma hafızası sıfırlanır.

    İkisi de süreç ömürlü: `server` importu `.env`i pytest sürecine yüklüyor
    (yani geliştiricinin gerçek anahtarları görünür) ve `_ANAHTAR_SOGUMA` modül
    düzeyinde tutuluyor — testler arası sızarsa iddialar sıraya bağımlı olurdu.
    """
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    monkeypatch.setattr(translate.genai, "errors", None, raising=False)
    yield
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()


@pytest.fixture(autouse=True)
def _uykusuz(monkeypatch):
    """Geri-çekilme uykuları testte beklenmesin (503 yolu 6 sn yakardı)."""
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)


def _api_hatasi_yakalansin(monkeypatch):
    """Sahte istisnamız `except genai_errors.APIError` dalına girsin."""
    monkeypatch.setattr(translate.genai_errors, "APIError", _APIHatasi)


def _fabrika(*istemciler):
    """Anahtar indeksine göre istemci veren sahte fabrika (gerçeğiyle aynı sözleşme)."""

    def fabrika(indeks=0):
        if indeks >= len(istemciler):
            raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
        return istemciler[indeks]

    fabrika.anahtar_sayisi = len(istemciler)
    return fabrika


def test_uzun_503_dalgasi_butcede_yedek_modele_gecer(monkeypatch):
    """Beş anahtar x üç uzun tur yerine süre dolunca çalışan yedek denenir."""
    _api_hatasi_yakalansin(monkeypatch)
    saat = [0.0]
    cagrilar = []
    monkeypatch.setattr(translate.time, "monotonic", lambda: saat[0])

    class Modeller:
        def generate_content(self, **kw):
            cagrilar.append(kw["model"])
            if kw["model"] == "gemini-3.6-flash":
                saat[0] += 30
                raise _APIHatasi(503)
            return type("Y", (), {"text": '{"translation": "yedek"}'})()

    istemci = type("I", (), {"models": Modeller()})()
    yanit, model = translate._generate_with_fallback(
        _fabrika(*([istemci] * 5)),
        ("gemini-3.6-flash", "gemini-3.5-flash"), "metin",
    )
    assert model == "gemini-3.5-flash"
    assert "yedek" in yanit.text
    assert cagrilar == ["gemini-3.6-flash"] * 2 + ["gemini-3.5-flash"]


def test_butceyi_asan_basarili_yanit_atilmaz(monkeypatch):
    """Bütçe yalnız yeni denemeleri sınırlar, gelen çeviriyi kaybettirmez."""
    saat = [0.0]
    monkeypatch.setattr(translate.time, "monotonic", lambda: saat[0])
    istemci = _SahteClient()
    uret = istemci.models.generate_content

    def yavas(**kw):
        saat[0] += 75
        return uret(**kw)

    monkeypatch.setattr(istemci.models, "generate_content", yavas)
    _, model = translate._generate_with_fallback(
        _fabrika(istemci), ("gemini-3.6-flash", "gemini-3.5-flash"), "metin",
    )
    assert model == "gemini-3.6-flash"
    assert len(istemci.models.cagrilar) == 1


def test_istemci_zaman_asimi_ve_tek_deneme(monkeypatch):
    """Gerçek SDK yapılandırması sınırsız beklemeyi ve iç içe tekrarı önler."""
    yakalanan = []
    monkeypatch.setattr(translate.genai, "Client", lambda **kw: yakalanan.append(kw))
    fabrika = translate._gemini_fabrikasi("sahte-anahtar")
    fabrika(0)
    secenek = yakalanan[0]["http_options"]
    assert secenek.timeout == 90_000
    assert secenek.retry_options.attempts == 1


# ---------- zincir: GEMINI-TEK ----------

def test_zincir_yalniz_gemini_modelleri():
    """Gemini dışı sağlayıcı zincire GERİ SIZAMAZ.

    Yönlendirme (`<sağlayıcı>:<model>`) kaldırıldığı için önekli bir ad artık
    hiçbir yere yönlenmez: Gemini ucuna olduğu gibi gider, 404 alır ve halka
    SESSİZCE elenir. Yani geri sızan bir önek "model meşgul" kılığında bir arıza
    üretirdi — tel tuzağının sebebi bu.
    """
    assert translate.DEFAULT_MODELS
    for model in translate.DEFAULT_MODELS:
        assert model.startswith("gemini-"), model
        assert ":" not in model, model


def test_kaldirilan_saglayici_yuzeyi_geri_gelmesin():
    """OpenAI-uyumlu sağlayıcı yüzeyi tümüyle kalktı.

    Geri gelirse iki maliyet birlikte döner: ikinci bir düşme kuralı ve
    OpenRouter'ın `:free` sonekinin sessizce PARAYA dönme riski (gerçek vaka: bu
    projenin kıyas turları soneksiz modellere gidip hesapta 0,05 $ yaktı).
    """
    for ad in ("OPENAI_UYUMLU", "_openai_uyumlu_uret", "_onek_ayir", "_SaglayiciHatasi"):
        assert not hasattr(translate, ad), f"{ad} geri gelmiş"


def test_flash_lite_zincirden_KALDIRILDI():
    """`gemini-3.5-flash-lite` 2026-09-09'da zincirden çıkarıldı (kullanıcı kararı).

    Gerekçe ölçüm: sözlük kuralına uyumu zincirin en kötüsüydü — Shadow Slave'in
    önbelleğinde 3.6-flash 60 bölümde 5 ihlal, 3.5-flash 45 bölümde 1, LITE ise
    4 bölümde 30. Somut vaka: 109. bölümü lite çevirdi, `Saint -> Aziz` kaynakta
    12 kez geçti ve 12'si de İngilizce kaldı.

    Zincirin son halkası olduğu için de tehlikeliydi: üst halkalar 429/503 ile
    elendiğinde okuma sessizce ORAYA iniyordu ve çeviri kalıcı önbelleğe yazılıp
    bir daha denetlenmiyordu.
    """
    assert "gemini-3.5-flash-lite" not in translate.DEFAULT_MODELS


def test_olculmemis_model_zincirin_basinda_durmaz():
    """`gemini-3.7-flash` 2026-08-23'te çıkarıldı: kalitesi hiç ölçülemedi ama
    reddettiğinde zincir bir alta inmeden önce 3 deneme + 6 sn uyku yakıyordu.
    Geri eklenecekse ÖNCE kalitesi ölçülmeli."""
    assert "gemini-3.7-flash" not in translate.DEFAULT_MODELS


# ---------- anahtar havuzu: keşif ve sıra ----------

def test_anahtarlar_numarasina_gore_siralanir(monkeypatch):
    """Sıra addaki SAYIDAN gelir; sayı taşımayan ad birincidir.

    `.env`'i elle düzenleyen kullanıcı ikinci anahtarı `GEMINI2_API_KEY` ya da
    `GEMINI_API_KEY_2` diye yazabilir. Tek bir kanonik ad dayatmak, anahtarı
    sessizce görünmez kılardı ve arıza "kota dolu" kılığına girerdi.
    """
    monkeypatch.setenv("GEMINI_API_KEY_3", "ucuncu")
    monkeypatch.setenv("GEMINI2_API_KEY", "ikinci")
    monkeypatch.setenv("GEMINI_API_KEY", "birinci")
    assert translate.gemini_anahtarlari() == ["birinci", "ikinci", "ucuncu"]


def test_bos_anahtar_havuza_girmez(monkeypatch):
    """`.env`'de tanımlı ama BOŞ bırakılmış değişken bir halka açmamalı — açsaydı
    her istekte 400'e çarpan sahte bir anahtar denenirdi."""
    monkeypatch.setenv("GEMINI_API_KEY", "birinci")
    monkeypatch.setenv("GEMINI2_API_KEY", "   ")
    assert translate.gemini_anahtarlari() == ["birinci"]


def test_ayni_anahtar_iki_kez_sayilmaz(monkeypatch):
    """Sunucu `api_key`'i `GEMINI_API_KEY`'den okuyor: argüman ve ortam AYNI değeri
    taşır. Tekrar elenmezse havuz iki halka gösterir ve kota dolduğunda AYNI
    anahtar boşuna ikinci kez denenirdi."""
    monkeypatch.setenv("GEMINI_API_KEY", "ayni")
    assert translate.gemini_anahtarlari("ayni") == ["ayni"]


def test_cagridan_gelen_anahtar_basa_gecer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ortamdaki")
    assert translate.gemini_anahtarlari("acikca-verilen") == [
        "acikca-verilen",
        "ortamdaki",
    ]


def test_kapi_ortamdaki_anahtari_da_sayar(monkeypatch):
    """Kapı tek değişkene değil HAVUZA bakar: ikinci anahtar yalnız `.env`'de
    duruyor olabilir ve onu görmeyen bir kapı çalışabilir kurulumu reddederdi."""
    assert not translate.ceviri_anahtari_var_mi("")
    monkeypatch.setenv("GEMINI2_API_KEY", "ikinci")
    assert translate.ceviri_anahtari_var_mi("")


def test_kapi_argumandaki_anahtarla_da_acilir():
    assert translate.ceviri_anahtari_var_mi("acikca-verilen")


# ---------- düşme kuralı: KOTA -> sıradaki ANAHTAR ----------

def test_kota_dolunca_ayni_modelde_sonraki_anahtara_gecilir(monkeypatch):
    """İşin ÇEKİRDEĞİ: 429 modeli DEĞİŞTİRMEZ, anahtarı değiştirir.

    Kota bir kalite kusuru değildir; bir alt modele inmek kaliteden ödün vermek
    olurdu. Zincirin ikinci boyutu (model) ancak anahtarlar tükendiğinde devreye
    girer.
    """
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(429)])
    ikinci = _SahteClient(['{"translation": "ikinci anahtar"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"  # MODEL AYNI KALDI
    assert yanit.text == '{"translation": "ikinci anahtar"}'
    assert birinci.models.cagrilar == ["gemini-3.6-flash"]
    assert ikinci.models.cagrilar == ["gemini-3.6-flash"]


def test_tum_anahtarlar_tukenince_sonraki_modele_inilir(monkeypatch):
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(429), '{"translation": "alt halka"}'])
    ikinci = _SahteClient([_APIHatasi(429), '{"translation": "alt halka"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    assert birinci.models.cagrilar == ["gemini-3.6-flash", "gemini-3.5-flash"]


def test_kota_soguma_ayni_anahtari_bir_daha_denemez(monkeypatch):
    """Bir bölüm birden çok parça = birden çok istek. Kota dolan anahtar soğumaya
    alınmazsa her parça o anahtara boşuna bir tur daha atardı."""
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(429)])
    ikinci = _SahteClient(['{"a":1}', '{"a":2}'])
    fabrika = _fabrika(birinci, ikinci)
    for _ in range(2):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert birinci.models.cagrilar == ["gemini-3.6-flash"]  # ikinci turda atlandı
    assert ikinci.models.cagrilar == ["gemini-3.6-flash"] * 2


def test_soguma_MODEL_basinadir(monkeypatch):
    """Gemini'nin günlük kotası model başına ayrı: 3.6'da tükenen anahtar 3.5'te
    hâlâ çalışır. Tek bir "anahtar bitti" bayrağı çalışan halkaları da kapatırdı."""
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(429), '{"translation": "3.5 calisti"}'])
    ikinci = _SahteClient([_APIHatasi(429)])
    fabrika = _fabrika(birinci, ikinci)
    yanit, model = translate._generate_with_fallback(
        fabrika, ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    # Birinci anahtar 3.6'da soğumada AMA 3.5'te yeniden denendi ve çevirdi.
    assert birinci.models.cagrilar == ["gemini-3.6-flash", "gemini-3.5-flash"]


def test_soguma_suresi_dolunca_anahtar_geri_gelir(monkeypatch):
    """Soğuma 60 sn: 429 ya DAKİKALIK ya GÜNLÜK sınırdan gelir ve ikisi ayırt
    edilemez. Dakikalık bir tökezlemede anahtarı KALICI kaybetmek, ödenen en
    pahalı hata olurdu."""
    _api_hatasi_yakalansin(monkeypatch)
    # TEK anahtar: rotasyon (2026-09-09) çok anahtarlı kurulumda ikinci isteği
    # başka bir anahtardan başlatır, o yüzden soğumanın süresi tek anahtarla
    # izole edilir — yoksa test soğumayı değil rotasyonu ölçerdi.
    tek = _SahteClient([_APIHatasi(429), '{"translation": "geri geldi"}'])
    fabrika = _fabrika(tek)
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert translate._sogumada(0, "gemini-3.6-flash")

    zaman = [translate.time.monotonic() + translate.ANAHTAR_SOGUMA_SN + 1]
    monkeypatch.setattr(translate.time, "monotonic", lambda: zaman[0])
    assert not translate._sogumada(0, "gemini-3.6-flash")
    yanit, _model = translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert yanit.text == '{"translation": "geri geldi"}'


# ---------- anahtar rotasyonu: her istek SONRAKİ anahtardan başlar ----------

def test_istekler_anahtarlar_arasinda_DONUSUMLU_dagitilir(monkeypatch):
    """Her istek bir SONRAKİ anahtardan başlar (2026-09-09, kullanıcı isteği).

    Eskiden her istek DAİMA #1'den başlıyordu. Gemini'nin ücretsiz günlük kotası
    model başına 20 istek / PROJE olduğu için (429 gövdesinden ölçüldü:
    `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quotaValue 20) ilk
    anahtar erkenden tükeniyor, sonraki HER istek önce ona çarpıp 429 yiyor,
    soğuma yazıyor ve ancak sonra #2'ye geçiyordu — yani havuz beş anahtarlıyken
    bile yük tek anahtara yığılıyordu.

    Rotasyon sayacın başlangıç değerinden BAĞIMSIZ olarak sınanır: üç anahtar,
    üç istek, nereden başlanırsa başlansın her anahtar tam bir kez kullanılmalı.
    """
    _api_hatasi_yakalansin(monkeypatch)
    istemciler = [_SahteClient() for _ in range(3)]
    fabrika = _fabrika(*istemciler)
    for _ in range(3):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert [len(c.models.cagrilar) for c in istemciler] == [1, 1, 1]


def test_bes_anahtarin_yuz_hakki_bitmeden_yedek_modele_gecilmez(monkeypatch):
    """Beş bağımsız 20 istek kotası önce seçilen modelde tamamen kullanılır."""
    _api_hatasi_yakalansin(monkeypatch)
    monkeypatch.setattr(translate, "pasifik_gece_yarisina_kalan", lambda: 3600)
    birincil, yedek = "gemini-3.6-flash", "gemini-3.5-flash"
    istemciler = [
        _SahteClient(['{"translation": "ok"}'] * 20 + [_kota_hatasi(gunluk=True)])
        for _ in range(5)
    ]
    fabrika = _fabrika(*istemciler)
    for istek in range(100):
        _, model = translate._generate_with_fallback(fabrika, (birincil, yedek), "p")
        assert model == birincil
        # Her beş istekte bütün anahtarlar aynı sayıda kullanılmış olmalı.
        if (istek + 1) % 5 == 0:
            assert [len(c.models.cagrilar) for c in istemciler] == [(istek + 1) // 5] * 5

    _, model = translate._generate_with_fallback(fabrika, (birincil, yedek), "p")
    assert model == yedek
    assert all(c.models.cagrilar.count(birincil) == 21 for c in istemciler)
    assert sum(c.models.cagrilar.count(yedek) for c in istemciler) == 1


def test_rotasyon_soguyan_anahtari_yine_de_atlar(monkeypatch):
    """Rotasyon soğumanın YERİNE geçmez, onunla birlikte çalışır.

    Kotası dolan anahtar sırası geldiğinde de atlanmalı; yoksa rotasyon her
    turda o anahtara bir boş istek daha attırırdı.
    """
    _api_hatasi_yakalansin(monkeypatch)
    dolu = _SahteClient([_APIHatasi(429)])
    saglam = _SahteClient()
    fabrika = _fabrika(dolu, saglam)
    for _ in range(3):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert dolu.models.cagrilar == ["gemini-3.6-flash"]  # bir kez, sonra soğumada
    assert len(saglam.models.cagrilar) == 3


def test_rotasyon_tek_anahtarla_da_calisir(monkeypatch):
    """Tek anahtarlı kurulum (varsayılan `.env`) rotasyondan etkilenmemeli."""
    _api_hatasi_yakalansin(monkeypatch)
    tek = _SahteClient()
    fabrika = _fabrika(tek)
    for _ in range(3):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    assert len(tek.models.cagrilar) == 3


def test_rotasyon_SAGLAM_anahtarlar_arasinda_esit_dagilir(monkeypatch):
    """Soğumadaki anahtar rotasyon SIRASINI da tüketmemeli (kullanıcı isteği).

    Kotası dolan anahtar zaten atlanıyordu, ama rotasyon sayacı onu yine de bir
    tur harcıyordu: üç anahtarın biri kotadayken dört istek sağlam ikiliye 3/1
    dağılıyordu. Kotası dolmuş bir anahtardan "başlamamak", sırayı da onun
    üstünden atlamak demektir.
    """
    _api_hatasi_yakalansin(monkeypatch)
    dolu = _SahteClient([_kota_hatasi(gunluk=True)])
    saglam = [_SahteClient() for _ in range(2)]
    fabrika = _fabrika(dolu, *saglam)
    translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    onceki = [len(c.models.cagrilar) for c in saglam]
    for _ in range(4):
        translate._generate_with_fallback(fabrika, ("gemini-3.6-flash",), "p")
    artis = [len(c.models.cagrilar) - o for c, o in zip(saglam, onceki)]
    assert artis == [2, 2]
    assert dolu.models.cagrilar == ["gemini-3.6-flash"]  # bir kez, sonra hiç


# ---------- kota TÜRÜ: günlük mü dakikalık mı ----------

def test_GUNLUK_kota_anahtari_dakikalarla_geri_GETIRMEZ(monkeypatch):
    """Günlük kota (RPD) Pasifik gece yarısına kadar KAPALIDIR.

    Soğuma sabit 60 sn iken günlük kotası dolan anahtar dakikada bir yeniden
    deneniyordu: her bölüm o anahtara bir boş istek daha atıyor, 429 yiyor ve
    kullanıcı bunun bedelini bekleme olarak ödüyordu. Kullanıcı isteği:
    "kotası dolan anahtarlardan tekrar başlamasın, kotası boşaldıktan sonra
    tekrar kullanmaya başlasın."
    """
    _api_hatasi_yakalansin(monkeypatch)
    dolu = _SahteClient([_kota_hatasi(gunluk=True)])
    saglam = _SahteClient()
    translate._generate_with_fallback(
        _fabrika(dolu, saglam), ("gemini-3.6-flash",), "p"
    )
    ileri = translate.time.monotonic() + translate.ANAHTAR_SOGUMA_SN + 300
    monkeypatch.setattr(translate.time, "monotonic", lambda: ileri)
    assert translate._sogumada(0, "gemini-3.6-flash")


def test_DAKIKALIK_kota_anahtari_bir_dakikada_geri_gelir(monkeypatch):
    """Dakikalık sınır (RPM/TPM) kendiliğinden açılır — uzun soğuma, çalışan bir
    anahtarı sebepsiz kaybetmek olurdu."""
    _api_hatasi_yakalansin(monkeypatch)
    dolu = _SahteClient([_kota_hatasi(gunluk=False)])
    saglam = _SahteClient()
    translate._generate_with_fallback(
        _fabrika(dolu, saglam), ("gemini-3.6-flash",), "p"
    )
    ileri = translate.time.monotonic() + translate.ANAHTAR_SOGUMA_SN + 1
    monkeypatch.setattr(translate.time, "monotonic", lambda: ileri)
    assert not translate._sogumada(0, "gemini-3.6-flash")


def test_kota_turu_okunamazsa_KISA_soguma_secilir(monkeypatch):
    """Gövde ayrıştırılamazsa dakikalık varsayılır: yanlış tarafta hata yapmak
    anahtarı gün boyu kaybetmekten ucuzdur."""
    _api_hatasi_yakalansin(monkeypatch)
    dolu = _SahteClient([_APIHatasi(429)])  # gövdesiz
    saglam = _SahteClient()
    translate._generate_with_fallback(
        _fabrika(dolu, saglam), ("gemini-3.6-flash",), "p"
    )
    ileri = translate.time.monotonic() + translate.ANAHTAR_SOGUMA_SN + 1
    monkeypatch.setattr(translate.time, "monotonic", lambda: ileri)
    assert not translate._sogumada(0, "gemini-3.6-flash")


# ---------- düşme kuralı: KOTA DIŞI arızalar -> sıradaki MODEL ----------

def test_404_modeli_ATLAMAZ_sonraki_ANAHTARI_dener(monkeypatch):
    """404 modeli ATLAMAZ, sıradaki ANAHTARI dener (2026-09-15, ölçümle düzeltildi).

    Eski kural "404 model yok demektir, ikinci anahtar da aynı cevabı verirdi"
    diyordu ve o varsayım bu projenin KENDİ ölçümüyle çürüktü. `kota_durum.py`
    2026-09-06'da şunu yazdı:

        GEMINI_API_KEY    gemini-2.5-flash  AÇIK
        GEMINI2_API_KEY   gemini-2.5-flash  AÇIK
        GEMINI3_API_KEY   gemini-2.5-flash  YOK (bu projede sunulmuyor)

    Yani model erişimi PROJE başınadır — tıpkı kota gibi — ve anahtar başına
    DEĞİŞİR. Eski kural tek bir 404'te o modeldeki kalan bütün SAĞLAM anahtarları
    iptal ediyordu. Zincirin İKİ halkası da aynı anahtarda 404 alınca çeviri
    tümden duruyordu: gerçek arıza 2026-09-15, kullanıcıda BEŞ anahtar vardı,
    dördü çalışıyordu ve hiçbiri denenmiyordu.

    Bu, 503 dalında 2026-09-09'da düzeltilen hatanın AYNISIDIR (aşağıdaki test);
    o tur yalnız 503'ü düzeltmiş, 404'ü atlamıştı.
    """
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(404)])
    ikinci = _SahteClient(['{"translation": "ikinci anahtar"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"  # MODEL AYNI KALDI
    assert yanit.text == '{"translation": "ikinci anahtar"}'
    assert ikinci.models.cagrilar == ["gemini-3.6-flash"]  # ikinci anahtar DENENDİ


def test_tum_anahtarlar_404_verince_sonraki_modele_inilir(monkeypatch):
    """Havuz gerçekten tükendiyse (ad yanlış / model hiçbir projede yok) zincir
    yine sıradaki MODELe iner — anahtar döngüsü bunu geciktirmez, 404 hızlı
    döner ve bu dalda UYKU yoktur."""
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(404), '{"translation": "alt halka"}'])
    ikinci = _SahteClient([_APIHatasi(404), '{"translation": "alt halka"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-yok", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    assert birinci.models.cagrilar == ["gemini-yok", "gemini-3.5-flash"]
    # İkinci anahtar YALNIZ tükenen modelde denendi: alt halkayı birinci anahtar
    # zaten çevirdi, havuzu boşuna dolaşmak her halkanın maliyetini ikiye katlardı.
    assert ikinci.models.cagrilar == ["gemini-yok"]


def test_404_beklemez_tur_tekrari_yapmaz(monkeypatch):
    """404 `turda_gecici` İŞARETLEMEZ: erişim beklemekle açılmaz.

    503 dalı turu geri-çekilerek TEKRARLAR (2s→4s). 404 orada olsaydı her bölüm
    zincir başına boşuna 6 sn yakardı ve arıza "yavaş çeviriyor" kılığına girerdi.
    """
    _api_hatasi_yakalansin(monkeypatch)
    uyudu = []
    monkeypatch.setattr(translate.time, "sleep", lambda sn: uyudu.append(sn))
    istemci = _SahteClient([_APIHatasi(404), _APIHatasi(404)])
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(
            _fabrika(istemci), ("gemini-yok", "gemini-yok-2"), "p"
        )
    assert uyudu == []  # HİÇ uyunmadı


def test_zincirin_tamami_404_ise_mesaj_MESGUL_demez(monkeypatch):
    """Yanlış teşhis, arızanın kendisi kadar pahalıdır.

    Zincirin tamamı 404'ten düştüğünde eski mesaj "Tüm modeller şu anda meşgul
    (geçici). Biraz sonra tekrar deneyin." diyordu. Bu kullanıcıyı BEKLEMEYE
    iter, oysa erişim beklemekle ASLA açılmaz — gerçek vaka 2026-09-15:
    kullanıcı "5 anahtarım var, kotanın dolması imkânsız" diyerek arızayı kota
    tarafında aradı. Mesaj artık sebebi ve çıkışı söylüyor.

    Aynı kural anahtarsızlık dalında zaten vardı ("modeller meşgul" demek yerine
    "anahtar yok"); 404 dalı atlanmıştı.
    """
    _api_hatasi_yakalansin(monkeypatch)
    istemci = _SahteClient([_APIHatasi(404), _APIHatasi(404)])
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(
            _fabrika(istemci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
        )
    mesaj = str(hata.value)
    assert "meşgul" not in mesaj.lower()
    assert "404" in mesaj and "gemini-3.6-flash" in mesaj
    assert "kota_durum" in mesaj  # kullanıcıya teşhis aracını gösterir


def test_503_modeli_ATLAMAZ_sonraki_ANAHTARI_dener(monkeypatch):
    """503 modeli ATLAMAZ, sıradaki ANAHTARI dener (2026-09-09, ölçümle düzeltildi).

    Eski kural "500/503 sunucu arızasıdır, anahtar fark etmez" diyordu ve o
    varsayım ÖLÇÜMLE çürüdü. 5 anahtar x 3 tur canlı yoklama (2026-09-09):

        gemini-3.6-flash  tur2: #1:429 #2:AÇIK #3:AÇIK #4:503 #5:AÇIK
        gemini-3.5-flash  tur2: #1:429 #2:503  #3:AÇIK #4:AÇIK #5:AÇIK

    503 tek bir anahtarda çıkarken diğerleri AYNI ANDA açık — yani anahtar
    fark EDİYOR. Eski kural tek geçici 503'te o modeldeki kalan bütün sağlam
    anahtarları iptal ediyordu; iki model üst üste böyle atlanınca okuma
    zincirin dibine iniyordu (kullanıcı şikâyeti: "5 anahtar var ama lite'a
    düşüyor").
    """
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(503)])
    ikinci = _SahteClient(['{"translation": "ikinci anahtar"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"  # MODEL ATLANMADI
    assert yanit.text == '{"translation": "ikinci anahtar"}'
    # Havuz varsa anahtar başına TEK deneme: sıradaki anahtar zaten yeni bir
    # denemedir, aynı anahtarda uyuyup beklemek saf kayıptı (bkz.
    # `test_gecici_hata_COK_ANAHTARLI_kurulumda_UYUMAZ`).
    assert birinci.models.cagrilar == ["gemini-3.6-flash"]
    assert ikinci.models.cagrilar == ["gemini-3.6-flash"]


def test_503_tum_anahtarlarda_cikarsa_alt_modele_inilir(monkeypatch):
    """Anahtarlar tükenince model boyutu devreye girer — zincir yine de iner."""
    _api_hatasi_yakalansin(monkeypatch)
    # Alt modele inmek için TUR TEKRARININ da tükenmesi gerekir: geçici arızada
    # zincir, anahtarları uykusuz dolaştıktan sonra geri-çekilip turu tekrarlar.
    tuketen = [_APIHatasi(503)] * translate.MAX_RETRIES
    birinci = _SahteClient(tuketen + ['{"translation": "alt halka"}'])
    ikinci = _SahteClient(list(tuketen) + ['{"translation": "alt halka"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"


def _soguma_kayitlari(monkeypatch):
    """`_sogut` çağrılarını (indeks, model, süre, sebep) olarak yakalar; gerçeği de çağırır."""
    kayit = []
    gercek = translate._sogut

    def sar(indeks, model, sure=None, sebep="kota"):
        kayit.append((indeks, model, sure, sebep))
        gercek(indeks, model, sure, sebep)

    monkeypatch.setattr(translate, "_sogut", sar)
    return kayit


def test_gecici_TUKENINCE_model_sogumaya_alinir(monkeypatch):
    """503 dönen istek de GÜNLÜK KOTADAN sayılır (ölçüldü 2026-09-21).

    O güne kadar 503'ün bedava olduğu varsayılıyordu ve doygun model ısrarla
    deneniyordu. Sunucu verisi tersini gösterdi: `gemini-3.6-flash` beş anahtarın
    BEŞİNDE de tam 20 denemede 429'a çarptı (ücretsiz günlük sınır 20/proje/model)
    ve o denemelerin neredeyse tamamı 503'tü — gün boyu 103 deneme harcandı, 2
    bölüm çevrildi. Model akşam toparlasa bile kotası bittiği için kullanılamaz
    hâle geliyordu. Zarar iki katlı: boşa geçen süre + geri gelmeyen kota.
    """
    _api_hatasi_yakalansin(monkeypatch)
    kayit = _soguma_kayitlari(monkeypatch)
    tuketen = [_APIHatasi(503)] * (translate.MAX_RETRIES + 1)
    a1, a2 = _SahteClient(list(tuketen)), _SahteClient(list(tuketen))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika(a1, a2), ("gemini-3.6-flash",), "p")
    assert translate._sogumada(0, "gemini-3.6-flash")
    assert translate._sogumada(1, "gemini-3.6-flash")
    assert {(i, m) for i, m, _s, _n in kayit} == {
        (0, "gemini-3.6-flash"), (1, "gemini-3.6-flash")}
    # Sebep AYIRT EDİLİR: mesaj "kota soğumasında" derse kullanıcı arızayı kota
    # tarafında arar — oysa kota dolu değil, model yoğun.
    assert {n for _i, _m, _s, n in kayit} == {"gecici"}


def test_gecici_soguma_YALNIZ_o_modele_yazilir(monkeypatch):
    """Doygunluk MODELE aittir. 3.6'da tükenen anahtar 3.5'te hâlâ çalışır —
    tek bir "anahtar bitti" işareti ayakta duran halkaları da kapatırdı."""
    _api_hatasi_yakalansin(monkeypatch)
    tuketen = [_APIHatasi(503)] * (translate.MAX_RETRIES + 1)
    tek = _SahteClient(tuketen + ['{"translation": "alt halka"}'])
    _yanit, model = translate._generate_with_fallback(
        _fabrika(tek), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    assert translate._sogumada(0, "gemini-3.6-flash")
    assert not translate._sogumada(0, "gemini-3.5-flash")


def test_gecici_soguma_ARDISIK_tukeniste_uzar(monkeypatch):
    """Doygunluk saatlerce sürebiliyor ama ara ara açılıyor (3.6, 2026-09-21:
    09:44-19:38 arası sürekli 503, arada 13:31'de bir başarı). Sabit kısa süre
    kotayı yakar, sabit uzun süre modelin toparladığı anı kaçırır. Üstel artış
    ikisini de karşılar: ilk deneme yakındır, ısrar eden doygunlukta aralık açılır."""
    _api_hatasi_yakalansin(monkeypatch)
    kayit = _soguma_kayitlari(monkeypatch)
    for _ in range(3):
        translate._ANAHTAR_SOGUMA.clear()  # soğumayı sil, ARDIŞIKLIK sayacını koru
        tek = _SahteClient([_APIHatasi(503)] * (translate.MAX_RETRIES + 1))
        with pytest.raises(translate.TranslateError):
            translate._generate_with_fallback(_fabrika(tek), ("gemini-3.6-flash",), "p")
    assert [s for _i, _m, s, _n in kayit] == [
        translate.GECICI_SOGUMA_TABAN_SN,
        translate.GECICI_SOGUMA_TABAN_SN * 2,
        translate.GECICI_SOGUMA_TABAN_SN * 4,
    ]


def test_gecici_soguma_BASARIDAN_sonra_tabana_doner(monkeypatch):
    """Model toparladıysa geçmiş doygunluk cezası taşınmaz: sonraki tökezleme
    yine en kısa aralıkla denenir. Yoksa tek bir kötü dalga, günün kalanında
    modeli sebepsiz uzakta tutardı."""
    _api_hatasi_yakalansin(monkeypatch)
    kayit = _soguma_kayitlari(monkeypatch)
    tuketen = [_APIHatasi(503)] * (translate.MAX_RETRIES + 1)
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(
            _fabrika(_SahteClient(list(tuketen))), ("gemini-3.6-flash",), "p")
    translate._ANAHTAR_SOGUMA.clear()
    translate._generate_with_fallback(
        _fabrika(_SahteClient(['{"a": 1}'])), ("gemini-3.6-flash",), "p")
    translate._ANAHTAR_SOGUMA.clear()
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(
            _fabrika(_SahteClient(list(tuketen))), ("gemini-3.6-flash",), "p")
    assert [s for _i, _m, s, _n in kayit] == [translate.GECICI_SOGUMA_TABAN_SN] * 2


def test_gecici_soguma_TAVANI_asmaz(monkeypatch):
    """Üstel artış sınırsız olsaydı birkaç tükenişten sonra model gün boyu
    kapanır ve toparlanması hiçbir zaman fark edilmezdi."""
    _api_hatasi_yakalansin(monkeypatch)
    kayit = _soguma_kayitlari(monkeypatch)
    for _ in range(12):
        translate._ANAHTAR_SOGUMA.clear()
        tek = _SahteClient([_APIHatasi(503)] * (translate.MAX_RETRIES + 1))
        with pytest.raises(translate.TranslateError):
            translate._generate_with_fallback(_fabrika(tek), ("gemini-3.6-flash",), "p")
    assert max(s for _i, _m, s, _n in kayit) == translate.GECICI_SOGUMA_TAVAN_SN


def test_butce_dolunca_da_gecici_soguma_yazilir(monkeypatch):
    """Süre bütçesi dolduğunda da model o an çeviremiyordur. Soğutma yalnız
    turların tükenmesine bağlansaydı, uzun 503'lerde (deneme başına 29 sn)
    bütçe ÖNCE dolar ve kota koruması hiç devreye girmezdi — ölçülen günde en
    çok kota yakan yol tam olarak budur."""
    _api_hatasi_yakalansin(monkeypatch)
    kayit = _soguma_kayitlari(monkeypatch)
    saat = [0.0]
    monkeypatch.setattr(translate.time, "monotonic", lambda: saat[0])

    class Modeller:
        def generate_content(self, **kw):
            if kw["model"] == "gemini-3.6-flash":
                saat[0] += 30
                raise _APIHatasi(503)
            return type("Y", (), {"text": '{"translation": "yedek"}'})()

    istemci = type("I", (), {"models": Modeller()})()
    _yanit, model = translate._generate_with_fallback(
        _fabrika(*([istemci] * 5)), ("gemini-3.6-flash", "gemini-3.5-flash"), "p")
    assert model == "gemini-3.5-flash"
    assert kayit and all(m == "gemini-3.6-flash" for _i, m, _s, _n in kayit)


def test_503_BASKA_anahtar_calisiyorsa_SOGUTMAZ(monkeypatch):
    """Soğutma modelin TÜKENMESİNE bağlıdır, tek bir 503'e değil. Ölçüm
    (2026-09-09) 503'ün tek anahtarda çıkarken diğerlerinin AYNI ANDA açık
    dönebildiğini gösterdi; orada soğutmak sağlam bir anahtarı sebepsiz
    kaybetmek olurdu. Havuz çeviriyi tamamladıysa doygunluk yok demektir."""
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient([_APIHatasi(503)] * translate.MAX_RETRIES)
    ikinci = _SahteClient(['{"a": 1}'])
    translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash",), "p"
    )
    assert not translate._sogumada(0, "gemini-3.6-flash")
    assert not translate._sogumada(1, "gemini-3.6-flash")


def test_gecici_hatada_uyku_ANAHTAR_basina_DEGIL_TUR_basina(monkeypatch):
    """Havuz UYKUSUZ dolaşılır; uyku yalnız tüm anahtarlar tükendikten sonra.

    İki ayrı yanlış arasındaki denge, ikisi de ölçüldü:
      * Anahtar başına 3 deneme + uyku (2026-09-09 hâli) -> zincirin tamamı 503
        verdiğinde 5 anahtar x 2 model = 30 istek ve 60 sn UYKU. Kullanıcı bunu
        "aşırı yavaş çeviriyor" diye gördü.
      * Uykuyu TÜMDEN kaldırmak -> 10 deneme saniyeler içinde tükeniyor ve zincir
        pes ediyor. Gerçek vaka (2026-09-10): 15 bölümlük toplu çeviri ikinci
        bölümde "Tüm modeller şu anda meşgul" ile durdu. Oysa Google'ın kendi
        503 gövdesi "Spikes in demand are usually temporary. Please try again
        later." diyor — yani beklemek BAZEN tam olarak doğru cevap.

    Doğrusu ikisinin arası: sağlam anahtarı UYKUSUZ ara (hızlı), hiçbiri
    çeviremediyse geri-çekilerek turu tekrarla (dayanıklı).
    """
    uyku = []
    monkeypatch.setattr(translate.time, "sleep", uyku.append)
    _api_hatasi_yakalansin(monkeypatch)
    istemciler = [_SahteClient([_APIHatasi(503)] * 30) for _ in range(3)]
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(
            _fabrika(*istemciler), ("gemini-3.6-flash",), "p"
        )
    # 3 anahtar x MAX_RETRIES tur — anahtar başına tek istek, tur başına bir uyku.
    assert sum(len(c.models.cagrilar) for c in istemciler) == 3 * translate.MAX_RETRIES
    assert uyku == [2.0, 4.0]


def test_gecici_hata_sonraki_TURDA_gecerse_model_ATLANMAZ(monkeypatch):
    """503 gerçekten geçiciyse bir sonraki tur çevirir; alt modele inilmez."""
    _api_hatasi_yakalansin(monkeypatch)
    a1 = _SahteClient([_APIHatasi(503), '{"translation": "ikinci tur"}'])
    a2 = _SahteClient([_APIHatasi(503)] * 5)
    yanit, model = translate._generate_with_fallback(
        _fabrika(a1, a2), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"
    assert yanit.text == '{"translation": "ikinci tur"}'


def test_tum_anahtarlar_KOTADAYSA_tur_tekrari_YAPILMAZ(monkeypatch):
    """Kota beklemekle açılmaz — geçici arızaya özgü tur tekrarı orada saf
    kayıptır ve okumayı sebepsiz geciktirirdi."""
    uyku = []
    monkeypatch.setattr(translate.time, "sleep", uyku.append)
    _api_hatasi_yakalansin(monkeypatch)
    istemciler = [_SahteClient([_kota_hatasi(gunluk=False)] * 5) for _ in range(3)]
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(
            _fabrika(*istemciler), ("gemini-3.6-flash",), "p"
        )
    assert uyku == []
    assert sum(len(c.models.cagrilar) for c in istemciler) == 3


def test_gecici_hata_TEK_anahtarda_geri_cekilme_KORUNUR(monkeypatch):
    """Tek anahtarlı kurulumda (varsayılan `.env`) başka seçenek yoktur —
    geri-çekilmeli tekrar orada hâlâ tek dayanıklılık aracı."""
    uyku = []
    monkeypatch.setattr(translate.time, "sleep", uyku.append)
    _api_hatasi_yakalansin(monkeypatch)
    tek = _SahteClient([_APIHatasi(503)] * 10)
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika(tek), ("gemini-3.6-flash",), "p")
    assert tek.models.cagrilar == ["gemini-3.6-flash"] * translate.MAX_RETRIES
    assert uyku == [2.0, 4.0]


def test_tasima_hatasi_sonraki_ANAHTARI_dener(monkeypatch):
    """Bağlantı kopması da 503 ile aynı sınıf: geçici, ve anahtar FARK EDER."""
    _api_hatasi_yakalansin(monkeypatch)
    kopuk = httpx.RemoteProtocolError("sunucu bağlantıyı kapattı")
    birinci = _SahteClient([kopuk] * translate.MAX_RETRIES)
    ikinci = _SahteClient(['{"translation": "ikinci anahtar"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"
    assert ikinci.models.cagrilar == ["gemini-3.6-flash"]


def test_tasima_hatasi_zinciri_oldurmez(monkeypatch):
    """Bağlantı kopması `APIError` DEĞİLDİR ve bir dönem HİÇBİR dala girmiyordu:
    istisna zincirin dışına sızıp çeviriyi tümden öldürüyordu (kullanıcı ham bir
    hata görüyordu). Ölçülen vaka (2026-09-02): `gemini-3.6-flash` 81 sn sonra
    `RemoteProtocolError`. Tek motor kaldığından bu yolun dayanıklılığı artık
    çevirinin TAMAMININ dayanıklılığıdır."""
    _api_hatasi_yakalansin(monkeypatch)
    kopuk = httpx.RemoteProtocolError("sunucu bağlantıyı kapattı")
    birinci = _SahteClient([kopuk] * translate.MAX_RETRIES + ['{"translation": "alt"}'])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    # 503 ile AYNI sınıf arıza: aynı modelde geri-çekilmeli tekrar, sonra alt model.
    assert birinci.models.cagrilar.count("gemini-3.6-flash") == translate.MAX_RETRIES


def test_tasima_hatasi_gecerse_ceviri_surer(monkeypatch):
    """Tek bir kopma çeviriyi bir alt modele düşürmemeli — tekrar denenip geçmeli."""
    _api_hatasi_yakalansin(monkeypatch)
    istemci = _SahteClient(
        [httpx.ConnectError("ağ"), '{"translation": "ayni model cevirdi"}']
    )
    yanit, model = translate._generate_with_fallback(
        _fabrika(istemci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.6-flash"


def test_bos_yanit_sonraki_modele_duser(monkeypatch):
    """Boş/engellenmiş yanıt içerik filtresidir: deterministik, anahtar değiştirmek
    işe yaramaz — başka bir MODEL çevirebilir."""
    _api_hatasi_yakalansin(monkeypatch)
    birinci = _SahteClient(["", '{"translation": "alt halka"}'])
    ikinci = _SahteClient([])
    yanit, model = translate._generate_with_fallback(
        _fabrika(birinci, ikinci), ("gemini-3.6-flash", "gemini-3.5-flash"), "p"
    )
    assert model == "gemini-3.5-flash"
    assert ikinci.models.cagrilar == []


# ---------- anahtarsızlık: DÜRÜST hata mesajı ----------

def test_anahtarsiz_zincir_dogru_teshis_verir():
    """"Modeller meşgul" demek yanlış teşhis olurdu: kullanıcının yapması gereken
    beklemek değil, anahtar ayarlamak."""
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika(), translate.DEFAULT_MODELS, "p")
    assert "GEMINI_API_KEY" in str(hata.value)


def test_zincir_tukenince_son_hata_mesaja_girer(monkeypatch):
    """"Tüm modeller meşgul" tek başına teşhis edilemez bir mesajdı. Son hatanın
    detayı mesaja girmeli, yoksa kota hatası geçici arıza gibi görünür."""
    _api_hatasi_yakalansin(monkeypatch)
    istemci = _SahteClient([_APIHatasi(429)] * 10)
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika(istemci), ("gemini-3.6-flash",), "p")
    assert "429" in str(hata.value)


# ---------- künye: hangi MOTOR çevirdi ----------

def test_motor_adi_tek_tanimdan_gelir():
    """Çağrı yerlerinde SABİT yazılmaz. Bir dönem tam olarak öyle yapılmıştı ve
    ikinci bir sağlayıcı girince rozet YANLIŞ bilgi veriyordu (Mistral'in çevirdiği
    bölüm "GEMINI ile çevrildi" diyordu). Motor bir daha değişirse tek satır."""
    assert translate.motor_adi("gemini-3.6-flash") == "gemini"
    assert translate.motor_adi("gemini-3.6-flash + gemini-3.5-flash") == "gemini"
    assert translate.motor_adi(None) is None
    assert translate.motor_adi("") is None


def test_ceviren_model_kunyeye_yazilir(monkeypatch):
    """Künye FİİLEN çeviren modeli göstermeli: kalite şikâyetlerinde "bunu hangi
    model çevirdi" sorusu tahminle cevaplanıyordu."""
    _api_hatasi_yakalansin(monkeypatch)
    istemci = _SahteClient(
        [_APIHatasi(429), '{"translation": "[[1]] çeviri", "detected_names": []}']
    )
    monkeypatch.setattr(
        translate, "_gemini_fabrikasi", lambda anahtar: _fabrika(istemci, istemci)
    )
    s = translate.translate_chapter(
        "Bir paragraf.", api_key="k", models=("gemini-3.6-flash", "gemini-3.5-flash")
    )
    assert s["engine"] == "gemini"
    assert s["model"] == "gemini-3.6-flash"  # 429 sonrası İKİNCİ ANAHTAR çevirdi


def _config_yakala(istemci_sonuclari=('{"translation": "ok"}',)):
    """`generate_content`e giden config'i yakalayan asgari istemci."""
    kutu = {}

    class _Modeller:
        def generate_content(self, **kw):
            kutu.update(kw)
            return type("Y", (), {"text": istemci_sonuclari[0]})()

    return type("I", (), {"models": _Modeller()})(), kutu


def test_gemini_isteginde_dusunme_KAPATILMAZ():
    """Düşünme MODELİN VARSAYILANINDA kalır: `thinking_config` HİÇ gönderilmez.

    2026-09-22'de kapatılmıştı (yalnız `gemini-2.5-flash`, iki bölüm ölçülerek:
    hizalama, sözlük ihlali ve kalıntı değişmedi; süre 65 -> 19 sn). Ertesi gün
    sunucu verisi o ölçümün GÖREMEDİĞİ iki arıza gösterdi ve karar geri alındı:

    * KOŞULLU sözlük kaydı uygulanamıyor. `Saint -> Aziz [KOŞUL: yalnız rütbe;
      gölgenin ADI ise İngilizce kalır]`: gölgenin adı olan "Saint" 2.5-flash'ta
      düşünme açıkken 44 paragrafın 44'ünde korunmuş, kapalıyken 21'in 5'inde
      "Aziz"e çevrilmiş. Kontrollü A/B (bölüm 667, aynı prompt, tek değişken):
      bütçe 0 -> beş adın BEŞİ "Aziz"; varsayılan -> beşi de "Saint". Eski ölçüm
      bunu göremezdi: uyum denetimi koşullu kayıtları bilerek dışarıda bırakıyor.
    * 3.x ailesinde sözlük uyumu ÇÖKEBİLİYOR (ölçülen model 2.5'ti, zincirin başı
      3.6). Düşünme kapalıyken 3.6-flash bir bölümde 22 kayıtlı terimi İngilizce
      bıraktı ("Sanctuary'ye", "Transcendent'a"); 3.5-flash aynı bölümün iki
      koşusunda 5 ve 33 (rün bloğunu çevirmeden kopyaladı). Düşünme açıkken
      3.6'nın 209 bölümünde yalnız biri ihlalliydi. Arıza olasılıksaldır (aynı
      bölümün kontrollü iki koşusu temiz çıktı) ama tek bozuk koşu bile kalıcı
      önbelleğe yazılır ve bir daha çeviri tetiklemez.
    """
    istemci, kutu = _config_yakala()
    translate._generate_with_fallback(_fabrika(istemci), ("gemini-3.6-flash",), "p")
    assert translate.GEMINI_DUSUNME_BUTCESI is None
    assert kutu["config"].thinking_config is None


def test_dusunme_butcesi_ayarlanabilir(monkeypatch):
    """Tümden kapatmak ile açık bırakmak arasındaki ORTA YOL kapalı kalmasın:
    sınırlı bütçe (ör. 2048) ölçülmek istenirse tek sabit değişir."""
    monkeypatch.setattr(translate, "GEMINI_DUSUNME_BUTCESI", 2048)
    istemci, kutu = _config_yakala()
    translate._generate_with_fallback(_fabrika(istemci), ("gemini-3.6-flash",), "p")
    assert kutu["config"].thinking_config.thinking_budget == 2048
