"""Zamir belirsizliği işaretleyicisi — Türkçenin cinsiyetsiz "o"su (2026-10-16, Faz A7).

Saf modül, API çağırmaz, YALNIZ İŞARETLER. İngilizce he/she ayrımı Türkçede tek "o"ya
iner; paragrafta bir erkek ve bir kadın birlikte eylemdeyken çeviri adları zamire
indirirse kimin ne yaptığı kaybolur (literatürde bilinen bilgi kaybı; kör nokta K9).
Hiçbir denetim buna bakmıyordu.

Ölçüt bilerek DAR ve işaret düzeyinde:
* Kaynakta HEM eril (he/him/his/himself) HEM dişil (she/her/hers/herself) zamir var,
* kaynaktaki iki ad (büyük harfli, cümle ortası) en az ikisi ve
* çeviride bu adlardan en fazla biri geçiyor, buna karşın Türkçe 3. tekil zamir
  ("o, onu, ona, onun, ondan, onda, onunla") en az iki kez var.
Model düzeltmesi YOK: yanlış deterministik karar talimata/metne girerse zarar verir
(Saint A/B dersi). Önce ölçülür; onarım ancak elle isabet kabul edilebilirse yazılır.
"""
from __future__ import annotations

import re

_ERIL = re.compile(r"\b(?:he|him|his|himself)\b", re.IGNORECASE)
_DISIL = re.compile(r"\b(?:she|her|hers|herself)\b", re.IGNORECASE)
_TR_O = re.compile(r"(?<!\w)(?:o|onu|ona|onun|ondan|onda|onunla|kendisi\w*)(?!\w)", re.IGNORECASE)
_AD = re.compile(r"(?<=[a-z,;] )[A-Z][a-z]{2,}(?:'s)?")
# Cümle ortasında büyük harfle gelen ama kişi adı olmayan sık sözcükler.
_AD_DEGIL = frozenset("I Mr Mrs Ms Lord Lady Sir God Gods Spell Nightmare".split())


def _adlar(en: str) -> set[str]:
    out = set()
    for m in _AD.finditer(en):
        ad = m.group(0).removesuffix("'s")
        if ad not in _AD_DEGIL:
            out.add(ad)
    return out


def belirsiz_mi(en: str, tr: str) -> bool:
    """Paragrafta he/she ayrımı Türkçede kayboldu mu (işaret)."""
    if not (_ERIL.search(en) and _DISIL.search(en)):
        return False
    adlar = _adlar(en)
    if len(adlar) < 2:
        return False
    tr_kucuk = tr.lower()
    gecen = sum(1 for a in adlar if a.lower() in tr_kucuk)
    return gecen <= 1 and len(_TR_O.findall(tr)) >= 2


def paragraf_isaretleri(tr_paras: list[str], en_paras: list[str]) -> list[int]:
    """Belirsizleşen paragrafların indeksleri. Hizasızsa ölçülmez ([])."""
    if not tr_paras or len(tr_paras) != len(en_paras):
        return []
    return [i for i, (tr, en) in enumerate(zip(tr_paras, en_paras)) if belirsiz_mi(en, tr)]
