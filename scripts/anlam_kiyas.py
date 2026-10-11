"""Anlam/bağlam kıyası: kolları aynı girdiyle çevir, ayrı bir hakemle kör karşılaştır.

Neden: uzunluk oranı ve aynı modelin kendi denetimi anlam farkını ayırt etmiyor;
2026-10-10 analiz açık/kapalı kıyası "daha çok bulgu"yu kalite düşüşünden ayıramadı.
Bu araç kolları (bayrak kümeleri) SABİT kaynak/sözlük/önceki bölüm/bellek havuzuyla
çevirir, sonra yalnız iki çevirinin belirgin ayrıştığı paragrafları ayrı bir hakem
modele (varsayılan gemini-2.5-pro) X/Y sırası rastgele, kör olarak sorar: anlam
(kaynağa sadakat), akıcılık ve tutarlılık AYRI oylanır. Sonuç işaret testiyle özetlenir.

Adımlar (hepsi ücretli çağrıları yalnız açıkça istenince yapar):
  hazirla   salt-okunur canlı DB'den bölümleri, sözlüğü, önceki bölümü, bellek havuzunu alır
  calistir  kolları sunucuda (Vertex kimliği orada) geçici DB ile çevirir; canlı veriye yazmaz
  yargila   kol çiftlerini hakem modele sorar
  ozet      kazanma/kaybetme/beraberlik ve işaret testi
  ornek     elle doğrulama için rastgele hakem kararlarını yazdırır (dosyaya yazmaz)

Kollar SIRAYLA koşar: bayraklar ortam değişkenidir ve aynı süreçte iki kol aynı anda
koşarsa birbirinin bayrağını görür. Bölümler bir kol içinde paralel çevrilir.
Hakem notları kısa tutulur ve alıntı istenmez: raporlar romandan metin taşımamalı.
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK / "app") not in sys.path:
    sys.path.insert(0, str(KOK / "app"))

SUNUCU = "OMEREK@100.75.105.102"
UZAK_PYTHON = "/home/OMEREK/novel-cevirmen/.venv/bin/python -u -"
CANLI_DB = "/home/OMEREK/novel-cevirmen/cache/chapters.db"
UZAK_APP = "/home/OMEREK/novel-cevirmen-sozluk/app"
ENJEKTE = ["ceviri_kalite", "ceviri_baglam", "ceviri_bellek", "ceviri_izleri", "translate"]

# Kol = bayrak kümesi. Kalite denetimi bütün kollarda KAPALI: onarım farkları örterdi.
KOLLAR = {
    "A": {"CEVIRI_ANALIZ": "1", "CEVIRI_STIL": "1", "CEVIRI_BELLEK": "0"},   # canlı yol
    "A2": {"CEVIRI_ANALIZ": "1", "CEVIRI_STIL": "1", "CEVIRI_BELLEK": "0"},  # gürültü tabanı
    "B": {"CEVIRI_ANALIZ": "0", "CEVIRI_STIL": "1", "CEVIRI_BELLEK": "0"},   # eski yol
    "C": {"CEVIRI_ANALIZ": "1", "CEVIRI_STIL": "0", "CEVIRI_BELLEK": "0"},   # özet, üslupsuz
    "D": {"CEVIRI_ANALIZ": "0", "CEVIRI_STIL": "1", "CEVIRI_BELLEK": "1"},   # bellek, analizsiz
    "E": {"CEVIRI_ANALIZ": "1", "CEVIRI_STIL": "0", "CEVIRI_BELLEK": "1"},   # özet + bellek
}
BOYUTLAR = ("anlam", "akicilik", "tutarlilik")

HAKEM_TALIMATI = """Sen İngilizceden Türkçeye roman çevirisinde deneyimli bir editörsün.
Her maddede bir İngilizce paragraf (kaynak), ondan önceki kaynak paragraf (yalnız bağlam)
ve kaynağın iki Türkçe çevirisi (X ve Y) var. Çevirilerin hangi sistemden geldiğini
bilmiyorsun; X/Y sırası rastgeledir, sıraya göre taraf tutma.
Üç boyutu AYRI değerlendir:
- anlam: kaynağa sadakat. Yanlış anlam, atlanan ya da eklenen bilgi, yanlış özne/nesne/
  gönderge (kim kime ne yaptı), olumsuzluk/kip/zaman hatası, deyimin yanlış ya da kelimesi
  kelimesine aktarılması, sahne bağlamına uymayan sözcük anlamı.
