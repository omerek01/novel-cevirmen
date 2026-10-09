"""Eski hatalı sözlük kayıtlarının temizliği: BULGUYU BİLEN model önerisi + onaylı uygulama.

Neden ayrı bir istek (reports/sozluk-kalite-arastirma): `sozluk_dogrulama` her kaydı TEK BAŞINA
gösteriyor. Deterministik denetimin işaretlediği 128 kaydın 102'si o doğrulamadan "geçti" döndü,
çünkü model `Devil -> Şeytan` kaydını görürken `daemon -> Şeytan` kaydını görmüyordu. Burada her
VAKA bir bulguyu ve ilgili BÜTÜN kayıtları birlikte, İngilizce bağlam cümleleriyle verir; model
vaka için tek bir karar seçer.

Akış (üç ayrı, açık adım):
  1. `vakalari_kur` — deterministik, API'siz. Kaynak: `sozluk_kapi.sozlugu_denetle` bulguları +
     "kayıt öncesi uyum oranı" düşük kayıtlar (`kayit_oncesi_uyum`).
  2. `vakalari_sor` — YALNIZ ücretsiz zincir (`sozluk_dogrulama.ucretsiz_zincir`); sonuç yalnız
     ÖNERİDİR, DB'ye yazmaz. Yanıt yerel olarak doğrulanır: vakada olmayan kaynak, kapıdan geçmeyen
     yeni karşılık, bilinmeyen işlem reddedilir.
  3. `onerileri_uygula` — kullanıcının gözden geçirdiği öneri dosyasından, yalnız `onay: true`
     işaretli işlemler. Elle yazılmış (`origin='manual'`) kayıt ASLA değiştirilmez.
"""
from __future__ import annotations

import json
import os

from . import cache, glossary, library, sozluk_dogrulama, translate
from . import sozluk_kapi

ISLEMLER = ("karsilik_degistir", "alternatif_yazim", "sil", "dokunma")
VAKA_PARTI = 8
UYUM_MIN_BOLUM = 10   # kayıttan önce en az bu kadar bölümde geçmeli
UYUM_ESIK = 0.5       # bunun altı inceleme vakası

TEMIZLIK_INSTRUCTION = (
    "Sen İngilizce→Türkçe web roman çevirisinin SÖZLÜK editörüsün. Sözlük çeviri talimatına KURAL "
    "olarak girer: yanlış bir kayıt kitap boyunca her geçişte uygulanır. Sana VAKALAR verilecek. Her "
    "vakada otomatik denetimin bulduğu sorun ve ilgili BÜTÜN kayıtlar (İngilizce kaynak, Türkçe karşılık, "
    "kitaptan İngilizce cümle) var. Vakayı bütün olarak değerlendir ve her kayıt için TEK işlem seç:\n"
    "- karsilik_degistir: karşılık yanlış/eksik/biçimsiz; yeni_karsilik ver (yalın hâlde, gerçek Türkçe).\n"
    "- alternatif_yazim: bu kayıt vakadaki başka bir kaydın AYNI kavramının yazımıdır; kanonik alanına o "
    "kaydın kaynağını yaz. (Aynı karşılığı almış İKİ FARKLI kavram ise alternatif_yazim DEĞİL; "
    "karşılıklarını ayır.)\n"
    "- sil: kaynak bu kitapta çoğunlukla SIRADAN İngilizce sözcük (seven, lost, call) ya da kayıt "
    "anlamsız (bir cümle parçası); her geçişine özel karşılık dayatmak çeviriyi bozar.\n"
    "- dokunma: kayıt doğru; uyarı yanlış alarm.\n"
    "Kurallar (çeviri sözlüğüyle AYNI):\n"
    "- Bir KİŞİYİ adlandıran ifade (gerçek ad ya da ad yerine geçen lakap) İngilizce kalır; karşılığı "
    "kaynağın kendisidir.\n"
    + translate.LAKAP_KURALI +
    "- Başka her özel ad Türkçeye çevrilir. Karşılıkta İngilizce iyelik ('s) ya da sonda kesmeli ek "
    "olmaz; tekil kaynağa tekil, çoğul kaynağa çoğul karşılık.\n"
    "- Emin değilsen dokunma seç; yanlış bir düzeltme yanlış bir kayıttan daha zararlıdır.\n"
    'Yanıtı SADECE şu JSON ile ver: {"vakalar": [{"id": "...", "gerekce": "kısa", "islemler": '
    '[{"source": "...", "islem": "karsilik_degistir|alternatif_yazim|sil|dokunma", '
    '"yeni_karsilik": "", "kanonik": ""}]}]}. source alanını sana verilen yazımla AYNEN ver; vakadaki '
    "HER kayıt için bir işlem döndür."
)


