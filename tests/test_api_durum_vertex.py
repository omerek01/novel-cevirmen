"""Vertex çağrıları ve RET yanıtları API durum kaydında (2026-09-29, kullanıcı isteği).

Vertex bir dönem kayda HİÇ girmiyordu: kayıt Gemini ANAHTAR x model tablosuydu ve
Vertex'in anahtarı yok, yazılsaydı anahtar #1'in satırına düşerdi. Bedeli: Vertex'in
ret/yoğunluk sıklığı hiçbir yerde görünmüyordu (#782/#787 retleri ancak arşiv
taranarak bulundu). Artık Vertex kendi kimliğiyle (`VERTEX_KIMLIGI`, sıra 0) yazılır
ve panelde AYRI bir kart olarak durur; Gemini kartlarına ve toplamlarına karışmaz.

RET ayrı bir sonuç sınıfıdır: HTTP düzeyinde başarılı (200 + dolu metin) ama içerik
çeviri değil. Kayıt önce başarı olarak düşer, ret anlaşılınca AYNI kayıt düzeltilir.
"""
import pytest

from core import api_durum, translate

VERTEX = "vertex/gemini-3.6-flash"


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch):
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    translate._VERTEX_ISTEMCI.clear()
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    yield
    translate._VERTEX_ISTEMCI.clear()


class _Meta:
    prompt_token_count = 5000
    candidates_token_count = 4000
    thoughts_token_count = 3000


class _Yanit:
    usage_metadata = _Meta()

    def __init__(self, text='{"translation": "[[1]] tamam"}'):
        self.text = text


class _APIHatasi(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def _sahte_istemci(monkeypatch, *sonuclar):
    sira = list(sonuclar)

    class _Modeller:
        def generate_content(self, **kw):
            sonuc = sira.pop(0) if len(sira) > 1 else sira[0]
            if isinstance(sonuc, Exception):
                raise sonuc
            return sonuc

    class _Istemci:
        def __init__(self, **kw):
            self.models = _Modeller()

    monkeypatch.setattr(translate.genai, "Client", _Istemci)
    monkeypatch.setattr(translate.genai_errors, "APIError", _APIHatasi)


def _fabrika(indeks=0):
    raise AssertionError("Vertex halkası Gemini anahtar havuzuna dokunmamalı")


_fabrika.anahtar_sayisi = 1


def _sayac(model=VERTEX, kimlik=api_durum.VERTEX_KIMLIGI):
    for s in api_durum.gunluk_sayaclar():
        if s["anahtar"] == kimlik and s["model"] == model:
            return s
    return None


def _son(model=VERTEX, kimlik=api_durum.VERTEX_KIMLIGI):
    for d in api_durum.son_durumlar():
        if d["anahtar"] == kimlik and d["model"] == model:
            return d
    return None


# ---------------------------------------------------------------- kayıt

def test_vertex_basarisi_KENDI_kimligiyle_kaydedilir(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _Yanit())
    translate._generate_with_fallback(_fabrika, (VERTEX,), "p")
    s = _sayac()
    assert s and s["deneme"] == 1 and s["basari"] == 1
    assert s["giris_token"] == 5000 and s["cikis_token"] == 7000  # düşünme dahil
    d = _son()
    assert d["sira"] == 0  # Gemini "Anahtar N" sıralarıyla ÇAKIŞMAZ
    # Gemini anahtar satırlarına hiçbir şey düşmedi.
    assert all(x["anahtar"] == api_durum.VERTEX_KIMLIGI for x in api_durum.gunluk_sayaclar())


@pytest.mark.parametrize("kod", [429, 500, 503])
def test_vertex_yogunlugu_GERCEK_http_koduyla_kaydedilir(monkeypatch, kod):
    """429 içeride 503'e çevriliyor (Gemini havuzunu soğutmasın diye); panel ise
    Google'ın FİİLEN döndürdüğü kodu göstermeli."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(kod))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika, (VERTEX,), "p")
    d = _son()
    assert d["sonuc"] == api_durum.GECICI
    assert d["http_kodu"] == kod
    assert _sayac()["hata"] >= 1


def test_vertex_izin_hatasi_kaydedilir(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(403))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika, (VERTEX,), "p")
    d = _son()
    assert d["sonuc"] == api_durum.ANAHTAR and d["http_kodu"] == 403


def test_proje_yoksa_KAYIT_YOK(monkeypatch):
    """Anahtarsızlık bir çağrı değildir (Gemini yolundaki kuralın aynısı)."""
    _sahte_istemci(monkeypatch, AssertionError("istek atılmamalı"))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika, (VERTEX,), "p")
    assert api_durum.gunluk_sayaclar() == []


def test_vertex_kaydi_sogumaya_DONUSMEZ(monkeypatch):
    """Vertex kaydı yeniden başlatmada bir Gemini anahtarına soğuma olarak geri
    yüklenmemeli: kota soğuması yalnız Gemini havuzunda yazılır."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(429))
    with pytest.raises(translate.TranslateError):
        translate._generate_with_fallback(_fabrika, (VERTEX,), "p")
    assert api_durum.aktif_sogumalar() == []


# ---------------------------------------------------------------- panel

def test_panelde_vertex_AYRI_kart_toplamlara_karismaz():
    api_durum.istek_kaydet("k1", 1, "gemini-3.6-flash", api_durum.BASARI, 200)
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.BASARI, 200)
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.GECICI, 429)
    v = api_durum.panel_verisi(["k1"], ("gemini-3.6-flash",), {}, vertex_modelleri=[VERTEX])
    assert [k["etiket"] for k in v["anahtarlar"]][0] == "Anahtar 1"
    vertex = v["vertex"]
    assert vertex["modeller"][0]["model"] == VERTEX
    assert vertex["modeller"][0]["bugun"]["deneme"] == 2
    assert vertex["modeller"][0]["http_kodu"] == 429
    # Gemini günlük toplamı yalnız Gemini havuzunu sayar.
    assert v["bugun_toplam"]["deneme"] == 1
    assert v["anahtar_sayisi"] == 1