- akicilik: Türkçenin doğallığı ve dilbilgisi (ek ve yazım hatası, bozuk cümle). Anlamı
  etkilemeyen üslup tercihi hata değildir.
- tutarlilik: "onceki_ceviriler" örnekleriyle (kitabın önceki bölümlerinin çevirisi) ve
  bölümün geri kalanıyla tutarlılık: hitap (sen/siz, efendim), rütbe ve unvan karşılıkları,
  karakterlerin konuşma biçimi, tırnak ve yazım biçimi.
Her boyut için "X", "Y" ya da "esit" ver. Fark yoksa ya da yalnız zevk farkıysa "esit";
belirgin ve somut bir fark varsa taraf seç. Alıntı yapma: "not" alanına en fazla 15
kelimeyle somut nedeni yaz.
Yalnız JSON: {"kararlar":[{"id":0,"anlam":"X","akicilik":"esit","tutarlilik":"esit",
"not":"Y 'last straw' deyimini kelimesi kelimesine çevirmiş"}]}. Her id tam bir kez."""

_NOKTALAMA = re.compile(r"[^\w\s]", re.UNICODE)


def _normal(metin: str) -> str:
    return " ".join(_NOKTALAMA.sub(" ", (metin or "").casefold()).split())


def maddeler(a: dict, b: dict, tohum: int, esik: float = 0.9) -> list[dict]:
    """İki kolun belirgin ayrıştığı paragraflar; hiza tutmazsa boş liste.

    Noktalama/harf büyüklüğü farkı ayrışma sayılmaz. X/Y yönü tohumla rastgeledir."""
    if not a.get("source") or not b.get("source") or a["source"] != b["source"]:
        return []
    en = a["source"].split("\n\n")
    ta, tb = (a.get("translation") or "").split("\n\n"), (b.get("translation") or "").split("\n\n")
    if not (len(en) == len(ta) == len(tb)):
        return []
    rng = random.Random(tohum)
    sonuc = []
    for i, (e, x, y) in enumerate(zip(en, ta, tb)):
        if difflib.SequenceMatcher(None, _normal(x), _normal(y), autojunk=False).ratio() >= esik:
            continue
        x_kol = rng.choice(("a", "b"))
        sonuc.append({"p": i, "kaynak": e, "onceki_kaynak": en[i - 1] if i else "",
                      "a": x, "b": y, "x_kol": x_kol,
                      "X": x if x_kol == "a" else y, "Y": y if x_kol == "a" else x})
    return sonuc


def kararlari_coz(yanit: dict, madde_listesi: list[dict]) -> list[dict]:
    """Hakemin X/Y kararını kola çevirir; eksik/fazla/geçersiz yanıt ValueError."""
    if not isinstance(yanit, dict) or not isinstance(yanit.get("kararlar"), list):
        raise ValueError("Hakem yanıtında kararlar listesi yok.")
    gorulen: dict[int, dict] = {}
    for k in yanit["kararlar"]:
        if not isinstance(k, dict) or type(k.get("id")) is not int:
            raise ValueError("Hakem kararı biçimsiz.")
        if k["id"] in gorulen or not 0 <= k["id"] < len(madde_listesi):
            raise ValueError("Hakem kararı yinelenmiş ya da aralık dışı.")
        if any(k.get(b) not in ("X", "Y", "esit") for b in BOYUTLAR):
            raise ValueError("Hakem kararının değeri geçersiz.")
        gorulen[k["id"]] = k
    if len(gorulen) != len(madde_listesi):
        raise ValueError("Hakem bütün maddelere karar vermedi.")
    sonuc = []
    for i, m in enumerate(madde_listesi):
        k = gorulen[i]
        cevir = {"X": m["x_kol"], "Y": "b" if m["x_kol"] == "a" else "a", "esit": "esit"}
        sonuc.append({"p": m["p"], **{b: cevir[k[b]] for b in BOYUTLAR},
                      "not": str(k.get("not") or "")[:200]})
    return sonuc


def eksik_isler(satirlar: list[dict], kollar: list[str], bolumler: list[int]) -> dict[str, list[int]]:
    """Kaldığı yerden devam: çevirisi olmayan (hiç koşmamış ya da hata vermiş) kol/bölümler."""
    tamam = {(r.get("kol"), r.get("bolum")) for r in satirlar if r.get("translation")}
    sonuc = {k: sorted(b for b in bolumler if (k, b) not in tamam) for k in kollar}
    return {k: v for k, v in sonuc.items() if v}


def isaret_testi(a: int, b: int) -> float:
    """İki yönlü kesin işaret testi (beraberlikler hariç)."""
    n = a + b
    if n == 0:
        return 1.0
    kuyruk = sum(math.comb(n, i) for i in range(min(a, b) + 1)) / 2 ** n
    return min(1.0, 2 * kuyruk)


def boyut_ozeti(kararlar: list[dict], boyut: str) -> dict:
    a = sum(k[boyut] == "a" for k in kararlar)
    b = sum(k[boyut] == "b" for k in kararlar)
    esit = sum(k[boyut] == "esit" for k in kararlar)
    return {"a": a, "b": b, "esit": esit, "p": isaret_testi(a, b)}


# ---------------------------------------------------------------- uzak çalıştırma

def _uzak(kod: str, yuk: dict, satir_isle=None, zaman_asimi=None) -> list[dict]:
    """Kodu sunucuda çalıştırır; stdout'un her satırı bir JSON nesnesidir."""
    uzak = "YUK=" + repr(json.dumps(yuk, ensure_ascii=True)) + "\n" + kod
    proc = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-i",
         str(Path.home() / ".ssh/google_compute_engine"), SUNUCU, UZAK_PYTHON],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdin.write(uzak.encode()); proc.stdin.close()
    satirlar = []
    for satir in proc.stdout:
        veri = json.loads(satir)
        satirlar.append(veri)
        if satir_isle:
            satir_isle(veri)
    if proc.wait(timeout=zaman_asimi):
        raise RuntimeError(proc.stderr.read().decode("utf-8", "replace")[-3000:])
    return satirlar


