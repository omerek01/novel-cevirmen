"""Yalnız-çeviri JSON biçiminde bozuk yanıt kurtarılırken kapanış ayracı sızmaz.

Roman bağlamı yolunda çıktı yalnız {"translation": "..."} taşır; eski kurtarma
çevirinin sonunu `detected_names` anahtarıyla buluyordu. Anahtar gelmeyince metin
sona kadar alındı ve JSON'un kapanışı (`"}`) son paragrafa yapıştı (deney: 961).
"""
from core import translate


def test_kacissiz_tirnakli_bozuk_json_kapanisi_sizdirmaz():
    yanit = '{"translation": "[[1]] Ona "dur" dedi.\n\n[[2]] Sonra gitti."\n}'
    sonuc = translate._parse_response(yanit)
    assert sonuc["translation"] == '[[1]] Ona "dur" dedi.\n\n[[2]] Sonra gitti.'


def test_kapanissiz_yarim_yanit_yine_kurtarilir():
    yanit = '{"translation": "[[1]] Ona "dur" dedi.\n\n[[2]] Sonra'
    assert translate._parse_response(yanit)["translation"] == '[[1]] Ona "dur" dedi.\n\n[[2]] Sonra'


def test_eski_bicimde_detected_names_siniri_korunur():
    yanit = '{"translation": "[[1]] Ona "dur" dedi.", "detected_names": ["Sunny"]}'
    sonuc = translate._parse_response(yanit)
    assert sonuc["translation"] == '[[1]] Ona "dur" dedi.'
