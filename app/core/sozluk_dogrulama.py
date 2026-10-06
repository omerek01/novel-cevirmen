"""Sözlük kayıtlarının MODEL doğrulaması (aday -> kural yaşam döngüsünün denetimi).

Neden var (2026-10-06, `SOZLUK-SISTEMI-ARASTIRMA.md` katman 3): model bir terimi
ilk gördüğü bölümde, dar bağlamla adlandırıyor ve karşılık doğrulanmadan KURAL
olarak kalıcılaşıyordu. Deterministik kapı (`sozluk_kapi`) biçim, sayı, çakışma
ve varyantı yakalar; ANLAMI yakalayamaz. Ölçülen vakalar: `God of Death ->
Savaş Tanrısı`, `Corruption -> Yolsuzluk` (Ascension/Corruption yolu),
`Flame of Divinity -> İlahiyat Alevi` (ilahiyat = teoloji), `Evertwine ->
Altın ip` (adın çevirisi değil, eşyanın tarifi).

Yöntem iki çalışmadan:
  * TransAgents'ın "çıkarma ajanı": sıradan sözcükleri (`Seven`, `Lost`) terim
    listesinden eler — burada `genel_sozcuk` alanı.
  * LLM-BT (geri çeviri): Türkçe karşılık bağlamsız İngilizceye geri çevrilir
    (`Savaş Tanrısı` -> "God of War"). Geri çeviri inceleme notunda BİLGİ olarak
    gösterilir; tek başına karar VERMEZ — ölçüm aşağıda.

ÖLÇÜM (2026-10-06, sunucu kopyası, 20 bilinen hatalı + 20 bilinen doğru kayıt,
`gemini-3.6-flash`): model hatalıların 13'üne kendisi "uygun değil", 2'sine
(`Seven`, `Lost`) "sıradan sözcük" dedi — 15/20; doğrulardan HİÇBİRİNİ reddetmedi
(0/20). Geri çeviri örtüşmesine dayalı ek kural (Jaccard < 0.5) hatalılarda modelin
zaten yakaladıkları DIŞINDA hiçbir şey yakalamadı, doğruların 4'ünü sahte reddetti
(eş anlamlılar: chitin/shell, Barrow/Mound, Aspect/Appearance, Beast/Creature).
Kural bu yüzden KALDIRILDI. Modelin kaçırdıkları (`Flame of Divinity -> İlahiyat
Alevi`, `Transcended Echo -> Yüce Yankı`, `Winter Beast -> Kış Canavarı`,
`Changing Star`) ya kapının/kalıp denetiminin ya da kategori politikasının işi.

Kurallar:
  * YALNIZ ücretsiz zincir (`translate.DEFAULT_MODELS`). Kullanıcının çeviri için
    seçtiği model (Claude, Vertex) burada KULLANILMAZ: arka planda koşan bir
    bakım işinin sessizce para harcaması, bu projede bir kez ödenmiş derstir
    (OpenRouter `:free`). `tests/test_sozluk_dogrulama.py` tel tuzağıyla tutar.
  * Sonuç kaydı DEĞİŞTİRMEZ: sorunlu kayıt incelemeye düşer, öneri onaya sunulur
    (sözlük kullanıcınındır). Tanım ve tür YALNIZ boşsa yazılır.
  * Arka plan doğrulaması `SOZLUK_DOGRULAMA=0` ile kapanır.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from . import api_durum, cache, glossary, library, sozluk_kapi
from . import translate

PARTI = 25  # tek çağrıdaki kayıt sayısı: çıktı ~25 x 120 token, tek istekte rahat
ARKA_PLAN_BEKLEME_SN = 300.0  # toplu çeviride her bölüm yeni aday getirir: biriktir

DOGRULAMA_INSTRUCTION = (
    "Sen İngilizce→Türkçe web roman çevirisinde terim denetçisisin. Sana bir kitabın "
    "SÖZLÜĞÜNDEN kayıtlar verilecek: İngilizce kaynak, kayıtlı Türkçe karşılık ve "
    "geçtiği cümle. Her kayıt için şunları yap:\n"
    "1. tur: kaydın türü — kisi (kişi adı ya da lakabı), yer, orgut (klan, lonca, "
    "hanedan, ordu), rutbe (güç/rütbe/sınıf basamağı), yetenek (beceri, büyü, nitelik), "
    "nesne (eşya, silah, Anı/Memory), diger.\n"
    "2. tanim: kavramın bu kitapta NE olduğunu anlatan tek kısa Türkçe cümle (en çok "
    "15 sözcük). Bağlamdan çıkar; emin değilsen genel tanımı yaz.\n"
    "3. geri_ceviri: Türkçe karşılığı, kaynağı GÖRMEDEN İngilizceye nasıl çevirirdin? "
    "Kaynağı kopyalama; yalnız Türkçe metne bak.\n"
    "4. uygun: karşılık kaynağın ANLAMINI doğru veriyor mu (true/false). Yanlış anlam "
    "(God of Death -> Savaş Tanrısı), yanlış alan (Corruption -> Yolsuzluk, oysa güç "
    "yolu: Yozlaşma), tarif-çeviri ('Evertwine' -> 'Altın ip'), uydurma birleşik sözcük, "
    "dilbilgisi hatası (yalın olmayan karşılık, tekil kaynağa çoğul karşılık) -> false.\n"
    "5. genel_sozcuk: kaynak, metinde çoğunlukla SIRADAN bir İngilizce sözcük olarak "
    "geçen bir sözcük mü (seven, lost, strong, fool) — yani her geçişine özel karşılık "
    "dayatmak sıradan kullanımları bozar mı (true/false).\n"
    "6. sorun: uygun false ya da genel_sozcuk true ise kısa gerekçe; değilse boş.\n"
    "7. oneri: uygun false ise önerdiğin karşılık; değilse boş.\n"
    "Kurallar (çeviri sözlüğüyle AYNI):\n"
    "- Bir KİŞİYİ adlandıran ifade (gerçek ad ya da ad yerine geçen lakap) İngilizce "
    "kalır: karşılığı kaynağın kendisidir ve bu UYGUNDUR.\n"
    + translate.LAKAP_KURALI +
    "- Başka her özel ad Türkçeye çevrilir; Türkçe karşılık gerçek Türkçe sözcüklerden "
    "kurulmalı.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"terms": [{"source": "...", "tur": "...", '
    '"tanim": "...", "geri_ceviri": "...", "uygun": true, "genel_sozcuk": false, '
    '"sorun": "", "oneri": ""}]}\n'
    "- source alanını sana verilen yazımla AYNEN geri ver; listedeki HER kayıt için "
    "bir sonuç döndür."
)


def ucretsiz_zincir() -> tuple[str, ...]:
    """Doğrulamanın kullanacağı zincir: ücretsiz halkalar, kullanıcı seçimi YOK."""
    return tuple(m for m in translate.DEFAULT_MODELS if not translate._ucretli_modeli(m))


# ---------- deterministik geri çeviri karşılaştırması ----------
_DURAK = frozenset("the a an of and in on to by for with from".split())


def _icerik(metin: str) -> set[str]:
    sozcukler = re.findall(r"[a-z0-9]+", (metin or "").casefold().replace("’", "'").replace("'s", ""))
    return {sozluk_kapi._tekil(s) for s in sozcukler if s not in _DURAK}


def geri_ceviri_uyumu(kaynak: str, geri: str) -> float | None:
    """Kaynak ile geri çevirinin içerik sözcüğü örtüşmesi (Jaccard, tekil). Geri
    çeviri yoksa None. `God of Death` / `God of War` -> 1/3."""
    a, b = _icerik(kaynak), _icerik(geri)
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def karar_ver(kayit: dict, yanit: dict) -> tuple[str, dict]:
    """("gecti" | "sorunlu", not) — not inceleme ekranında gösterilir.

    Sorunlu sayılan iki durum:
      * model "uygun değil" dedi
      * sıradan sözcük ve karşılık İngilizce korunmuyor (her geçişe dayatılır)
    Geri çeviri örtüşmesi (`uyum`) nota BİLGİ olarak yazılır, karar vermez — eş
    anlamlılarda sahte red üretiyordu (modül belgesindeki ölçüm).
    """
    korunan = sozluk_kapi.ingilizce_korunan(kayit["source"], kayit.get("target") or "")
    uyum = None if korunan else geri_ceviri_uyumu(kayit["source"], yanit.get("geri_ceviri") or "")
    not_ = {
        "geri_ceviri": (yanit.get("geri_ceviri") or "").strip()[:200] or None,
        "uyum": None if uyum is None else round(uyum, 2),
        "sorun": (yanit.get("sorun") or "").strip()[:300] or None,
        "oneri": (yanit.get("oneri") or "").strip()[:200] or None,
        "genel_sozcuk": bool(yanit.get("genel_sozcuk")),
        "uygun": yanit.get("uygun"),
        "zaman": time.time(),
    }
    sorunlu = False
    if yanit.get("uygun") is False:
        sorunlu = True
    # "Sıradan sözcük" TEK BAŞINA sorun değildir. Ölçüm (1050 kayıt): model 38 kaydı
    # yalnız bu yüzden işaretledi (`Echo`, `Skill`, `Flaw`, `Fire`, `Saint`) ve
    # karşılıkları sıradan kullanımda da DOĞRU — sözlük onları her geçişte doğru
    # çeviriyor. Zarar yalnız karşılık sıradan anlamı BOZDUĞUNDA doğar (`Seven ->
    # Yediler`: "seven days" -> "yediler gün"); bunun deterministik işareti tekil
    # kaynağa çoğul karşılık (`sozluk_kapi.sayi_uyumsuzlugu`).
    if not_["genel_sozcuk"] and not korunan and sozluk_kapi.sayi_uyumsuzlugu(
        kayit["source"], kayit.get("target") or ""
    ):
        sorunlu = True
        not_["sorun"] = not_["sorun"] or (
            "Sıradan bir sözcük, karşılığı ise bir grup adı: sıradan geçişler bozulur. "
            "Koşul ekle (yalnız grup adı olarak) ya da sil."
        )
    return ("sorunlu" if sorunlu else "gecti"), not_


# ---------- model çağrısı ----------
def _ayristir(metin: str | None) -> list[dict]:
    ham = (metin or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return []
    liste = veri.get("terms") if isinstance(veri, dict) else veri
    return [x for x in liste or [] if isinstance(x, dict)]


def ingilizce_baglam(book_slug: str, kayit: dict, korpus: str = "") -> str:
    """Kaydın İngilizce bağlam cümlesi: önce ilk görüldüğü bölüm, yoksa korpus."""
    metin = ""
    if kayit.get("first_chapter") is not None:
        for b in cache.kaynak_bolumleri(book_slug):
            if b.get("chapter_no") == kayit["first_chapter"]:
                metin = b.get("source") or ""
                break
    for kaynak_metin in (metin, korpus):
        if kaynak_metin:
            cumle = translate.cumle_bul(kaynak_metin, kayit["source"])
            if cumle:
                return cumle
    return ""


def dogrula_parti(
    kayitlar: list[dict], api_key: str = "", kitap_basligi: str = "",
    models: tuple[str, ...] | None = None,
) -> dict[str, dict]:
    """Bir parti kaydı modele sor: {kaynak: ham yanıt}. Model kaydı atladıysa yok.

    Her kayıtta `source`, `target`, isteğe bağlı `baglam_en` ve `kaynak_cumle`.
    """
    if not kayitlar:
        return {}
    if not translate.ceviri_anahtari_var_mi(api_key):
        raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
    satirlar = []
    for k in kayitlar:
        satirlar.append(
            f"- KAYNAK: {k['source']} | KARŞILIK: {k.get('target') or k['source']}"
            + (f" | İNGİLİZCE CÜMLE: {k['baglam_en'][:300]}" if k.get("baglam_en") else "")
            + (f" | TÜRKÇE CÜMLE: {k['kaynak_cumle'][:300]}" if k.get("kaynak_cumle") else "")
        )
    user = (f"KİTAP: {kitap_basligi}\n\n" if kitap_basligi else "") + "KAYITLAR:\n" + "\n".join(satirlar)
    response, _model = translate._generate_with_fallback(
        translate._gemini_fabrikasi(api_key), models or ucretsiz_zincir(), user,
        system=DOGRULAMA_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS,
    )
    fold_map = {glossary.fold_term(k["source"]): k["source"] for k in kayitlar}
    out: dict[str, dict] = {}
    for x in _ayristir(getattr(response, "text", None)):
        kaynak = fold_map.get(glossary.fold_term(str(x.get("source") or "")))
        if kaynak:
            out[kaynak] = x
    return out


def kitabi_dogrula(
    book_slug: str,
    kapsam: str = "yeni",
    api_key: str = "",
    parti: int = PARTI,
    sinir: int | None = None,
    yaz: bool = True,
    ilerleme=None,
    models: tuple[str, ...] | None = None,
) -> list[dict]:
    """Kitabın kayıtlarını doğrula; sonuç listesini döndür.

    `kapsam`: "yeni" = hiç doğrulanmamış OTOMATİK kayıtlar (arka plan yolu);
    "hepsi" = sözlüğün tamamı (bakım aracı, geriye dönük denetim); "eksik" = hiç
    doğrulanmamış bütün kayıtlar. `models` YALNIZ bakım aracından, açıkça (Vertex
    ücretlidir); arka plan yolu her zaman ücretsiz zinciri kullanır.
    `yaz=False`: kuru çalıştırma — DB'ye hiçbir şey yazılmaz.
    """
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    satirlar = glossary.get_glossary_rows(book_slug)
    if kapsam == "yeni":
        secilen = [r for r in satirlar if not r.get("dogrulama") and r.get("origin") == "auto"]
    elif kapsam == "eksik":
        secilen = [r for r in satirlar if not r.get("dogrulama")]
    else:
        secilen = list(satirlar)
    if sinir:
        secilen = secilen[:sinir]
    if not secilen:
        return []
    _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    baslik = (library.get_book(book_slug) or {}).get("title") or ""
    sonuclar: list[dict] = []
    for i in range(0, len(secilen), parti):
        grup = [
            {**r, "baglam_en": ingilizce_baglam(book_slug, r, korpus)}
            for r in secilen[i:i + parti]
        ]
        try:
            yanitlar = dogrula_parti(grup, api_key, baslik, models)
        except translate.TranslateError as hata:
            if ilerleme:
                ilerleme(f"! parti {i // parti + 1} atlandı: {hata}")
            continue
        for r in grup:
            yanit = yanitlar.get(r["source"])
            if yanit is None:
                continue
            sonuc, not_ = karar_ver(r, yanit)
            kayit = {"source": r["source"], "target": r.get("target"), "sonuc": sonuc,
                     "tur": glossary._tur(yanit.get("tur")),
                     "tanim": (yanit.get("tanim") or "").strip()[:300] or None, "not": not_}
            sonuclar.append(kayit)
            if yaz:
                sonucu_yaz(book_slug, kayit)
        if ilerleme:
            ilerleme(f"  {min(i + parti, len(secilen))}/{len(secilen)} kayıt doğrulandı")
    return sonuclar


def sonucu_yaz(book_slug: str, kayit: dict) -> None:
    """Tek sonucu sözlüğe işle (rapordan uygulama yolu da bunu kullanır)."""
    glossary.tanim_yaz(book_slug, kayit["source"], kayit.get("tanim"), kayit.get("tur"), yalniz_bossa=True)
    glossary.dogrulama_yaz(book_slug, kayit["source"], kayit["sonuc"], kayit.get("not") or {})


# ---------- arka plan ----------
_CALISAN: set[str] = set()
_KILIT = threading.Lock()
SON_DURUM: dict[str, dict] = {}


def acik_mi() -> bool:
    return os.getenv("SOZLUK_DOGRULAMA", "1") != "0"


def arka_planda_dogrula(book_slug: str, kapsam: str = "yeni", bekle: float | None = None) -> bool:
    """Kitap için tek-uçuşlu arka plan doğrulaması başlat. Başladıysa True.

    Toplu çeviride her bölüm yeni aday getirir; her biri için ayrı istek kotayı
    yakardı. İş `bekle` saniye BİRİKTİRİR, sonra o ana kadar gelen bütün yeni
    adayları tek seferde (parti parti) doğrular. Çalışırken gelen tetik yok sayılır:
    uyandığında zaten "doğrulanmamış olanların hepsi"ni okuyor.
    """
    if not acik_mi() or not translate.ceviri_anahtari_var_mi(os.getenv("GEMINI_API_KEY", "")):
        return False
    with _KILIT:
        if book_slug in _CALISAN:
            return False
        _CALISAN.add(book_slug)

    def is_():
        try:
            time.sleep(ARKA_PLAN_BEKLEME_SN if bekle is None else bekle)
            # `threading.Thread` bağlamı KOPYALAMAZ: API kaydı amacı burada kurulur.
            with api_durum.islem("sozluk_dogrulama"):
                sonuc = kitabi_dogrula(book_slug, kapsam)
            SON_DURUM[book_slug] = {
                "zaman": time.time(), "islenen": len(sonuc),
                "sorunlu": sum(1 for x in sonuc if x["sonuc"] == "sorunlu"),
            }
        except Exception as hata:  # noqa: BLE001 — arka plan işi çeviriyi asla düşürmez
            SON_DURUM[book_slug] = {"zaman": time.time(), "hata": str(hata)[:300]}
        finally:
            with _KILIT:
                _CALISAN.discard(book_slug)

    threading.Thread(target=is_, name=f"sozluk-dogrulama-{book_slug}", daemon=True).start()
    return True


def durum(book_slug: str) -> dict:
    return {"calisiyor": book_slug in _CALISAN, "son": SON_DURUM.get(book_slug), "acik": acik_mi()}