_HAZIRLA = r'''
import json, sqlite3, sys
sys.path.insert(0, UZAK_APP)
from core import glossary as g
def ro(): return sqlite3.connect('file:' + CANLI_DB + '?mode=ro', uri=True)
g._connect = ro
p = json.loads(YUK); c = ro(); c.row_factory = sqlite3.Row
for no in p['bolumler']:
    r = c.execute("select * from chapters where book_slug=? and chapter_no=? and source_text is not null "
                  "and ifnull(content_type,'text')!='html' order by created_at desc", (p['kitap'], no)).fetchone()
    if r is None: continue
    o = c.execute("select * from chapters where book_slug=? and chapter_no=? and ifnull(content_type,'text')!='html' "
                  "order by created_at desc", (p['kitap'], no - 1)).fetchone()
    havuz = [tuple(x) for x in c.execute(
        "select chapter_no, source_text, translation from chapters where book_slug=? and chapter_no<? "
        "and chapter_no>=? and source_text is not null and ifnull(content_type,'text')!='html' "
        "order by chapter_no desc", (p['kitap'], no, no - p['havuz']))]
    print(json.dumps({'book_slug': r['book_slug'], 'chapter_no': r['chapter_no'], 'url': r['url'],
        'source': r['source_text'], 'canli_ceviri': r['translation'], 'canli_model': r['model'],
        'glossary': g.ceviri_sozlugu(r['book_slug']), 'conditions': g.ceviri_kosullari(r['book_slug']),
        'prev_context': o['translation'] if o else '',
        'previous': ({'url': o['url'], 'book_slug': o['book_slug'], 'chapter_no': o['chapter_no'],
                      'source': (o['raw_source'] or o['source_text']), 'hizali_kaynak': o['source_text'] or '',
                      'translation': o['translation'] or ''} if o else None),
        'havuz_satirlari': havuz}, ensure_ascii=True), flush=True)
'''

_ENJEKSIYON = r'''
import json, os, sys, tempfile, types, time, threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv('/home/OMEREK/novel-cevirmen/.env')
sys.path.insert(0, UZAK_APP)
p = json.loads(YUK)
tmp = tempfile.mkdtemp(prefix='anlam-kiyas-')
os.environ.update(NOVEL_DB_PATH=tmp + '/deney.db', SOZLUK_DOGRULAMA='0', CEVIRI_KALITE='0')
import core
for name, code in p['kod'].items():
    m = types.ModuleType('core.' + name); m.__package__ = 'core'; m.__file__ = '<deney-' + name + '>'
    sys.modules['core.' + name] = m; setattr(core, name, m)
    exec(compile(code, m.__file__, 'exec'), m.__dict__)
'''

