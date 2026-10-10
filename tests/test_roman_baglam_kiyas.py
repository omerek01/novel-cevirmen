"""Karşılaştırmada kaynak/model/sözlük sabit kalır; API açık seçenektir."""
import pytest


def test_kiyas_snapshot_ayni_model_ve_veriyi_kullanir():
    from roman_baglam_kiyas import hazirla
    x = {"source": "Source.", "glossary": {"A": "B"}, "conditions": {},
         "book_slug": "kitap", "chapter_no": 1, "url": "test://1"}
    p = hazirla([x], "vertex/gemini-3.6-flash")
    assert len(p) == 2
    assert p[0]["snapshot_sha256"] == p[1]["snapshot_sha256"]
    assert p[0]["model"] == p[1]["model"]
    assert {a["analiz"] for a in p} == {False, True}
    x["glossary"]["A"] = "C"
    assert hazirla([x], "vertex/gemini-3.6-flash")[0]["snapshot_sha256"] != p[0]["snapshot_sha256"]


def test_kiyas_model_yedegi_sessizce_kullanmaz():
    from roman_baglam_kiyas import hazirla
    with pytest.raises(ValueError):
        hazirla([], "vertex/gemini-3.6-flash + gemini-3.5-flash")