# ---------- 1. vakalar (deterministik) ----------
def kayit_oncesi_uyum(book_slug: str) -> dict[str, dict]:
    """Kayıttan ÖNCE terimin geçtiği bölümlerde, sonradan seçilen karşılığın kökü çeviride var mı.

    Düşük oran iki şey demek olabilir: kayıt yanlış (model o sözcüğü hiç öyle çevirmedi — `Lost`,
    `Corruption`) ya da terim geç kaydedildi ve eski bölümler tutarsız. Karar değil, vaka kaynağı.
    Koşullu ve İngilizce korunan kayıtlar ölçülmez (ölçüt farklı)."""
    satirlar = [r for r in glossary.get_glossary_rows(book_slug)
                if r.get("first_chapter") is not None and not r.get("kosul")
                and (r.get("target") or "").strip().casefold() != r["source"].strip().casefold()]
    bolumler = [(b.get("chapter_no"), b.get("source") or "", b.get("translation") or "")
                for b in cache.kaynak_bolumleri(book_slug) if b.get("chapter_no") is not None]
    sozluk = glossary.ceviri_sozlugu(book_slug)
    tekil = translate._tekili_kayitli_cogullar(sozluk)
    out = {}
    for r in satirlar:
        desen = translate._term_regex(r["source"], cogul_esnek=r["source"] not in tekil)
        once = [tr for n, src, tr in bolumler if n < r["first_chapter"] and desen.search(src)]
        if len(once) < UYUM_MIN_BOLUM:
            continue
        ilk = r["target"].split()[0]
        kok = ilk[:max(4, len(ilk) - 2)].casefold()
        uyan = sum(1 for tr in once if kok in tr.casefold())
        out[r["source"]] = dict(once=len(once), uyan=uyan, oran=round(uyan / len(once), 3))
    return out


def vakalari_kur(book_slug: str, bulgular: dict[str, list[dict]] | None = None,
                 uyum: dict[str, dict] | None = None) -> list[dict]:
    """Bulguları ilişkili kayıtlara göre BİRLEŞTİRİR (birlikte değerlendirilmesi gerekenler tek vaka)."""
    satirlar = {r["source"]: r for r in glossary.get_glossary_rows(book_slug)}
    if bulgular is None:
        _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
        bulgular = sozluk_kapi.sozlugu_denetle(list(satirlar.values()), glossary.yasaklar(book_slug),
                                               glossary.politikalar(book_slug), korpus)
    if uyum is None:
        uyum = kayit_oncesi_uyum(book_slug)
    for kaynak, u in uyum.items():
        if u["oran"] < UYUM_ESIK:
            bulgular.setdefault(kaynak, []).append(dict(
                tur="kayit_oncesi_uyum",
                aciklama=f"Kayıttan önce {u['once']} bölümde geçti; model yalnız {u['uyan']} bölümde bu "
                         "karşılığa benzer bir çeviri kullandı (sıradan sözcük ya da yanlış karşılık olabilir).",
                ilgili=[]))
    ebeveyn: dict[str, str] = {}

    def kok(x):
        while ebeveyn.setdefault(x, x) != x:
            ebeveyn[x] = ebeveyn[ebeveyn[x]]
            x = ebeveyn[x]
        return x
    for kaynak, liste in bulgular.items():
        if kaynak not in satirlar:
            continue
        kok(kaynak)
        for b in liste:
            for diger in b.get("ilgili") or []:
                if diger in satirlar:
                    ebeveyn[kok(diger)] = kok(kaynak)
    gruplar: dict[str, list[str]] = {}
    for kaynak in ebeveyn:
        gruplar.setdefault(kok(kaynak), []).append(kaynak)
    _t, _k, korpus = cache.kaynak_kapsamasi(book_slug)
    vakalar = []
    for i, uyeler in enumerate(sorted(gruplar.values(), key=lambda u: sorted(u)[0].casefold())):
        uyeler = sorted(uyeler, key=str.casefold)
        kayitlar = []
        for s in uyeler:
            r = satirlar[s]
            kayitlar.append(dict(source=s, target=r.get("target"), origin=r.get("origin"),
                                 first_chapter=r.get("first_chapter"),
                                 baglam_en=sozluk_dogrulama.ingilizce_baglam(book_slug, r, korpus)[:300]))
        vakalar.append(dict(id=f"v{i + 1}", kayitlar=kayitlar,
                            bulgular=[dict(source=s, tur=b.get("tur"), aciklama=b.get("aciklama"))
                                      for s in uyeler for b in bulgular.get(s, [])]))
    return vakalar