_CALISTIR = _ENJEKSIYON + r'''
from core import translate as t, ceviri_izleri as iz
kilit = threading.Lock()
def cevir(kol, x):
    s = time.monotonic()
    satir = {'kol': kol, 'kitap': x['book_slug'], 'bolum': x['chapter_no']}
    # Vertex 429 "meşgul" geçicidir: deney canlı okumayla aynı kotayı paylaşır,
    # bu yüzden bir dakika beklenip en fazla iki kez yeniden denenir.
    for deneme in range(3):
        try:
            r = t.translate_chapter(x['source'], '', glossary=x['glossary'], kosullar=x.get('conditions') or {},
                models=(p['model'],), prev_context=x.get('prev_context') or '', bolum_no=x['chapter_no'],
                book_slug=x['book_slug'], bolum_url=x['url'] + '#' + kol, onceki_bolum=x.get('previous'),
                bellek_havuzu=x.get('bellek_havuzu') or [])
            satir.update(translation=r['translation'], source=r['source'], model=r.get('model'), deneme=deneme + 1)
            satir.pop('hata_turu', None); satir.pop('hata_mesaji', None)
            izler = iz.iz_oku(x['url'] + '#' + kol)
            if izler:
                v = izler[0]['veri']
                satir['iz'] = {'bellek': v.get('bellek'), 'ozet': len((v.get('analiz') or {}).get('ozet') or []),
                               'terim': len((v.get('analiz') or {}).get('terimler') or [])}
            break
        except Exception as e:
            satir.update(hata_turu=type(e).__name__, hata_mesaji=str(e)[:300])
            if deneme < 2 and ('429' in str(e) or 'meşgul' in str(e)):
                time.sleep(60)
                continue
            break
    satir['saniye'] = round(time.monotonic() - s, 1)
    with kilit:
        print(json.dumps(satir, ensure_ascii=True), flush=True)
for kol in p['kollar']:
    hedef = [x for x in p['ornekler'] if x['chapter_no'] in set(p['isler'][kol])]
    os.environ.update(p['bayraklar'][kol])
    with ThreadPoolExecutor(p['es']) as ex:
        list(ex.map(lambda x: cevir(kol, x), hedef))
'''

_YARGILA = r'''
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv('/home/OMEREK/novel-cevirmen/.env')
sys.path.insert(0, UZAK_APP)
from core import translate as t
from google import genai
from google.genai import types
p = json.loads(YUK)
istemci = genai.Client(vertexai=True, project=t.vertex_projesi(),
                       location=(os.getenv(t.VERTEX_KONUM_ENV) or 'global').strip(),
                       http_options=types.HttpOptions(timeout=600000))
kilit = threading.Lock()
def sor(is_):
    s = time.monotonic(); satir = {'anahtar': is_['anahtar']}
    try:
        r = istemci.models.generate_content(model=p['hakem'], contents=json.dumps(is_['istem'], ensure_ascii=False),
            config=types.GenerateContentConfig(system_instruction=p['talimat'], response_mime_type='application/json',
                                               temperature=0, max_output_tokens=32768))
        satir.update(yanit=r.text or '', bitis=str(r.candidates[0].finish_reason).split('.')[-1])
    except Exception as e:
        satir.update(hata=type(e).__name__ + ': ' + str(e)[:200])
    satir['saniye'] = round(time.monotonic() - s, 1)
    with kilit:
        print(json.dumps(satir, ensure_ascii=True), flush=True)
with ThreadPoolExecutor(p['es']) as ex:
    list(ex.map(sor, p['isler']))
'''


def _sabitle(kod: str) -> str:
    return kod.replace("UZAK_APP", repr(UZAK_APP)).replace("CANLI_DB", repr(CANLI_DB))


# ---------------------------------------------------------------- komutlar