def test_vertex_kurulu_degilse_kart_yok():
    v = api_durum.panel_verisi(["k1"], ("gemini-3.6-flash",), {})
    assert v["vertex"] is None


def test_olay_listesinde_vertex_adiyla_gorunur():
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.GECICI, 503)
    olaylar = api_durum.olaylari_disa_ver(api_durum.son_olaylar(5), ["k1"])
    assert olaylar[0]["anahtar"] == "Vertex"  # "Çıkarılmış anahtar" DEĞİL


def test_gecis_ozeti_vertexte_anahtar_saymaz():
    ozet = api_durum.gecis_ozeti(
        VERTEX, "gemini-3.6-flash",
        [{"model": VERTEX, "sira": 0, "sonuc": api_durum.GECICI, "kod": 503}],
    )
    assert "anahtarda" not in ozet.split(":", 1)[1]
    assert "geçici hata" in ozet


# ---------------------------------------------------------------- ret

def test_ret_basari_kaydini_DUZELTIR():
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.BASARI, 200)
    onceki = _son()["son_basari"]
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.BASARI, 200)
    deneme = api_durum.ret_kaydet(VERTEX)
    s = _sayac()
    assert (s["deneme"], s["basari"], s["hata"], s["ret"]) == (2, 1, 1, 1)
    d = _son()
    assert d["sonuc"] == api_durum.RET
    assert d["son_basari"] == onceki  # ret "son başarı" sayılmaz
    assert api_durum.son_olaylar(1)[0]["sonuc"] == api_durum.RET
    assert deneme == {"model": VERTEX, "sira": 0, "sonuc": api_durum.RET, "kod": 200}


def test_ret_kaydi_BASKA_modelin_basarisini_duzeltmez():
    api_durum.istek_kaydet("k1", 1, "gemini-3.6-flash", api_durum.BASARI, 200)
    api_durum.ret_kaydet(VERTEX)
    s = _sayac("gemini-3.6-flash", "k1")
    assert (s["basari"], s["hata"], s["ret"]) == (1, 0, 0)


def test_panel_karti_ret_durumunu_gosterir():
    api_durum.istek_kaydet(api_durum.VERTEX_KIMLIGI, 0, VERTEX, api_durum.BASARI, 200)
    api_durum.ret_kaydet(VERTEX)
    v = api_durum.panel_verisi([], (), {}, vertex_modelleri=[VERTEX])
    m = v["vertex"]["modeller"][0]
    assert m["durum"] == api_durum.RET
    assert m["bugun"]["ret"] == 1


RET_METNI = "Bu metni birebir çevirmek yerine kısa bir özetini sunabilirim."


def test_ceviri_yolunda_ret_kaydedilir_ve_gecis_yazilir(monkeypatch):
    """Vertex iki kez reddedip ücretsiz halkaya inilince: iki ret kaydı + "neden
    bu model?" için bir geçiş olayı."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _Yanit(RET_METNI), _Yanit(RET_METNI))

    class _Gemini:
        class models:
            @staticmethod
            def generate_content(**kw):
                return _Yanit()

    def fabrika(indeks=0):
        return _Gemini()

    fabrika.anahtar_sayisi = 1
    fabrika.anahtar_kimlikleri = ["k1"]
    out = translate._translate_chunk(fabrika, (VERTEX, "gemini-3.6-flash"), ["P1"], {}, "")
    assert out["model"] == "gemini-3.6-flash"
    assert _sayac()["ret"] == 2
    gecis = api_durum.son_olaylar(10, turler=("gecis",))
    assert len(gecis) == 1
    assert gecis[0]["hedef"] == "gemini-3.6-flash"
    assert "ret" in gecis[0]["ayrinti"]["ozet"]
