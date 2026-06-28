"""translate: bozuk/yarım JSON kurtarma + paragraf parçalama (saf fonksiyonlar)."""
from core import translate


def test_parse_clean_json():
    out = translate._parse_response('{"translation": "Merhaba", "detected_names": ["Kim"]}')
    assert out["translation"] == "Merhaba"
    assert out["detected_names"] == ["Kim"]


def test_parse_fenced_json():
    raw = '```json\n{"translation": "Selam", "detected_names": []}\n```'
    out = translate._parse_response(raw)
    assert out["translation"] == "Selam"
    assert out["detected_names"] == []


def test_parse_empty_returns_blank():
    out = translate._parse_response("")
    assert out == {"translation": "", "detected_names": []}


def test_parse_broken_json_recovers_translation():
    # detected_names'ten önce kesilmiş, kapanmamış JSON
    raw = '{"translation": "Yarım kalan çeviri metni", "detected_names'
    out = translate._parse_response(raw)
    assert "Yarım kalan çeviri" in out["translation"]
    assert out["detected_names"] == []


def test_parse_broken_json_with_escapes():
    raw = '{"translation": "Satır1\\nSatır2 \\"alıntı\\"", "detected_names'
    out = translate._parse_response(raw)
    assert "Satır1\nSatır2" in out["translation"]
    assert '"alıntı"' in out["translation"]


def test_extract_translation_falls_back_to_raw():
    # 'translation' alanı hiç yoksa ham metni döndürür
    assert translate._extract_translation("düz metin") == "düz metin"


def test_split_paragraphs_respects_max_words():
    paras = [" ".join(["kelime"] * 100) for _ in range(5)]
    text = "\n\n".join(paras)
    chunks = translate._split_paragraphs(text, max_words=250)
    assert len(chunks) >= 2
    # hiçbir parça paragraf ortasından bölünmemiş (her parça tam paragraflardan)
    for c in chunks:
        assert c.strip()


def test_split_paragraphs_single_when_small():
    assert translate._split_paragraphs("kısa metin") == ["kısa metin"]


def test_last_sentences():
    out = translate._last_sentences("Bir. İki. Üç.", 2)
    assert out == "İki. Üç."


# ---------- engellenmiş (boş) yanıt → sıradaki modele düşme ----------
class _FakeResp:
    def __init__(self, text):
        self._t = text

    @property
    def text(self):
        return self._t


class _FakeModels:
    def __init__(self, by_model):
        self.by_model = by_model
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        return _FakeResp(self.by_model[model])


class _FakeClient:
    def __init__(self, by_model):
        self.models = _FakeModels(by_model)


def test_fallback_on_blocked_empty_response():
    # m1 boş/engellenmiş döner (PROHIBITED_CONTENT gibi) → m2'ye düşülür.
    client = _FakeClient({"m1": "", "m2": '{"translation":"Çeviri","detected_names":[]}'})
    resp = translate._generate_with_fallback(client, ("m1", "m2"), "user")
    assert "Çeviri" in resp.text
    assert client.models.calls == ["m1", "m2"]  # m1 denendi, m2'ye geçildi


def test_all_blocked_raises_content_filter_error():
    import pytest

    client = _FakeClient({"m1": "", "m2": "   "})  # ikisi de boş/whitespace
    with pytest.raises(translate.TranslateError, match="içerik filtresi"):
        translate._generate_with_fallback(client, ("m1", "m2"), "user")