# ---------- 2. model önerisi (yalnız ücretsiz zincir, yazmaz) ----------
def _istek(vakalar: list[dict], kitap: str) -> str:
    parcalar = [f"KİTAP: {kitap}"] if kitap else []
    for v in vakalar:
        satir = [f"VAKA {v['id']}:"]
        for b in v["bulgular"]:
            satir.append(f"  SORUN ({b['source']}): {b['aciklama']}")
        for k in v["kayitlar"]:
            satir.append(f"  - KAYNAK: {k['source']} | KARŞILIK: {k['target']}"
                         + (f" | İNGİLİZCE CÜMLE: {k['baglam_en']}" if k.get("baglam_en") else ""))
        parcalar.append("\n".join(satir))
    return "\n\n".join(parcalar)


def _ayristir(metin: str | None) -> list[dict]:
    ham = (metin or "").strip()
    if ham.startswith("```"):
        ham = ham.strip("`").removeprefix("json").strip()
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return []
    liste = veri.get("vakalar") if isinstance(veri, dict) else veri
    return [x for x in liste or [] if isinstance(x, dict)]


def yaniti_dogrula(vaka: dict, yanit: dict, mevcut: list[dict]) -> list[dict]:
    """Modelin işlemlerini YEREL kurallarla süz. Dönen her işlemde `durum`: oneri | reddedildi."""
    kayitlar = {k["source"]: k for k in vaka["kayitlar"]}
    fold = {glossary.fold_term(s): s for s in kayitlar}
    out, gorulen = [], set()
    for x in yanit.get("islemler") or []:
        s = fold.get(glossary.fold_term(str(x.get("source") or "")))
        islem = x.get("islem")
        kayit = dict(vaka=vaka["id"], source=s or x.get("source"), islem=islem,
                     eski_karsilik=kayitlar[s]["target"] if s else None,
                     yeni_karsilik=(x.get("yeni_karsilik") or "").strip() or None,
                     kanonik=None, gerekce=(yanit.get("gerekce") or "")[:300], durum="oneri", onay=False)
        if not s or s in gorulen:
            out.append({**kayit, "durum": "reddedildi", "neden": "vakada olmayan ya da tekrar eden kaynak"})
            continue
        gorulen.add(s)
        if islem not in ISLEMLER:
            out.append({**kayit, "durum": "reddedildi", "neden": f"bilinmeyen işlem {islem!r}"})
            continue
        if kayitlar[s].get("origin") == "manual" and islem != "dokunma":
            out.append({**kayit, "durum": "reddedildi", "neden": "elle yazılmış kayıt değiştirilmez"})
            continue
        if islem == "karsilik_degistir":
            yeni = kayit["yeni_karsilik"]
            if not yeni or yeni == kayitlar[s]["target"]:
                out.append({**kayit, "durum": "reddedildi", "neden": "yeni karşılık yok ya da aynı"})
                continue
            sorun = sozluk_kapi.bicim_sorunlari(s, yeni) + (
                [sozluk_kapi.sayi_uyumsuzlugu(s, yeni)] if sozluk_kapi.sayi_uyumsuzlugu(s, yeni) else [])
            baska = [r for r in mevcut if r["source"] != s and (r.get("target") or "").casefold() == yeni.casefold()
                     and r["source"] not in kayitlar]
            if sorun or baska:
                out.append({**kayit, "durum": "reddedildi",
                            "neden": "; ".join(sorun) or f"karşılık başka kavramda kullanılıyor: {baska[0]['source']}"})
                continue
        if islem == "alternatif_yazim":
            k = fold.get(glossary.fold_term(str(x.get("kanonik") or "")))
            if not k or k == s:
                out.append({**kayit, "durum": "reddedildi", "neden": "kanonik kayıt vakada değil"})
                continue
            kayit["kanonik"] = k
        out.append(kayit)
    for s in kayitlar.keys() - gorulen:
        out.append(dict(vaka=vaka["id"], source=s, islem=None, durum="yanitsiz", onay=False))
    return out


