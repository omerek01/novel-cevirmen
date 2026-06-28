"""İsim-koruyan İngilizce -> Türkçe çeviri.

Gemini + paragraf bazlı parçalama (chunk) + parçalar arası bağlam taşıma +
sözlük (glossary) ile tutarlı özel isim koruması.

Dayanıklılık: her parça için model yedek zinciri denenir; bir model geçici
olarak meşgulse (429/500/503) üstel geri-çekilmeyle birkaç kez denenir, sonra
sıradaki modele düşülür.
"""
from __future__ import annotations

import json
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

# Yedek zinciri: ilki meşgul/kota-dolu ise sıradakine düşer.
# gemini-3.1-flash-lite günlük 500 istek (RPD); gemini-2.5-flash sadece 20.
DEFAULT_MODELS = ("gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-flash-lite")
# Parça çıktısı modelin token sınırını aşıp çeviriyi kesmesin diye ölçülü tutulur.
MAX_WORDS_PER_CHUNK = 1600
RETRY_CODES = {500, 503}  # geçici sunucu hatası: aynı modelde tekrar dene
FALLBACK_CODES = {404, 429}  # model yok / kota doldu: bekleme, sıradaki modele geç
MAX_RETRIES = 3

# İçerik güvenlik filtreleri (kategori başına) — gevşetilebilir kategorileri kapat.
# Web romanlarda şiddet/karanlık tema sık; varsayılan filtreler yanlış-pozitif engeller.
# NOT: PROHIBITED_CONTENT bununla AŞILAMAZ (ayrı, kapatılamayan filtre) → o durumda
# yanıt boş gelir ve sıradaki modele düşülür (bir model engellerken başkası çevirebilir).
SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_NONE"}
    for c in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]

SYSTEM_INSTRUCTION = (
    "Sen profesyonel bir İngilizce'den Türkçe'ye web roman çevirmenisin.\n"
    "Kurallar:\n"
    "- Akıcı, doğal, edebi Türkçe üret. Birebir değil, anlamı koru.\n"
    "- SADECE gerçek kişi/karakter adlarını İngilizce koru (örn. Sunny, Kim Dokja).\n"
    "- Büyü, beceri, sınıf, ırk, unvan, eşya, yer ve sistem/dünya terimlerini "
    "İngilizce BIRAKMA; Türkçe'ye çevir (Spell -> Büyü, Nightmare -> Kabus, "
    "Skill -> Beceri gibi). Bir kelimenin büyük harfle başlaması onu korumak "
    "için sebep DEĞİLDİR.\n"
    "- SÖZLÜK bir eşlemedir (kaynak -> karşılık): metinde KAYNAK terimi gördüğünde "
    "onu çevirme, tam olarak KARŞILIK ile yaz.\n"
    "- ÖNCEKİ ÇEVİRİ verilirse onu TEKRAR çevirme; yalnızca devamlılık için kullan.\n"
    "- METİN paragrafları [[n]] ile numaralıdır. Çeviride HER paragrafın başına AYNI "
    "[[n]] işaretini koy; hiçbir işareti ATLAMA, BİRLEŞTİRME veya sırasını DEĞİŞTİRME. "
    "Bir İngilizce paragraf bir Türkçe paragrafa karşılık gelir.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"translation": "[[1]] ...\\n\\n[[2]] ...", '
    '"detected_names": ["..."]}\n'
    "- detected_names: SADECE metinde geçen KARAKTER (kişi) isimleri. "
    "Yer, beceri, eşya, sistem veya dünya terimlerini DAHİL ETME."
)

# Paragraf hizalama işaretçisi: [[1]], [[ 2 ]] gibi. Çeviride korunur → her Türkçe
# paragrafı kaynak İngilizce paragrafıyla eşler (sayı tutmasa bile hizalama bozulmaz).
MARKER_RE = re.compile(r"\[\[\s*(\d+)\s*\]\]")


class TranslateError(Exception):
    """Çeviri kalıcı olarak başarısız olduğunda fırlatılır (model meşgul, kota vb.)."""


class _Retryable(Exception):
    """İç sinyal: bu modelde geçici hata tükendi; sıradaki modele geç."""


