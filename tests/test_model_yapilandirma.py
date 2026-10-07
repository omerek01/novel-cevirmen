"""Model yapılandırması açık ve görünür (Faz 1I) — davranış DEĞİŞMEDİ."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from core import translate


def test_zincir_birincil_ve_yedeklerden_turer_davranis_ayni():
    assert translate.DEFAULT_MODELS == (translate.PRIMARY_TRANSLATION_MODEL, *translate.FALLBACK_TRANSLATION_MODELS)
    # Varsayılan DEĞİŞMEDİ (değiştirmek ayrı, ölçülmüş bir karar).
    assert translate.DEFAULT_MODELS == ("gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "z-ai/glm-5.3")
    assert translate.VARSAYILAN_MODEL == translate.PRIMARY_TRANSLATION_MODEL
    # Ücretli model zincire sızmaz.
    assert not any(translate._ucretli_modeli(m) for m in translate.DEFAULT_MODELS)


def test_ayar_ucu_yapilandirmayi_gosterir():
    with TestClient(server.app) as c:
        veri = c.get("/api/settings/model").json()
    y = veri["yapilandirma"]
    assert y["birincil"] == translate.PRIMARY_TRANSLATION_MODEL
    assert y["yedekler"] == list(translate.FALLBACK_TRANSLATION_MODELS)
    assert y["etkin_zincir"][0] in (veri["secili"], translate.PRIMARY_TRANSLATION_MODEL)
