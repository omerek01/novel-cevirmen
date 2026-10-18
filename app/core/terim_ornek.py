"""Terim kullanım örneği — DelTA tarzı (2026-10-17, plan Faz 4; deneysel, `CEVIRI_TERIM_ORNEK=1`).

DelTA (2024/25) özel ad kaydının yanında uzun süreli bellekten ilgili geçmiş cümle çiftlerini
ÖRNEK olarak getiriyor. Bizde sözlük kaydı zaten istemde; eksik olan, modelin bir terimi
kayıttan farklı çevirmeye devam ettiği yerde "bu kitapta bu terim böyle çevrildi" kanıtı.

Kapsam bilerek DAR (projenin dersi: yalnız hedefli, doğrulanmış bağlam; genel bellek ve özet
ölçümde kazanç vermedi):
  * Terim adayı = SON `GERI_BOLUM` bölümün künyesinde kayıtlı karşılıktan SAPAN
    (`karsilik_sapmasi`) ya da İngilizce kalan (`glossary_leaks`) kayıt, VE bu bölümün kaynağında geçiyor.
  * Koşullu kayıt (`kosullar`) ve korunan ad (`X -> X`) ALINMAZ: koşullu terimin tek anlamlı
    örneği öteki anlamı yanlış yönlendirir (Saint A/B dersi); korunan adın örneğe ihtiyacı yok.
  * Örnek = önceki bölümlerden, kaynakta terimin ve çeviride KAYITLI karşılığın (Türkçe
    çekimleriyle) birlikte geçtiği EN YENİ kısa paragraf çifti. Yoksa terim atlanır.
  * En çok `EN_COK_TERIM` terim; parça başına yalnız o parçada geçenler. Yeni model çağrısı yok.
  * Gelecek bölüm hiçbir koşulda girmez (`cache.bellek_havuzu`, yalnız `chapter_no < N`).
Kapalıyken çeviri istemi bayt bayt aynıdır.
"""
from __future__ import annotations

import json
import os
from collections import Counter

from . import cache, translate, turkce_eslesme

GERI_BOLUM = 30
MIN_BOLUM = 2  # tek bölümlük bulgu ısrarlı sorun sayılmaz
EN_COK_TERIM = 5
ORNEK_UST_KARAKTER = 420  # örnek paragrafın İngilizce uzunluk sınırı (istem kısa kalsın)


def acik_mi() -> bool:
    return os.getenv("CEVIRI_TERIM_ORNEK", "0") == "1"


def sorunlu_terimler(book_slug: str, bolum_no: int, glossary: dict[str, str], geri: int = GERI_BOLUM) -> Counter:
    """Önceki `geri` bölümün KÜNYESİNDE sapma ya da sızıntı görülen BÖLÜM sayısı, kaynak terime göre.

    İki koruma (canlı kopya ölçümü, 2026-10-17): SS'in son 50 bölümünün 36'sı örnek alıyordu, ama
    kaynak neredeyse tümüyle 994'ün tek seferlik künyesi (6 terim; bugünkü sözlükle yeniden
    ölçünce sızıntı yok) ve 972–974'ün bilinen sahte "Night" uyarısıydı — 30 bölümlük pencere tek
    bölümü 30 bölüme yayıyordu. Bu yüzden terim en az `MIN_BOLUM` ayrı bölümde sorun çıkarmış
    olmalı ve künyedeki karşılık BUGÜNKÜ sözlük karşılığıyla aynı olmalı (değiştiyse bulgu bayattır).

    Yeniden HESAPLANMAZ: her bölümün `karsilik_sapmasi` ve `glossary_leaks` alanı çevrilirken
    zaten yazılıyor. İlk sürüm 30 bölümü baştan ölçüyordu; yerelde bölüm başına 8–21 sn
    (SS, 860 kayıtlı sözlük) — e2-micro'da her çeviriden önce dakikalar demekti. Künye, terimin
    o bölüm çevrilirken sapıp sapmadığıdır; sonra sözlük değiştiyse eski bulgu kalır, bu yüzden
    örnek yine GÜNCEL karşılıkla doğrulanır (`ornek_bul`). Aynı bölümün yalnız en yeni kaydı."""
    conn = cache._connect()
    try:
        satirlar = conn.execute(
            "SELECT chapter_no, karsilik_sapmasi, glossary_leaks FROM chapters WHERE book_slug = ? "
            "AND chapter_no < ? AND chapter_no >= ? AND translation IS NOT NULL ORDER BY chapter_no, created_at DESC",
            (book_slug, bolum_no, bolum_no - geri)).fetchall()
    finally:
        conn.close()
    sayac: Counter = Counter()
    gorulen = set()
    for no, sapma, sizinti in satirlar:
        if no in gorulen:
            continue
        gorulen.add(no)
        bolumde = set()
        for ham in (sapma, sizinti):
            try:
                veri = json.loads(ham) if ham else {}
            except (TypeError, ValueError):
                continue
            if isinstance(veri, dict):
                bolumde.update(k for k, v in veri.items()
                               if isinstance(v, str) and (glossary.get(k) or "").casefold() == v.casefold())
        sayac.update(bolumde)  # bir bölüm bir terimi bir kez sayar
    return Counter({k: n for k, n in sayac.items() if n >= MIN_BOLUM})