def translate_chapter(
    text: str,
    api_key: str,
    glossary: dict[str, str] | None = None,
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> dict:
    """Tüm bölümü parçalayıp çevirir; bağlamı taşır, yeni isimleri biriktirir.

    İşaretçi (``[[n]]``) ile paragraf-hizalı üretir: dönen ``translation`` ve ``source``
    AYNI ``\\n\\n`` paragraf sayısına sahiptir (i. Türkçe paragraf <-> i. İngilizce
    paragraf). Bir parçada hizalama tutmazsa o parça tek blok olur ve ``source`` None
    döner (çeviri yine de tam; iki-dilli o bölümde devre dışı).

    Döner: {"translation": str, "source": str|None, "detected_names": list[str],
            "chunk_count": int}
    """
    glossary = dict(glossary or {})
    client = genai.Client(api_key=api_key)
    chunks = _split_paragraphs(text)

    tr_paras: list[str] = []
    en_paras: list[str] = []
    new_names: set[str] = set()
    prev_tail = ""
    aligned = True

    for chunk in chunks:
        chunk_en = [p.strip() for p in chunk.split("\n\n") if p.strip()]
        result = _translate_chunk(client, models, chunk_en, glossary, prev_tail)
        for name in result["detected_names"]:
            if name and name not in glossary:
                new_names.add(name)
        chunk_tr = _split_by_markers(result["translation"], len(chunk_en))
        if chunk_tr is not None:
            tr_paras.extend(chunk_tr)
            en_paras.extend(chunk_en)
            prev_tail = _last_sentences("\n\n".join(chunk_tr[-2:]), 2)
        else:
            # Hizalama tutmadı: işaretleri temizleyip tek blok ekle, kaynağı bırak.
            clean = _strip_markers(result["translation"])
            tr_paras.append(clean)
            en_paras.append(chunk)
            aligned = False
            prev_tail = _last_sentences(clean, 2)

    return {
        "translation": "\n\n".join(tr_paras),
        "source": "\n\n".join(en_paras) if aligned else None,
        "detected_names": sorted(new_names),
        "chunk_count": len(chunks),
    }


def _split_by_markers(translation: str, n: int) -> list[str] | None:
    """``[[k]]`` işaretli çeviriyi paragraf listesine böler (1..n tam ve sıralıysa).

    Her segment, ``[[k]]`` ile bir sonraki işarete kadarki metin. 1..n işaretlerinin
    hepsi yoksa, bir paragraf boş kalırsa → None (çağıran hizalamasız akışa düşer).
    """
    if not translation:
        return None
    matches = list(MARKER_RE.finditer(translation))
    if not matches:
        return None
    parts: dict[int, str] = {}
    for i, m in enumerate(matches):
        k = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(translation)
        seg = translation[start:end].strip()
        parts[k] = (parts[k] + "\n\n" + seg).strip() if k in parts else seg
    if set(parts) != set(range(1, n + 1)):
        return None
    out = [parts[k] for k in range(1, n + 1)]
    return None if any(not s for s in out) else out


def _strip_markers(text: str) -> str:
    return MARKER_RE.sub("", text or "").strip()


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
    models: tuple[str, ...],
    en_paras: list[str],
    glossary: dict[str, str],
    prev_tail: str,
) -> dict:
    glossary_str = json.dumps(glossary, ensure_ascii=False) if glossary else "(boş)"
    numbered = "\n\n".join(f"[[{i + 1}]] {p}" for i, p in enumerate(en_paras))
    user = (
        f"SÖZLÜK (kaynak -> karşılık; kaynağı görünce karşılığını yaz): {glossary_str}\n\n"
        f"ÖNCEKİ ÇEVİRİNİN SONU (sadece bağlam, tekrar çevirme): "
        f"{prev_tail or '(yok)'}\n\n"
        f"ÇEVRİLECEK METİN (her paragraf [[n]] ile numaralı; işaretleri koru):\n{numbered}"
    )
    response = _generate_with_fallback(client, models, user)
    return _parse_response(response.text)


def _generate_with_fallback(client: genai.Client, models: tuple[str, ...], user: str):
    """Model yedek zincirini sırayla dener; hepsi başarısızsa TranslateError fırlatır."""
    last_exc: Exception | None = None
    blocked = False
    for model in models:
        try:
            return _generate_once_with_retry(client, model, user)
        except _Retryable as exc:
            last_exc = exc
            blocked = blocked or getattr(exc, "blocked", False)
            continue
    if blocked:
        raise TranslateError(
            "Bu bölümün içeriği hiçbir model tarafından çevrilemedi (içerik filtresi); "
            "metin engellenmiş olabilir."
        ) from last_exc
    raise TranslateError(
        "Tüm modeller şu anda meşgul (geçici). Biraz sonra tekrar deneyin."
    ) from last_exc


def _generate_once_with_retry(client: genai.Client, model: str, user: str):
    """Tek modelde üstel geri-çekilmeyle dener; geçici hata/engel tükenince _Retryable."""
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    temperature=0.3,
                    safety_settings=SAFETY_SETTINGS,
                ),
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code in FALLBACK_CODES:
                raise _Retryable() from exc  # kota/erişim yok -> sıradaki modele geç
            if code in RETRY_CODES:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise _Retryable() from exc
            raise TranslateError(f"Çeviri hatası: {exc}") from exc
        # Yanıt geldi ama boş/engellenmiş olabilir (finish_reason PROHIBITED_CONTENT/
        # SAFETY/RECITATION → HTTP 200, metin yok). Bu deterministiktir; aynı modelde
        # tekrar denemek beyhude → sıradaki modele düş (başka model çevirebilir).
        try:
            txt = response.text or ""
        except Exception:  # bazı engellenmiş yanıtlarda .text istisna fırlatır
            txt = ""
        if txt.strip():
            return response
        exc = _Retryable()
        exc.blocked = True
        raise exc


def _parse_response(raw: str | None) -> dict:
    if not raw:
        return {"translation": "", "detected_names": []}
    text = raw.strip()
    # Bazı modeller JSON'u ```json ... ``` çitiyle sarar; temizle.
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        return {
            "translation": data.get("translation", ""),
            "detected_names": list(data.get("detected_names") or []),
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        # JSON bozuk/yarım: ham basmak yerine 'translation' alanını ayıklamayı dene.
        return {"translation": _extract_translation(text), "detected_names": []}


def _extract_translation(text: str) -> str:
    """Bozuk/yarım JSON'dan çeviri metnini kurtar; olmazsa ham metni döndür."""
    match = re.search(
        r'"translation"\s*:\s*"(.*?)"\s*,\s*"detected_names"', text, re.DOTALL
    ) or re.search(r'"translation"\s*:\s*"(.*)$', text, re.DOTALL)
    if not match:
        return text
    captured = match.group(1)
    try:
        return json.loads('"' + captured + '"')  # \n, \" gibi kaçışları çöz
    except json.JSONDecodeError:
        return captured.replace("\\n", "\n").replace('\\"', '"').rstrip('"')
