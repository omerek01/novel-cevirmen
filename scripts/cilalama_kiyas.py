"""Türkçe cilalama kıyası: canlı çeviri ile aynı çevirinin cilalanmış hâli, kör hakemle.

Neden: 2026-10-13 araştırması (Lost in Literalism, ACL 2025; Iterative Translation
Refinement, EAMT 2024) çeviriden SONRA ayrı bir "hedef dilde cilalama" turunun çeviri
kokusunu (kelimesi kelimesine yapı) belirgin azalttığını, aynı kuralları çeviri
istemine eklemenin ise azaltmadığını, bazen artırdığını gösteriyor. Bizim istem
çalışmaları da (bağlam/üslup/bellek) ölçülebilir kazanç vermemişti.

Tek değişken: L kolu canlının kayıtlı çevirisi, P kolu AYNI çevirinin cilalanmışı.
Fark yalnız cilalamadan gelir. Hakem ve özet `anlam_kiyas.py` ile yapılır:
  anlam_kiyas.py hazirla --bolumler ... --cikti veri.json
  cilalama_kiyas.py cilala --veri veri.json --cikti sonuc.jsonl
  anlam_kiyas.py yargila --veri veri.json --sonuc sonuc.jsonl --ciftler P:L --cikti yargi.jsonl
  anlam_kiyas.py ozet --yargi yargi.jsonl
  cilalama_kiyas.py isaretler --sonuc sonuc.jsonl
Çıktılar roman metni içerir: depoya eklenmez.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anlam_kiyas as ak  # noqa: E402

CILALA_TALIMATI = """Sen deneyimli bir Türkçe roman editörüsün. Sana İngilizce bir web roman
bölümünün paragrafları ("en") ve her paragrafın Türkçe çevirisi ("tr") veriliyor. Görevin
çeviriyi CİLALAMAK: anlamı, bilgiyi ve sahneyi DEĞİŞTİRMEDEN metni, Türkçe yazılmış bir
romandan çıkmış gibi doğal hâle getirmek.

DÜZELT (yalnız gerçekten varsa):
- İngilizce söz dizimini izleyen, çeviri kokan cümleler: Türkçenin doğal sırasıyla yeniden kur.
- Ekten anlaşılan gereksiz özne ve iyelik zamirleri (o, onlar, onun, onların).
- İngilizce "a/an" karşılığı gereksiz "bir".
- "tarafından" ile kurulmuş edilgen yapılar: etkene çevir.
- Kalıp aktarmaları: "sahip olmak" (have), "bir şekilde" (-ly), "gibi görünüyordu" (seemed),
  gereksiz "olarak", "Bu, ..." ile başlayan açıklama cümleleri.
- Yakın tekrarlar, uzun ad tamlaması zincirleri, aynı bağlacın üst üste kullanımı.
- Tırnak ve kesme işaretlerinin yanlış kullanımı.

DOKUNMA:
- Anlam, olay sırası, kim kime ne yaptı, olumsuzluk, kip ve zaman aynen kalır. Bilgi ekleme,
  çıkarma, açıklama yapma, süsleme. Az bilinen deyim ya da eskimiş sözcük getirme.
- "korunacak_terimler" listesindeki karşılıklar ve özel adlar AYNEN kalır (yalnız aldıkları
  ek cümleye göre değişebilir).
- Hitap düzeyi (sen/siz) ve karakterlerin konuşma biçimi.
- Zaten doğal olan paragrafı DEĞİŞTİRME, olduğu gibi döndür.
- Paragraf sayısı ve sırası: her "n" tam bir kez döner; paragraf birleştirme ya da bölme yok.

Yalnız JSON: {"paragraflar":[{"n":0,"tr":"..."}]}"""

# 2. sürüm (2026-10-13): 1. sürüm akıcılığı belirgin artırdı (hakem 27-7, p 0,001) ama
# anlamda geri kaldı (22-33): zarf ve süre sözcüklerini düşürdü ("suddenly", "a few
# moments"), kaynakta olmayan sözcük ve ad ekledi, yakın ama yanlış anlamlı sözcük seçti
# ("deteriorate" -> "iflas etmek"). En küçük değişiklik ilkesi ve cümle cümle kaynak
# denetimi bu kayıpları hedefler.
CILALA_TALIMATI_2 = """Sen deneyimli bir Türkçe roman editörüsün. Sana İngilizce bir web roman
bölümünün paragrafları ("en") ve her paragrafın Türkçe çevirisi ("tr") veriliyor. Görevin
çeviri kokan yerleri düzeltmek; anlam ve bilgi BİREBİR korunur.