def ornek_bul(kaynak: str, karsilik: str, havuz: list[dict]) -> dict | None:
    """Terimin kayıtlı karşılıkla çevrildiği en yeni kısa paragraf çifti."""
    desen = translate._term_regex(kaynak)
    for x in sorted(havuz, key=lambda y: -y["bolum"]):
        if (len(x["en"]) <= ORNEK_UST_KARAKTER and desen.search(x["en"])
                and turkce_eslesme.karsilik_gecer(karsilik, x["tr"])):
            return {"bolum": x["bolum"], "en": x["en"], "tr": x["tr"]}
    return None


def secim(kaynak_metin: str, glossary: dict[str, str] | None, kosullar: dict[str, str] | None,
          havuz: list[dict], sorunlu: Counter) -> list[dict]:
    """[{source, target, sapma, bolum, en, tr}] — sorunlu ve bu bölümde geçen terimler (saf)."""
    if not glossary or not kaynak_metin or not havuz or not sorunlu:
        return []
    kosullu = {k.casefold() for k in (kosullar or {})}
    out = []
    # Eşitlikte ada göre: sayaç `set`ten doldurulduğu için `most_common()` eşit sayılı
    # terimleri süreçten sürece (hash tohumu) farklı sırada veriyordu; `EN_COK_TERIM`
    # sınırında hangi terimin isteme gireceği rastgele olurdu.
    for kaynak, sayi in sorted(sorunlu.items(), key=lambda kv: (-kv[1], kv[0].casefold())):
        karsilik = glossary.get(kaynak)
        if (not karsilik or kaynak.casefold() in kosullu or kaynak.casefold() == karsilik.casefold()
                or not translate._term_regex(kaynak).search(kaynak_metin)):
            continue
        ornek = ornek_bul(kaynak, karsilik, havuz)
        if ornek:
            out.append({"source": kaynak, "target": karsilik, "sapma": sayi, **ornek})
        if len(out) >= EN_COK_TERIM:
            break
    return out


def hazirla(book_slug: str, bolum_no, kaynak_metin: str, glossary, kosullar) -> list[dict] | None:
    """Pipeline girişi: bayrak kapalıysa ya da seçilecek terim yoksa None."""
    if not acik_mi() or not book_slug or type(bolum_no) is not int:
        return None
    sorunlu = sorunlu_terimler(book_slug, bolum_no, glossary or {})
    if not sorunlu:  # çoğu bölümde: havuz hiç okunmaz
        return None
    return secim(kaynak_metin, glossary, kosullar, cache.bellek_havuzu(book_slug, bolum_no, GERI_BOLUM), sorunlu) or None


def metin(ornekler: list[dict] | None, en_paras: list[str]) -> str:
    """Parçanın istemine eklenecek blok; parçada geçen terim yoksa boş."""
    parca = "\n\n".join(en_paras)
    secilen = [o for o in ornekler or () if translate._term_regex(o["source"]).search(parca)]
    if not secilen:
        return ""
    satirlar = ["TERİM KULLANIM ÖRNEKLERİ (bu kitabın önceki bölümlerinden, kabul edilmiş çeviri). "
                "Bu terimler son bölümlerde sözlükteki karşılıktan farklı çevrildi; sözlük karşılığını "
                "örnekteki gibi kullan. Örnekleri ÇEVİRME, yalnız terimin nasıl kullanıldığını gör."]
    for o in secilen:
        satirlar.append(f"- {o['source']} -> {o['target']} (bölüm {o['bolum']})\n  EN: {o['en']}\n  TR: {o['tr']}")
    return "\n".join(satirlar)
