"""RET yanıtı: model çevirmek yerine serbest metinle "özet sunabilirim" der.

Ölçülen arıza (2026-09-28, sunucu verisi): `vertex/gemini-3.6-flash` iki bölümde
(shadow-slave #782, #787) çeviriyi REDDETTİ ve yerine birkaç cümlelik bir özet +
"bir sonraki bölümün özetini ister misiniz?" döndürdü. Yanıtta ne JSON vardı ne
[[n]] işaretçisi. Ret kalıcı DEĞİLDİ: aynı istek Vertex'e yeniden gönderilince
iki bölüm de düzgün çevrildi. Aynı dönemde AI Studio yolundan çevrilen ~700
bölümde tek bir ret yok.

Açık ayrıştırıcıdaydı: `_extract_translation` "translation" alanını bulamayınca
HAM metni çeviri diye döndürüyordu, zincir yalnız HTTP hatasında düştüğü için
ret 200 + dolu metin olarak başarı sayılıp önbelleğe yazılıyordu.

Kural (kullanıcı kararı): Vertex ATLANMAZ — ret alan model bir kez daha denenir;
yine reddederse YALNIZ o parça zincirin sıradaki halkasına iner.
"""
import pytest

from core import translate

RET = (
    "Bu metni birebir çevirmek yerine, bu bölümde gerçekleşen olayların kısa bir "
    "özetini sunabilirim:\n\nKarakterler bir yere gider ve konuşur.\n\n"
    "Bir sonraki bölümün özetini ister misiniz?"
)
CEVIRI_JSON = '{"translation": "[[1]] Birinci paragraf.\\n\\n[[2]] İkinci.", "detected_names": []}'


# ---------------------------------------------------------------- ayrıştırıcı

def test_ret_metni_GECERSIZ_sayilir():
    out = translate._parse_response(RET)
    assert out.get("gecersiz") is True
    assert out["translation"] == ""  # ret metni ASLA çeviri olarak taşınmaz


def test_gecerli_json_gecersiz_DEGIL():
    out = translate._parse_response(CEVIRI_JSON)
    assert not out.get("gecersiz")
    assert out["translation"].startswith("[[1]]")


def test_yarim_json_kurtarilir_gecersiz_DEGIL():
    """Kesilmiş JSON (max token) eskisi gibi kurtarılır — o bir ÇEVİRİDİR."""
    out = translate._parse_response('{"translation": "[[1]] Yarım kalan çevi')
    assert not out.get("gecersiz")
    assert out["translation"].startswith("[[1]]")


def test_isaretcili_duz_metin_gecersiz_DEGIL():
    """JSON'suz ama [[n]] işaretli yanıt meşru bir çeviridir (hizalanabilir);
    yalnız ne JSON ne işaretçi taşıyan yanıt ret sayılır."""
    out = translate._parse_response("[[1]] Birinci paragraf.\n\n[[2]] İkinci.")
    assert not out.get("gecersiz")
    assert "[[2]]" in out["translation"]


# ---------------------------------------------------------------- zincir

class _SahteUretici:
    """`_generate_with_fallback` yerine geçer; çağrılan zinciri kaydeder."""

    def __init__(self, *yanitlar):
        self.yanitlar = list(yanitlar)
        self.zincirler: list[tuple[str, ...]] = []

    def __call__(self, factory, models, user, *a, **k):
        self.zincirler.append(tuple(models))
        yanit = self.yanitlar.pop(0)
        if isinstance(yanit, Exception):
            raise yanit

        class _Y:
            text = yanit

        return _Y(), models[0]


ZINCIR = ("vertex/gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.5-flash")


def _parca(monkeypatch, sahte):
    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    return translate._translate_chunk(lambda: None, ZINCIR, ["P1", "P2"], {}, "")


def test_ret_once_AYNI_modelde_yeniden_denenir(monkeypatch):
    """Vertex ATLANMAZ: ret rastgeledir, ikinci deneme çoğunlukla tutar."""
    sahte = _SahteUretici(RET, CEVIRI_JSON)
    out = _parca(monkeypatch, sahte)
    assert sahte.zincirler[1] == ("vertex/gemini-3.6-flash",)
    assert out["model"] == "vertex/gemini-3.6-flash"
    assert out["translation"].startswith("[[1]]")
    assert not out.get("gecersiz")


def test_ikinci_ret_SIRADAKI_halkaya_iner(monkeypatch):
    sahte = _SahteUretici(RET, RET, CEVIRI_JSON)
    out = _parca(monkeypatch, sahte)
    assert sahte.zincirler[2] == ("gemini-3.6-flash",)
    assert out["model"] == "gemini-3.6-flash"  # künye fiilen çevireni yazar
    assert out["translation"].startswith("[[1]]")


def test_tekrarda_hata_alinirsa_da_zincir_devam_eder(monkeypatch):
    sahte = _SahteUretici(RET, translate.TranslateError("vertex 503"), CEVIRI_JSON)
    out = _parca(monkeypatch, sahte)
    assert out["model"] == "gemini-3.6-flash"


def test_hepsi_reddederse_ret_KAYDEDILMEZ_hata_verilir(monkeypatch):
    """Ret metnini ⚠ ile önbelleğe yazmak, bölümü SONSUZA DEK bozuk bırakırdı
    (önbellek isabeti yeniden çeviri tetiklemez). Hata ise tekrar denenebilir."""
    sahte = _SahteUretici(RET, RET, RET, RET)
    with pytest.raises(translate.TranslateError):
        _parca(monkeypatch, sahte)


def test_tek_halkali_zincir_baska_modele_INMEZ(monkeypatch):
    """Claude seçiliyken zincir tek halkadır; ret onarımı o kuralı delmemeli —
    ne ücretliden ücretsize ne tersine sessiz geçiş."""
    sahte = _SahteUretici(RET, RET)
    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    with pytest.raises(translate.TranslateError):
        translate._translate_chunk(lambda: None, ("claude-sonnet-5",), ["P1"], {}, "")
    assert sahte.zincirler == [("claude-sonnet-5",), ("claude-sonnet-5",)]


def test_gecerli_yanitta_fazladan_istek_YOK(monkeypatch):
    """Ücretli halkada her fazladan istek PARA."""
    sahte = _SahteUretici(CEVIRI_JSON)
    _parca(monkeypatch, sahte)
    assert len(sahte.zincirler) == 1