EN KÜÇÜK DEĞİŞİKLİK İLKESİ: yalnız gerçekten çeviri kokan, Türkçede doğal durmayan yeri
değiştir; geri kalan sözcüklere dokunma. Doğal olan paragrafı aynen döndür.

DÜZELTİLECEKLER (varsa):
- İngilizce söz dizimini izleyen cümle: Türkçenin doğal sırasıyla kur.
- Ekten anlaşılan gereksiz özne/iyelik zamiri (o, onlar, onun). Zamiri ASLA bir kişi adıyla
  değiştirme; kim olduğu belirsizleşecekse zamiri bırak.
- İngilizce "a/an" karşılığı gereksiz "bir"; "tarafından" edilgeni; "sahip olmak", "bir
  şekilde", "gibi görünüyordu", gereksiz "olarak" kalıplarının doğal karşılığı.
- Yakın sözcük tekrarı ve yanlış tırnak/kesme işareti.

ANLAM KURALLARI (çiğnenemez):
- Kaynaktaki HER bilgi kalır: zarflar ve süre/zaman sözcükleri (suddenly, immediately, a few
  moments, now, still, already), çekinceler (seemed, perhaps, almost), sayılar, olumsuzluk, kip.
- Kaynakta olmayan hiçbir sözcük, ad, duygu ya da açıklama EKLENMEZ.
- Bir sözcüğü anlamı farklı bir sözcükle değiştirme ("bozulmak" yerine "iflas etmek" olmaz).
- "korunacak_terimler" listesindeki karşılıklar ve özel adlar aynen kalır (yalnız ekleri değişebilir).
- Hitap düzeyi (sen/siz) ve konuşma biçimi aynen kalır.
- Paragraf sayısı ve sırası aynı: her "n" tam bir kez döner.

Bitirmeden önce değiştirdiğin her cümleyi İngilizcesiyle karşılaştır: kaynaktaki bilgilerin
hepsi duruyor mu, kaynakta olmayan bir şey girdi mi? Şüphedeysen özgün cümleyi bırak.

Yalnız JSON: {"paragraflar":[{"n":0,"tr":"..."}]}"""

# 3. sürüm (2026-10-13, kullanıcı kararı "ara sürümü geliştir, ölç"): 1. sürümün
# düzeltme listesi (akıcılık kazancı) + 2. sürümün anlam kuralları ve cümle cümle
# kaynak denetimi. 2. sürüm 447 paragrafın yalnız 57'sine dokunmuştu: "en küçük
# değişiklik" yerine "çeviri kokan her yeri düzelt, doğal olana dokunma".
CILALA_TALIMATI_3 = """Sen deneyimli bir Türkçe roman editörüsün. Sana İngilizce bir web roman
bölümünün paragrafları ("en") ve her paragrafın Türkçe çevirisi ("tr") veriliyor. Görevin
çeviriyi CİLALAMAK: metni, Türkçe yazılmış bir romandan çıkmış gibi doğal kılmak. Anlam ve
bilgi BİREBİR korunur.

DÜZELT (çeviri kokan her yeri düzelt; doğal olan cümleye dokunma):
- İngilizce söz dizimini izleyen cümleler: Türkçenin doğal sırasıyla yeniden kur.
- Ekten anlaşılan gereksiz özne ve iyelik zamirleri (o, onlar, onun). Zamiri ASLA bir kişi
  adıyla değiştirme; kim olduğu belirsizleşecekse zamiri bırak.
- İngilizce "a/an" karşılığı gereksiz "bir"; "tarafından" ile kurulmuş edilgen yapılar
  (etkene çevir).
- Kalıp aktarmaları: "sahip olmak" (have), "bir şekilde" (-ly), "gibi görünüyordu" (seemed;
  çekince anlamını koru: "-mış gibiydi", "anlaşılan"), gereksiz "olarak", "Bu, ..." ile
  başlayan açıklama cümleleri.