def vakalari_sor(book_slug: str, vakalar: list[dict], api_key: str = "", parti: int = VAKA_PARTI,
                 ilerleme=None) -> list[dict]:
    """Ücretsiz zincirle öneri al. DB'ye YAZMAZ. Model kararı yalnız öneri; onay kullanıcınındır."""
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not translate.ceviri_anahtari_var_mi(api_key):
        raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)
    kitap = (library.get_book(book_slug) or {}).get("title") or ""
    mevcut = glossary.get_glossary_rows(book_slug)
    sonuc = []
    for i in range(0, len(vakalar), parti):
        grup = vakalar[i:i + parti]
        try:
            response, model = translate._generate_with_fallback(
                translate._gemini_fabrikasi(api_key), sozluk_dogrulama.ucretsiz_zincir(), _istek(grup, kitap),
                system=TEMIZLIK_INSTRUCTION, max_tokens=translate.MAX_OUTPUT_TOKENS)
        except translate.TranslateError as hata:
            if ilerleme:
                ilerleme(f"! parti {i // parti + 1} atlandı: {hata}")
            continue
        yanitlar = {str(y.get("id")): y for y in _ayristir(getattr(response, "text", None))}
        for v in grup:
            for x in yaniti_dogrula(v, yanitlar.get(v["id"], {}), mevcut):
                sonuc.append({**x, "model": model})
        if ilerleme:
            ilerleme(f"  {min(i + parti, len(vakalar))}/{len(vakalar)} vaka")
    return sonuc


# ---------- 3. onaylı uygulama ----------
def onerileri_uygula(book_slug: str, oneriler: list[dict]) -> list[dict]:
    """YALNIZ `onay: true` ve `durum: oneri` olan işlemler. Elle yazılmış kayda dokunulmaz."""
    rapor = []
    for x in oneriler:
        if not (x.get("onay") is True and x.get("durum") == "oneri") or x.get("islem") == "dokunma":
            continue
        satir = next((r for r in glossary.get_glossary_rows(book_slug) if r["source"] == x["source"]), None)
        if satir is None:
            rapor.append({**x, "uygulandi": False, "neden": "kayıt artık yok"})
            continue
        if satir.get("origin") == "manual" or satir.get("target") != x.get("eski_karsilik"):
            rapor.append({**x, "uygulandi": False, "neden": "kayıt elle yazılmış ya da öneriden sonra değişmiş"})
            continue
        if x["islem"] == "karsilik_degistir":
            # Kullanıcı onayladığı için elle düzeltme sayılır (origin='manual'): otomatik algılama ezmez.
            glossary.set_term(book_slug, x["source"], x["yeni_karsilik"])
        elif x["islem"] == "alternatif_yazim":
            # Yazım başka bir KAYDIN kaynağıyken eklenemez: önce o kayıt silinir (tam hâli saklanır),
            # yazım eklenemezse kayıt geri yazılır — yarım işlem kalmaz.
            silinen = glossary.delete_term(book_slug, x["source"], yol="inceleme")
            try:
                if glossary.yazim_ekle(book_slug, x["kanonik"], x["source"]) is None:
                    raise glossary.YazimCakismasi("kanonik kayıt yok")
            except glossary.YazimCakismasi as hata:
                if silinen:
                    glossary.set_term(book_slug, silinen["source"], silinen.get("target"),
                                      origin=silinen.get("origin") or "auto")
                rapor.append({**x, "uygulandi": False, "neden": f"alternatif yazım eklenemedi: {hata}"})
                continue
        elif x["islem"] == "sil":
            glossary.reddet(book_slug, x["source"])
        rapor.append({**x, "uygulandi": True})
    return rapor

