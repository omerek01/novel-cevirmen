"""Terim alanı onarımı: model yanıtta ad/terim alanlarını hiç yazmazsa parça bir kez daha denenir.

Gerçek vaka (2026-10-17, vertex/gemini-3.8-flash, shadow-slave #1021): yanıt yalnız
`translation` taşıdı, `detected_names`/`detected_terms` alanları HİÇ yoktu. Ayrıştırma
eksik alanı boş sayıyordu; bölümde öldürülen Dehşet'in adı (Sybil of the Fallen Grace)
sessizce sözlüğe hiç önerilmedi. "Alan var ama boş" (bölümde yeni ad yok) meşrudur,
"alan yok" ise modelin talimatı atladığıdır."""
from core import translate


class _Sahte:
    """Her çağrıda sıradaki yanıtı döner; `None` terim = alanlar eksik yanıt."""

    def __init__(self, *ciktilar):
        self.ciktilar = list(ciktilar)
        self.cagri = 0

    def __call__(self, *a, **k):
        self.cagri += 1
        cikti = self.ciktilar.pop(0) if self.ciktilar else ("", None)
        if isinstance(cikti, Exception):
            raise cikti
        metin, terimler = cikti
        out = {"translation": metin, "detected_names": [], "detected_terms": terimler or {},
               "model": f"sahte-{self.cagri}"}
        if terimler is None:
            out["alan_eksik"] = True
        return out


KAYNAK = "\n\n".join(f"P{i} Sybil of the Fallen Grace " + "x" * 300 for i in range(3))
TERIM = {"Sybil of the Fallen Grace": "Düşmüş Lütuf Kâhini"}


def _hizali(oran=1.0):
    # Türkçe metin: kaynağı aynen döndürmek İngilizce kalıntı onarımını tetikler
    # ve çağrı sayıları bu testin ölçtüğü şeyden kopar.
    tr = [f"P{i} Düşmüş Lütuf Kâhini " + "x" * 300 for i in range(3)]
    return "\n\n".join(f"[[{i + 1}]] " + p[: max(1, int(len(p) * oran))]
                       for i, p in enumerate(tr))


def _cevir(monkeypatch, sahte, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])
    return translate.translate_chapter(KAYNAK, "anahtar", models=("m",))


# --- ayrıştırma -----------------------------------------------------------------

def test_yalniz_ceviri_tasiyan_yanit_alan_eksik_isaretlenir():
    out = translate._parse_response('{"translation": "[[1]] Merhaba"}')
    assert out["alan_eksik"] is True
    assert out["detected_terms"] == {}


def test_bos_ama_var_olan_alanlar_isaretlenmez():
    out = translate._parse_response(
        '{"translation": "[[1]] Merhaba", "detected_names": [], "detected_terms": {}}')
    assert not out.get("alan_eksik")


def test_tek_alan_yeterlidir():
    out = translate._parse_response('{"translation": "[[1]] Merhaba", "detected_names": []}')
    assert not out.get("alan_eksik")


def test_eski_sema_alani_isaretlenmez():
    out = translate._parse_response(
        '{"translation": "[[1]] Merhaba", "detected_places": {"Ariel": "Ariel"}}')
    assert not out.get("alan_eksik")


def test_bozuk_json_kurtarmasinda_alan_yoksa_isaretlenir():
    out = translate._parse_response('{"translation": "[[1]] Merhaba')
    assert out["alan_eksik"] is True


def test_ret_yaniti_alan_eksik_sayilmaz():
    # Ret ayrı yolla (gecersiz) işlenir; iki onarım üst üste binmemeli.
    out = translate._parse_response("Bunu çeviremem, özetini sunabilirim.")
    assert out.get("gecersiz") and not out.get("alan_eksik")


# --- bölüm akışı -----------------------------------------------------------------

def test_alanlari_eksik_parca_yeniden_denenir_ve_terim_kurtulur(monkeypatch):
    sahte = _Sahte((_hizali(), None), (_hizali(), TERIM))
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 2
    assert sonuc["detected_terms"] == TERIM
    assert sonuc["terim_alani_eksik"] == 0


def test_alanlari_tam_parcada_onarim_tetiklenmez(monkeypatch):
    sahte = _Sahte((_hizali(), {}))
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 1
    assert sonuc["terim_alani_eksik"] == 0


def test_yeniden_deneme_de_eksikse_ilk_ceviri_kalir_ve_sayilir(monkeypatch):
    sahte = _Sahte((_hizali(), None), (_hizali(), None))
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 2
    assert sonuc["model"] == "sahte-1"
    assert sonuc["terim_alani_eksik"] == 1


def test_kisalmis_yeniden_deneme_alinmaz(monkeypatch):
    sahte = _Sahte((_hizali(), None), (_hizali(0.3), TERIM))
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 2
    assert sonuc["model"] == "sahte-1"
    assert sonuc["detected_terms"] == {}
    assert sonuc["terim_alani_eksik"] == 1


def test_hizasiz_yeniden_deneme_hizali_ilkin_yerine_gecmez(monkeypatch):
    hizasiz = "\n\n".join(KAYNAK.split("\n\n"))
    sahte = _Sahte((_hizali(), None), (hizasiz, TERIM))
    sonuc = _cevir(monkeypatch, sahte, CEVIRI_HIZALAMA_ONARIM="0")
    assert sahte.cagri == 2
    assert sonuc["source"] is not None  # ilk (hizalı) hâl kaldı
    assert sonuc["terim_alani_eksik"] == 1


def test_yeniden_deneme_hatasi_ilk_ceviriyi_kaybettirmez(monkeypatch):
    sahte = _Sahte((_hizali(), None), RuntimeError("503"))
    sonuc = _cevir(monkeypatch, sahte)
    assert sonuc["translation"] and sonuc["model"] == "sahte-1"
    assert sonuc["terim_alani_eksik"] == 1


def test_bayrakla_kapatilir(monkeypatch):
    sahte = _Sahte((_hizali(), None), (_hizali(), TERIM))
    sonuc = _cevir(monkeypatch, sahte, CEVIRI_TERIM_ALANI_ONARIM="0")
    assert sahte.cagri == 1
    assert sonuc["terim_alani_eksik"] == 1


# --- analiz yolu -----------------------------------------------------------------

def test_analiz_yolunda_alan_istenmedigi_icin_isaret_dusurulur(monkeypatch):
    # CEVIRI_ANALIZ yolunda çıktı talimatı terim listesini YASAKLAR; terimler
    # analizden gelir. Orada eksik alan kusur değildir, yeniden deneme tetiklenmemeli.
    class _Yanit:
        text = '{"translation": "[[1]] Merhaba"}'

    monkeypatch.setattr(translate, "_izli_uret", lambda *a, **k: (_Yanit(), "m"))
    jeton = translate._ROMAN_URETIM.set("ROMAN BAĞLAMI")
    try:
        out = translate._translate_chunk(lambda: None, ("m",), ["Hello"], {}, "")
    finally:
        translate._ROMAN_URETIM.reset(jeton)
    assert not out.get("alan_eksik")


def test_normal_yolda_isaret_korunur(monkeypatch):
    class _Yanit:
        text = '{"translation": "[[1]] Merhaba"}'

    monkeypatch.setattr(translate, "_izli_uret", lambda *a, **k: (_Yanit(), "m"))
    out = translate._translate_chunk(lambda: None, ("m",), ["Hello"], {}, "")
    assert out["alan_eksik"] is True
