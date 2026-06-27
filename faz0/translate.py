"""İsim-koruyan İngilizce -> Türkçe çeviri.

Gemini + paragraf bazlı parçalama (chunk) + parçalar arası bağlam taşıma +
sözlük (glossary) ile tutarlı özel isim koruması.
"""
from __future__ import annotations

import json
import re

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_WORDS_PER_CHUNK = 1400

SYSTEM_INSTRUCTION = (
    "Sen profesyonel bir İngilizce'den Türkçe'ye web roman çevirmenisin.\n"
    "Kurallar:\n"
    "- Akıcı, doğal, edebi Türkçe üret. Birebir değil, anlamı koru.\n"
    "- KARAKTER (kişi) isimlerini ASLA çevirme; aynen koru. Diğer tüm kelimeleri "
    "(yer, beceri, sistem/dünya terimleri dahil) normal şekilde Türkçe'ye çevir.\n"
    "- SÖZLÜK'te verilen terimleri ne olursa olsun tam karşılığıyla AYNEN kullan.\n"
    "- ÖNCEKİ ÇEVİRİ verilirse onu TEKRAR çevirme; yalnızca devamlılık için kullan.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"translation": "...", "detected_names": ["..."]}\n'
    "- detected_names: SADECE metinde geçen KARAKTER (kişi) isimleri. "
    "Yer, beceri, eşya, sistem veya dünya terimlerini DAHİL ETME."
)


def translate_chapter(
    text: str,
    api_key: str,
    glossary: dict[str, str] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Tüm bölümü parçalayıp çevirir; bağlamı taşır, yeni isimleri biriktirir.

    Döner: {"translation": str, "detected_names": list[str], "chunk_count": int}
    """
    glossary = dict(glossary or {})
    client = genai.Client(api_key=api_key)
    chunks = _split_paragraphs(text)

    out_parts: list[str] = []
    new_names: set[str] = set()
    prev_tail = ""

    for chunk in chunks:
        result = _translate_chunk(client, model, chunk, glossary, prev_tail)
        out_parts.append(result["translation"])
        for name in result["detected_names"]:
            if name and name not in glossary:
                new_names.add(name)
        # Bir sonraki parçaya devamlılık için son cümleleri bağlam olarak taşı.
        prev_tail = _last_sentences(result["translation"], 2)

    return {
        "translation": "\n\n".join(out_parts),
        "detected_names": sorted(new_names),
        "chunk_count": len(chunks),
    }


def _split_paragraphs(text: str, max_words: int = MAX_WORDS_PER_CHUNK) -> list[str]:
    """Paragraf sınırlarında böl; cümle ortasından asla bölme."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        words = len(para.split())
        if current and current_words + words > max_words:
            chunks.append("\n\n".join(current))
            current, current_words = [para], words
        else:
            current.append(para)
            current_words += words

    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def _last_sentences(text: str, count: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    return " ".join(sentences[-count:]) if sentences else ""


def _translate_chunk(
    client: genai.Client,
    model: str,
    chunk: str,
    glossary: dict[str, str],
    prev_tail: str,
) -> dict:
    glossary_str = json.dumps(glossary, ensure_ascii=False) if glossary else "(boş)"
    user = (
        f"SÖZLÜK (aynen koru): {glossary_str}\n\n"
        f"ÖNCEKİ ÇEVİRİNİN SONU (sadece bağlam, tekrar çevirme): "
        f"{prev_tail or '(yok)'}\n\n"
        f"ÇEVRİLECEK METİN:\n{chunk}"
    )
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return _parse_response(response.text)


def _parse_response(raw: str | None) -> dict:
    if not raw:
        return {"translation": "", "detected_names": []}
    try:
        data = json.loads(raw)
        return {
            "translation": data.get("translation", ""),
            "detected_names": list(data.get("detected_names") or []),
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        # JSON bozuksa ham metni çeviri kabul et — içeriği kaybetme.
        return {"translation": raw.strip(), "detected_names": []}