- Yakın sözcük tekrarı, uzun ad tamlaması zincirleri, aynı bağlacın üst üste kullanımı.
- Tırnak ve kesme işaretlerinin yanlış kullanımı.

ANLAM KURALLARI (çiğnenemez):
- Kaynaktaki HER bilgi kalır: zarflar ve süre/zaman sözcükleri (suddenly, immediately, a few
  moments, now, still, already), çekinceler (seemed, perhaps, almost, probably), sayılar,
  olumsuzluk, kip ve zaman.
- Kaynakta olmayan hiçbir sözcük, ad, duygu, açıklama ya da süsleme EKLENMEZ.
- Bir sözcüğü yalnız AYNI anlamda daha doğal bir karşılıkla değiştir; yakın ama farklı
  anlamlı sözcük seçme ("bozulmak" yerine "iflas etmek", "kaynak" yerine "masraf" olmaz).
- Az bilinen deyim ya da eskimiş sözcük getirme.
- "korunacak_terimler" listesindeki karşılıklar ve özel adlar AYNEN kalır (yalnız aldıkları
  ek cümleye göre değişebilir).
- Hitap düzeyi (sen/siz) ve karakterlerin konuşma biçimi aynen kalır.
- Paragraf sayısı ve sırası aynı: her "n" tam bir kez döner; paragraf birleştirme ya da
  bölme yok.

Bitirmeden önce değiştirdiğin her cümleyi İngilizcesiyle karşılaştır: kaynaktaki bilgilerin
hepsi duruyor mu, kaynakta olmayan bir şey girdi mi? Bir değişiklik anlamı zayıflatıyorsa o
cümlede özgün çeviriyi bırak.

