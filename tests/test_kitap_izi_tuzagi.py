"""Tel tuzağı: kitaba özel bilgi koda geri sızmasın (kitap profili Faz 1).

`app/core` içinde "shadow-slave" / "Sunny" / "Spell" geçen DAVRANIŞ kodu yakalanır: dize ve ad
belirteçleri taranır; yorumlar, belge dizeleri ve `KITAP_PROFILLERI` kaydı (profilin kod katmanı)
hariçtir. Kitaba özel bir kural profilin alanı olmalı (`varlik_grafigi.profil`).

`IZIN` bilinçli istisnalardır; sayı TAM eşleşmeli: azaldıysa sabiti düşür, artıyorsa yeni iz
profile taşınmalı.
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize
from collections import Counter

KOK = pathlib.Path(__file__).resolve().parent.parent / "app" / "core"
IZ = re.compile(r"shadow-slave|\bSunny\b|\bSpell\b")
IZIN = {
    # Çeviri istemi örnekleri: SS'te ölçülmeden bayt değişmez (plan Faz 1; çeviri kalitesi riski).
    "translate.py": 9,
    # Yalnız ölçüm yapan zamir işaretleyicisi: "kişi adı değil" listesi, akışa bağlı değil.
    "zamir_denetimi.py": 1,
}
_BELGE_DUGUMLERI = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _haric_satirlar(kaynak: str) -> set[int]:
    haric: set[int] = set()
    for d in ast.walk(ast.parse(kaynak)):
        if isinstance(d, _BELGE_DUGUMLERI) and d.body:
            b = d.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                haric.update(range(b.lineno, b.end_lineno + 1))
        hedefler = d.targets if isinstance(d, ast.Assign) else [d.target] if isinstance(d, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "KITAP_PROFILLERI" for t in hedefler):
            haric.update(range(d.lineno, d.end_lineno + 1))
    return haric


def _izler(kaynak: str) -> list[tuple[int, str]]:
    haric = _haric_satirlar(kaynak)
    turler = {tokenize.STRING, tokenize.NAME, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
    return [(t.start[0], m.group()) for t in tokenize.generate_tokens(io.StringIO(kaynak).readline)
            if t.type in turler and t.start[0] not in haric for m in IZ.finditer(t.string)]


def test_davranis_kodunda_kitaba_ozel_iz_yok():
    bulunan = Counter()
    yerler: dict[str, list] = {}
    for yol in sorted(KOK.glob("*.py")):
        izler = _izler(yol.read_text(encoding="utf-8"))
        if izler:
            bulunan[yol.name] = len(izler)
            yerler[yol.name] = izler
    assert dict(bulunan) == IZIN, yerler


def test_tuzak_yorumu_ve_profili_atlar_kodu_yakalar():
    kaynak = (
        '"""Sunny belge dizesi."""\n'
        "# Spell yorumu\n"
        'KITAP_PROFILLERI = {"shadow-slave": {"ana_karakter": "Sunny"}}\n'
        'def f():\n    """Spell."""\n    return "Sunny" in x\n'
    )
    assert _izler(kaynak) == [(6, "Sunny")]