def hazirla(a):
    from core import ceviri_bellek
    if Path(a.cikti).exists():
        raise SystemExit("Çıktı var; başka hedef kullanın.")
    bolumler = [int(x) for x in a.bolumler.split(",")]
    ornekler = []
    for x in _uzak(_sabitle(_HAZIRLA), {"kitap": a.kitap, "bolumler": bolumler, "havuz": a.havuz}):
        x["bellek_havuzu"] = ceviri_bellek.havuz_kur(x.pop("havuz_satirlari"))
        ornekler.append(x)
    Path(a.cikti).parent.mkdir(parents=True, exist_ok=True)
    Path(a.cikti).write_text(json.dumps(ornekler, ensure_ascii=False), encoding="utf-8")
    print([(x["chapter_no"], len(x["source"]), len(x["bellek_havuzu"]), bool(x["previous"])) for x in ornekler])


def calistir(a):
    """Çıktı varsa kaldığı yerden sürer: yalnız çevirisi olmayan kol/bölümler koşar."""
    ornekler = json.loads(Path(a.veri).read_text(encoding="utf-8"))
    kollar = a.kollar.split(",")
    onceki = ([json.loads(s) for s in Path(a.cikti).read_text(encoding="utf-8").splitlines() if s.strip()]
              if Path(a.cikti).exists() else [])
    isler = eksik_isler(onceki, kollar, [x["chapter_no"] for x in ornekler])
    if not isler:
        print("Eksik iş yok."); return
    print("Koşacak:", isler, flush=True)
    yuk = {"ornekler": ornekler, "kollar": [k for k in kollar if k in isler], "isler": isler,
           "bayraklar": {k: KOLLAR[k] for k in isler}, "model": a.model, "es": a.es,
           "kod": {n: (KOK / "app/core" / (n + ".py")).read_text(encoding="utf-8") for n in ENJEKTE}}
    with open(a.cikti, "a", encoding="utf-8") as f:
        def yaz(satir):
            f.write(json.dumps(satir, ensure_ascii=False) + "\n"); f.flush()
            print(json.dumps({k: satir.get(k) for k in ("kol", "bolum", "saniye", "hata_turu")}), flush=True)
        _uzak(_sabitle(_CALISTIR), yuk, yaz)


def _isler(sonuclar, ornekler, ciftler, tohum):
    from core import ceviri_bellek
    ornek = {x["chapter_no"]: x for x in ornekler}
    kol = {(r["kol"], r["bolum"]): r for r in sonuclar if r.get("translation")}
    isler = []
    for cift in ciftler:
        k1, k2 = cift.split(":")
        for no, x in sorted(ornek.items()):
            r1, r2 = kol.get((k1, no)), kol.get((k2, no))
            if not r1 or not r2:
                continue
            m = maddeler(r1, r2, tohum=tohum * 100003 + no)
            if not m:
                continue
            en = r1["source"].split("\n\n")
            referans = ceviri_bellek.sec(x.get("bellek_havuzu") or [], en, bolum_no=no)
            isler.append({"anahtar": f"{cift}|{no}", "cift": cift, "bolum": no, "maddeler": m,
                          "istem": {"onceki_ceviriler": [{"en": y["en"], "tr": y["tr"]} for y in referans],
                                    "maddeler": [{"id": i, "onceki_kaynak": y["onceki_kaynak"],
                                                  "kaynak": y["kaynak"], "X": y["X"], "Y": y["Y"]}
                                                 for i, y in enumerate(m)]}})
    return isler


def yargila(a):
    if Path(a.cikti).exists():
        raise SystemExit("Çıktı var; başka hedef kullanın.")
    sonuclar = [json.loads(s) for s in Path(a.sonuc).read_text(encoding="utf-8").splitlines() if s.strip()]
    ornekler = json.loads(Path(a.veri).read_text(encoding="utf-8"))
    bekleyen = _isler(sonuclar, ornekler, a.ciftler.split(","), a.tohum)
    print(f"{len(bekleyen)} hakem işi, {sum(len(i['maddeler']) for i in bekleyen)} madde", flush=True)
    with open(a.cikti, "x", encoding="utf-8") as f:
        for tur in range(3):
            if not bekleyen:
                break
            yuk = {"hakem": a.hakem, "talimat": HAKEM_TALIMATI, "es": a.es,
                   "isler": [{"anahtar": i["anahtar"], "istem": i["istem"]} for i in bekleyen]}
            yanitlar = {y["anahtar"]: y for y in _uzak(_YARGILA, yuk)}
            kalan = []
            for is_ in bekleyen:
                y = yanitlar.get(is_["anahtar"], {})
                try:
                    kararlar = kararlari_coz(json.loads(y.get("yanit") or ""), is_["maddeler"])
                except (ValueError, json.JSONDecodeError) as exc:
                    print(f"  {is_['anahtar']}: geçersiz ({y.get('hata') or exc}); tur {tur + 1}", flush=True)
                    kalan.append(is_)
                    continue
                f.write(json.dumps({"cift": is_["cift"], "bolum": is_["bolum"], "hakem": a.hakem,
                                    "saniye": y.get("saniye"), "kararlar": kararlar},
                                   ensure_ascii=False) + "\n"); f.flush()
            bekleyen = kalan
    if bekleyen:
        print("Karara bağlanamayan işler:", [i["anahtar"] for i in bekleyen])


