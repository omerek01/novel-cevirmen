"""Sabit kaynak/sözlük/model ile analiz açık-kapalı ve onarım kıyası.

Varsayılan yalnız deney planıdır. --calistir seçilen Vertex modelinde ücretli
çağrı yapar; aday kod VM belleğinde çalışır, tüm DB yazımları geçici DB'yedir.
Üretim çevirileri veya servis dosyaları değiştirilmez.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

KOK = Path(__file__).resolve().parents[1]


def hazirla(ornekler: list[dict], model: str) -> list[dict]:
    if not re.fullmatch(r"vertex/gemini-[\w.-]+", model):
        raise ValueError("Deney yalnız açıkça seçilen tek bir Vertex modeli kullanır.")
    sonuc = []
    for i, x in enumerate(ornekler):
        snapshot = hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        siralar = [False, True] if i % 2 == 0 else [True, False]
        for acik in siralar:
            sonuc.append({"ornek": x, "model": model, "analiz": acik, "snapshot_sha256": snapshot})
    return sonuc


UZAK_KOD = r'''
import json,os,sys,tempfile,types,time
from dotenv import load_dotenv
load_dotenv('/home/OMEREK/novel-cevirmen/.env')
sys.path.insert(0,'/home/OMEREK/novel-cevirmen-sozluk/app')
p=json.loads(PAYLOAD)
with tempfile.TemporaryDirectory(prefix='roman-baglam-') as tmp:
 os.environ['NOVEL_DB_PATH']=tmp+'/deney.db'
 os.environ['SOZLUK_DOGRULAMA']='0'
 os.environ['CEVIRI_KALITE']='0'
 import core
 for name,code in p['kod'].items():
  m=types.ModuleType('core.'+name);m.__package__='core';m.__file__='<deney-'+name+'>'
  sys.modules['core.'+name]=m;setattr(core,name,m)
  exec(compile(code,m.__file__,'exec'),m.__dict__)
 from core import translate as t,ceviri_izleri as iz,ceviri_baglam as b,ceviri_kalite as q
 for arm in p['deneyler']:
  x=arm['ornek'];model=arm['model'];start=time.monotonic()
  os.environ['CEVIRI_ANALIZ']='1' if arm['analiz'] else '0'
  row={'kitap':x['book_slug'],'bolum':x['chapter_no'],'analiz':arm['analiz'],
       'model':model,'snapshot_sha256':arm['snapshot_sha256']}
  track={'cagrilar':[],'asamalar':[]};token=t._CEVIRI_IZ.set(track)
  try:
   if arm['analiz']:
    r=t.translate_chapter(x['source'],'',glossary=x['glossary'],kosullar=x.get('conditions',{}),
      models=(model,),prev_context=x.get('prev_context',''),bolum_no=x['chapter_no'],
      book_slug=x['book_slug'],bolum_url=x['url'],onceki_bolum=x.get('previous'))
    track=iz.iz_oku(x['url'])[0]['veri']
   else:
    r=t._translate_chapter_impl(x['source'],'',glossary=x['glossary'],kosullar=x.get('conditions',{}),
      models=(model,),prev_context=x.get('prev_context',''),bolum_no=x['chapter_no'])
   row.update(translation=r['translation'],source=r['source'],uretim=r,iz=track)
   if r['source']:
    paras=r['source'].split('\n\n');tr=r['translation'].split('\n\n')
    effective=b.yerel_sozluk(x['glossary'],track['analiz']) if arm['analiz'] else x['glossary']
    relevant=t._relevant_glossary(effective,x['source']);quality_trace={}
    quality_calls={'cagrilar':[]};qt=t._CEVIRI_IZ.set(quality_calls)
    def uret(user,system,stage):
     from core import api_durum
     with api_durum.baglam(asama=stage):
      return t._izli_uret(t._gemini_fabrikasi(''),(p.get('hakem') or model,),user,
                         system=system,max_tokens=t.MAX_OUTPUT_TOKENS)
    def kontrol(yeni):
     degisen={i for i,s in enumerate(yeni) if s!=tr[i]}
     return not degisen.intersection(t.sozluk_ihlali_paragraflari(effective,yeni,paras,x.get('conditions',{}))) and not degisen.intersection(t.ingilizce_kalinti(yeni,paras,effective))
    try:
     row['kalite']=q.denetle_ve_onar(tr,paras,relevant,x.get('conditions',{}),uret,kontrol,iz=quality_trace)
    except Exception as e: row['onarim_hatasi']=type(e).__name__
    finally:t._CEVIRI_IZ.reset(qt)
    row.update(onarim_izi=quality_trace,onarim_cagrilari=quality_calls['cagrilar'],onarim_sonrasi='\n\n'.join(tr))
  except Exception as e:
   row.update(hata_turu=type(e).__name__,kod=getattr(e,'code',None))
   traces=iz.iz_oku(x['url'])
   if arm['analiz'] and traces:row['iz']=traces[0]['veri']
  finally:
   t._CEVIRI_IZ.reset(token)
  row['saniye']=round(time.monotonic()-start,2)
  print(json.dumps(row,ensure_ascii=True),flush=True)
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--veri", type=Path, required=True)
    p.add_argument("--cikti", type=Path, required=True)
    p.add_argument("--model", default="vertex/gemini-3.6-flash")
    p.add_argument("--hakem", help="Ayrı hakem deneyi; tek Vertex modeli, varsayılan seçilen model.")
    p.add_argument("--calistir", action="store_true")
    a = p.parse_args()
    deneyler = hazirla(json.loads(a.veri.read_text(encoding="utf-8")), a.model)
    if a.hakem:
        hazirla([], a.hakem)
    if a.cikti.exists():
        raise SystemExit("Çıktı var; başka hedef kullanın.")
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    if not a.calistir:
        a.cikti.write_text(json.dumps(deneyler, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Deney planı hazır; model çağrısı yapılmadı.")
        return
    payload = {"deneyler": deneyler, "hakem": a.hakem,
               "kod": {n: (KOK / "app/core" / (n + ".py")).read_text(encoding="utf-8")
                       for n in ["ceviri_kalite", "ceviri_baglam", "ceviri_izleri", "translate"]}}
    remote = "PAYLOAD=" + repr(json.dumps(payload, ensure_ascii=True)) + "\n" + UZAK_KOD
    proc = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-i",
        str(Path.home() / ".ssh/google_compute_engine"), "OMEREK@100.75.105.102",
        "/home/OMEREK/novel-cevirmen/.venv/bin/python -u -"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdin.write(remote.encode()); proc.stdin.close()
    with a.cikti.open("x", encoding="utf-8") as f:
        for line in proc.stdout:
            row = json.loads(line); f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            print(json.dumps({k: row.get(k) for k in ["kitap", "bolum", "analiz", "saniye", "hata_turu", "onarim_hatasi"]}), flush=True)
    if proc.wait():
        raise RuntimeError(proc.stderr.read().decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
