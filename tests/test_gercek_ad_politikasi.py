"""Gerçek Ad (True Name) politikası (2026-10-15, kullanıcı kararı: "gerçek adlar Türkçe yazılacak").

Büyü'nün verdiği anlamlı ad (Lost from Light, Changing Star) kişiyi adlandırsa da İngilizce
kalmaz; kişinin kendi adı (Sunny, Nephis) kalır. Üç istem de aynı kuralı taşımalı: çeviri,
okurken terim önerisi ve sözlük sınıflaması — biri ayrışırsa aynı kitapta iki politika oluşur."""
from __future__ import annotations

from core import translate


def test_uc_istem_gercek_ad_kuralini_tasir():
    for istem in (translate.SYSTEM_INSTRUCTION, translate.SUGGEST_INSTRUCTION, translate.CLASSIFY_INSTRUCTION):
        assert translate.GERCEK_AD_KURALI in istem
    assert "Işıktan Mahrum" in translate.GERCEK_AD_KURALI


def test_kisi_adi_kurali_gercek_ad_sozcugunu_kendi_ad_icin_kullanmaz():
    # "gerçek adlar (Sunny…)" ifadesi True Name ile karışıyordu: kişinin KENDİ adı denir.
    for istem in (translate.SYSTEM_INSTRUCTION, translate.SUGGEST_INSTRUCTION, translate.CLASSIFY_INSTRUCTION):
        assert "gerçek adlar (Sunny" not in istem and "Gerçek ad da (Sunny)" not in istem
    # Ad tespiti paragrafı Gerçek Adı kişi adı listesinden dışlar. Kuralın kendisi `detected_terms`
    # demez: analiz ayrı kipte o paragraf çeviri isteminden çıkarılır, kural kalır.
    assert "GERÇEK AD da detected_names'e girmez" in translate.SYSTEM_INSTRUCTION
    assert "detected_terms" not in translate.GERCEK_AD_KURALI