def ozet(a):
    satirlar = [json.loads(s) for s in Path(a.yargi).read_text(encoding="utf-8").splitlines() if s.strip()]
    ciftler: dict[str, list] = {}
    for s in satirlar:
        ciftler.setdefault(s["cift"], []).extend(s["kararlar"])
    print("| Çift (a:b) | Boyut | a kazandı | b kazandı | eşit | p |")
    print("|---|---|---:|---:|---:|---:|")
    for cift, kararlar in ciftler.items():
        for boyut in BOYUTLAR:
            o = boyut_ozeti(kararlar, boyut)
            print(f"| {cift} | {boyut} | {o['a']} | {o['b']} | {o['esit']} | {o['p']:.3f} |")


def ornek(a):
    """Elle doğrulama: seçilen çiftten rastgele kararlı maddeleri yazdırır (dosyaya yazmaz)."""
    sonuclar = [json.loads(s) for s in Path(a.sonuc).read_text(encoding="utf-8").splitlines() if s.strip()]
    kol = {(r["kol"], r["bolum"]): r for r in sonuclar if r.get("translation")}
    yargilar = [json.loads(s) for s in Path(a.yargi).read_text(encoding="utf-8").splitlines() if s.strip()]
    havuz = []
    for y in yargilar:
        if y["cift"] != a.cift:
            continue
        k1, k2 = a.cift.split(":")
        r1, r2 = kol[(k1, y["bolum"])], kol[(k2, y["bolum"])]
        en, t1, t2 = r1["source"].split("\n\n"), r1["translation"].split("\n\n"), r2["translation"].split("\n\n")
        for k in y["kararlar"]:
            if k[a.boyut] != "esit":
                havuz.append((y["bolum"], k, en[k["p"]], t1[k["p"]], t2[k["p"]]))
    random.Random(a.tohum).shuffle(havuz)
    for no, k, e, x, z in havuz[:a.adet]:
        print(f"\n== bölüm {no} p{k['p']} | hakem {a.boyut}: {k[a.boyut]} | not: {k['not']}")
        print(f"EN: {e}\nA : {x}\nB : {z}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)
    h = alt.add_parser("hazirla"); h.add_argument("--kitap", default="shadow-slave")
    h.add_argument("--bolumler", required=True); h.add_argument("--havuz", type=int, default=30)
    h.add_argument("--cikti", required=True); h.set_defaults(f=hazirla)
    c = alt.add_parser("calistir"); c.add_argument("--veri", required=True)
    c.add_argument("--kollar", default="A,A2,B,C,D,E"); c.add_argument("--model", default="vertex/gemini-3.6-flash")
    c.add_argument("--es", type=int, default=1); c.add_argument("--cikti", required=True); c.set_defaults(f=calistir)
    y = alt.add_parser("yargila"); y.add_argument("--veri", required=True); y.add_argument("--sonuc", required=True)
    y.add_argument("--ciftler", default="B:A,C:A,D:B,E:C,A2:A"); y.add_argument("--hakem", default="gemini-2.5-pro")
    y.add_argument("--es", type=int, default=4); y.add_argument("--tohum", type=int, default=11)
    y.add_argument("--cikti", required=True); y.set_defaults(f=yargila)
    o = alt.add_parser("ozet"); o.add_argument("--yargi", required=True); o.set_defaults(f=ozet)
    r = alt.add_parser("ornek"); r.add_argument("--sonuc", required=True); r.add_argument("--yargi", required=True)
    r.add_argument("--cift", required=True); r.add_argument("--boyut", default="anlam")
    r.add_argument("--adet", type=int, default=10); r.add_argument("--tohum", type=int, default=3)
    r.set_defaults(f=ornek)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
