"""`scripts/degerlendirme.py` — çevrimdışı: API çağrılmaz, önbelleğe yazılmaz."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core import cache, glossary

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "degerlendirme.py"
_spec = importlib.util.spec_from_file_location("degerlendirme", _YOL)
dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dg)

EN = "Kaan lit the lantern.\n\nThe Silver Tower rang twice.\n\nMira froze."
TR = "Kaan feneri yaktı.\n\nGümüş Kule iki kez çaldı.\n\nMira dondu kaldı."


def _bolum(slug, no, ceviri=TR, kaynak=EN, model="gemini-3.6-flash"):
    cache.save_chapter(f"https://x/{slug}/{no}", {
        "book_slug": slug, "book_title": slug, "title": f"C{no}", "chapter_no": no,
        "translation": ceviri, "source": kaynak, "next_url": None, "detected_names": [],
        "chunk_count": 1, "model": model,
    })


@pytest.fixture
def klasor(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "CIKTI_KOKU", tmp_path)
    monkeypatch.setattr(dg, "SET_DOSYASI", tmp_path / "set.json")
    return tmp_path


def test_olcum_terim_ve_cumle_duzeyini_ayri_verir_uzunluk_alarmdir():
    o = dg.olc(EN, TR, {"Silver Tower": "Gümüş Kule"}, {})
    assert o["hizali"] and o["paragraf"] == [3, 3] and o["sozluk_ihlali"] == []
    assert o["eksik_icerik_alarmi"] is False
    kisa = dg.olc(EN, "Kaan.\n\nSilver Tower.\n\nMira.", {"Silver Tower": "Gümüş Kule"}, {})
    assert kisa["sozluk_ihlali"] == ["Silver Tower"]
    assert kisa["eksik_icerik_alarmi"] is True
    assert kisa["kisa_paragraflar"]  # paragraf düzeyinde de yakalanır


def test_set_kitaplar_arasinda_dengeli_ve_deterministik():
    for n in range(1, 6):
        _bolum("a", n)
    for n in range(1, 3):
        _bolum("b", n)
    s1 = dg.set_sec(4, None)
    assert [x["book_slug"] for x in s1] == ["a", "b", "a", "b"]
    assert s1 == dg.set_sec(4, None)
    assert {x["chapter_no"] for x in s1 if x["book_slug"] == "a"} == {1, 5}


def test_kuru_kip_api_cagirmaz_onbellege_yazmaz(klasor, monkeypatch):
    _bolum("a", 1)
    glossary.set_term("a", "Silver Tower", "Gümüş Kule")
    monkeypatch.setattr(dg.translate, "translate_chapter",
                        lambda *a, **k: pytest.fail("kuru kip API çağırdı"))
    once = cache.get_chapter("https://x/a/1")
    assert dg.main(["--adet", "1"]) == 0
    assert cache.get_chapter("https://x/a/1") == once
    kosu = next(p for p in klasor.iterdir() if p.is_dir())
    assert (kosu / "taban" / "insan-degerlendirmesi.md").exists()


def test_calistir_ceviriyi_disarida_tutar_ve_ozet_insan_puanini_okur(klasor, monkeypatch):
    _bolum("a", 1)
    monkeypatch.setattr(dg.translate, "translate_chapter", lambda text, **k: {
        "translation": "Kaan feneri yaktı.\n\nGümüş Kule çaldı.\n\nMira dondu.",
        "model": "gemini-3.6-flash",
    })
    sonuclar = dg.calistir(dg.set_sec(1, None), "gemini-3.6-flash", taban=False, klasor=klasor / "k")
    assert sonuclar[0]["model"] == "gemini-3.6-flash"
    assert cache.get_chapter("https://x/a/1")["translation"] == TR  # önbellek değişmedi
    form = klasor / "k" / "insan-degerlendirmesi.md"
    form.write_text(
        form.read_text(encoding="utf-8")
        .replace("- Akıcılık (1-5): ", "- Akıcılık (1-5): 4")
        .replace("- Anlam doğruluğu (1-5): ", "- Anlam doğruluğu (1-5): 5"),
        encoding="utf-8",
    )
    [satir] = dg.ozet(klasor / "k")
    assert satir["akicilik"] == 4 and satir["anlam"] == 5 and satir["hizali"] is True


def test_ucretli_model_reddedilir(klasor, monkeypatch):
    _bolum("a", 1)
    monkeypatch.setattr(dg.translate, "translate_chapter",
                        lambda *a, **k: pytest.fail("ücretli modelle çağrı yapıldı"))
    assert dg.main(["--calistir", "--model", "claude-sonnet-5"]) == 2
    assert dg.main(["--calistir", "--model", "gpt-9"]) == 2
    monkeypatch.setattr(dg.translate, "secili_zincir", lambda: ("claude-haiku-4-5",))
    assert dg.main(["--calistir"]) == 2
