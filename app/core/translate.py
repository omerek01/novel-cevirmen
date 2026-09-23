"""İsim-koruyan İngilizce -> Türkçe çeviri.

Gemini + paragraf bazlı parçalama (chunk) + parçalar arası bağlam taşıma +
sözlük (glossary) ile tutarlı özel isim koruması.

Dayanıklılık: her parça için model yedek zinciri denenir; bir model geçici
olarak meşgulse (429/500/503) üstel geri-çekilmeyle birkaç kez denenir, sonra
sıradaki modele düşülür.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — tzdata yoksa sabit UTC-8'e düşülür
    ZoneInfo = None  # type: ignore[assignment]

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from . import api_durum, kullanim
from . import settings as _ayarlar
from .glossary import fold_term

# Çeviri modeli zinciri — TEK MOTOR: GEMINI (2026-09-02, kullanıcı kararı).
#
# GEMINI DIŞI SAĞLAYICILAR ZİNCİRDEN ÇIKARILDI. Bir dönem OpenAI-uyumlu üç sağlayıcı
# (OpenRouter/minimax, Mistral, Groq/Cerebras kod desteği) zincirde duruyordu; gerekçe
# KOTAydı, kalite değil. Ölçüm tersini söyledi:
#   - minimax (2026-09-02): UZUNLUK ORANI medyanı 22 bölümde 0,949 ve 22'sinin 22'si
#     de 0,98'in ALTINDA — yani metni sistematik olarak KISALTIYOR. Hizalama ve
#     `sozluk_ihlalleri` ikilisi bunu göstermiyordu: onlar "terimi doğru yazdın mı"
#     diye sorar, "cümleyi eksiksiz kurdun mu" diye SORMAZ.
#   - mistral-medium (2026-08-30): gerçek bölümlerde cümle akıcılığı beklentiyi
#     karşılamadı; uzunluk oranı 0,914 ile ölçülenlerin en kötüsü.
#   - Groq: ücretsiz TPM 8.000, bu projenin girdisi tek başına 5.061 token → hepsi 413.
#   - Cerebras: ücretsiz bağlam 8.192 token → aynı duvar.
# Bakımı da bedavaya gelmiyordu: ikinci bir düşme kuralı, `:free` sonekinin sessizce
# paraya dönme riski (gerçek vaka: kıyas turları hesapta 0,05 $ yaktı) ve sağlayıcıya
# özel token tavanları. Kalite kazancı yoksa bu yükü taşımanın anlamı yok.
#
# Kotanın yerine gelen çözüm ANAHTAR HAVUZU (aşağıda): aynı zincir, birden çok Gemini
# anahtarı. Kota dolunca başka bir SAĞLAYICIYA değil, başka bir ANAHTARA geçilir —
# yani kaliteden ödün verilmeden kota genişler.
#
# Ölçüm geçmişi (gerçek bölüm metinleriyle):
#   gemini-3.6-flash       akıcılık EN İYİ; önbellekteki 76 bölümde uzunluk oranı
#                          medyanı 0,972 (ölçülenlerin en iyisi). Ücretsiz kotası dar.
#   gemini-3.5-flash       akıcılık iyi, kota geniş; 503'e meyilli → orta halka
#   gemini-3.5-flash-lite  EN HIZLI ve en dayanıklı ama SÖZLÜK KURALINA %24 oranında
#                          UYMUYOR (3.6-flash %0,7) → yalnız son çare
#   gemini-3.1-pro-preview / gemini-pro-latest  429 — ücretsiz katmanda YOK
#
# Not: ücretsiz katmanın model-başına RPD tablosu Google tarafından artık
# yayınlanmıyor (AI Studio > Rate limits'ten bakılır). Bu yüzden kotaya göre değil,
# 429'a DAYANIKLI tasarıma güveniyoruz: bir halka tükenirse önce sıradaki ANAHTAR,
# o da tükenirse sıradaki MODEL denenir.
#
# PARÇALAMA KALİTEYİ İYİLEŞTİRMİYOR (ölçüldü 2026-09-02): "bölümü 3'e bölsek model
# daha az atlar mı" hipotezi sınandı. Aynı model, aynı bölüm, üç parça: oran 0,922 →
# 0,912 (DÜŞTÜ), süre 51 → 76 sn, token ~1,8 kat (prompt'un %41-48'i sabit yük —
# sistem talimatı + sözlük her parçada YENİDEN gider). Parçalama yalnız dar bağlam
# pencerelerine sığmak için bir araçtır, kalite aracı değil.
#
# `gemini-3.5-flash-lite` ZİNCİRDEN ÇIKARILDI (2026-09-09, kullanıcı kararı).
# Ölçüm: sözlük kuralına uyumu zincirin EN KÖTÜsüydü — Shadow Slave'in
# önbelleğinde 3.6-flash 60 bölümde 5 ihlal, 3.5-flash 45 bölümde 1, lite ise
# 4 bölümde 30. Somut vaka: 109. bölümü lite çevirdi, `Saint -> Aziz` kaynakta
# 12 kez geçti ve 12'si de İngilizce kaldı. Son halka olması bunu daha da kötü
# yapıyordu: üst halkalar 429/503 ile elendiğinde okuma sessizce ORAYA iniyor,
# çeviri kalıcı önbelleğe yazılıyor ve bir daha denetlenmiyordu.
#
# Zincir bu yüzden bir dönem İKİ halkaydı. Daralan kapasitenin karşılığı anahtar
# tarafında ödendi: 503 ve 404 artık sıradaki ANAHTARI deniyor (eskiden modeli
# atlıyorlardı) ve istekler anahtarlar arasında DÖNÜŞÜMLÜ dağıtılıyor.
#
# ÜÇÜNCÜ HALKA `gemini-2.5-flash` (2026-09-15, kullanıcı kararı + arıza). Zincirin
# iki halkası da 3.x AİLESİNDENDİ ve o aile kullanıcının anahtarlarına 404 dönmeye
# başlayınca ayakta kalan hiçbir halka kalmadı — çeviri TÜMDEN durdu. 2.5 o gün
# çalışan tek modeldi ama YALNIZ seçilebilir listedeydi, yani ancak ayarı açıp elle
# seçen kullanıcı çeviri yapabildi.
#
# Ders: zincirin dayanıklılığı halka SAYISINDAN değil, halkaların BİRLİKTE
# ölmemesinden gelir. Aynı ailenin iki sürümü ortak bir kaderi paylaşıyor (aynı
# erişim politikası, yakın kota havuzları); farklı nesilden bir halka bunu kırar.
# 2.5 SONA konur, başa değil: ölçümde 3.6-flash hâlâ daha iyi (oran 0,972 / 0,932)
# ve 2.5'e ancak üst halkalar elendiğinde inilir, yani 3.x çalışırken davranış
# birebir eskisi gibi kalır. Künye rozeti fiilen çevireni yazdığı için inildiği
# gizlenmez. Kotası 3.x'ten AYRI olduğu için o gün de gerçek bir yedektir.
#
# Bu, zincire ÖLÇÜLMEMİŞ model koymama kuralının istisnası DEĞİL: 2.5 ölçüldü
# (2026-09-06, 3 gerçek bölüm — oran 0,932, hizalama 3/3, 3 bölümde 1 sözlük
# ihlali, ölçülenlerin en hızlısı). Ölçülmemiş olsaydı yine listede kalırdı.
DEFAULT_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
)

# ---------------------------------------------------------------------------
# SEÇİLEBİLİR MODEL — okuyucudaki ayardan gelir (2026-09-02, kullanıcı isteği)
# ---------------------------------------------------------------------------
# Seçim zincirin YERİNİ ALMAZ, BAŞINA geçer (`zincir_kur`). Sebep dayanıklılık:
# ölçüldü ki 3.7 ve 3.8 bu projenin uzunluktaki isteklerini sık sık 503 ile
# reddediyor. Seçim "yalnız bunu kullan" diye yorumlansaydı, o modeli seçen
# kullanıcının okuması modelin kapasitesi daraldığı anda TÜMDEN dururdu. Seçim bir
# TERCİHTİR, kilit değil: tercih edilen model çeviremezse okuma alt halkalardan
# devam eder ve künye rozeti FİİLEN çevirenin adını yazar — yani "3.8 seçtim ama
# 3.6 çevirmiş" durumu kullanıcıdan gizlenmez.
#
# `etiket` okuyucuya çıkar, `not` ise ölçüm özetidir: kullanıcı seçerken neyin
# bedelini ödediğini görmeli. Ölçüm 2026-09-02, `scratch/gemini_kiyas.py`.
# ---------------------------------------------------------------------------
# CLAUDE — ÜCRETLİ ve YALNIZ AÇIKÇA SEÇİLİNCE (2026-09-02, kullanıcı kararı)
# ---------------------------------------------------------------------------
# Zincirin bugüne kadarki bütün halkaları ÜCRETSİZ. Claude ücretli, ve bu tek fark
# tasarımı belirliyor: Claude ASLA yedek halka olamaz. Sebep, bu projede bir kez
# ödenmiş bir ders — OpenRouter'ın `:free` soneki düştüğünde istek 200 dönüyor,
# çeviri çalışıyor, hiçbir hata görünmüyor, yalnız FATURA işliyordu. Sessizce paraya
# dönen bir arıza, gürültülü bir arızadan tehlikelidir.
#
# Bu yüzden `zincir_kur` Claude seçilince TEK HALKALI bir zincir kurar: Gemini'ye
# sessizce düşülmez (hangi modelin çevirdiği belirsiz kalmaz) ve tersi de olmaz —
# Gemini seçiliyken kota dolsa bile Claude'a ASLA inilmez, yani beklenmedik harcama
# yapısal olarak imkânsız.
#
# Fiyat ve ölçüm (`scratch/claude_maliyet.py`, gerçek prompt + gerçek bölümler):
# ortalama bölüm 8.284 giriş + 4.952 çıkış token. Çıkış tokenı girişin 5 katı
# fiyatta olduğu için maliyetin ~%75'i ÇIKIŞTAN gelir — prompt önbelleklemesi
# (girişin %58'i sabit yük) bu iş yükünde yalnız ~%13 kazandırır, o yüzden
# kurulmadı. Ölçmeden önce tam tersi bekleniyordu.
CLAUDE_ANAHTAR_ENVLERI = ("CLAUDE_API_KEY", "ANTHROPIC_API_KEY")
# `dusunme`: Claude'un "extended thinking" ayarı. KAPALI tutulur çünkü düşünme
# çıktısı da ÇIKIŞ tokenı olarak faturalanır ($5-10/M) ve çeviri mekanik bir iş —
# kazancı belirsiz, maliyeti düzenli. Sonnet 5'te `thinking` HİÇ verilmezse adaptif
# düşünme AÇIK gelir (varsayılan), yani açıkça kapatmak şart. Haiku 4.5 eski nesil:
# orada `disabled` göndermek yerine parametreyi hiç vermemek doğru yol.
CLAUDE_MODELLER = {
    "claude-haiku-4-5": {
        "etiket": "Haiku 4.5",
        "not": "ÜCRETLİ ~$0,033/bölüm. Hızlı ve ucuz Claude. Kalitesi ölçülmedi.",
        "dusunme": None,  # eski nesil: parametre verilmez
    },
    "claude-sonnet-5": {
        "etiket": "Sonnet 5",
        "not": "ÜCRETLİ ~$0,066/bölüm. Haiku'nun iki katı. Kalitesi ölçülmedi.",
        "dusunme": {"type": "disabled"},
    },
}


def _claude_modeli(model: str | None) -> bool:
    return bool(model) and model in CLAUDE_MODELLER


def claude_anahtari() -> str:
    """Claude anahtarı. İki ad da kabul edilir: `CLAUDE_API_KEY` kullanıcının bu
    projede yazdığı ad, `ANTHROPIC_API_KEY` ise SDK'nın kanonik adı — birini
    dayatmak, diğerini yazan kurulumu sessizce anahtarsız gösterirdi."""
    for ad in CLAUDE_ANAHTAR_ENVLERI:
        deger = (os.getenv(ad) or "").strip()
        if deger:
            return deger
    return ""


GEMINI_SECENEKLERI = (
    {
        "ad": "gemini-3.8-flash",
        "etiket": "3.8 Flash",
        "not": "En yeni. Uzun bölümlerde sık 503 veriyor; ölçülemedi.",
    },
    {
        "ad": "gemini-3.7-flash",
        "etiket": "3.7 Flash",
        "not": "Uzun bölümleri reddediyor ve reddi PAHALI (74-220 sn). Ölçülemedi.",
    },
    {
        "ad": "gemini-3.6-flash",
        "etiket": "3.6 Flash",
        "not": "Varsayılan. 76 bölümde uzunluk oranı 0,972 — ölçülenlerin en iyisi.",
    },
    {
        "ad": "gemini-3.5-flash",
        "etiket": "3.5 Flash",
        "not": "Kıyasın en temizi: oran 0,985, sıfır sözlük ihlali. Daha yavaş.",
    },
    # `gemini-3-flash-preview` BİLEREK YOK (2026-09-06). Bir gün eklenmesi
    # önerilirse ölçüm kaydı şudur: 3 gerçek bölümde hizalamayı 3/3 KAYBETTİ
    # (53-62 paragraflık bölümlere 19-25 paragraf döndü — paragrafları birleştirip
    # metnin yarısını attı), uzunluk oranı 0,436'da kaldı (3.6-flash 0,952) ve en
    # yavaşıydı (109 sn / 49 sn). Yani çevirmiyor, ÖZETLİYOR.
    #
    # Listede tutulamamasının sebebi zincirin onu KURTARAMAMASI: düşme yalnız
    # HATADA olur (429/503/404), başarılı ama kötü bir yanıtta olmaz. Seçilseydi
    # her bölüm böyle çevrilir, iki dilli okuma ölür ve İngilizce-kalıntı denetimi
    # de çalışamazdı (hizalama ister). Sert bir uyarı notu yetmez: seçenek listesi
    # bir TEKLİFTİR ve teklif edilmemesi gereken tek şey sessizce bozan bir yoldur.
    #
    # AYRICA: `gemini-3-flash` ve `gemini-3.0-flash` adları API'de YOK (404).
    # Gemini 3'ün çalışan tek adı `-preview` sonekliydi.
    #
    # Eski nesil ama ölçümde SAĞLAM çıktı: oran 0,932, hizalama 3/3, 3 bölümde 1
    # sözlük ihlali ve en HIZLIsı (45 sn / 3.6-flash'ın 49 sn'si). Kotası ayrı
    # olduğu için 3.x halkaları tükendiğinde gerçek bir alternatif.
    {
        "ad": "gemini-2.5-flash",
        "etiket": "2.5 Flash",
        "not": "Eski nesil, sağlam: oran 0,932, hizalama 3/3, en hızlısı (45 sn).",
    },
)
SECILEBILIR_MODELLER = GEMINI_SECENEKLERI + tuple(
    {"ad": ad, "etiket": bilgi["etiket"], "not": bilgi["not"], "ucretli": True}
    for ad, bilgi in CLAUDE_MODELLER.items()
)
SECILEBILIR_ADLAR = tuple(m["ad"] for m in SECILEBILIR_MODELLER)
# Ayarın DB anahtarı. Varsayılan, zinciri bugünkü hâlinde bırakan seçimdir —
# yani ayar hiç dokunulmamışsa davranış birebir eskisi gibi kalır.
MODEL_AYAR_ANAHTARI = "ceviri_modeli"
VARSAYILAN_MODEL = DEFAULT_MODELS[0]


def zincir_kur(secili: str | None = None) -> tuple[str, ...]:
    """Seçilen modele göre model zinciri.

    İKİ DAVRANIŞ, ve ayrım ÜCRETTEN geliyor:
      * Gemini seçimi -> seçilen model zincirin BAŞINA geçer, gerisi YEDEK kalır.
        Halkaların hepsi ücretsiz, dolayısıyla aşağı inmek bedava; okumanın
        durmaması her zaman daha değerli.
      * Claude seçimi -> zincir TEK HALKA. Ücretli bir halkanın altına ücretsiz
        yedek koymak cazip görünür ama iki şeyi birden bozardı: künye rozeti
        "Claude" derken bölümü Gemini çevirmiş olabilirdi, ve daha kötüsü, tersi
        yönde bir gün birinin "Gemini'nin altına Claude koyalım" demesinin önü
        açılırdı — sessiz harcamanın kapısı. Claude çeviremezse hata verir.

    Tekrar elenir ve sıra korunur. Tanınmayan/boş bir seçim SESSİZCE yok sayılır:
    ayar tablosunda elle bozulmuş bir değer, her isteği 404'e çarpan bir birinci
    halka yaratırdı ve arıza "model meşgul" kılığına girerdi.
    """
    if secili not in SECILEBILIR_ADLAR:
        return DEFAULT_MODELS
    if _claude_modeli(secili):
        return (secili,)
    return tuple(dict.fromkeys((secili, *DEFAULT_MODELS)))


def secili_zincir() -> tuple[str, ...]:
    """Ayardaki seçime göre model zinciri — zincirin TEK çözüm noktası.

    Zinciri çağrı yerlerine tek tek geçirmek yerine burada çözülmesinin sebebi
    somut: zinciri kullanan BEŞ yol var (okuma, prefetch, toplu çeviri, içe
    aktarılan sayfa, sözlük terim önerisi) ve bu projede aynı kuralın birden çok
    yerde yazılması defalarca ayrışmayla sonuçlandı (künye alanları, motor adı).
    Biri güncellenmeyi unutulursa kullanıcı "modeli değiştirdim ama bazı bölümler
    hâlâ eskisiyle çevriliyor" derdi ve sebebi görünmez olurdu.

    DB okunamazsa varsayılan zincire düşülür: bir ayar okuma hatası çevirinin
    tamamını durdurmamalı.
    """
    try:
        secili = _ayarlar.get(MODEL_AYAR_ANAHTARI, VARSAYILAN_MODEL)
    except sqlite3.Error:
        return DEFAULT_MODELS
    return zincir_kur(secili)

# Anahtar yokluğu TEK yerden anlatılır: mesaj beş ayrı çağrı yerinde kopyalanmıştı ve
# sağlayıcılar kaldırılınca hepsi "ya da MISTRAL_API_KEY ekleyin" demeye devam ederdi.
ANAHTAR_YOK_MESAJI = (
    "Çeviri için API anahtarı yok: .env dosyasına GEMINI_API_KEY ekleyin."
)

# ---------------------------------------------------------------------------
# ANAHTAR HAVUZU — birden çok Gemini anahtarı, SIRAYLA
# ---------------------------------------------------------------------------
# UYARI, önce bunu oku: Gemini'nin ücretsiz kotası PROJE başınadır, ANAHTAR başına
# DEĞİL. Aynı Google Cloud projesinden üretilmiş iki anahtar AYNI RPM/RPD havuzundan
# içer ve ikincisi hiçbir şey kazandırmaz — birincisi 429 alırsa ikincisi de alır.
# Havuzun anlamlı olması için anahtarların AYRI PROJELERDEN gelmesi gerekir.
#
# Değişken adı ESNEK tutulur (`GEMINI_API_KEY`, `GEMINI2_API_KEY`,
# `GEMINI_API_KEY_3`…): tek bir kanonik ad dayatmak, `.env`'i elle düzenleyen
# kullanıcının anahtarı sessizce görünmez kılmasına yol açardı — ve arıza "kota dolu"
# kılığına girerdi. Sıra addaki SAYIDAN gelir; sayı taşımayan ad birinci sayılır.
_ANAHTAR_DESENI = re.compile(r"^GEMINI_?(\d*)_?API_KEY_?(\d*)$")


def _anahtar_sirasi(ad: str) -> tuple[int, str]:
    """`GEMINI_API_KEY` -> 1, `GEMINI2_API_KEY` -> 2, `GEMINI_API_KEY_3` -> 3."""
    eslesme = _ANAHTAR_DESENI.match(ad)
    no = (eslesme.group(1) or eslesme.group(2) or "1") if eslesme else "1"
    return (int(no) if no.isdigit() else 1, ad)


def gemini_anahtar_degiskenleri() -> list[str]:
    """Ortamdaki Gemini anahtar değişkenlerinin ADLARI, deneme sırasıyla.

    Testler için de gerekli: "anahtarsız reddedilir" iddiaları TÜM anahtar
    değişkenlerini silmeli. Adları tek tek yazmak, ikinci bir anahtar eklendiğinde
    testi geliştiricinin makinesindeki `.env`'e bağımlı kılardı (`server` importu
    `.env`i pytest sürecine yüklüyor).
    """
    adlar = [
        ad
        for ad, deger in os.environ.items()
        if _ANAHTAR_DESENI.match(ad) and (deger or "").strip()
    ]
    return sorted(adlar, key=_anahtar_sirasi)


def anahtar_degiskenleri() -> list[str]:
    """Çeviriyi mümkün kılan TÜM anahtar değişkenlerinin adları (Gemini + Claude).

    Testler için TEK doğru kaynak: "anahtarsız reddedilir" iddiaları bunların
    hepsini silmeli. Adları tek tek yazmak, yeni bir sağlayıcı ya da üçüncü bir
    anahtar eklendiğinde testi sessizce geliştiricinin `.env`ine bağımlı kılar
    (`server` importu onu pytest sürecine yüklüyor) — bu proje o tuzağa bir kez
    düştü ve testler geliştiricinin makinesinde geçip başka yerde kalıyordu.
    """
    return gemini_anahtar_degiskenleri() + [
        ad for ad in CLAUDE_ANAHTAR_ENVLERI if (os.getenv(ad) or "").strip()
    ]


def gemini_anahtarlari(birincil: str | None = None) -> list[str]:
    """Kullanılacak anahtarlar, DENEME SIRASIYLA; tekrar elenir.

    ``birincil`` (çağrı zincirinden gelen `api_key`) daima ilk sıradadır: sunucu onu
    `GEMINI_API_KEY`'den okuyor, yani normalde ortamdaki ilk anahtarla aynıdır ve
    tekrar eleme sırayı bozmadan tek kayda indirir. Testlerin açıkça geçtiği anahtar
    da böylece ortamdakinin ÖNÜNE geçer.
    """
    sirali: list[str] = []
    adaylar = [birincil or ""]
    adaylar += [os.environ[ad] for ad in gemini_anahtar_degiskenleri()]
    for deger in adaylar:
        deger = (deger or "").strip()
        if deger and deger not in sirali:
            sirali.append(deger)
    return sirali


# Kota dolan anahtar SOĞUMAYA alınır: aynı bölümün sonraki parçaları o anahtara boşuna
# gitmesin (bir bölüm birden çok parça, her parça ayrı istek).
#
# Süre neden 60 sn: Gemini'nin 429'u ya DAKİKALIK (RPM) ya da GÜNLÜK (RPD) sınırdan
# gelir ve ikisi yanıttan ayırt edilemez. 60 sn dakikalık sınırı TAM karşılar; günlük
# sınırda ise dakikada bir boşa istek maliyeti bırakır (ucuz, ve gün dönümünde
# kendiliğinden düzelir). Alternatifi — uzun soğuma — dakikalık bir tökezlemede
# anahtarı gün boyu kaybettirirdi, ki asıl kaçınılan şey o.
#
# Soğuma MODEL BAŞINADIR: Gemini'nin günlük kotası model başına ayrı tutulur, yani
# 3.6-flash'ta tükenen anahtar 3.5-flash'ta hâlâ çalışır. Tek bir "anahtar bitti"
# bayrağı, çalışan halkaları da kapatırdı.
ANAHTAR_SOGUMA_SN = 60.0
_ANAHTAR_SOGUMA: dict[tuple[int, str], float] = {}
# Ardışık TÜKENİŞ sayacı, MODEL başına: doygunluk modele aittir (503 beş anahtarda
# aynı anda çıkıyor), anahtara değil. Başarılı bir yanıt sayacı sıfırlar.
_GECICI_SAYAC: dict[str, int] = {}
# Soğumanın SEBEBİ, yalnız hata mesajı için. İki sebep ayırt edilmezse mesaj
# "kota soğumasında" der ve kullanıcı arızayı kota tarafında arar — bu projede
# yanlış teşhis eden mesajın bedeli bir kez ödendi (404 dalı, 2026-09-15).
_SOGUMA_SEBEBI: dict[tuple[int, str], str] = {}


def _hata_govdesi(hata: Exception) -> dict:
    """429/4xx yanıtının JSON gövdesi; okunamazsa boş sözlük."""
    ham = getattr(hata, "details", None)
    if isinstance(ham, dict) and ham:
        return ham
    metin = str(hata)
    basla = metin.find("{")
    if basla < 0:
        return {}
    try:
        cozulen = json.loads(metin[basla:])
    except (ValueError, TypeError):
        return {}
    return cozulen if isinstance(cozulen, dict) else {}


def gunluk_kota_mi(hata: Exception) -> bool:
    """429 GÜNLÜK sınırdan mı geldi? Ayrımı yalnız `quotaId` söyler.

    Gemini kota aşımını iki ayrı sınırdan verir ve HTTP kodu ikisinde de 429:
      * DAKİKALIK (RPM/TPM) — bir dakika içinde kendiliğinden açılır.
      * GÜNLÜK    (RPD)     — Pasifik gece yarısına kadar KAPALI kalır.
    Gerçek gövde (2026-09-09 ölçümü, `gemini-3.6-flash`):
        quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
        quotaValue: 20
    """
    return kota_ayrintisi(hata)["tur"] == "gunluk"


def _hata_ayrintilari(hata: Exception) -> list[dict]:
    govde = _hata_govdesi(hata)
    err = govde.get("error", govde) if isinstance(govde, dict) else {}
    if not isinstance(err, dict):
        return []
    return [a for a in (err.get("details") or []) if isinstance(a, dict)]


def kota_ayrintisi(hata: Exception) -> dict:
    """429 gövdesinin YAPILANDIRILMIŞ kısmı: tür, sınır, kota kimliği, bekleme.

    ``tur``: "gunluk" (quotaId'de PerDay) · "dakikalik" (PerMinute) · None (gövde
    okunamadı ya da ikisi de yok). Üçüncü durum AYRI tutulur: çeviri yolu onu
    dakikalık sayar (bir dakika erken denemek ucuzdur), ama API durum paneli
    "belirsiz" demeli — tahmini gözlem gibi sunmak, 2026-09-18'de tam olarak
    ayıklamaya çalıştığımız belirsizliği yeniden üretirdi.
    Ham gövde SAKLANMAZ; yalnız bu alanlar kayda girer.
    """
    sonuc: dict = {"tur": None, "sinir": None, "kimlik": None, "yeniden_sn": None}
    ihlaller: list[dict] = []
    for ayrinti in _hata_ayrintilari(hata):
        tip = (ayrinti.get("@type") or "").split(".")[-1]
        if tip == "QuotaFailure":
            ihlaller += [i for i in ayrinti.get("violations") or [] if isinstance(i, dict)]
        elif tip == "RetryInfo":
            try:
                sonuc["yeniden_sn"] = float(str(ayrinti.get("retryDelay") or "").rstrip("s"))
            except ValueError:
                pass

    def _kimlik(ihlal: dict) -> str:
        return ihlal.get("quotaId") or ihlal.get("quotaMetric") or ""

    # Birden çok ihlal gelirse GÜNLÜK kazanır: açılma süresini o belirler.
    secilen = (
        next((i for i in ihlaller if "PerDay" in _kimlik(i)), None)
        or next((i for i in ihlaller if "PerMinute" in _kimlik(i)), None)
        or (ihlaller[0] if ihlaller else None)
    )
    if secilen is not None:
        kimlik = _kimlik(secilen)
        sonuc["kimlik"] = kimlik or None
        if "PerDay" in kimlik:
            sonuc["tur"] = "gunluk"
        elif "PerMinute" in kimlik:
            sonuc["tur"] = "dakikalik"
        try:
            sonuc["sinir"] = int(secilen.get("quotaValue"))
        except (TypeError, ValueError):
            pass
    return sonuc


def anahtar_reddi_mi(kod: int | None, hata: Exception) -> bool:
    """Hata ANAHTARA mı bağlı (geçersiz/iptal/izinsiz)? Öyleyse sıradaki anahtar.

    401/403 her zaman anahtara bağlıdır. 400 ise İKİ ayrı şeydir: Gemini geçersiz
    anahtarı 400 INVALID_ARGUMENT + ``reason: API_KEY_INVALID`` ile bildirir, ama
    gerçek bir istek hatası da (bozuk parametre) 400 döner ve o her anahtarda aynı
    sonucu verir. Yalnız ilki anahtara bağlıdır.
    """
    if kod in (401, 403):
        return True
    if kod != 400:
        return False
    if any(a.get("reason") == "API_KEY_INVALID" for a in _hata_ayrintilari(hata)):
        return True
    return "API_KEY_INVALID" in str(hata) or "API key not valid" in str(hata)


def pasifik_gece_yarisina_kalan() -> float:
    """GÜNLÜK kotanın sıfırlanmasına kalan saniye (yaz saatine duyarlı)."""
    simdi = datetime.now(timezone.utc)
    pas = None
    if ZoneInfo is not None:
        try:
            pas = simdi.astimezone(ZoneInfo("America/Los_Angeles"))
        except Exception:  # noqa: BLE001 — tzdata yoksa sabit ofsete düş
            pas = None
    if pas is None:
        pas = simdi.astimezone(timezone(timedelta(hours=-8)))
    ertesi = (pas + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Alt sınır: saat tam gece yarısıysa soğuma sıfıra düşüp anlamsızlaşmasın.
    return max(ANAHTAR_SOGUMA_SN, (ertesi - pas).total_seconds())


def _kota_soguma_suresi(hata: Exception) -> float:
    """Kotanın TÜRÜNE göre soğuma: günlükse gün sonuna, değilse bir dakika.

    Sabit 60 sn iken günlük kotası dolan anahtar DAKİKADA BİR yeniden deneniyor,
    her bölüm ona boş bir istek daha atıyor ve kullanıcı bunu bekleme olarak
    ödüyordu. Ayrıştırılamayan gövdede DAKİKALIK varsayılır: yanlış tarafta hata
    yapmak (bir dakika erken denemek) anahtarı gün boyu kaybetmekten ucuzdur.
    """
    return pasifik_gece_yarisina_kalan() if gunluk_kota_mi(hata) else ANAHTAR_SOGUMA_SN


def _sogumada(indeks: int, model: str) -> bool:
    return _ANAHTAR_SOGUMA.get((indeks, model), 0.0) > time.monotonic()


def _sogut(
    indeks: int, model: str, sure: float | None = None, sebep: str = "kota"
) -> None:
    _ANAHTAR_SOGUMA[(indeks, model)] = time.monotonic() + (
        ANAHTAR_SOGUMA_SN if sure is None else sure
    )
    _SOGUMA_SEBEBI[(indeks, model)] = sebep


def _gecici_soguma_suresi(model: str) -> float:
    """Ardışık tükeniş sayısına göre üstel süre; sayacı ARTIRIR (tükeniş başına bir kez)."""
    sayi = _GECICI_SAYAC.get(model, 0) + 1
    _GECICI_SAYAC[model] = sayi
    return min(GECICI_SOGUMA_TABAN_SN * (2 ** (sayi - 1)), GECICI_SOGUMA_TAVAN_SN)


def _gecici_sogut(indeksler: set[int], model: str) -> None:
    """Model bu çağrıda HİÇ çeviremedi → 503 veren anahtarları o modelde soğut.

    Soğutma tek bir 503'e değil, modelin TÜKENMESİNE bağlıdır: ölçüm (2026-09-09)
    503'ün bir anahtarda çıkarken diğerlerinin AYNI ANDA açık dönebildiğini
    gösterdi, orada soğutmak sağlam anahtarı sebepsiz kaybetmek olurdu. Havuz
    çeviriyi tamamladıysa doygunluk yok demektir ve buraya hiç gelinmez.
    """
    if not indeksler:
        return
    sure = _gecici_soguma_suresi(model)
    for indeks in indeksler:
        _sogut(indeks, model, sure, sebep="gecici")


def anahtar_sogumalarini_temizle() -> None:
    """Soğuma hafızası modül düzeyinde ve SÜREÇ ÖMÜRLÜDÜR; testler sıfırlamalı."""
    _ANAHTAR_SOGUMA.clear()
    _GECICI_SAYAC.clear()
    _SOGUMA_SEBEBI.clear()
    _GERI_YUKLENEN.clear()


# Soğuma YENİDEN BAŞLATMAYA dayanır (2026-09-18). Bellekteki soğuma monotonic saate
# bağlı ve süreçle birlikte ölüyordu: günlük kotası dolan anahtar her restart'tan
# sonra yeniden deneniyor, her model için bir boş 429 daha yiyordu. Bitiş kayıtta
# UTC epoch olarak durur (`api_durum.api_son.soguma_bitis`) ve süreç o anahtar
# listesini İLK kez gördüğünde monotonic saate çevrilerek geri yüklenir. Eşleme
# anahtar KİMLİĞİYLE yapılır, sırayla değil: `.env` yeniden sıralanırsa soğuma yanlış
# anahtara taşınmasın. Geçmiş bitişler aktif engel sayılmaz.
_GERI_YUKLENEN: set[tuple[str, ...]] = set()


def _sogumalari_geri_yukle(kimlikler: list[str]) -> None:
    anahtar = tuple(kimlikler)
    if not anahtar or anahtar in _GERI_YUKLENEN:
        return
    _GERI_YUKLENEN.add(anahtar)
    duvar, mono = time.time(), time.monotonic()
    for kimlik, model, bitis in api_durum.aktif_sogumalar(duvar):
        if kimlik not in kimlikler:
            continue  # anahtar .env'den çıkarılmış: kullanımı yeni anahtara TAŞINMAZ
        yer = (kimlikler.index(kimlik), model)
        hedef = mono + (bitis - duvar)
        if _ANAHTAR_SOGUMA.get(yer, 0.0) < hedef:
            _ANAHTAR_SOGUMA[yer] = hedef


def aktif_soguma_bitisleri(kimlikler: list[str]) -> dict[tuple[str, str], float]:
    """API durum paneli için: ÇEVİRİ YOLUNUN kendi soğumaları, UTC epoch olarak.

    Panel ayrı bir kaynağa (yalnız veritabanına) baksaydı iki yer ayrışabilirdi:
    panel "soğumada" derken çeviri o anahtarı deniyor olurdu. Süreç yeni açıldıysa
    ve henüz çeviri yapılmadıysa bellek boştur; önce kayıttan geri yüklenir
    (Google'a istek atmaz).
    """
    _sogumalari_geri_yukle(kimlikler)
    duvar, mono = time.time(), time.monotonic()
    return {
        (kimlikler[i], model): duvar + (bitis - mono)
        for (i, model), bitis in list(_ANAHTAR_SOGUMA.items())
        if bitis > mono and 0 <= i < len(kimlikler)
    }


# ---------------------------------------------------------------------------
# ANAHTAR ROTASYONU — her istek SONRAKİ anahtardan başlar (2026-09-09)
# ---------------------------------------------------------------------------
# Eskiden her istek DAİMA #1'den başlıyordu ve havuz ancak arıza hâlinde işe
# yarıyordu. Ölçüm bunun neden pahalı olduğunu gösterdi: Gemini'nin ücretsiz
# günlük kotası model başına 20 istek / PROJE (429 gövdesinden okundu —
# `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quotaValue 20). Yani ilk
# anahtar erken tükeniyor, sonraki HER istek önce ona çarpıp 429 yiyor, soğuma
# yazıyor, ancak sonra #2'ye geçiyordu. Beş anahtarlı bir havuzda bile yük tek
# anahtara yığılıyor ve kotanın dörtte beşi boşta duruyordu.
#
# Rotasyon yükü havuza EŞİT dağıtır: istek başına başlangıç indeksi bir kayar,
# yani bir sonraki bölüm bir sonraki anahtardan başlar. Soğumanın YERİNE geçmez
# — sırası gelen anahtar kotadaysa yine atlanır.
_ROTASYON = 0


def _sonraki_baslangic(sayi: int, model: str | None = None) -> int:
    """Bu isteğin başlayacağı anahtar indeksi; her çağrıda bir ilerler.

    Soğumadaki (kotası dolu) anahtar başlangıç olarak SEÇİLMEZ ve sırayı da
    tüketmez. Döngü onu zaten atlıyordu, ama rotasyon sayacı bir tur harcadığı
    için sağlam anahtarlara eşitsiz dağılıyordu: üç anahtarın biri kotadayken
    dört istek kalan ikiliye 3/1 gidiyordu.
    """
    global _ROTASYON
    if sayi <= 1:
        return 0
    for _ in range(sayi):
        deger = _ROTASYON % sayi
        _ROTASYON += 1
        if model is None or not _sogumada(deger, model):
            return deger
    return _ROTASYON % sayi  # hepsi soğumada: sıradan devam, döngü zaten atlar


def anahtar_rotasyonunu_sifirla() -> None:
    """Rotasyon sayacı modül düzeyinde ve SÜREÇ ÖMÜRLÜDÜR; testler sıfırlamalı."""
    global _ROTASYON
    _ROTASYON = 0


def _gemini_fabrikasi(api_key: str | None):
    """Gemini istemcilerini TEMBEL kuran fabrika (anahtar havuzu üzerinden).

    ``fabrika(indeks)`` o sıradaki anahtarın istemcisini verir; istemci ancak
    gerçekten kullanılacağı anda kurulur. Peşinen kurmak, hiç inilmeyen bir halka
    için bile anahtarı zorunlu kılardı.

    ``fabrika.anahtar_sayisi`` çağıranın kaç anahtar deneyebileceğini söyler —
    `_generate_once_with_retry` KOTA (429) durumunda bu sayıya kadar döner.

    Anahtar yoksa fabrika ÇAĞRILDIĞINDA hata verir, kurulurken değil: zincir o
    halkayı atlayıp devam edebilsin diye.
    """
    anahtarlar = gemini_anahtarlari(api_key)
    tutulan: dict[int, genai.Client] = {}
    # Kayıt için kalıcı kimlikler (değer değil, özet) — bkz. `api_durum`.
    kimlikler = [api_durum.anahtar_kimligi(a) for a in anahtarlar]
    _sogumalari_geri_yukle(kimlikler)

    def fabrika(indeks: int = 0) -> genai.Client:
        if indeks >= len(anahtarlar):
            raise TranslateError(ANAHTAR_YOK_MESAJI)
        if indeks not in tutulan:
            tutulan[indeks] = genai.Client(
                api_key=anahtarlar[indeks],
                http_options=types.HttpOptions(
                    timeout=GEMINI_ISTEK_ZAMAN_ASIMI_MS,
                    # Tekrarı havuz yönetir; SDK içinde gizli tekrar yapılmasın.
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return tutulan[indeks]

    fabrika.anahtar_sayisi = len(anahtarlar)
    fabrika.anahtar_kimlikleri = kimlikler
    return fabrika


def _anahtar_kimligi(client_factory, indeks: int) -> str:
    """Kayıttaki anahtar kimliği; kimlik taşımayan (test) fabrikada sıra adı."""
    kimlikler = getattr(client_factory, "anahtar_kimlikleri", None)
    if kimlikler and 0 <= indeks < len(kimlikler):
        return kimlikler[indeks]
    return f"sira{indeks + 1}"


def motor_adi(model: str | None) -> str | None:
    """Künyenin MOTOR alanı: bölümü çeviren sağlayıcı.

    Tek motor kaldı (Gemini), ama alan çağrı yerlerinde SABİT YAZILMAZ. Bir dönem tam
    olarak öyle yapılmıştı ("tek motor kaldığından sabit") ve ikinci bir sağlayıcı
    zincire girince bu doğrudan YANLIŞ bilgiye dönüştü: Mistral'in çevirdiği bölüm
    rozette "GEMINI ile çevrildi" diyordu. Künyeyi üreten DÖRT nokta da bu tek tanımı
    çağırır, böylece motor bir daha değişirse tek satır güncellenir.

    DB'de eski `mistral`/`claude` satırları duruyor; onlar yazıldıkları anda
    saklandığı için etkilenmez (okuyucu rozeti değeri olduğu gibi gösterir).
    """
    if not model:
        return None
    # Parcalar farkli halkalara dusmus olabilir (" + " ile birlesik gelir); sira
    # korunur, tekrar elenir. Claude TEK HALKALI oldugu icin pratikte karisik bir
    # kunye uretmez, ama kural tek yerde dursun diye ayrim burada yapilir.
    return " + ".join(
        dict.fromkeys(
            "claude" if _claude_modeli(m) else "gemini"
            for m in model.split(" + ")
            if m
        )
    ) or None


def ceviri_anahtari_var_mi(api_key: str | None = None) -> bool:
    """Çeviri yapabilecek EN AZ BİR anahtar var mı?

    Kapı, çağrı zincirinden gelen anahtara ek olarak ORTAMI da sayar: ikinci anahtar
    yalnız `.env`'de duruyor olabilir ve onu görmeyen bir kapı, pekâlâ çalışabilecek
    bir kurulumu sebepsiz reddederdi.
    """
    return bool(gemini_anahtarlari(api_key)) or bool(claude_anahtari())

# Parça çıktısı modelin token sınırını aşıp çeviriyi kesmesin diye ölçülü tutulur.
# Büyük parça = daha az kopma noktası = bölüm içinde daha tutarlı üslup; sınırı
# `max_output_tokens` (aşağıda) koruyor, ölçümle 1600'den yükseltildi.
MAX_WORDS_PER_CHUNK = 2800
# Çıktı token tavanı açıkça verilir: varsayılan sınır parçanın ortasında kesilirse
# JSON bozulur ve kurtarma ayrıştırıcısına düşeriz (hizalama kaybı). Türkçe çeviri
# İngilizce kaynaktan ~1.4x token tutar; 2800 kelimelik parça için bolca pay bırakır.
MAX_OUTPUT_TOKENS = 32768
# DÜŞÜNME (thinking) MODELİN VARSAYILANINDA (2026-09-23, sunucu verisiyle ölçüldü).
# `None` = `thinking_config` HİÇ gönderilmez. 2026-09-22'de 0 yapılmıştı: ölçüm
# (yalnız gemini-2.5-flash, iki bölüm) hizalama, sözlük ihlali ve kalıntıyı
# değişmemiş, süreyi 65 -> 19 sn bulmuştu. Bir gün sonra iki arıza çıktı ve
# ikisini de o ölçüm GÖREMEZDİ:
#
#   * KOŞULLU kayıt uygulanamıyor. `Saint -> Aziz [KOŞUL: yalnız rütbe; gölgenin
#     ADI ise İngilizce kalır]` — 2.5-flash'ta gölgenin adı düşünme açıkken 44
#     paragrafın 44'ünde korunmuş, kapalıyken 21'in 5'inde "Aziz" olmuş. Kontrollü
#     A/B (bölüm 667, aynı prompt, tek değişken): bütçe 0 -> beş adın BEŞİ "Aziz",
#     varsayılan -> beşi de "Saint". Uyum denetimi koşullu kayıtları BİLEREK
#     ölçmüyor (`_denetlenebilir_terimler`), yani bu arıza hiçbir sayıya yansımadı.
#   * 3.x ailesinde sözlük uyumu ÇÖKEBİLİYOR — ölçülen model 2.5'ti, zincirin başı
#     3.6. Düşünme kapalıyken 3.6-flash bir bölümde 22 kayıtlı terimi İngilizce
#     bıraktı ("Sanctuary'ye", "Transcendent'a"), 3.5-flash aynı bölümün iki
#     koşusunda 5 ve 33 (rün bloğunu çevirmeden kopyaladı). Düşünme açıkken 3.6'nın
#     209 bölümünde yalnız biri ihlalliydi. Arıza OLASILIKSAL (aynı bölümün
#     kontrollü iki koşusu temiz çıktı), ama tek bozuk koşu kalıcı önbelleğe yazılır.
#
# Bedeli: bölüm başına ~40-60 sn (kapalıyken 12-18 sn) ve çıkışın ~%75'i düşünme
# tokeni. Okumanın gövdesi prefetch'ten geldiği için süre çoğunlukla görünmez.
#
# Sayı verilirse gönderilir (0 = kapalı). Ara değer (ör. 2048) ÖLÇÜLMEDEN
# kullanılmaz: ölçüm KOŞULLU kaydı ve 3.x modelini İÇERMELİ — ilk kapatma tam
# olarak bu iki boşluktan geçti. Claude yolu bu daldan geçmez (`_claude_uret`).
GEMINI_DUSUNME_BUTCESI: int | None = None
# Bölümler arası bağlam: önceki bölümün son kaç kelimelik Türkçesi yeni bölümün ilk
# parçasına verilir (zamir/hitap/sahne sürekliliği bölüm sınırında kopmasın).
PREV_CHAPTER_CONTEXT_WORDS = 160
RETRY_CODES = {500, 503}  # geçici sunucu hatası: aynı modelde tekrar dene
FALLBACK_CODES = {404, 429}  # model yok / kota doldu: bekleme, sıradaki modele geç
MAX_RETRIES = 3
# Canlı kayıtta başarılı çeviriler 30–55 sn; 503 denemeleri ise 29 sn'ye
# çıkıyor. Beş anahtar x üç tur, yedek modele geçmeden dakikalar harcatıyordu.
# Devam eden üretimi kesmeyiz; bütçe dolunca YENİ bir deneme başlatmayız.
GEMINI_ISTEK_ZAMAN_ASIMI_MS = 90_000
MODEL_DENEME_BUTCESI_SN = 60.0
# 503 SOĞUTMASI (2026-09-21, ölçüldü). 503'ün BEDAVA olduğu varsayılıyordu ve
# doygun model ısrarla deneniyordu. Sunucu verisi tersini söyledi: `gemini-3.6-flash`
# beş anahtarın BEŞİNDE de tam 20 denemede 429'a çarptı (ücretsiz günlük sınır
# 20/proje/model) ve o denemelerin neredeyse tamamı 503'tü — gün boyu 103 deneme
# harcandı, 2 bölüm çevrildi. Yani 503 dönen istek de günlük kotadan SAYILIYOR:
# doygun model kendi kotasını yakıyor ve akşam toparladığında kullanılamıyor.
#
# Süre ÜSTEL artar, çünkü doygunluk saatlerce sürebiliyor ama ara ara açılıyor
# (aynı gün 09:44-19:38 sürekli 503, arada 13:31'de bir başarı). Sabit kısa süre
# kotayı yakar, sabit uzun süre toparlanma anını kaçırır; üstel artış ilk denemeyi
# yakın tutar, ısrar eden doygunlukta aralığı açar. BAŞARIDA sayaç sıfırlanır —
# tek bir kötü dalga günün kalanında modeli sebepsiz uzakta tutmamalı.
GECICI_SOGUMA_TABAN_SN = 60.0
GECICI_SOGUMA_TAVAN_SN = 900.0
# Sözlük bu boyutun altındaysa parçaya süzme yapılmadan tamamı gönderilir.
GLOSSARY_FILTER_MIN = 40

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

# Yakın anlamlı sistem terimleri: model bunları birbirine karıştırıp sözlükteki bir
# karşılığı komşu kelimeye taşıyabiliyor (gözlenen: sözlükte "Tier -> Kademe" varken
# "level" de "kademe" çevrildi). Sabit ayrım listesi tutarlılığı bölümden bölüme korur.
# SÖZLÜK bunları EZER (kullanıcı kendi karşılığını yazarsa o geçerli).
CORE_TERM_HINTS = (
    ("level", "seviye"),
    ("tier", "kademe"),
    ("rank", "rütbe"),
    ("grade", "derece"),
    ("stage", "aşama"),
    ("class", "sınıf"),
    ("realm", "diyar"),
    ("skill", "beceri"),
    ("trait", "özellik"),
    ("attribute", "nitelik"),
)
_CORE_HINT_STR = ", ".join(f"{en} -> {tr}" for en, tr in CORE_TERM_HINTS)

# Bir kişiyi ad YERİNE GEÇEREK adlandıran lakap da İngilizce kalır. Gerçek bulgu
# (Shadow Slave 6. bölüm, 2026-08-23): anlatıcı gerçek adını bilmediği kişileri
# özelliklerine göre adlandırıyor (`Scholar`, `Shifty`, `Hero`). Kural "İngilizce
# kalan TEK sınıf gerçek kişi adları, UNVAN çevrilir" derken model bunları harfiyen
# unvan sayıp Türkçeleştirdi (`Kurnaz`, `Bilgin`, `Kahraman`) ve karşılık sözlüğe
# KURAL olarak yazıldı; sonraki bölüm de ona uydu. Model bunları `detected_names`
# kutusuna hiç önermedi, yani süzgeçlerin eleyeceği bir şey yoktu — boşluk kuraldaydı.
#
# Ölçüt DAR tutulur: belirteç ('a/an/the') alan ya da bir SINIFI anlatan sözcük
# lakap DEĞİLDİR. Aksi halde `an Aspirant` / `the Awakened` gibi sistem terimleri de
# İngilizce'ye kaçardı — bu, düzeltmeye çalıştığımız hatadan daha büyük bir zarar.
#
# ÜÇ talimat da (çeviri, okurken terim önerisi, bakım aracının sınıflandırması) bu
# TEK metni kullanır: üçü ayrışırsa aynı kitapta iki farklı politika oluşur.
LAKAP_KURALI = (
    "- LAKAP ÖLÇÜTÜ (ad mı, kategori unvanı mı): sözcük büyük harfle başlıyor, TEK "
    "belirli bir kişiyi gösteriyor ve önünde 'a/an/the' YOKSA cümlede tıpkı bir ad "
    "gibi duruyor demektir -> LAKAPTIR, İngilizce kalır ('Scholar nodded' -> "
    "'Scholar başını salladı'; 'Hero drew his sword' -> 'Hero kılıcını çekti'). "
    "Önünde belirteç varsa YA DA bir sınıfı/kategoriyi anlatıyorsa lakap DEĞİLDİR, "
    "çevrilir ('an Aspirant' -> 'bir Aday', 'the Awakened' -> 'Uyanmışlar', "
    "'a scholar arrived' -> 'bir bilgin geldi'). Aynı sözcük bir cümlede lakap, "
    "başkasında cins isim olabilir; ölçüt BELİRTEÇ ve tek-kişi göndergesidir.\n"
)

SYSTEM_INSTRUCTION = (
    "Sen profesyonel bir İngilizce'den Türkçe'ye web roman çevirmenisin.\n"
    "Kurallar:\n"
    "- Akıcı, doğal, edebi Türkçe üret. Birebir değil, anlamı koru.\n"
    # Ölçülen arıza (2026-09-05, shadow-slave önbelleği): hizalama TUTTUĞU hâlde
    # tek tek paragraflar İngilizce dönüyordu — #179/#181/#188 tam, #58/#177/#194
    # cümle başındaki bağlaç ya da yardımcı fiil kalıntısı. Prompt paragraf
    # DÜZENİNİ ("her paragrafın başına [[n]] koy") şart koşuyordu ama hiçbir
    # maddesi paragrafın ÇEVRİLMİŞ olmasını istemiyordu: model işaretçiyi doğru
    # koyup metni olduğu gibi kopyalayınca hiçbir kural çiğnenmiş olmuyordu.
    "- HİÇBİR paragrafı, cümleyi ya da cümle parçasını İngilizce BIRAKMA; kaynak "
    "metni olduğu gibi KOPYALAMA. Her [[n]] paragrafının karşılığı TÜRKÇE olmalı. "
    "Bu kural cümle başındaki bağlaçları ve yardımcı fiilleri de kapsar: 'But' -> "
    "'Ama', 'Then' -> 'Sonra', 'And' -> 'Ve'. İngilizce 'was/were/did' gibi "
    "yardımcı fiiller Türkçede EKE dönüşür, olduğu gibi bırakılmaz ('Was Neph "
    "working?' -> 'Neph çalışıyor muydu?'; 'Was Neph çalışıyor muydu?' YANLIŞTIR). "
    "Tek istisna yukarıdaki KİŞİ ADLARI kuralıdır.\n"
    # Gerçek vaka (shadow-slave #201): `ten times` -> `ten kat`. Model ölçü
    # sözcüğünü çevirdi, sayıyı bırakti. Sayı hatası ötekilerden PAHALI: cümlenin
    # anlamını değiştirir ve okurken "ten kat" gözden kaçabilir.
    "- SAYILARI da çevir: 'ten times' -> 'on kat', 'three days' -> 'üç gün', "
    "'a hundred' -> 'yüz'. İngilizce sayı sözcüğünü ('one, two, ten, hundred, "
    "thousand') olduğu gibi bırakma. Tek istisna sayının bir ÖZEL ADIN parçası "
    "olmasıdır (Nine Dragons Emperor, Ninth Heaven) — orada ad kuralı geçerlidir.\n"
    # Gerçek bulgu (bölüm 1862): "turn the tables on them" → "masaları onlara karşı
    # çevirecekti". Genel "birebir değil" maddesi bunu tutmadı; deyimler AYRI ve
    # örnekli bir kural istiyor.
    "- DEYİMLERİ VE KALIP İFADELERİ KELİME KELİME ÇEVİRME. Türkçedeki karşılığını "
    "kullan; karşılığı yoksa anlamını açık Türkçeyle yaz. Örnekler: 'turn the tables "
    "(on someone)' -> 'durumu tersine çevirmek / işi onların aleyhine döndürmek' "
    "('masaları çevirmek' YANLIŞ); 'break the ice' -> 'buzları eritmek'; 'in his "
    "shoes' -> 'onun yerinde'; 'call it a day' -> 'paydos etmek'; 'the ball is in "
    "your court' -> 'sıra sende'. ÖLÇÜT: kurduğun Türkçe cümleyi bağlamı bilmeyen "
    "biri okuduğunda 'bu ne demek şimdi' diyorsa kalıbı birebir çevirmişsindir; "
    "o cümleyi anlamıyla yeniden yaz.\n"
    "- İngilizce korunacak TEK sınıf: bir KİŞİYİ ADLANDIRAN ifadeler. İkisi de "
    "girer: gerçek adlar (Sunny, Kim Dokja, Nephis) ve gerçek adı bilinmeyen birini "
    "ad YERİNE GEÇEREK adlandıran lakaplar (Scholar, Shifty, Hero). Başka hiçbir "
    "özel ad İngilizce kalmaz.\n"
    + LAKAP_KURALI +
    "- Büyü, beceri, sınıf, ırk, KATEGORİ UNVANI, eşya, YER, LONCA/klan/birlik/örgüt ve "
    "sistem/dünya terimlerini İngilizce BIRAKMA; Türkçe'ye çevir (Spell -> Büyü, "
    "Nightmare -> Kabus, Skill -> Beceri, Zero Wing -> Sıfır Kanat gibi). Bir "
    "kelimenin büyük harfle başlaması onu korumak için sebep DEĞİLDİR.\n"
    "- Yer ve lonca adlarını çevirirken kelimeleri UYDURMA biçimde birleştirme: "
    "'Lightshadow City' -> 'Işıkgölge Şehri' (doğru), 'Işıkölge' (YANLIŞ). "
    "Türkçe karşılık gerçek Türkçe kelimelerden kurulmalı.\n"
    "- Bir lonca/örgüt adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "geri kalanı çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- SÖZLÜK bir eşlemedir (kaynak -> karşılık). Uygulama kuralları:\n"
    "  * Karşılığı YALNIZCA kaynak terimin KENDİSİ metinde geçtiğinde kullan; "
    "çoğul/iyelik hâli de sayılır (Tier, Tiers, Tier's).\n"
    "  * Kaynak terim metinde FARKLI YAZILMIŞ olabilir: bitişik, tireli, fazladan "
    "boşluklu ya da başka büyük-küçük harflerle ('Ore Empire' ~ 'OreEmpire' ~ "
    "'Ore-Empire' ~ 'ORE EMPIRE'). Hepsi AYNI terimdir; karşılığı yine uygula ve "
    "detected_terms'te sözlükteki yazımı kullan.\n"
    "  * Karşılığı BAŞKA bir kelimeye ASLA taşıma. Eşanlamlı ve yakın anlamlı "
    "kelimeler sözlüğe DAHİL DEĞİLDİR: sözlükte 'Tier -> Kademe' varsa 'level' "
    "yine 'seviye' olarak çevrilir, 'kademe' DEĞİL.\n"
    "  * Karşılık cümlede ek almalıysa Türkçe ekini DOĞRU getir (aşağıdaki EK KURALI).\n"
    # Ölçülen arıza (2026-09-11, shadow-slave #376/#378/#380/#381): `Saint -> Aziz`
    # kayıtlı ve prompt'a giriyordu, model yine de bölümden bölüme farklı çeviriyordu.
    # `Saint` metinde hem bir rütbe hem bir varlığın adı olarak geçiyor; model onu
    # ad gördüğü an "İngilizce korunacak TEK sınıf" kuralına sığınıyordu. Sözlüğün
    # o istisnayı EZİP EZMEDİĞİ hiçbir yerde yazmıyordu — oysa aynı prompt sistem
    # terimleri için önceliği açıkça söylüyor. Boşluk KURALDAYDI, modelde değil.
    "  * Sözlükte KENDİNDEN FARKLI bir karşılıkla kayıtlı bir ad, bir KİŞİYİ ya da "
    "bir varlığı adlandırıyor GİBİ GÖRÜNSE BİLE sözlük karşılığıyla çevrilir; "
    "yukarıdaki KİŞİ ADLARI istisnası onu kurtarmaz. İngilizce kalacak adlar "
    "sözlükte kendi yazımıyla durur (Sunny -> Sunny); karşılık kaynaktan "
    "farklıysa o ad bilerek Türkçeleştirilmiştir.\n"
    # Aynı İngilizce sözcüğün bağlama göre iki karşılığı olabiliyor (ölçülen vaka:
    # `Great` hem Kabus Yaratığı rütbesi hem gündelik "Great!" ünlemi). Koşulsuz
    # bir kayıt modele "her yerde bunu yaz" der ve ünlemleri de bozardı.
    "  * Bir satırda [KOŞUL: ...] varsa karşılık YALNIZ o koşul sağlandığında "
    "geçerlidir. Koşul sağlanmıyorsa o kelimeyi bağlama göre normal çevir; "
    "sözlük karşılığını ZORLAMA.\n"
    "  * Kaynak çoğul veya iyelikse karşılık da Türkçe'de çoğul/iyelik olur "
    "(Tiers -> Kademeler; the Tier's power -> Kademenin gücü).\n"
    "  * İngilizce korunan özel isim ek alırken kesme işareti kullan ve eki "
    "okunuşa göre seç (Sunny'nin, Sunny'ye, Kim Dokja'yı, Nephis'in).\n"
    f"- Yakın anlamlı sistem terimlerini BİRBİRİNE KARIŞTIRMA; her biri ayrı "
    f"çevrilir: {_CORE_HINT_STR}. Bu listede olan bir kelime için SÖZLÜK'te farklı "
    "bir karşılık verilmişse SÖZLÜK geçerlidir.\n"
    # Gözlenen hata: "Blackwater farklı bir seviyeindeydi" (doğrusu: seviyesindeydi).
    # Ek kuralı yalnız SÖZLÜK maddesinin altındaydı; yukarıdaki sistem terimlerini
    # ve metnin geri kalanını kapsamıyordu. Artık bağımsız ve kaynaştırma ünsüzü açık.
    "- EK KURALI (sözlük karşılıkları, yukarıdaki sistem terimleri ve METNİN TAMAMI "
    "için geçerlidir): Ünlüyle biten bir köke ünlüyle başlayan ek gelirse ARAYA "
    "KAYNAŞTIRMA ÜNSÜZÜ girer — iyelikte 's', ilgi hâlinde 'n', yönelmede 'y': "
    "seviye -> seviyesi / seviyenin / seviyeye / seviyesinde; kademe -> kademesi / "
    "kademenin / kademeye; beceri -> becerisi / becerinin / beceriye. "
    "'seviyei', 'seviyein', 'seviyeinde', 'kademein', 'becerii' gibi kaynaştırmasız "
    "biçimler YANLIŞTIR ve ASLA yazılmaz. Ünlü uyumuna ve ünsüz yumuşamasına da uy, "
    "kökü bozma (Kabus -> Kabusu / Kabuslar).\n"
    "- ÖNCEKİ ÇEVİRİ verilirse onu TEKRAR çevirme; yalnızca devamlılık için kullan: "
    "anlatım kişisi, kip ve hitap düzeyi (sen/siz) oradan devam etmeli — bölüm başında "
    "üslup değiştirme.\n"
    "- METİN paragrafları [[n]] ile numaralıdır. Çeviride HER paragrafın başına AYNI "
    "[[n]] işaretini koy; hiçbir işareti ATLAMA, BİRLEŞTİRME veya sırasını DEĞİŞTİRME. "
    "Bir İngilizce paragraf bir Türkçe paragrafa karşılık gelir.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"translation": "[[1]] ...\\n\\n[[2]] ...", '
    '"detected_names": ["..."], '
    '"detected_terms": {"İngilizce özel ad": "Türkçe karşılığı"}}\n'
    "- detected_names: metinde geçen KİŞİLERİ adlandıran ifadeler — gerçek adlar VE "
    "yukarıdaki LAKAP ÖLÇÜTÜ'nü geçen lakaplar, İngilizce yazımıyla (çeviride de "
    "İngilizce kalan tek sınıf bunlardır). Buraya bir KİŞİYİ ADLANDIRMAYAN hiçbir "
    "şeyi yazma: lonca/klan, şehir, krallık, imparatorluk, kale, eşya, beceri, ırk, "
    "kategori unvanı, canavar türü buraya girerse kitabın sözlüğüne İngilizce olarak "
    "çakılır ve sonraki bölümlerde de Türkçeye çevrilemez. Bir KİŞİYİ mi adlandırıyor "
    "diye tereddüt ediyorsan detected_names'e DEĞİL detected_terms'e yaz.\n"
    "- detected_names'teki her ad çeviri metninde de AYNEN İngilizce yazımıyla "
    "geçmelidir. Çeviride Türkçeleştirdiğin bir adı buraya YAZMA ve buraya asla "
    "Türkçe kelime koyma (Türkçeleştirdiysen yeri detected_terms'tir).\n"
    "- detected_terms: metinde geçen DİĞER TÜM ÖZEL ADLAR — hiçbirini atlama: yer "
    "(şehir/imparatorluk/kale/bölge/diyar), lonca/klan/birlik/örgüt, EŞYA ve eser "
    "ve silah, BECERİ/büyü/teknik/yetenek, kategori unvanı, ırk/tür, sınıf, adı olan canavar, "
    "olay/kurum ve sistem/dünya terimi. Anahtar İngilizce özgün ad, değer senin "
    "çeviride KULLANDIĞIN Türkçe karşılık "
    "(\"Puppeteer's Shroud\" -> \"Kuklacının Örtüsü\", "
    '"Zero Wing" -> "Sıfır Kanat", "Lightshadow City" -> "Işıkgölge Şehri").\n'
    "- ÖLÇÜT: metinde BÜYÜK HARFLE başlayarak o dünyaya ait belirli bir şeyi "
    "adlandıran her ifade detected_terms'e girer; sıradan cins isim (a sword, the "
    "city) girmez ama adlandırılmış hâli (the Sword of Dawn) GİRER. Birden çok "
    "kelimeli adı BÜTÜN olarak ver, parçalama.\n"
    "- HİYERARŞİ İSTİSNASI: metnin sıralı bir düzenin adlandırılmış BASAMAĞI olarak "
    "kullandığı ad (canavar rütbesi, güç kademesi, tehlike derecesi) KÜÇÜK harfle "
    "yazılmış olsa bile detected_terms'e girer. Bu dizilerin yazımı kitap içinde "
    "tutarsızdır ve büyük harf ölçütü onları kaçırır. AYIRT EDİCİ: ad bir DİZİ "
    "hâlinde sayılıyorsa ya da bir düzene bağlanıyorsa ('lowest to highest', "
    "'rank of', 'above/below the ...') basamaktır ve girer; düzene bağlanmadan, "
    "tek başına geçen sıradan cins isim girmez.\n"
    "- detected_terms'te çeviride ne yazdıysan burada AYNISINI ver; ikisi tutmazsa "
    "sözlük bozulur. Böyle bir ad yoksa boş bırak."
)

# Paragraf hizalama işaretçisi: [[1]], [[ 2 ]] gibi. Çeviride korunur → her Türkçe
# paragrafı kaynak İngilizce paragrafıyla eşler (sayı tutmasa bile hizalama bozulmaz).
MARKER_RE = re.compile(r"\[\[\s*(\d+)\s*\]\]")


class TranslateError(Exception):
    """Çeviri kalıcı olarak başarısız olduğunda fırlatılır (model meşgul, kota vb.)."""


class _Retryable(Exception):
    """İç sinyal: bu anahtar/model denemesi başarısız — çağıran nereye düşeceğine karar verir.

    Taşınan bayraklar düşme YÖNÜNÜ belirler (`_generate_once_with_retry`):
      * ``kota``      429 — sıradaki ANAHTAR, ve bu anahtar soğumaya alınır.
      * ``gecici``    500/503/taşıma — sıradaki ANAHTAR, soğutma YOK.
      * ``yok``       404 — sıradaki ANAHTAR (model erişimi PROJE başınadır),
        havuz tükenince sıradaki MODEL. Soğutma ve bekleme YOK.
      * (bayraksız)   engellenmiş / anahtarsız — sıradaki MODEL.
      * ``blocked``   içerik filtresi; hata mesajını değiştirir.
      * ``anahtarsiz`` bu halkada hiç anahtar yoktu; hata mesajını değiştirir.
    """


def translate_chapter(
    text: str,
    api_key: str,
    glossary: dict[str, str] | None = None,
    models: tuple[str, ...] | None = None,
    prev_context: str = "",
    kosullar: dict[str, str] | None = None,
) -> dict:
    """Tüm bölümü parçalayıp çevirir; bağlamı taşır, yeni isimleri biriktirir.

    İşaretçi (``[[n]]``) ile paragraf-hizalı üretir: dönen ``translation`` ve ``source``
    AYNI ``\\n\\n`` paragraf sayısına sahiptir (i. Türkçe paragraf <-> i. İngilizce
    paragraf). Bir parçada hizalama tutmazsa o parça tek blok olur ve ``source`` None
    döner (çeviri yine de tam; iki-dilli o bölümde devre dışı).

    ``prev_context``: ÖNCEKİ BÖLÜMÜN son Türkçe metni. İlk parçanın bağlamı olur —
    parçalar arası devamlılık zaten taşınıyordu ama bölüm sınırında sıfırlanıyor,
    sahnenin ortasında biten bir bölümün devamı bağlamsız çevriliyordu.

    Döner: {"translation": str, "source": str|None, "detected_names": list[str],
            "detected_terms": dict[str, str], "chunk_count": int, "engine": str}

    ``detected_names`` karakter adlarıdır (İngilizce kalır); ``detected_terms``
    karakter dışı TÜM özel adlardır (kaynak -> modelin kullandığı Türkçe karşılık).

    ``engine`` dönüşte hep "gemini": tek motor var, ama alan bölüm künyesinin
    (`chapters.engine`) parçası ve DB'de eski kayıtlar başka değer taşıyor.
    """
    glossary = dict(glossary or {})
    models = models or secili_zincir()
    chunks = _split_paragraphs(text)

    client_factory = _gemini_fabrikasi(api_key)

    tr_paras: list[str] = []
    en_paras: list[str] = []
    new_names: set[str] = set()
    new_terms: dict[str, str] = {}
    # Kullanılan modeller: sıra korunur, tekrar elenir (dict anahtarı). Bölümün
    # parçaları farklı halkalara düşmüş olabilir; künye hepsini göstermeli.
    used_models: dict[str, None] = {}
    prev_tail = _tail_words(prev_context, PREV_CHAPTER_CONTEXT_WORDS)
    aligned = True

    for chunk in chunks:
        chunk_en = [p.strip() for p in chunk.split("\n\n") if p.strip()]
        result = _translate_chunk(
            client_factory, models, chunk_en, glossary, prev_tail, kosullar,
        )
        if result.get("model"):
            used_models[result["model"]] = None
        for name in result["detected_names"]:
            if name and name not in glossary:
                new_names.add(name)
        # Karakter dışı özel adlar Türkçe karşılığıyla sabitlenir; ilk gören kazanır
        # (bölüm içinde tekrar gelirse ilki korunur), sözlükteki kullanıcı kaydı hep üstün.
        for kaynak, hedef in (result.get("detected_terms") or {}).items():
            if kaynak and hedef and kaynak not in glossary:
                new_terms.setdefault(kaynak, hedef)
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

    # Kaynakta hiç geçmeyen anahtarlar (model uydurması) sözlüğe girmemeli. Terimler
    # ÖNCE süzülür: `ayikla_karakter_adlari` 1. elemesinde bu listeyi kullanıyor,
    # elenmiş bir anahtarın karakter adını sessizce kurtarması istenmez.
    # İNGİLİZCE KALAN paragrafları onar. Hizalama tutmadıysa ölçüt uygulanamaz:
    # hangi Türkçe paragrafın hangi İngilizce paragrafa karşılık geldiği bilinmiyor.
    kalinti: dict[int, str] = {}
    if aligned:
        kalinti = ingilizce_kalinti(tr_paras, en_paras, glossary)
        if kalinti:
            # Onarım turu AYRI aşama olarak kaydedilir: "bölüm başına kaç istek"
            # sorusu ancak böyle cevaplanır (onarım da kotadan düşer).
            with api_durum.baglam(asama="kalinti_onarimi"):
                kalinti = _kalintiyi_onar(
                    client_factory, models, tr_paras, en_paras, kalinti,
                    glossary, used_models, new_names, new_terms, kosullar,
                )
        # SÖZLÜK ihlalini de onar. Tespit tek başına yetmiyordu: bayrak künyeye
        # yazılıp okuyucuda ⚠ çıkıyor ama çeviri kalıcı önbelleğe bozuk giriyor
        # ve önbellek isabeti bir daha çeviri tetiklemediği için kullanıcı o
        # terimi SONSUZA DEK İngilizce görüyordu (shadow-slave #376/#378/#381).
        # Kalıntı onarımından SONRA koşar: o tur paragrafı zaten yenilemiş
        # olabilir, önce ölçmek boşa bir istek attırırdı.
        ihlalli = sozluk_ihlali_paragraflari(glossary, tr_paras, en_paras, kosullar)
        if ihlalli:
            with api_durum.baglam(asama="sozluk_onarimi"):
                _paragraflari_yeniden_cevir(
                    client_factory, models, tr_paras, en_paras, sorted(ihlalli),
                    glossary, used_models, new_names, new_terms, kosullar,
                )

    new_terms = ayikla_terim_anahtarlari(new_terms, text)
    translation = "\n\n".join(tr_paras)
    return {
        "translation": translation,
        "source": "\n\n".join(en_paras) if aligned else None,
        # Süzgeç ŞART: model karakter olmayan adları (lonca, şehir, eşya) düzenli
        # olarak bu kutuya sızdırıyor ve oraya düşen her ad sözlüğe İNGİLİZCE
        # çakılıyor (`merge_names`, X -> X) — kitap boyunca çevrilemez hâle gelir.
        "detected_names": ayikla_karakter_adlari(
            sorted(new_names), new_terms, translation, text
        ),
        "detected_terms": new_terms,
        # Künye: bölümü FİİLEN çeviren model(ler). Parçalar farklı halkalara düştüyse
        # hepsi yazılır ("… + …"); boş bölümde (hiç parça yok) None.
        "model": " + ".join(used_models) or None,
        # Onarımdan SONRA hâlâ İngilizce kalan paragraflar. Boş = temiz. Künyeye
        # yazılır ve okuyucuda ⚠ ile görünür; sessiz kalmak, kullanıcının bir
        # daha asla çeviri tetiklemeyecek bozuk bir önbellek satırıyla kalması
        # demekti.
        "ingilizce_kalinti": kalinti,
        # Onarımdan SONRA hâlâ sözlüğe uymayan terimler. Ölçüt bilerek BÖLÜM
        # geneli ve hizalamadan BAĞIMSIZ: onarım hizalama ister (hangi paragraf
        # bozuk?), denetim istemez (düz metin karşılaştırması). Hizalama
        # tutmadığında bayrağı düşürmek, kullanıcının bozuk bir bölümü hiçbir
        # uyarı görmeden okuması demekti.
        "glossary_leaks": sozluk_ihlalleri(
            glossary,
            "\n\n".join(en_paras) if aligned else text,
            translation,
            kosullar,
        ),
        "chunk_count": len(chunks),
        # MOTOR fiilen çeviren model(ler)den türetilir. Sabit "gemini" yazmak,
        # Mistral zincirin ilk halkası olduğundan doğrudan yanlış bilgiydi:
        # Mistral'in çevirdiği bölüm rozette "GEMINI ile çevrildi" diyordu.
        "engine": motor_adi(" + ".join(used_models)),
    }


# Türkçe'ye özgü harfler: İngilizce KALACAK bir karakter adı bunları içermez.
# Gerçek bulgu: model `detected_names`'e "Kızıl Alev Kalesi" ve "Dark Oyuncular"
# yazdı, ikisi de sözlüğe "İngilizce korunacak" diye girdi.
_TR_HARF_RE = re.compile(r"[çğıİöşüÇĞÖŞÜ]")


def kaynakta_gecen(terim: str, kaynak: str, cogul_esnek: bool = False) -> bool:
    """Terim İNGİLİZCE kaynak metinde geçiyor mu (varyant + çekim toleranslı).

    Kaynak boşsa DAİMA True. Doğrulayamadığımız kaydı atmak, o adı "her bölümde
    yeniden karar" durumuna geri döndürür — sözlüğün var oluş sebebinin tersi.
    Eski önbellek satırlarında `source_text` NULL olabilir; orada eleme yapılmaz.

    Arama `_term_regex` ile: düz `in` kontrolü kesme işareti varyantını
    (``Heaven's Burial`` ~ ``Heaven’s Burial``, ölçülmüş gerçek vaka) kaçırır ve
    MEŞRU terimi eler.
    """
    if not (kaynak or "").strip() or not (terim or "").strip():
        return True
    return bool(_term_regex(terim, cogul_esnek).search(kaynak))


def ayikla_terim_anahtarlari(
    terms: dict[str, str], kaynak: str
) -> dict[str, str]:
    """`detected_terms` anahtarlarından kaynakta geçmeyenleri (uydurma) at.

    Aynı gerekçe `detected_names` süzgecindeki 4. elemeyle ortak: model kaynakta
    hiç bulunmayan bir adı anahtar yapabiliyor (ölçüm: başka kitapların
    karakterleri sözlüğe düşmüştü). Kaynak yoksa hiçbir şey elenmez.
    """
    # Terimlerde çoğul esnek: model `Evil Beasts` bildirip kaynakta `Evil Beast`
    # geçiyorsa MEŞRU kaydı elemek, onu her bölümde yeniden karar konusu yapardı.
    # Şüphede kaydı bırakmak, kaybetmekten ucuzdur.
    return {
        k: v
        for k, v in (terms or {}).items()
        if kaynakta_gecen(k, kaynak, cogul_esnek=True)
    }


def ayikla_karakter_adlari(
    names: list[str], terms: dict[str, str], translation: str, kaynak: str = ""
) -> list[str]:
    """`detected_names`'ten gerçekten İngilizce kalan KİŞİ adlarını süz.

    Bu kutuya düşen her ad sözlüğe `X -> X` diye girer (`glossary.merge_names`) ve
    sözlük prompt'ta KURALdır: bir daha asla Türkçeye çevrilmez. Model ise kutuyu
    düzenli olarak karakter dışı adlarla dolduruyor — kullanıcının ölçtüğü sonuç,
    "karakter dışı her özel ad Türkçe olsun" kuralına rağmen sözlüğün İngilizce
    kayıtlarla dolması (`Blackwater Guild`, `Star-Moon Kingdom`, `Ancient Rock City`).

    Üç eleme, hepsi de modelin KENDİ çıktısına dayanır (tahmin/sözlük listesi yok):

    1. Ad `detected_terms`'te de varsa → Türkçe karşılık kazanır (orası daha bilgili).
    2. Ad Türkçe'ye özgü harf içeriyorsa → zaten Türkçeleştirilmiş, İngilizce sayma.
    3. Ad çeviri metninde AYNEN geçmiyorsa → model onu çeviride Türkçeleştirmiş
       demektir; `X -> X` yazmak modelin kendi kararıyla çelişir ve sonraki
       bölümleri İngilizceye zorlar.
    4. Ad İNGİLİZCE KAYNAKTA geçmiyorsa → İngilizce bir ad değildir. 1-3 bunu
       kaçırıyordu: model çevirdiği adı Türkçe hâliyle bu kutuya yazınca
       (ölçüm: `Bilgin`, `Kurnaz` — `Scholar`/`Shifty`'nin Türkçesi, kaynakta
       0 bölüm) 2. eleme saf-ASCII oldukları için, 3. eleme çeviride gerçekten
       geçtikleri için geçiriyordu. Kaynak verilmezse bu eleme koşmaz.

    Karşılaştırma `fold_term` üzerinden: Türkçe ek/yazım varyantı ("Nephis'in",
    "OreEmpire") adı elemesin.
    """
    ceviri = fold_term(translation)
    terim_anahtarlari = {fold_term(k) for k in terms}
    ayikli: list[str] = []
    for ad in names:
        anahtar = fold_term(ad)
        if not anahtar or anahtar in terim_anahtarlari:
            continue
        if _TR_HARF_RE.search(ad):
            continue
        if anahtar not in ceviri:
            continue
        if not kaynakta_gecen(ad, kaynak):
            continue
        ayikli.append(ad)
    return ayikli


SUGGEST_INSTRUCTION = (
    "Sen bir İngilizce→Türkçe web roman çevirmenisin. Sana bir ÖZEL AD ve geçtiği "
    "cümle verilecek; bu adın kitap sözlüğüne nasıl kaydedileceğine karar ver.\n"
    "Kural (çeviri sözlüğünün kuralıyla AYNI):\n"
    "- Ad bir KİŞİYİ adlandırıyorsa İngilizce KALIR: karşılık, adın kendisidir. "
    "Gerçek ad da (Sunny) ad yerine geçen lakap da (Scholar, Shifty) bu sınıftadır.\n"
    + LAKAP_KURALI +
    "- Başka her özel ad (yer, şehir, imparatorluk, lonca/klan/örgüt, eşya, silah, "
    "beceri/büyü/teknik, kategori unvanı, ırk, adlandırılmış canavar, sistem/dünya terimi) "
    "TÜRKÇE'ye çevrilir; karşılık o Türkçe biçimdir.\n"
    "- Bir örgüt/yer adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "gerisi çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- Türkçe karşılık GERÇEK Türkçe kelimelerden kurulmalı; kelimeleri uydurma "
    "biçimde birleştirme ('Lightshadow City' -> 'Işıkgölge Şehri' doğru, 'Işıkölge' "
    "YANLIŞ). Kaynaktaki büyük harf, korunması için sebep DEĞİLDİR.\n"
    "- CÜMLE bağlamı belirleyicidir: aynı sözcük bir kitapta kişi adı, başkasında "
    "yer adı olabilir ('Rain' bir karakter de olabilir, 'yağmur' da).\n"
    '- Yanıtı SADECE şu JSON ile ver: {"is_character": true/false, "target": "..."}\n'
    "- is_character true ise target ADIN KENDİSİDİR (İngilizce yazımıyla, değiştirme)."
)


def suggest_term(
    source: str,
    context: str = "",
    api_key: str = "",
    models: tuple[str, ...] | None = None,
) -> dict:
    """Seçilen özel ad için sözlük karşılığı öner (okuyucudaki hızlı ekleme kısayolu).

    Döner: ``{"source": str, "target": str, "is_character": bool}``.

    Karakter adı → ``target == source`` (İngilizce kalır); başka her özel ad →
    Türkçe karşılık. Bu, `pipeline._sozluge_isle`'ın otomatik davranışının elle
    ekleme yolundaki karşılığıdır: iki yol aynı kuralı uygulamazsa aynı kitapta
    iki farklı politika oluşurdu.
    """
    source = (source or "").strip()
    if not source:
        raise TranslateError("Terim boş.")
    if not ceviri_anahtari_var_mi(api_key):
        raise TranslateError(ANAHTAR_YOK_MESAJI)
    user = (
        f"ÖZEL AD: {source}\n\n"
        f"GEÇTİĞİ CÜMLE (bağlam): {(context or '').strip()[:600] or '(yok)'}"
    )
    response, _model = _generate_with_fallback(
        _gemini_fabrikasi(api_key), models or secili_zincir(), user,
        system=SUGGEST_INSTRUCTION, max_tokens=512,
    )
    try:
        data = json.loads((response.text or "").strip().strip("`"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        data = {}
    is_char = bool(data.get("is_character"))
    hedef = (data.get("target") or "").strip()
    # Karakterde karşılık DAİMA kaynağın kendisi: model "Sunny -> Güneşli" gibi bir
    # şey döndürse bile sözlük kuralı bunu yasaklıyor.
    if is_char or not hedef:
        hedef = source
    return {"source": source, "target": hedef, "is_character": is_char}


CLASSIFY_INSTRUCTION = (
    "Sen bir İngilizce→Türkçe web roman çevirmenisin. Sana bir kitabın SÖZLÜĞÜNDEN "
    "özel ad listesi verilecek; hepsi şu an İngilizce korunuyor. Her ad için bunun "
    "doğru olup olmadığına karar ver.\n"
    "Kural (çeviri sözlüğünün kuralıyla AYNI):\n"
    "- Ad bir KİŞİYİ adlandırıyorsa İngilizce KALIR: karşılık adın kendisidir. "
    "Gerçek ad da (Sunny) ad yerine geçen lakap da (Scholar, Shifty) bu sınıftadır.\n"
    + LAKAP_KURALI +
    "- Başka her özel ad (yer, şehir, imparatorluk, krallık, kale, lonca/klan/örgüt, "
    "eşya, silah, zırh, beceri/büyü/teknik, kategori unvanı, ırk, sınıf, adlandırılmış canavar, "
    "olay, sistem/dünya terimi) TÜRKÇE'ye çevrilir; karşılık o Türkçe biçimdir.\n"
    "- Bir örgüt/yer adının İÇİNDE kişi adı geçiyorsa o kişi adı İngilizce kalır, "
    "gerisi çevrilir ('Wang Lin's Hall' -> 'Wang Lin Salonu').\n"
    "- Türkçe karşılık GERÇEK Türkçe kelimelerden kurulmalı; kelimeleri uydurma "
    "biçimde birleştirme ('Lightshadow City' -> 'Işıkgölge Şehri' doğru, 'Işıkölge' "
    "YANLIŞ). Kaynaktaki büyük harf, korunması için sebep DEĞİLDİR.\n"
    "- KİŞİ Mİ diye emin olamadığın adı KARAKTER say (is_character true): yanlış bir "
    "Türkçeleştirme kitap boyunca birebir uygulanır ve karakterin adını bozar.\n"
    '- Yanıtı SADECE şu JSON ile ver: {"terms": [{"source": "...", '
    '"is_character": true, "target": "..."}]}\n'
    "- source alanını sana verilen yazımla AYNEN geri ver ve listedeki HER ad için "
    "bir kayıt döndür; hiçbirini atlama."
)


def classify_terms(
    terms: list[str],
    api_key: str = "",
    book_title: str = "",
    models: tuple[str, ...] | None = None,
) -> dict[str, dict]:
    """Sözlükte İngilizce korunan adları TOPLU sınıflandır (bakım aracı).

    `suggest_term`'ün liste hâli: `scripts/sozluk_gozden_gecir.py` bununla eski
    kayıtları gözden geçirir. Neden gerek var: `detected_names` süzgeci yalnız
    BUNDAN SONRA çevrilecek bölümleri korur; kitapların sözlüğüne çakılmış eski
    "X -> X" kayıtları (ölçüldü: bir kitapta 201 kaydın 173'ü) prompt'ta KURAL
    olmaya devam eder ve o adlar bir daha asla Türkçeleşmez.

    Döner: ``{kaynak: {"is_character": bool, "target": str}}`` — modelin karşılık
    vermediği ad listeye HİÇ girmez (kaydı olduğu gibi bırakmak, uydurma bir
    karşılıkla değiştirmekten yeğdir).
    """
    temiz = [t.strip() for t in terms if (t or "").strip()]
    if not temiz:
        return {}
    if not ceviri_anahtari_var_mi(api_key):
        raise TranslateError(ANAHTAR_YOK_MESAJI)
    user = (
        (f"KİTAP: {book_title}\n\n" if book_title else "")
        + "ADLAR:\n" + "\n".join(f"- {t}" for t in temiz)
    )
    response, _model = _generate_with_fallback(
        _gemini_fabrikasi(api_key), models or secili_zincir(), user,
        system=CLASSIFY_INSTRUCTION, max_tokens=MAX_OUTPUT_TOKENS,
    )
    try:
        data = json.loads((response.text or "").strip().strip("`").removeprefix("json"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {}
    # Model kaynağı yazım varyantıyla geri verebiliyor → fold ile eşle, ama sözlükteki
    # ÖZGÜN yazımı anahtar yap (set_term o yazımı güncellemeli).
    fold_map = {fold_term(t): t for t in temiz}
    out: dict[str, dict] = {}
    for kayit in data.get("terms") or []:
        if not isinstance(kayit, dict):
            continue
        kaynak = fold_map.get(fold_term(str(kayit.get("source") or "")))
        hedef = str(kayit.get("target") or "").strip()
        if not kaynak or not hedef:
            continue
        is_char = bool(kayit.get("is_character"))
        out[kaynak] = {"is_character": is_char, "target": kaynak if is_char else hedef}
    return out


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


def _tail_words(text: str, count: int) -> str:
    """Metnin son ``count`` kelimesi (bölümler arası bağlam için).

    Cümle sayısıyla değil kelimeyle ölçülür: bir bölümün sonu tek uzun cümle de
    olabilir, otuz kısa replik de — bağlam bütçesi ikisinde de aynı kalmalı."""
    words = (text or "").split()
    if not words:
        return ""
    return " ".join(words[-count:])


# Terim parçalama: aynı özel ad metinde farklı yazımlarla geçebiliyor
# ("Ore Empire" ~ "OreEmpire" ~ "Ore-Empire"). Deseni kelime PARÇALARINDAN kurup
# aralarına esnek ayırıcı koyarız; yoksa sözlükte kayıtlı terim süzmede kaybolur,
# prompt'a hiç girmez ve model o adı her bölümde yeniden çevirir (gerçek bulgu).
_TERM_SEP_RE = re.compile(r"[\s\-_'’.·]+")
# Ters yön: sözlükte BİTİŞİK kayıtlı terim ("OreEmpire") metinde ayrık geçebilir.
# İç büyük harf sınırından bölünür; tek parçalı ad ("Blackwater") bölünmez.
_CAMEL_RE = re.compile(r"[A-ZÇĞİÖŞÜ]?[a-zçğıöşü]+|[A-ZÇĞİÖŞÜ]+(?![a-zçğıöşü])|\d+")
_TERM_GLUE = r"[\s\-_'’]*"  # parçalar arası: hiç, boşluk, tire, alt çizgi…


def _term_parts(term: str) -> list[str]:
    """Terimi eşleştirilebilir kelime parçalarına ayırır (ayırıcı + CamelCase)."""
    parts = [p for p in _TERM_SEP_RE.split(term.strip()) if p]
    if len(parts) == 1:
        camel = _CAMEL_RE.findall(parts[0])
        # Eşitlik şartı: bölme kayıpsız olmalı, aksi halde ad bozulur.
        if len(camel) > 1 and "".join(camel) == parts[0]:
            return camel
    return parts


# Anahtarın SONUNDAKİ çoğul ekini isteğe bağlı kılmak için en az bu kadar kök kalmalı.
# Kısa köklerde ("Os" -> "O") eşleşme sıradan harflere bulaşırdı.
MIN_COGUL_KOK = 3


# Cumle ayirici: nokta/unlem/soru/uc-nokta + bosluk. Kisaltma ("Dr.") yanlis
# bolebilir ama koken cumlesi bir KUNYE bilgisidir, bir cumle bir fazla ya da
# eksik olmasi bilgiyi bozmaz — karmasik bir cumle ayirici bu is icin fazla.
_CUMLE_AYIRICI = re.compile(r"(?<=[.!?…])\s+")
# Kokene giden cumle kirpilir: sozluk ekraninda satir alti bir kunye satiri, alinti degil.
KOKEN_CUMLE_MAX = 300


def cumle_bul(metin: str, terim: str) -> str | None:
    """`terim`in metinde GECTIGI ilk cumle; yoksa None.

    Terim eslestirme `_term_regex` ile yapilir — sozlugun her yerinde kullanilan
    AYNI olcut. Duz `in` aramasi yazim varyantini (Ore-Imparatorlugu) kacirir ve
    kayitli bir terim icin koken cumlesi bulunamazdi.
    """
    metin = (metin or "").strip()
    terim = (terim or "").strip()
    if not metin or not terim:
        return None
    try:
        desen = _term_regex(terim)
    except re.error:
        return None
    for satir in metin.splitlines():
        for cumle in _CUMLE_AYIRICI.split(satir):
            c = cumle.strip()
            if c and desen.search(c):
                return c[:KOKEN_CUMLE_MAX]
    return None


@lru_cache(maxsize=2048)
def _term_regex(term: str, cogul_esnek: bool = False) -> re.Pattern[str]:
    """Terimi kelime-sınırlı, çekim ekine ve YAZIM VARYANTINA toleranslı arayan desen.

    ``Tier`` deseni ``Tier``, ``Tiers``, ``Tier's`` ile eşleşir; ``Tiernan`` ile
    eşleşmez. ``Ore Empire`` deseni ``OreEmpire`` ve ``Ore-Empire`` ile de eşleşir
    (parçalar arası ayırıcı serbest). Alfanümerik olmayan uçlarda ``\\b`` eşleşmeyi
    öldüreceğinden koşullu.

    ``cogul_esnek``: ANAHTARIN sonundaki çoğul ekini de isteğe bağlı yapar. Kuyruk
    eki (``s?``) çoğulu EKLİYOR ama ÇIKARMIYORDU, yani **çoğul kaydedilmiş bir terim
    tekilini asla yakalayamıyordu** — kayıt sözlükte durduğu hâlde prompt'a hiç
    girmiyordu. Ölçülen vaka (2026-08-23): ``tyrants -> Tiranlar`` kaydı varken metinde
    ``tyrant`` 22 kez tekil, 2 kez çoğul geçiyordu; 24 geçişin 22'si kaçtı ve model
    ``the Tyrant``ı serbestçe çevirdi.

    Gerçek sözlükte ölçüldü: ``s`` ile biten 53 kaydın 17'sinin kökü metinde geçiyor
    ve **17'si de meşru tekil/çoğul çifti** (``Evil Beast``/``Evil Beasts``,
    ``Hell Tank``/``Hell Tanks``) — bu veride yanlış eşleşme yok.

    Yine de VARSAYILAN KAPALI ve çağıran yalnız TÜRKÇE KARŞILIKLI kayıtlarda açar
    (bkz. `_terim_metinde`): risk sınıfı İngilizce korunan KİŞİ adlarıdır (``Nephis``
    -> ``Nephi``), ve orada yanlış eşleşmenin bedeli sıradan bir sözcüğü İngilizce
    bırakmaktır. Yalnız SON ``s`` düşürülür; ``es`` çoğulları (``Witches`` -> ``Witch``)
    kapsam dışıdır — fazla soymak gerçek bir kökü bozardı, eksik soymak yalnız
    fırsat kaçırır.
    """
    parts = _term_parts(term)
    if not parts:
        return re.compile(r"(?!)")  # hiçbir şeyle eşleşmeyen desen
    if cogul_esnek and parts[-1][-1:].lower() == "s":
        kok = parts[-1][:-1]
        if len(kok) >= MIN_COGUL_KOK:
            parts = parts[:-1] + [kok]  # kuyruktaki `s?` çoğulu geri getirir
    head = r"\b" if parts[0][:1].isalnum() else ""
    tail = r"(?:['’]s|es|s)?\b" if parts[-1][-1:].isalnum() else ""
    core = _TERM_GLUE.join(re.escape(p) for p in parts)
    return re.compile(head + core + tail, re.IGNORECASE)


def _ingilizce_korunan(source: str, target: str) -> bool:
    """Kayıt fiilen "İngilizce korunacak" anlamına mı geliyor (`X -> X`)?

    Karşılaştırma `fold_term` ile: `Ore Empire -> OreEmpire` gibi bir kayıt da
    İngilizce korunuyor demektir. Bakım aracı (`scripts/sozluk_gozden_gecir.py`)
    da aynı ölçütü kullanıyor; iki yerde iki ayrı tanım olması, prompt'un ve
    raporun aynı kayıt için farklı karar vermesine yol açardı.
    """
    return fold_term(source) == fold_term(target or "")


def _terim_metinde(source: str, target: str, text: str) -> bool:
    """Terim metinde geçiyor mu — İngilizce korunan adda KÜÇÜK HARFLİ eşleşme sayılmaz.

    Sebep ölçüldü: `_term_regex` `IGNORECASE` arıyor ve İngilizce korunan tek
    kelimelik adların çoğu sıradan İngilizce kelime (`Dark`, `Blue`, `Sun`,
    `Rain`, `Wind`). Gerçek bölümlerde `Dark` 113, `Blue` 53, `Sun` 5 kez
    SIRADAN kelime olarak eşleşiyordu; her eşleşme "bu ad AYNEN İngilizce
    kalacak" kuralını prompt'a sokuyor ve model sıradan bir sıfatı çevirmiyor.

    Kural YALNIZ İngilizce korunan kayıtlara uygulanır çünkü kaybın yönü
    asimetrik: Türkçe karşılığı olan bir kayıt küçük yazıma uygulanınca doğru
    çeviri çıkar (zararsız), İngilizce korunan kayıt uygulanınca sıradan kelime
    İngilizce kalır (görünür bozukluk).

    Kaynağı TÜMÜYLE küçük harfli kayıt (gerçek örnek: `tls123 -> tls123`, bir
    kullanıcı adı) kural DIŞIDIR — orada büyük harf beklemek kaydı hiç
    eşleşmez hâle getirirdi.

    Düz "büyük-küçük harf duyarlı arama" DEĞİL: "SUNNY!" gibi tümü büyük harfli
    bağırma yazımı da geçerli bir geçiştir, elenmemeli.
    """
    korunan = _ingilizce_korunan(source, target)
    # Çoğul esnekliği YALNIZ Türkçe karşılıklı kayıtlarda: risk sınıfı İngilizce
    # korunan kişi adlarıdır (`Nephis` -> `Nephi`) ve orada yanlış eşleşme sıradan
    # bir sözcüğü İngilizce bıraktırır — pahalı yön.
    desen = _term_regex(source, not korunan)
    if not (korunan and not source.islower()):
        return bool(desen.search(text))
    return any(not m.group(0).islower() for m in desen.finditer(text))


def _denetlenebilir_terimler(
    glossary: dict[str, str] | None,
    kosullar: dict[str, str] | None,
):
    """İhlali ÖLÇÜLEBİLEN sözlük kayıtları (kaynak, karşılık) olarak akar.

    Ölçüt TEK yerde durur: denetim (`sozluk_ihlalleri`) ile onarımın hedefini
    seçen tespit (`sozluk_ihlali_paragraflari`) ayrışırsa, onarım denetimin
    görmediği bir "ihlali" düzeltmeye kalkar ve doğru çeviriyi bozar.
    """
    for source, target in (glossary or {}).items():
        if not source or not target:
            continue
        # KOŞULLU kayıt ölçülemez: karşılık YALNIZ o bağlamda geçerlidir ve
        # koşulun sağlanıp sağlanmadığı deterministik olarak bilinemez. Gerçek
        # vaka (shadow-slave): `Saint -> Aziz [KOŞUL: rütbe anlamında]` kayıtlı
        # iken terim gölge kölesinin ADI olarak geçip İngilizce kaldığında bu
        # DOĞRU çeviridir — koşulu yok sayan denetim sahte bir ⚠ üretir ve
        # otomatik onarım özel adı zorla Türkçeleştirirdi.
        if (kosullar or {}).get(source, "").strip():
            continue
        if _ingilizce_korunan(source, target):
            continue
        if _terim_metinde(source, target, target):
            continue  # karşılık kaynağı içeriyor: ölçülemez, sahte ihlal üretme
        yield source, target


def sozluk_ihlali_paragraflari(
    glossary: dict[str, str] | None,
    tr_paras: list[str],
    en_paras: list[str],
    kosullar: dict[str, str] | None = None,
) -> dict[int, dict[str, str]]:
    """İhlalin HANGİ paragraflarda olduğunu bulur: {indeks: {kaynak: karşılık}}.

    Onarımın ön koşulu: hizalama tuttuğunda i. Türkçe paragraf i. İngilizce
    paragrafa karşılık gelir, yani bozuk paragraf TAM olarak bilinir ve bölümün
    tamamı değil yalnız o paragraflar yeniden çevrilir.
    """
    if not glossary or not tr_paras or not en_paras:
        return {}
    out: dict[int, dict[str, str]] = {}
    for i, (tr, en) in enumerate(zip(tr_paras, en_paras)):
        ihlal = sozluk_ihlalleri(glossary, en, tr, kosullar)
        if ihlal:
            out[i] = ihlal
    return out


def sozluk_ihlalleri(
    glossary: dict[str, str] | None,
    kaynak: str | None,
    ceviri: str | None,
    kosullar: dict[str, str] | None = None,
) -> dict[str, str]:
    """Türkçe karşılığı kayıtlı olduğu hâlde çeviride İNGİLİZCE kalmış terimler.

    Zincir yalnız ERİŞİLEBİLİRLİĞE bakarak iniyor (kota dolunca bir alt halka) ve
    kaliteyi hiçbir yerde ölçmüyordu. Ölçüm (2026-08-30, Shadow Slave'in
    önbellekteki 110 bölümü): sözlük ihlali oranı 3.6-flash'ta %0,7 ·
    3.5-flash'ta %0,3 · **flash-lite'ta %23,9**. 109. bölümde `Saint -> Aziz`
    kaynakta 12 kez geçti, 12'si de İngilizce kaldı. Lite'ın çevirisi sessizce
    kalıcı önbelleğe yazılıp bir daha kontrol edilmiyordu.

    Denetim deterministiktir ve API çağırmaz — çeviriden sonra bedavaya koşar.
    Ölçüt, prompt'a hangi terimlerin girdiğini belirleyen ölçütle AYNI
    (`_terim_metinde`); ayrışırlarsa prompt'a giren bir terim denetimden kaçardı.

    DÖRT sınıf denetim dışıdır:
      * `X -> X` (İngilizce korunan karakter adları) — İngilizce kalmak ZORUNDA
      * bu bölümün kaynağında hiç geçmeyen kayıtlar
      * karşılığının İÇİNDE kaynağı geçen kayıtlar (`Ore Empire -> Ore Empire
        Krallığı`) — doğru çeviri bile deseni tetikler, ölçülemez
      * KOŞULLU kayıtlar (`[KOŞUL: ...]`) — karşılık yalnız o bağlamda geçerli,
        koşulun sağlanıp sağlanmadığı deterministik olarak ölçülemez

    Döner: kaçan terimlerin {kaynak: karşılık} eşlemesi (boş = uyumlu).
    """
    if not glossary or not kaynak or not ceviri:
        return {}
    ihlal: dict[str, str] = {}
    for source, target in _denetlenebilir_terimler(glossary, kosullar):
        if not _terim_metinde(source, target, kaynak):
            continue
        if _terim_metinde(source, target, ceviri):
            ihlal[source] = target
    return ihlal


# Türkçe'de KARŞILIĞI OLMAYAN İngilizce işlev sözcükleri. Çeviride birinin geçmesi
# o cümlenin (ya da bir parçasının) çevrilmeden kaldığının güçlü işaretidir.
# Liste bilerek DAR: Türkçe'de de var olan yazımlar ELENMİŞTİR. Ölçüm (2026-09-05,
# 21.411 gerçek paragraf) `not` ("not etmişti") ve `has` ("kendine has") yüzünden
# 126 sahte vaka üretmişti; `of` de Türkçe ünlem "Of!" ile çakıştığı için yok.
# Listeyi genişletirken ölçüt: sözcüğün Türkçe bir yazımı VAR MI — varsa girmez.
ISLEV_SOZCUKLERI = frozenset("""
the and but that with was were would could should they them their your from have
had been than then there what when which who will about into over just only even
still down this these those some more most much many very such how why where
while before after again once here never always said asked replied because though
although himself herself itself themselves yourself something nothing anything
everything someone everyone another being having going upon without within through
around against between among behind toward towards already almost enough perhaps
however therefore instead rather quite really actually simply finally suddenly
slowly quickly seemed looked thought knew felt make take took come came went know
think
""".split())

# İngilizce SAYI sözcükleri. AYRI bir sınıf, çünkü `ISLEV_SOZCUKLERI`'nin kuralı
# ("Türkçe yazımı olan sözcük girmez") bunları dışarıda bırakıyordu: `ten` Türkçede
# cilt demek. Oysa sızıntı gerçek ve PAHALI — yanlış kalan bir sayı cümlenin
# anlamını değiştirir (gerçek vaka, shadow-slave #201: `ten times` -> `ten kat`,
# model ölçü sözcüğünü çevirmiş, sayıyı bırakmış).
#
# Ölçüm (21.411 paragraf) bu sınıfın güvenle ayrılabileceğini gösterdi: sayı
# sözcüklerinin 112 geçişinin TAMAMI özel ad parçasıydı (`Solitary Nine`,
# `Ninth Heaven`, `Thousand Transformations`, `Hundred Flowers Pavilion`) ve hepsi
# BÜYÜK harfliydi; tek gerçek sızıntı küçük harfliydi.
SAYI_SOZCUKLERI = frozenset("""
one two three four five six seven eight nine ten eleven twelve thirteen fourteen
fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty
seventy eighty ninety hundred thousand million billion first second third fourth
fifth sixth seventh eighth ninth tenth dozen twice
""".split())

# Blok ölçütü: bu kadar aday token'dan azına BAKILMAZ. Ölçüm, kısa replikte
# (``"Sunny! Sunny! Uyan!"`` ~ ``"Sunny! Sunny! Wake up!"``) oranın DOĞRU çeviride
# bile 0,5-0,67'ye çıktığını gösterdi: özel ad + ünlem paragrafın tamamı oluyor.
KALINTI_MIN_TOKEN = 5
# Ölçülen dağılımda 0,7 ile 1,0 arasında HİÇ paragraf yok — eşik o boşluğa konur.
KALINTI_ORAN = 0.9

_KALINTI_TOK = re.compile(r"[A-Za-z\u00c0-\u024f'\u2019]+")
# Cümle sonu sayılan işaretler: bunlardan sonra gelen BÜYÜK harf özel ad DEĞİLDİR.
_CUMLE_SONU = ".!?:;\u2026\"\u201c\u201d'\u2018\u2019(-[\u2014\u2013"


def _kalinti_normal(metin: str) -> str:
    return unicodedata.normalize("NFKC", metin or "").replace("\u2019", "'")


def _cumle_basinda(metin: str, konum: int) -> bool:
    """`konum`daki sözcük bir cümlenin BAŞINDA mı?

    Ayrım load-bearing: cümle başındaki büyük harf özel ad göstermez. Bu ayrım
    olmadan ``Was Neph...`` vakasındaki ``Was`` "özel ad" sayılıp elenirdi.
    """
    onc = metin[:konum].rstrip()
    return not onc or onc[-1] in _CUMLE_SONU


def _ozel_adlar(kaynak: str) -> set[str]:
    """Kaynakta CÜMLE BAŞI DIŞINDA büyük harfle geçen token'lar = özel ad."""
    kaynak = _kalinti_normal(kaynak)
    out: set[str] = set()
    for m in _KALINTI_TOK.finditer(kaynak):
        w = m.group(0)
        if w[:1].isupper() and not _cumle_basinda(kaynak, m.start()):
            out.add(w.lower())
    return out


def _sozluk_kapsami(ceviri: str, glossary: dict[str, str] | None) -> list[tuple[int, int]]:
    """Çeviride sözlük kaydıyla örtüşen aralıklar (İÇİNDEKİ işlev sözcüğü sızıntı değil).

    Gerçek vaka: ``Auro of the Nine`` sözlükte İngilizce korunuyor; içindeki
    ``the`` iki bölümde sahte sızıntı üretiyordu. YALNIZ işlev sözcüğü İÇEREN
    kayıtlar taranır — 300 kayıtlık bir sözlükte hepsini her paragrafta regex'e
    sokmak boşuna maliyet olurdu.
    """
    if not glossary:
        return []
    araliklar: list[tuple[int, int]] = []
    for kaynak in glossary:
        parcalar = _KALINTI_TOK.findall(kaynak or "")
        if not any(p.lower() in ISLEV_SOZCUKLERI for p in parcalar):
            continue
        for m in _term_regex(kaynak).finditer(ceviri):
            araliklar.append((m.start(), m.end()))
    return araliklar


def _blok_kalintisi(ceviri: str, kaynak: str) -> bool:
    """Paragrafın TAMAMI (ya da neredeyse tamamı) İngilizce mi?"""
    ozel = _ozel_adlar(kaynak)
    kaynak_kume = {w.lower() for w in _KALINTI_TOK.findall(_kalinti_normal(kaynak))}
    aday = [
        w.lower()
        for w in _KALINTI_TOK.findall(_kalinti_normal(ceviri))
        if w.lower() not in ozel
    ]
    if len(aday) < KALINTI_MIN_TOKEN:
        return False
    return sum(1 for w in aday if w in kaynak_kume) / len(aday) >= KALINTI_ORAN


def _sozcuk_kalintisi(
    ceviri: str, kaynak: str, glossary: dict[str, str] | None
) -> bool:
    """Paragrafın İÇİNDE tek tük İngilizce işlev sözcüğü kalmış mı?

    Blok ölçütü bunu göremez: ``...But sadece birkaç dakika sonra`` çevrilmiştir,
    yalnız baştaki bağlaç düşmemiştir — oran 13'te 1'dir.
    """
    ceviri_n = _kalinti_normal(ceviri)
    kaynak_kume = {w.lower() for w in _KALINTI_TOK.findall(_kalinti_normal(kaynak))}
    sozluk_anahtarlari = {(k or "").lower() for k in (glossary or {})}
    kapsam = _sozluk_kapsami(ceviri_n, glossary)
    eslesmeler = list(_KALINTI_TOK.finditer(ceviri_n))
    for sira, m in enumerate(eslesmeler):
        w = m.group(0)
        lw = w.lower()
        sayi = lw in SAYI_SOZCUKLERI
        if not sayi and lw not in ISLEV_SOZCUKLERI:
            continue
        # Kaynakta GEÇMİYORSA Türkçe bir sözcüktür, sızıntı değil.
        if lw not in kaynak_kume:
            continue
        # Sözlükte İngilizce korunan bir adın KENDİSİ (ör. `Song` adlı karakter).
        if lw in sozluk_anahtarlari:
            continue
        # Çok kelimeli bir sözlük kaydının İÇİNDE (`Auro of the Nine` -> `the`).
        if any(a <= m.start() and m.end() <= b for a, b in kapsam):
            continue
        # Çeviride BÜYÜK harfli ve cümle başında değilse özel adın parçasıdır
        # (`Glorious Will` -> `Will`). Cümle başındaki büyük harf ayırt etmez.
        if w[:1].isupper() and not _cumle_basinda(ceviri_n, m.start()):
            continue
        # SAYI sınıfına ÖZEL guard: sonraki sözcük büyük harfliyse ad başlangıcıdır
        # (`Nine Dragons Emperor`, `Ninth Heaven`). Cümle başındaki büyük harf
        # ayırt etmediği için yukarıdaki guard bu deseni göremiyor.
        #
        # İŞLEV sözcüklerine UYGULANAMAZ: gerçek vaka `Was Neph...` tam olarak bu
        # desendedir (sonraki sözcük büyük harfli bir kişi adı) ve aynı guard onu
        # sessizce elerdi. İki sınıfın guard'ları bilerek AYRIDIR.
        if sayi:
            sonraki = eslesmeler[sira + 1].group(0) if sira + 1 < len(eslesmeler) else ""
            if sonraki[:1].isupper():
                continue
        return True
    return False


def ingilizce_kalinti(
    tr_paras: list[str],
    en_paras: list[str],
    glossary: dict[str, str] | None = None,
) -> dict[int, str]:
    """Çevrilmeden İNGİLİZCE kalmış paragrafları bulur (indeks -> çeviri metni).

    Ölçülen arıza (2026-09-05, shadow-slave): hizalama TUTTUĞU hâlde tek tek
    paragraflar İngilizce dönüyordu ve boru hattında bunu gören hiçbir denetim
    yoktu. `_split_by_markers` yalnız YAPIYI doğruluyor (işaretler tam mı),
    `sozluk_ihlalleri` yalnız KAYITLI terimlere bakıyor — ikisi de "bu paragraf
    Türkçe mi" sorusunu sormuyordu. Sonuç kalıcı önbelleğe yazıldığı ve önbellek
    isabeti bir daha çeviri tetiklemediği için kullanıcı o paragrafı SONSUZA DEK
    İngilizce görüyordu.

    Denetim deterministiktir ve API çağırmaz — `sozluk_ihlalleri` gibi bedavaya
    koşar. İKİ ölçüt birleşir, çünkü arıza iki biçimde geliyor:
      * BLOK: paragrafın tamamı kaynakla aynı (``"But to me, it's a paradise."``)
      * SÖZCÜK: paragraf çevrilmiş ama cümle başındaki bağlaç/yardımcı fiil
        düşmemiş (``...But sadece birkaç dakika sonra``, ``Was Neph...``) ya da
        iki özel ad arasındaki bağlaç kalmış (``Sunny and Nephis``)

    Hizalama tutmayan bölümlerde ölçüt UYGULANAMAZ (hangi Türkçe paragrafın hangi
    İngilizce paragrafa karşılık geldiği bilinmiyor) ve boş döner.

    Kalibrasyon: 21.411 gerçek paragrafta 6 gerçek vaka, 0 yanlış pozitif.
    """
    if not tr_paras or len(tr_paras) != len(en_paras):
        return {}
    out: dict[int, str] = {}
    for i, (tr, en) in enumerate(zip(tr_paras, en_paras)):
        if not (tr or "").strip() or not (en or "").strip():
            continue
        if _blok_kalintisi(tr, en) or _sozcuk_kalintisi(tr, en, glossary):
            out[i] = tr
    return out


def _kalintiyi_onar(
    client_factory,
    models: tuple[str, ...],
    tr_paras: list[str],
    en_paras: list[str],
    kalinti: dict[int, str],
    glossary: dict[str, str],
    used_models: dict[str, None],
    new_names: set[str],
    new_terms: dict[str, str],
    kosullar: dict[str, str] | None = None,
) -> dict[int, str]:
    """Sızan paragrafları TEK turda yeniden çevirir; KALAN sızıntıyı döner.

    `tr_paras` YERİNDE güncellenir. Onarım yalnız sızan paragrafları gönderir:
    hizalama tuttuğu için hangilerinin çevrilmediği tam olarak bilinir ve tipik
    vaka 60 paragraflık bölümde 1 paragraftır — bölümün tamamını yeniden
    çevirmek her sızıntıyı tam bölüm maliyetine (ücretli model seçiliyken PARAYA)
    çıkarırdı.

    TEK tur bilinçlidir. Sızıntı modelin dikkat kaymasıdır ve kısa, odaklı bir
    istek onu çoğunlukla düzeltir; düzeltmiyorsa döngü kurmak maliyeti katlar.
    Onarılamayan sızıntı bayrak olarak yukarı taşınır ve okuyucuda görünür.
    """
    if not _paragraflari_yeniden_cevir(
        client_factory, models, tr_paras, en_paras, sorted(kalinti),
        glossary, used_models, new_names, new_terms, kosullar,
    ):
        return kalinti
    return ingilizce_kalinti(tr_paras, en_paras, glossary)


def _paragraflari_yeniden_cevir(
    client_factory,
    models: tuple[str, ...],
    tr_paras: list[str],
    en_paras: list[str],
    indeksler: list[int],
    glossary: dict[str, str],
    used_models: dict[str, None],
    new_names: set[str],
    new_terms: dict[str, str],
    kosullar: dict[str, str] | None = None,
) -> bool:
    """Verilen paragrafları TEK turda yeniden çevirir; `tr_paras` YERİNDE güncellenir.

    İki onarım yolunun (İngilizce kalıntı, sözlük ihlali) ORTAK gövdesi. Aynı
    işi iki yerde yazmak bu projede defalarca ayrışmayla sonuçlandı (künye
    alanları, motor adı): biri künyeye modeli yazmayı unutsa rozet onaran
    halkayı gizlerdi. Ölçüt her yolun KENDİsinde kalır, tur mekaniği burada.

    Döner: tur uygulandı mı (False = çağıran ölçtüğü hatayı olduğu gibi tutar).
    """
    hedef = [en_paras[i] for i in indeksler]
    # Bağlam: ilk bozuk paragraftan ÖNCEKİ Türkçe paragraf. Bağlamsız çevrilen
    # bir replik hitap düzeyini (sen/siz) ve kipi bölümün geri kalanından koparır.
    onceki = tr_paras[indeksler[0] - 1] if indeksler[0] else ""
    try:
        sonuc = _translate_chunk(
            client_factory, models, hedef, glossary,
            _last_sentences(onceki, 2), kosullar,
        )
    except Exception:
        # Onarım BEST-EFFORT: bölüm zaten çevrildi, yalnız bir paragrafı bozuk.
        # Hatayı yukarı sızdırmak BAŞARILI bir çeviriyi tümden kaybettirirdi.
        return False

    yeni = _split_by_markers(sonuc.get("translation") or "", len(hedef))
    if yeni is None:
        return False
    if sonuc.get("model"):
        used_models[sonuc["model"]] = None
    for ad in sonuc.get("detected_names") or []:
        if ad and ad not in glossary:
            new_names.add(ad)
    for kaynak, karsilik in (sonuc.get("detected_terms") or {}).items():
        if kaynak and karsilik and kaynak not in glossary:
            new_terms.setdefault(kaynak, karsilik)
    for sira, i in enumerate(indeksler):
        if yeni[sira].strip():
            tr_paras[i] = yeni[sira]
    return True


def metinde_gecen_terimler(glossary: dict[str, str] | None, metin: str) -> list[str]:
    """Sözlük kayıtlarından metinde GEÇENLERİN kaynakları (sıralı).

    "Bu bölümde geçen terimler" süzgeci için. Ölçüt prompt'a hangi terimlerin
    gireceğini belirleyen ölçütle AYNI (`_terim_metinde`) ve süzgeç eşiğinden
    bağımsızdır: küçük sözlükte de yalnız geçenler döner. Ucuz ön eleme `fold_term`.
    """
    if not glossary or not (metin or "").strip():
        return []
    katlanmis = fold_term(metin)
    return sorted(
        s for s, t in glossary.items()
        if s and fold_term(s) in katlanmis and _terim_metinde(s, t, metin)
    )


def _relevant_glossary(glossary: dict[str, str], text: str) -> dict[str, str]:
    """Bu parçada fiilen geçen sözlük terimlerini süz (ek almış hâlleri dahil).

    Sözlüğün TAMAMINI her parçaya göndermek, metinde hiç geçmeyen terimlerin
    karşılıklarının komşu kelimelere sızmasına zemin hazırlıyor (gözlenen:
    ``Tier -> Kademe`` kaydı varken ``level`` de "kademe" çevrildi). Küçük
    sözlüklerde süzme yapılmaz: kazanç yok, düzensiz çoğul (``wolf/wolves``)
    yüzünden terim kaçırma riski var.

    Ön eleme `fold_term` üzerinden yapılır (boşluk/tire/kesme atılmış hâl). Düz
    ``term.lower() in text.lower()`` kontrolü, metinde ``OreEmpire`` yazan bir adı
    ``Ore Empire`` kaydıyla eşleştiremiyordu: terim daha regex'e VARMADAN eleniyor,
    sözlükte kayıtlı olmasına rağmen prompt'a girmiyordu.
    """
    if not glossary or len(glossary) < GLOSSARY_FILTER_MIN:
        return dict(glossary or {})
    folded = fold_term(text)  # metin de aynı indirgemeden geçer
    out: dict[str, str] = {}
    for source, target in glossary.items():
        term = (source or "").strip()
        if not term or fold_term(term) not in folded:  # ucuz ön eleme
            continue
        if _terim_metinde(term, target, text):
            out[source] = target
    return out


def _translate_chunk(
    client_factory,
    models: tuple[str, ...],
    en_paras: list[str],
    glossary: dict[str, str],
    prev_tail: str,
    kosullar: dict[str, str] | None = None,
) -> dict:
    """Bir parçayı Gemini ile çevirir (model yedek zinciriyle).

    Dönen sözlükte ``model`` = bu parçayı FİİLEN çeviren model. Parça başına ayrı
    tutulur: uzun bölümde ilk parça kotayı bitirip sonraki parçalar bir alt halkaya
    düşebiliyor, tek bir "bölümün modeli" varsayımı yanlış olurdu.
    """
    user = _build_user_prompt(en_paras, glossary, prev_tail, kosullar)
    # Fabrika ÇAĞRILMADAN geçirilir: Gemini istemcisi ancak gerçekten bir Gemini
    # halkasına inilirse kurulur. Peşinen kurmak, çeviri yalnız Mistral'e gitse
    # bile GEMINI_API_KEY'i zorunlu kılıyordu.
    response, model = _generate_with_fallback(client_factory, models, user)
    out = _parse_response(response.text)
    out["model"] = model
    return out


# `glossary.ceviri_kosullari` ek anlamları koşul metnine bu işaretle işler.
EK_ANLAM_ISARETI = "BAŞKA ANLAM:"


def _build_user_prompt(
    en_paras: list[str],
    glossary: dict[str, str],
    prev_tail: str,
    kosullar: dict[str, str] | None = None,
) -> str:
    """Çeviri promptunu kurar. Bölümlerin SIRASI load-bearing — bkz. SON HATIRLATMA.

    ``kosullar``: {kaynak: koşul} — karşılığın HANGİ BAĞLAMDA geçerli olduğunu
    anlatan serbest metin. Karşılığın YERİNE GEÇMEZ, yanına ``[KOŞUL: ...]`` diye
    iliştirilir; `sozluk_ihlalleri` ve terim eşleştirme karşılığı olduğu gibi görür.
    """
    metin = "\n\n".join(en_paras)
    relevant = _relevant_glossary(glossary, metin)
    kosullar = kosullar or {}

    def _satir(s: str, t: str) -> str:
        # Koşul YALNIZ süzgeçten geçen (metinde fiilen geçen) terimler için yazılır;
        # geçmeyen bir terimin koşulu her istekte boşa token yakardı.
        kosul = (kosullar.get(s) or "").strip()
        return f"{s} -> {t}" + (f"  [KOŞUL: {kosul}]" if kosul else "")

    glossary_str = (
        "\n" + "\n".join(_satir(s, t) for s, t in relevant.items())
        if relevant
        else "(boş)"
    )
    # EK ANLAM açıklaması YALNIZ bu istekteki sözlükte ek anlamlı bir terim varsa
    # eklenir (2026-09-16). Sistem talimatına konsaydı HER isteğin prompt'u —
    # ölçülmeden — değişirdi; böyle yapınca ek anlam tanımlamamış kitapların
    # prompt'u bayt bayt aynı kalır. Koşul metni `glossary.ceviri_kosullari`'dan gelir.
    if any(EK_ANLAM_ISARETI in (kosullar.get(s) or "") for s in relevant):
        glossary_str += (
            f"\n(Koşulda {EK_ANLAM_ISARETI} \"X\" — <bağlam> geçen kelimenin birden çok "
            "kayıtlı karşılığı vardır: cümlenin bağlamı hangi koşula uyuyorsa O karşılığı "
            "yaz; hiçbirine uymuyorsa bağlama göre normal çevir.)"
        )
    numbered = "\n\n".join(f"[[{i + 1}]] {p}" for i, p in enumerate(en_paras))
    user = (
        f"SÖZLÜK — YALNIZ bu terimler için geçerli (kaynak -> karşılık); kaynağı "
        f"görünce karşılığını yaz, cümle gerektiriyorsa Türkçe ekini getir; "
        f"listede OLMAYAN kelimelere bu karşılıkları UYGULAMA: {glossary_str}\n\n"
        f"ÖNCEKİ ÇEVİRİNİN SONU (sadece bağlam, tekrar çevirme): "
        f"{prev_tail or '(yok)'}\n\n"
        f"ÇEVRİLECEK METİN (her paragraf [[n]] ile numaralı; işaretleri koru):\n{numbered}"
    )
    # SÖZLÜK hatırlatması metnin SONUNA da konur. Ölçülen sorun: uzun bölümlerde
    # (1500+ kelime) model, promptun başındaki sözlüğü "unutup" korunması gereken
    # özel adları Türkçeleştiriyordu (gerçek bulgu: 26 terimin 23'ü tek turda kayıp
    # → "Lightshadow City" yerine uydurma "Işıkölge"). Talimat metne en yakın yerde
    # tekrarlanınca kural görüş alanında kalıyor.
    if relevant:
        # Hatırlatma listesi DAİMA süzülür — `_relevant_glossary` eşiğin altındaki
        # sözlükleri hiç süzmüyor (`GLOSSARY_FILTER_MIN`), o yüzden buradaki liste
        # bölümde geçmeyen adları da kapsıyordu. Ölçüm: 30 terimlik bir kitapta
        # HER bölümde 18 ad "AYNEN İngilizce kalacak" diye dayatılıyordu, geçip
        # geçmediklerine bakılmadan — süzgecin önlemek için var olduğu kirlenmenin
        # ta kendisi. Ana SÖZLÜK listesi eşiğin altında olduğu gibi kalır (düzensiz
        # çoğul yüzünden terim kaçırma riski); dar tutulan yalnız ZORLAYICI kısım.
        korunacak = [
            s
            for s, t in relevant.items()
            if _ingilizce_korunan(s, t) and _terim_metinde(s, t, metin)
        ]
        user += (
            "\n\nSON HATIRLATMA — SÖZLÜK KURALI HÂLÂ GEÇERLİDİR: yukarıdaki sözlükte "
            "verilen karşılıkları BİREBİR kullan."
        )
        if korunacak:
            user += (
                " Şu adlar İngilizce yazımıyla AYNEN kalacak (yalnız Türkçe eki "
                "eklenebilir), ASLA Türkçeye çevrilmeyecek ve ASLA birleştirilip "
                "uydurma bir kelime yapılmayacak: " + ", ".join(korunacak) + "."
            )
    return user


class _KodluHata(Exception):
    """HTTP durumunu `genai_errors.APIError.code` ile AYNI alanda taşır.

    Böylece `_tek_anahtarla_uret`'teki TEK düşme/tekrar mantığı Claude için de
    aynen çalışır; ikinci bir kural kümesi doğmaz.
    """

    def __init__(self, code: int | None, detay: str = "") -> None:
        super().__init__(f"claude HTTP {detay or code}")
        self.code = code


class _ClaudeYanit:
    """`response.text` sözleşmesini karşılayan asgari sarmalayıcı.

    Yanıt nesnesi zincirin geri kalanına Gemini'ninkiyle aynı yüzeyle ulaşır —
    `_parse_response` sağlayıcıyı bilmez ve bilmemeli.
    """

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _claude_uret(model: str, user: str, system: str, max_tokens: int) -> _ClaudeYanit:
    """Claude ile üret; kullanılan tokenları GÖSTERGE deposuna yazar.

    Akış (`messages.stream`) kullanılır: `max_tokens` bu projede 32.768 ve SDK bu
    büyüklükte akışsız istekte HTTP zaman aşımına düşebiliyor.

    Düşünme ("extended thinking") KAPALI: düşünme çıktısı da ÇIKIŞ tokenı olarak
    faturalanıyor ve çeviri mekanik bir iş. Sonnet 5'te parametre hiç verilmezse
    adaptif düşünme AÇIK gelir, yani kapatmak açıkça yapılmalı. `temperature` da
    `temperature` HİÇ gönderilmez (Gemini yolunda 0.3): SDK'nın akış yardımcısı
    örnekleme parametrelerini kabul etmiyor (`stream()` imzasında yok) ve Sonnet 5
    zaten onları 400 ile reddediyor. Kopyalamaya çalışmak `TypeError` veriyordu —
    ölçülen vaka, bu entegrasyonun ilk gerçek çağrısı.
    """
    import anthropic  # tembel: Claude seçilmedikçe bağımlılık yüklenmesin

    anahtar = claude_anahtari()
    if not anahtar:
        atla = _Retryable()
        atla.anahtarsiz = True
        raise atla

    bilgi = CLAUDE_MODELLER[model]
    govde: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if bilgi.get("dusunme") is not None:
        govde["thinking"] = bilgi["dusunme"]

    client = anthropic.Anthropic(api_key=anahtar)
    try:
        with client.messages.stream(**govde) as akis:
            yanit = akis.get_final_message()
    except anthropic.APIStatusError as exc:
        kod = exc.status_code
        if kod == 429 or kod >= 500:
            raise _KodluHata(503, str(kod)) from exc  # geri-çekilmeli tekrar
        if kod in (401, 403):
            # Kurulum hatası: "modeller meşgul" demek yanlış teşhis olurdu ve
            # kullanıcıyı beklemeye iterdi. Zinciri BİLEREK öldürür.
            raise TranslateError(
                f"Claude anahtarı reddedildi (HTTP {kod}). CLAUDE_API_KEY doğru mu?"
            ) from exc
        raise _KodluHata(404, str(kod)) from exc
    except anthropic.APIConnectionError as exc:
        raise _KodluHata(503, "ağ") from exc

    # TOKEN saklanır, maliyet DEĞİL: fiyat sağlayıcının elinde ve değişir; doları
    # kaydetseydik fiyat değiştiği gün geçmiş kayıtlar sessizce yanlışa dönerdi.
    kullanim.ekle(
        model,
        getattr(yanit.usage, "input_tokens", 0) or 0,
        getattr(yanit.usage, "output_tokens", 0) or 0,
    )
    metin = "".join(b.text for b in yanit.content if getattr(b, "type", "") == "text")
    return _ClaudeYanit(metin)


def _generate_with_fallback(
    client_factory,
    models: tuple[str, ...],
    user: str,
    system: str = SYSTEM_INSTRUCTION,
    max_tokens: int = MAX_OUTPUT_TOKENS,
):
    """Model yedek zincirini sırayla dener; hepsi başarısızsa TranslateError fırlatır.

    İKİ BOYUTLU düşme var ve sırası load-bearing:
      1. KOTA (429) → aynı MODELDE sıradaki ANAHTAR (`_generate_once_with_retry`).
         Model sabit kalmalı: kota bir kalite kusuru değil, kaliteden ödün vermek
         için sebep de değil.
      2. Başka her arıza → sıradaki MODEL (burası).

    ``client_factory`` çağrılabilir bir FABRİKADIR, kurulmuş istemci değil: Gemini
    istemcisi ancak gerçekten kullanılacağı anda kurulur.

    ``system``/``max_tokens`` varsayılanları bölüm çevirisidir; terim önerisi gibi
    kısa işler kendi talimatını ve daha küçük bir tavanı geçer.

    Döner: ``(response, model)`` — FİİLEN çeviren modelin adı künyeye kadar taşınır.
    Yalnız `response` dönseydi zincirin hangi halkasının çevirdiği kaybolurdu; kalite
    şikâyetlerinde "bunu hangi model çevirdi" sorusu tahminle cevaplanıyordu.

    Zincirin ilk halkası dışında bir modele inilirse (ya da zincir tükenirse) NEDENİ
    kaydedilir (`api_durum.gecis_kaydet`): hangi anahtar hangi sonucu verdi. 2026-09-18'e
    kadar bu bilgi hiçbir yerde yoktu ve "3.6 seçiliyken neden 3.5?" sorusu tahminle
    cevaplanıyordu. İlk halka başarılıysa geçiş kaydı OLUŞMAZ.
    """
    # Ofset istek başına BİR kez alınır ve zincirdeki BÜTÜN modellere aynısı
    # uygulanır: aynı isteğin 3.6'da #2, 3.5'te #4'ten başlaması izi okunamaz
    # kılardı ve kotayı da daha eşit dağıtmazdı.
    baslangic = _sonraki_baslangic(
        max(1, getattr(client_factory, "anahtar_sayisi", 1)),
        models[0] if models else None,
    )
    last_exc: Exception | None = None
    blocked = False
    # Her halka ANAHTARSIZLIKTAN mı düştü? Öyleyse "modeller meşgul" demek yanlış
    # teşhis olur — kullanıcının yapması gereken beklemek değil, anahtar ayarlamak.
    anahtarsiz = True
    # Aynı sınıf ikinci bir yanlış teşhis: her halka 404'ten düştüyse sorun MEŞGUL
    # OLMAK değil ERİŞİMDİR (model bu anahtarların projesine sunulmuyor ya da ad
    # artık geçerli değil). "Biraz sonra tekrar deneyin" demek kullanıcıyı saatlerce
    # beklemeye iter, oysa beklemek bunu ASLA açmaz — gerçek vaka 2026-09-15:
    # 3.x halkalarının ikisi de 404 verirken kullanıcı "kotanın dolması imkânsız,
    # 5 anahtarım var" diye arıza aradı ve mesaj onu kota tarafına yönlendirdi.
    # Reddedilen anahtar (401/403) aynı aileden: beklemek onu da açmaz.
    modelsiz = True
    yok_goruldu = red_goruldu = False
    with api_durum.cagri() as denemeler:
        for model in models:
            try:
                yanit = _generate_once_with_retry(
                    client_factory, model, user, system, max_tokens, baslangic
                )
            except _Retryable as exc:
                last_exc = exc
                blocked = blocked or getattr(exc, "blocked", False)
                if not getattr(exc, "anahtarsiz", False):
                    anahtarsiz = False
                if getattr(exc, "erisimsiz", False) or getattr(exc, "yok", False):
                    yok_goruldu = yok_goruldu or getattr(exc, "yok", False)
                    red_goruldu = red_goruldu or getattr(exc, "anahtar_red", False)
                else:
                    modelsiz = False
                continue
            if models and model != models[0]:
                api_durum.gecis_kaydet(models[0], model, list(denemeler))
            return yanit, model
        hata = _zincir_hatasi(
            models, anahtarsiz, modelsiz, blocked, yok_goruldu, red_goruldu, last_exc
        )
        if denemeler:
            api_durum.gecis_kaydet(models[0], None, list(denemeler))
    raise hata from last_exc


def _zincir_hatasi(
    models, anahtarsiz, modelsiz, blocked, yok_goruldu, red_goruldu, last_exc
) -> TranslateError:
    """Zincir tükendiğinde kullanıcıya gidecek DÜRÜST mesaj.

    Her dal "kullanıcı bu mesaja uyarsa ne yapar" sorusuyla yazıldı: beklemek
    yalnız GEÇİCİ arızada doğru cevaptır.
    """
    if anahtarsiz and models and not blocked:
        return TranslateError(ANAHTAR_YOK_MESAJI)
    if modelsiz and models and not blocked:
        if red_goruldu and not yok_goruldu:
            return TranslateError(
                "Anahtarların hiçbiri kabul edilmedi (HTTP 401/403 ya da geçersiz "
                "anahtar). Beklemek bunu açmaz — .env'deki Gemini anahtarlarını "
                "kontrol edin; hangisinin çalıştığını `scripts/kota_durum.py` yazar."
            )
        if red_goruldu:
            return TranslateError(
                "Zincirdeki modeller bu anahtarlarla kullanılamıyor: bazı anahtarlar "
                "reddedildi (401/403), bazılarında model sunulmuyor (404): "
                + ", ".join(models)
                + ". Beklemek bunu açmaz; `scripts/kota_durum.py` anahtar-model "
                "erişimini yazar."
            )
        return TranslateError(
            "Zincirdeki modellerin hiçbiri bu anahtarlarda sunulmuyor (HTTP 404): "
            + ", ".join(models)
            + ". Anahtarlar sağlam — beklemek bunu açmaz. Hangi anahtarın hangi "
            "modele eriştiğini `scripts/kota_durum.py` yazar; okuyucunun ayarlar "
            "panelinden erişilebilen bir model seçin."
        )
    if blocked:
        return TranslateError(
            "Bu bölümün içeriği hiçbir model tarafından çevrilemedi (içerik filtresi); "
            "metin engellenmiş olabilir."
        )
    detay = getattr(last_exc, "detay", "")
    return TranslateError(
        "Tüm modeller şu anda meşgul (geçici). Biraz sonra tekrar deneyin."
        + (f" Son hata — {detay}" if detay else "")
    )


def _generate_once_with_retry(
    client_factory,
    model: str,
    user: str,
    system: str = SYSTEM_INSTRUCTION,
    max_tokens: int = MAX_OUTPUT_TOKENS,
    baslangic: int = 0,
):
    """Tek modelde ANAHTARLARI SIRAYLA dener; hepsi tükenirse _Retryable.

    Döngü ``baslangic`` indeksinden başlar ve havuzu dolanır (rotasyon), ama
    süre bütçesi içinde tüm anahtarları gezer. Bütçe dolarsa yeni deneme
    başlatmadan yedek modele geçer; devam eden başarılı yanıt korunur.

    Anahtar döngüsü DÖRT hata sınıfında döner, çünkü dördünde de başka bir
    anahtar İŞE YARAR:
      - 429 kota → başka anahtar (ayrı projedense) çalışır  → sıradaki anahtar,
        ve bu anahtar soğumaya alınır (kota kalıcıdır, tekrar denemek boşa gider)
      - 500/503/taşıma → ÖLÇÜLDÜ (2026-09-09): 503 tek bir anahtarda çıkarken
        diğerleri AYNI ANDA açık dönüyor  → sıradaki anahtar, havuz tükenirse
        geri-çekilmeli tur tekrarı. SOĞUTMA YOK: arıza geçici, anahtar sağlam.
      - 404 erişim → model erişimi PROJE başınadır (ölçüldü 2026-09-06)
                                                          → sıradaki anahtar
      - 401/403 anahtar reddi → yalnız O anahtar geçersiz  → sıradaki anahtar
    Kalan sınıflarda anahtar değiştirmek yalnız maliyeti ikiye katlar:
      - boş/engellenmiş → içerik filtresi deterministik            → sıradaki model
      - anahtar yok → hiçbir indekste anahtar yok                  → sıradaki model

    Havuzun TAMAMI yalnız erişim/red verdiyse fırlatılan istisna ``erisimsiz``
    taşır: zincir o zaman "meşgul" değil "erişim yok / anahtar reddedildi" der.
    """
    if _claude_modeli(model):
        # Claude'un TEK anahtari var. Gemini anahtar havuzu uzerinde donmek ayni
        # istegi bosuna tekrarlar ve her tekrar PARA harcardi.
        return _tek_anahtarla_uret(
            client_factory, 0, model, user, system, max_tokens
        )
    sayi = max(1, getattr(client_factory, "anahtar_sayisi", 1))
    # İKİ KATMAN, ve ayrım ölçülerek bulundu (iki ayrı yanlıştan sonra):
    #   İÇ  — havuzu UYKUSUZ dolaş. Sıradaki anahtar zaten yeni bir denemedir ve
    #         ölçüm 503'ün anahtara bağlı olduğunu gösterdi (bir anahtar 503
    #         alırken diğerleri aynı anda açık dönüyordu). Anahtar başına ayrıca
    #         3 kez geri-çekilmek 5 anahtar x 2 modelde 30 istek + 60 sn UYKU
    #         demekti; kullanıcı bunu "aşırı yavaş çeviriyor" diye gördü.
    #   DIŞ — hiçbir anahtar çeviremediyse geri-çekilerek turu TEKRARLA. Uykuyu
    #         tümden kaldırmak ters yönde bir hataydı: 10 deneme saniyeler içinde
    #         tükeniyor ve zincir pes ediyordu (gerçek vaka 2026-09-10, 15
    #         bölümlük toplu çeviri ikinci bölümde durdu). Google'ın 503 gövdesi
    #         "Spikes in demand are usually temporary. Please try again later."
    #         diyor — beklemek BAZEN tam olarak doğru cevaptır.
    # Tur tekrarı YALNIZ geçici arızaya özgüdür: kota beklemekle açılmaz, orada
    # tekrar saf kayıp olur ve okumayı sebepsiz geciktirirdi.
    son: Exception | None = None
    # Havuzda görülen sonuç sınıfları: yalnız erişim/red ise zincir "meşgul"
    # DEMEMELİ. Tek bir kota/geçici/soğuma bile beklemenin işe yarayabileceğini
    # gösterir.
    siniflar: set[str] = set()
    # Bu çağrıda 503/taşıma veren anahtarlar. Model HİÇ çeviremeden çıkılırsa
    # (turlar ya da süre bütçesi tükenince) bunlar o modelde soğumaya alınır;
    # 503 de günlük kotadan sayıldığı için ısrar etmek kotayı yakıyor.
    gecici_indeksler: set[int] = set()
    son_tarih = time.monotonic() + MODEL_DENEME_BUTCESI_SN
    delay = 2.0
    for tur in range(MAX_RETRIES):
        turda_gecici = False
        for adim in range(sayi):
            if son is not None and time.monotonic() >= son_tarih:
                # Son hata sınıfını koru: yedek zincir ve gözlem kaydı gerçek
                # nedeni (503/bağlantı/kota) görmeye devam etsin.
                _gecici_sogut(gecici_indeksler, model)
                raise son
            indeks = (baslangic + adim) % sayi
            if _sogumada(indeks, model):
                # Bu anahtar bu modelde az önce 429 yedi; boşuna gitme. Sebep yine
                # de TAŞINIR: zincir tükenirse mesaj "meşgul" değil "kota" demeli.
                siniflar.add("soguma")
                if tur == 0:
                    # İstek ATILMADI: sayaca girmez, ama geçişin nedeni olabilir.
                    api_durum.atlama_kaydet(
                        _anahtar_kimligi(client_factory, indeks), indeks + 1, model
                    )
                if son is None:
                    son = _Retryable()
                    # Sebep AYIRT EDİLİR: "kota soğumasında" diyen bir mesaj,
                    # yoğunluktan soğuyan anahtarda kullanıcıyı arızayı kota
                    # tarafında aramaya iter (ölçülen vaka 2026-09-21).
                    neden = (
                        "yoğunluk" if _SOGUMA_SEBEBI.get((indeks, model)) == "gecici"
                        else "kota"
                    )
                    son.detay = (
                        f"{model}: anahtar #{indeks + 1} {neden} soğumasında"
                    )
                continue
            try:
                yanit = _tek_anahtarla_uret(
                    client_factory, indeks, model, user, system, max_tokens, 1
                )
            except _Retryable as exc:
                son = exc
                if getattr(exc, "kota", False):
                    siniflar.add("kota")
                    _sogut(indeks, model, getattr(exc, "kota_sn", None))
                    continue  # KOTA → sıradaki anahtar, model aynı kalır
                if getattr(exc, "gecici", False):
                    # GEÇİCİ (500/503/taşıma) → sıradaki anahtar. SOĞUTMA YOK:
                    # soğuma kotaya özgüdür ve 503 alan anahtar ölçümde bir
                    # sonraki turda AÇIK dönüyor.
                    siniflar.add("gecici")
                    turda_gecici = True
                    gecici_indeksler.add(indeks)
                    continue
                if getattr(exc, "yok", False) or getattr(exc, "anahtar_red", False):
                    # 404 / 401-403 → sıradaki ANAHTAR. Soğutma YOK (kota değil)
                    # ve `turda_gecici` de İŞARETLENMEZ: erişim beklemekle açılmaz,
                    # tur tekrarı burada saf kayıp olurdu. Havuz tükenirse zincir
                    # sıradaki MODELe iner.
                    siniflar.add("yok" if getattr(exc, "yok", False) else "red")
                    continue
                raise  # engellenmiş / anahtarsız → sıradaki model
            else:
                # Model çevirdi: geçmiş doygunluk cezası taşınmaz, sonraki
                # tökezleme yine en kısa aralıkla denenir.
                _GECICI_SAYAC.pop(model, None)
                return yanit
        if not turda_gecici:
            break  # kota / anahtarsızlık: beklemek hiçbir şeyi değiştirmez
        if tur < MAX_RETRIES - 1:
            if time.monotonic() + delay >= son_tarih:
                break
            time.sleep(delay)
            delay *= 2
    _gecici_sogut(gecici_indeksler, model)
    son = son or _Retryable()
    if siniflar and siniflar <= {"yok", "red"}:
        son.erisimsiz = True
        son.yok = "yok" in siniflar
        son.anahtar_red = "red" in siniflar
    raise son


def _tek_anahtarla_uret(
    client_factory,
    indeks: int,
    model: str,
    user: str,
    system: str,
    max_tokens: int,
    tekrar_sayisi: int = MAX_RETRIES,
):
    """Tek model + TEK anahtar: geçici hatada üstel geri-çekilmeyle yeniden dener.

    ``tekrar_sayisi`` çağırandan gelir: anahtar havuzu varsa 1 (sıradaki anahtar
    zaten yeni bir deneme), tek anahtarlı kurulumda `MAX_RETRIES`.

    Her GERÇEK Gemini çağrısı burada TEK kez kaydedilir (`api_durum.istek_kaydet`):
    sonuç sınıfı, HTTP kodu, süre, token, kota ayrıntısı. Anahtarsızlık bir çağrı
    değildir ve kaydedilmez. Claude'un kendi harcama göstergesi var (`kullanim`).
    """
    kaydet = not _claude_modeli(model)
    kimlik = _anahtar_kimligi(client_factory, indeks)

    def _kayit(sonuc: str, bas: float, kod: int | None = None, **kw) -> None:
        if kaydet:
            api_durum.istek_kaydet(
                kimlik, indeks + 1, model, sonuc, kod,
                int((time.monotonic() - bas) * 1000), **kw,
            )

    delay = 2.0
    for attempt in range(max(1, tekrar_sayisi)):
        bas = time.monotonic()
        try:
            if _claude_modeli(model):
                response = _claude_uret(model, user, system, max_tokens)
                if not (response.text or "").strip():
                    atla = _Retryable()
                    atla.blocked = True
                    raise atla
                return response
            try:
                client = client_factory(indeks)
            except TranslateError as exc:
                # Anahtar yok → bu halka KULLANILAMAZ, ama zincir ölmesin. `anahtarsiz`
                # işareti, zincirin TAMAMI anahtarsızlıktan düşerse dürüst hata mesajı
                # üretilmesini sağlar ("modeller meşgul" demek yanlış teşhis olurdu).
                atla = _Retryable()
                atla.anahtarsiz = True
                raise atla from exc
            bas = time.monotonic()
            response = client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=0.3,
                    max_output_tokens=max_tokens,
                    safety_settings=SAFETY_SETTINGS,
                    thinking_config=(
                        types.ThinkingConfig(
                            thinking_budget=GEMINI_DUSUNME_BUTCESI
                        )
                        if GEMINI_DUSUNME_BUTCESI is not None
                        else None
                    ),
                ),
            )
        except (genai_errors.APIError, _KodluHata) as exc:
            code = getattr(exc, "code", None)
            if code in FALLBACK_CODES:
                atla = _Retryable()
                # Bayraklar çağıranın "sıradaki anahtar mı, sıradaki model mi"
                # kararını verir. İKİSİ de sıradaki ANAHTARI dener, ama sebepleri
                # ayrı: 429 kotadır (anahtar soğumaya alınır), 404 erişimdir
                # (soğutma yok — anahtar sağlam, o modeli görmüyor).
                atla.kota = code == 429
                # 404 bir dönem "model yok, ikinci anahtar da aynı cevabı verirdi"
                # sayılıp o modeli TÜMDEN iptal ediyordu. Varsayım ÖLÇÜMLE çürüdü
                # (2026-09-06, `scripts/kota_durum.py`): 3. anahtar
                # `gemini-2.5-flash`a 404 verirken 1. ve 2. anahtar AÇIK dönüyordu —
                # model erişimi PROJE başınadır, yani ANAHTAR başına değişir. Eski
                # kural tek bir 404'te o modeldeki kalan bütün SAĞLAM anahtarları
                # iptal ediyordu; zincirin iki halkası da aynı anahtarda 404 alınca
                # çeviri TÜMDEN duruyordu (5 anahtarın 4'ü çalışırken).
                atla.yok = code == 404
                if atla.kota:
                    # Soğuma süresi kotanın TÜRÜNDEN gelir (günlük mü dakikalık
                    # mı); tek sabit süre günlük kotada anahtarı dakikada bir
                    # boşuna denetiyordu.
                    atla.kota_sn = _kota_soguma_suresi(exc)
                    kota = kota_ayrintisi(exc)
                    sinif = {
                        "gunluk": api_durum.KOTA_GUNLUK,
                        "dakikalik": api_durum.KOTA_DAKIKALIK,
                    }.get(kota["tur"], api_durum.KOTA_BELIRSIZ)
                    _kayit(sinif, bas, code, kota=kota, soguma_sn=atla.kota_sn)
                else:
                    _kayit(api_durum.ERISIM, bas, code)
                # Sebep TAŞINIR: "tüm modeller meşgul" tek başına teşhis edilemez bir
                # mesajdı ve yapılandırma hatasını geçici arıza gibi gösteriyordu.
                atla.detay = f"{model} (anahtar #{indeks + 1}): {exc}"
                raise atla from exc
            if code in RETRY_CODES:
                _kayit(api_durum.GECICI, bas, code)
                if attempt < tekrar_sayisi - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                atla = _Retryable()
                # GEÇİCİ → sıradaki ANAHTAR. "Sunucu arızası, anahtar fark etmez"
                # varsayımı ölçümle çürüdü (2026-09-09): 503 tek bir anahtarda
                # çıkarken diğerleri AYNI ANDA açık dönüyor.
                atla.gecici = True
                atla.detay = f"{model} (anahtar #{indeks + 1}): {exc}"
                raise atla from exc
            if kaydet and anahtar_reddi_mi(code, exc):
                # ANAHTAR reddedildi (iptal/geçersiz/izinsiz) → sıradaki ANAHTAR
                # (2026-09-18, kullanıcı kararı). Eskiden bu dal çeviriyi TÜMDEN
                # öldürüyordu: rotasyon açıkken tek bir iptal edilmiş anahtar her
                # beş bölümden birini çevrilemez kılardı, dört anahtar sağlamken.
                # 404 dersinin aynısı — arıza ANAHTARA bağlı, modele değil.
                # Soğutma YOK: kota değil. Tur tekrarı da YOK: beklemek açmaz.
                # (Claude'da 401/403 `_claude_uret`te kurulum hatası sayılır.)
                _kayit(api_durum.ANAHTAR, bas, code)
                atla = _Retryable()
                atla.anahtar_red = True
                atla.detay = (
                    f"{model} (anahtar #{indeks + 1}): anahtar reddedildi (HTTP {code})"
                )
                raise atla from exc
            _kayit(api_durum.DIGER, bas, code)
            raise TranslateError(f"Çeviri hatası: {exc}") from exc
        except (_Retryable, TranslateError):
            raise  # kendi sinyalimiz (anahtar yok) — aşağıdaki dala düşmesin
        except httpx.HTTPError as exc:
            # TAŞIMA katmanı: bağlantı koptu, TLS, okuma zaman aşımı. Bunlar
            # `APIError` DEĞİLDİR ve bir dönem hiçbir dala girmeyip zinciri tümden
            # öldürüyordu — bölüm çevrilmiyor, kullanıcı ham bir istisna görüyordu.
            # Ölçülen vaka (2026-09-02): `gemini-3.6-flash` 81 sn sonra
            # `RemoteProtocolError`. Sunucu tarafı 503 ile aynı sınıf arızadır
            # (geçici, anahtar fark etmez) → aynı muamele: geri-çekilmeli tekrar,
            # sonra sıradaki model. Tek motor kaldığından bu yolun dayanıklılığı
            # artık çevirinin TAMAMININ dayanıklılığıdır.
            _kayit(api_durum.BAGLANTI, bas)
            if attempt < tekrar_sayisi - 1:
                time.sleep(delay)
                delay *= 2
                continue
            atla = _Retryable()
            atla.gecici = True  # 503 ile aynı sınıf: sıradaki ANAHTAR denenir
            atla.detay = f"{model} (anahtar #{indeks + 1}): {type(exc).__name__}"
            raise atla from exc
        # Yanıt geldi ama boş/engellenmiş olabilir (finish_reason PROHIBITED_CONTENT/
        # SAFETY/RECITATION → HTTP 200, metin yok). Bu deterministiktir; aynı modelde
        # tekrar denemek beyhude → sıradaki modele düş (başka model çevirebilir).
        try:
            txt = response.text or ""
        except Exception:  # bazı engellenmiş yanıtlarda .text istisna fırlatır
            txt = ""
        if txt.strip():
            giris, cikis = _token_sayilari(response)
            _kayit(api_durum.BASARI, bas, 200, giris=giris, cikis=cikis)
            return response
        _kayit(api_durum.BOS, bas, 200)
        exc = _Retryable()
        exc.blocked = True
        raise exc


