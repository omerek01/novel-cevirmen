"""Model `translation`ı paragraf DİZİSİ döndürünce (vertex 3.8, shadow-slave #950) JSON kuyruğu çeviriye sızmaz."""
from core import translate

GECERLI = '{"translation": ["[[1]] Bir.", "[[2]] İki."], "detected_names": ["Sunny"], "detected_terms": {"Echo": "Yankı"}}'
BOZUK = ('{"translation": [\n "[[1]] Bir \\"alıntı\\".",\n "[[2]] İki.\'"\n  ],\n  "detected_names": ["Sunny"],\n'
         '  "detected_terms": {"Sin of Solace": "Teselli Günahı"}\n}\n}')


def test_gecerli_dizi_birlestirilir():
    r = translate._parse_response(GECERLI)
    assert r["translation"] == "[[1]] Bir.\n\n[[2]] İki." and r["detected_terms"] == {"Echo": "Yankı"}


def test_bozuk_dizide_json_kuyrugu_ceviriye_sizmaz():
    r = translate._parse_response(BOZUK)
    assert "detected_terms" not in r["translation"] and "Teselli" not in r["translation"]
    assert r["translation"].startswith("[[1]] Bir") and "[[2]] İki." in r["translation"]
    assert r["detected_terms"] == {"Sin of Solace": "Teselli Günahı"} and r["detected_names"] == ["Sunny"]