Yalnız JSON: {"paragraflar":[{"n":0,"tr":"..."}]}"""

TALIMATLAR = {"1": CILALA_TALIMATI, "2": CILALA_TALIMATI_2, "3": CILALA_TALIMATI_3}

# Cilalama + canlıdaki kalite katmanı (denetle ve onar), sunucuda (Vertex kimliği orada).
# Kalite katmanı canlı yoldaki gibi kurulur: aynı model zinciri, aynı kabul kontrolü
# (sözlük ihlali ve İngilizce kalıntı). Geçici DB kullanılır; canlı veriye yazılmaz.
_CILALA_KALITE = r'''
import json, os, sys, tempfile, time, threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dotenv import load_dotenv
load_dotenv('/home/OMEREK/novel-cevirmen/.env')
sys.path.insert(0, UZAK_APP)
os.environ.update(NOVEL_DB_PATH=tempfile.mkdtemp(prefix='cilalama-') + '/deney.db', SOZLUK_DOGRULAMA='0')
from core import translate as t, ceviri_kalite as ck
p = json.loads(YUK)
modeller = (p['model'],)
fabrika = t._gemini_fabrikasi('')
sozluk, kosullar = p['sozluk'], p['kosullar']
kilit = threading.Lock()
def uret(user, system, asama):
    sema = t.yanit_semasi(None) if hasattr(t, 'yanit_semasi') else nullcontext()
    with t.api_durum.baglam(asama=asama), sema:
        return t._generate_with_fallback(fabrika, modeller, user, system=system, max_tokens=t.MAX_OUTPUT_TOKENS)
def cilala(is_):
    for deneme in range(3):
        try:
            r, _ = uret(json.dumps(is_['istem'], ensure_ascii=False), p['talimat'], 'cilalama')
            veri = json.loads(r.text)
            if isinstance(veri, list) and len(veri) == 1 and isinstance(veri[0], dict):
                veri = veri[0]
            liste = veri.get('paragraflar') if isinstance(veri, dict) else veri
            gelen = {}
            for k in liste:
                if isinstance(k, dict) and type(k.get('n')) is int and isinstance(k.get('tr'), str) and k['tr'].strip():
                    gelen.setdefault(k['n'], k['tr'].strip())
            return [gelen.get(i, s) for i, s in enumerate(is_['tr'])], sum(1 for i in range(len(is_['tr'])) if i not in gelen)
        except Exception as e:
            hata = e
            if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                time.sleep(60)
                continue
            if deneme < 2:
                continue
    raise hata
def isle(is_):
    s = time.monotonic(); satir = {'bolum': is_['bolum']}
    en = is_['en']
    try:
        cilali, eksik = cilala(is_)
        satir.update(cilali=cilali, eksik=eksik)
    except Exception as e:
        satir.update(hata='cilalama: ' + type(e).__name__ + ': ' + str(e)[:200])
        with kilit:
            print(json.dumps(satir, ensure_ascii=True), flush=True)
        return
    tr = list(cilali)
    ilgili = t._relevant_glossary(sozluk, '\n\n'.join(en))
    kos = {k: v for k, v in kosullar.items() if k in ilgili}
    def kabul(yeni):
        degisen = {i for i, x in enumerate(yeni) if x != tr[i]}
        ihlal = t.sozluk_ihlali_paragraflari(sozluk, yeni, en, kosullar)
        kalan = t.ingilizce_kalinti(yeni, en, sozluk)
        return not (degisen.intersection(ihlal) or degisen.intersection(kalan))
    try:
        metrik = ck.denetle_ve_onar(tr, en, ilgili, kos, uret, kabul)
        satir['kalite'] = {k: metrik.get(k) for k in ('durum', 'denetlenen', 'onarilan', 'onarilamayan', 'supheli')}
        satir['onarilmis'] = tr
    except ck.KaliteHatasi as e:
        satir['kalite_hata'] = str(e)[:200]
    satir['saniye'] = round(time.monotonic() - s, 1)
    with kilit:
        print(json.dumps(satir, ensure_ascii=True), flush=True)
with ThreadPoolExecutor(p['es']) as ex:
    list(ex.map(isle, p['isler']))
'''

# Çeviri kokusu belirtileri (1000 sözcük başına). Yardımcı ölçüdür, hakemin yerine geçmez.
ISARETLER = {
    "bir_sekilde": r"\bbir şekilde\b",
    "sahip_olmak": r"\bsahip (?:ol|değil)",
    "tarafindan": r"\btarafından\b",
    "ozne_zamiri": r"(?:^|[.!?…]\s+|[\"“'‘]\s*)(?:O|Onlar|Onun|Onların)\b",
    "gibi_gorunuyor": r"\bgibi görün(?:üyor|dü|mek)",
    "olarak": r"\bolarak\b",
    "bu_virgul": r"(?:^|[.!?…]\s+)Bu,",
    "kendi": r"\bkendi(?:si|ni|ne|nde|nden|leri)?\b",
}


def korunacak_terimler(x: dict) -> list[str]:
    """Bölümde kaynağı geçen sözlük kayıtlarının karşılıkları (boş karşılık = İngilizce kalır)."""
    kaynak = x["source"].casefold()
    sonuc = set()
    for en, tr in (x.get("glossary") or {}).items():
        if not en or not re.search(r"(?<!\w)" + re.escape(en.casefold()) + r"(?!\w)", kaynak):
            continue
        sonuc.add((tr or en).strip())
    return sorted(s for s in sonuc if s)


def cilalama_isi(x: dict) -> dict:
    en = x["source"].split("\n\n")
    tr = (x.get("canli_ceviri") or "").split("\n\n")
    if len(en) != len(tr):
        raise ValueError(f"{x['chapter_no']}: kaynak ve çeviri paragraf sayısı tutmuyor")
    return {"anahtar": str(x["chapter_no"]),
            "istem": {"korunacak_terimler": korunacak_terimler(x),
                      "paragraflar": [{"n": i, "en": e, "tr": t} for i, (e, t) in enumerate(zip(en, tr))]}}


def cilalama_coz(yanit, ozgun: list[str]) -> tuple[list[str], int]:
    """Cilalanmış paragraflar; eksik ya da boş dönen paragraf özgün kalır (sayısı döner)."""
    yanit = ak._tek_sarmali_ac(yanit)
    liste = yanit.get("paragraflar") if isinstance(yanit, dict) else yanit
    if not isinstance(liste, list):
        raise ValueError("Cilalama yanıtında paragraf listesi yok.")
    gelen = {}
    for k in liste:
        if isinstance(k, dict) and type(k.get("n")) is int and isinstance(k.get("tr"), str) and k["tr"].strip():
            gelen.setdefault(k["n"], k["tr"].strip())
    cikti = [gelen.get(i, t) for i, t in enumerate(ozgun)]
    return cikti, sum(1 for i in range(len(ozgun)) if i not in gelen)


def cilala(a):
    if Path(a.cikti).exists():
        raise SystemExit("Çıktı var; başka hedef kullanın.")
    ornekler = json.loads(Path(a.veri).read_text(encoding="utf-8"))
    isler = [cilalama_isi(x) for x in ornekler]
    ornek = {str(x["chapter_no"]): x for x in ornekler}
    bekleyen = isler
    with open(a.cikti, "x", encoding="utf-8") as f:
        for x in ornekler:
            f.write(json.dumps({"kol": "L", "bolum": x["chapter_no"], "source": x["source"],
                                "translation": x["canli_ceviri"], "model": x.get("canli_model")},
                               ensure_ascii=False) + "\n")
        for tur in range(3):
            if not bekleyen:
                break
            yuk = {"hakem": a.model, "talimat": TALIMATLAR[a.surum], "es": a.es,
                   "isler": [{"anahtar": i["anahtar"], "istem": i["istem"]} for i in bekleyen]}
            yanitlar = {y["anahtar"]: y for y in ak._uzak(ak._YARGILA, yuk)}
            kalan = []
            for is_ in bekleyen:
                y = yanitlar.get(is_["anahtar"], {})
                x = ornek[is_["anahtar"]]
                ozgun = x["canli_ceviri"].split("\n\n")
                try:
                    paragraflar, eksik = cilalama_coz(json.loads(y.get("yanit") or ""), ozgun)
                except (ValueError, json.JSONDecodeError) as exc:
                    print(f"  {is_['anahtar']}: geçersiz ({y.get('hata') or exc}; bitiş={y.get('bitis')}); "
                          f"tur {tur + 1}", flush=True)
                    kalan.append(is_)
                    continue
                f.write(json.dumps({"kol": a.kol, "bolum": x["chapter_no"], "source": x["source"],
                                    "translation": "\n\n".join(paragraflar), "model": a.model,
                                    "talimat_surumu": a.surum,
                                    "eksik_paragraf": eksik, "saniye": y.get("saniye")},
                                   ensure_ascii=False) + "\n"); f.flush()
                print(f"  {is_['anahtar']}: tamam ({y.get('saniye')} sn, eksik {eksik})", flush=True)
            bekleyen = kalan
    if bekleyen:
        print("Cilalanamayan bölümler:", [i["anahtar"] for i in bekleyen])


def cilala_kalite(a):
    """Cilalama + canlı kalite katmanı. Kollar: L (canlı), P{s} (cilalı), P{s}K (cilalı + kalite)."""
    if Path(a.cikti).exists():
        raise SystemExit("Çıktı var; başka hedef kullanın.")
    ornekler = json.loads(Path(a.veri).read_text(encoding="utf-8"))
    isler = []
    for x in ornekler:
        is_ = cilalama_isi(x)
        isler.append({"bolum": x["chapter_no"], "istem": is_["istem"],
                      "en": x["source"].split("\n\n"), "tr": x["canli_ceviri"].split("\n\n")})
    ilk = ornekler[0]
    yuk = {"model": a.model, "talimat": TALIMATLAR[a.surum], "es": a.es,
           "sozluk": ilk.get("glossary") or {}, "kosullar": ilk.get("conditions") or {}, "isler": isler}
    ornek = {x["chapter_no"]: x for x in ornekler}
    kol, kolk = f"P{a.surum}", f"P{a.surum}K"
    with open(a.cikti, "x", encoding="utf-8") as f:
        def yaz(satir):
            x = ornek[satir["bolum"]]
            if satir.get("hata"):
                print(f"  {satir['bolum']}: {satir['hata']}", flush=True)
                return
            f.write(json.dumps({"kol": kol, "bolum": x["chapter_no"], "source": x["source"],
                                "translation": "\n\n".join(satir["cilali"]), "eksik_paragraf": satir.get("eksik"),
                                "talimat_surumu": a.surum}, ensure_ascii=False) + "\n")
            if satir.get("onarilmis"):
                f.write(json.dumps({"kol": kolk, "bolum": x["chapter_no"], "source": x["source"],
                                    "translation": "\n\n".join(satir["onarilmis"]), "kalite": satir.get("kalite"),
                                    "talimat_surumu": a.surum}, ensure_ascii=False) + "\n")
            f.flush()
            k = satir.get("kalite") or {}
            print(f"  {satir['bolum']}: tamam ({satir.get('saniye')} sn; onarılan {len(k.get('onarilan') or [])}, "
                  f"onarılamayan {len(k.get('onarilamayan') or [])}{'; ' + satir['kalite_hata'] if satir.get('kalite_hata') else ''})",
                  flush=True)
        for x in ornekler:
            f.write(json.dumps({"kol": "L", "bolum": x["chapter_no"], "source": x["source"],
                                "translation": x["canli_ceviri"], "model": x.get("canli_model")},
                               ensure_ascii=False) + "\n")
        f.flush()
        ak._uzak(_CILALA_KALITE, yuk, yaz)


def _sozcuk_sayisi(metin: str) -> int:
    return len(re.findall(r"\w+", metin))


def isaretler(a):
    satirlar = [json.loads(s) for s in Path(a.sonuc).read_text(encoding="utf-8").splitlines() if s.strip()]
    kollar: dict[str, dict] = {}
    for s in satirlar:
        k = kollar.setdefault(s["kol"], {"sozcuk": 0, **{ad: 0 for ad in ISARETLER}})
        metin = s.get("translation") or ""
        k["sozcuk"] += _sozcuk_sayisi(metin)
        for ad, desen in ISARETLER.items():
            k[ad] += len(re.findall(desen, metin, flags=re.MULTILINE))
    print("| Belirti (1000 sözcükte) | " + " | ".join(kollar) + " |")
    print("|---|" + "---:|" * len(kollar))
    for ad in ISARETLER:
        print(f"| {ad} | " + " | ".join(f"{1000 * k[ad] / max(1, k['sozcuk']):.2f}" for k in kollar.values()) + " |")
    print("| sözcük | " + " | ".join(str(k["sozcuk"]) for k in kollar.values()) + " |")
    # Değişen paragraf oranı ve korunacak terim kaybı (P'de L'den az geçen terim).
    ornek = {(s["kol"], s["bolum"]): s for s in satirlar}
    if a.veri:
        veri = {x["chapter_no"]: x for x in json.loads(Path(a.veri).read_text(encoding="utf-8"))}
        kayip, degisen, toplam = [], 0, 0
        for (kol, no), s in sorted(ornek.items()):
            if kol == "L" or ("L", no) not in ornek:
                continue
            lt, pt = ornek[("L", no)]["translation"], s["translation"]
            l_par, p_par = lt.split("\n\n"), pt.split("\n\n")
            toplam += len(l_par)
            degisen += sum(1 for x, y in zip(l_par, p_par) if ak._normal(x) != ak._normal(y))
            for terim in korunacak_terimler(veri[no]):
                desen = r"(?<!\w)" + re.escape(terim.casefold())
                if len(re.findall(desen, pt.casefold())) < len(re.findall(desen, lt.casefold())):
                    kayip.append((no, terim))
        print(f"\nDeğişen paragraf: {degisen}/{toplam}")
        print(f"Terim geçişi azalan (bölüm, terim): {len(kayip)}", kayip[:30])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)
    c = alt.add_parser("cilala"); c.add_argument("--veri", required=True); c.add_argument("--cikti", required=True)
    c.add_argument("--model", default="gemini-3.8-flash"); c.add_argument("--es", type=int, default=2)
    c.add_argument("--surum", choices=sorted(TALIMATLAR), default="2")
    c.add_argument("--kol", default="P", help="Cilalanmış kolun adı (hakemde L ile eşlenir)")
    c.set_defaults(f=cilala)
    k = alt.add_parser("cilala-kalite"); k.add_argument("--veri", required=True); k.add_argument("--cikti", required=True)
    k.add_argument("--model", default="vertex/gemini-3.8-flash", help="translate zinciri adı (kalite katmanı da bunu kullanır)")
    k.add_argument("--es", type=int, default=2); k.add_argument("--surum", choices=sorted(TALIMATLAR), default="3")
    k.set_defaults(f=cilala_kalite)
    i = alt.add_parser("isaretler"); i.add_argument("--sonuc", required=True); i.add_argument("--veri")
    i.set_defaults(f=isaretler)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