def _token_sayilari(response) -> tuple[int, int]:
    """Gemini yanıtının (giriş, çıkış) tokenları; yoksa (0, 0).

    Çıkışa düşünme tokenları da eklenir: kotadan ve TPM'den onlar da düşer.
    """
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return 0, 0

    def _sayi(ad: str) -> int:
        deger = getattr(meta, ad, None)
        return deger if isinstance(deger, int) else 0

    return (
        _sayi("prompt_token_count"),
        _sayi("candidates_token_count") + _sayi("thoughts_token_count"),
    )


def _BOS_AYRISTIRMA() -> dict:
    return {
        "translation": "",
        "detected_names": [],
        "detected_terms": {},
    }


def _parse_response(raw: str | None) -> dict:
    if not raw:
        return _BOS_AYRISTIRMA()
    text = raw.strip()
    # Bazı modeller JSON'u ```json ... ``` çitiyle sarar; temizle.
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        # Eski şema (detected_guilds/detected_places) da okunur: tek "diğer özel
        # adlar" kutusuna genişletildi, ama model kimi zaman eski alan adlarını
        # üretiyor — o yanıtları düşürmek terimi sessizce kaybettirirdi.
        terimler = _esleme(data.get("detected_terms"))
        for eski in ("detected_guilds", "detected_places"):
            for kaynak, hedef in _esleme(data.get(eski)).items():
                terimler.setdefault(kaynak, hedef)
        return {
            "translation": data.get("translation", ""),
            "detected_names": _liste(data.get("detected_names")),
            "detected_terms": terimler,
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        # JSON bozuk/yarım: ham basmak yerine 'translation' alanını ayıklamayı dene.
        out = _BOS_AYRISTIRMA()
        out["translation"] = _extract_translation(text)
        return out


def _liste(deger) -> list[str]:
    """Model bazen tek string, bazen null döndürür; her hâlde listeye indir."""
    if isinstance(deger, str):
        return [deger] if deger.strip() else []
    if not isinstance(deger, list):
        return []
    return [d for d in deger if isinstance(d, str) and d.strip()]


def _esleme(deger) -> dict[str, str]:
    """``detected_terms`` eşlemesini temizle (kaynak -> karşılık).

    Model kimi zaman sözlük yerine düz liste döndürür; o durumda karşılık
    bilinmediği için kayıt ATILIR — yanlış karşılıkla sözlüğü kirletmektense
    terimi hiç eklememek yeğdir (sözlük prompt'ta KURALdır, öneri değil).
    """
    if not isinstance(deger, dict):
        return {}
    out: dict[str, str] = {}
    for kaynak, hedef in deger.items():
        if not isinstance(kaynak, str) or not isinstance(hedef, str):
            continue
        k, h = kaynak.strip(), hedef.strip()
        if k and h:
            out[k] = h
    return out


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
