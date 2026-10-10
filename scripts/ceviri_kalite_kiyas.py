"""Tam bölümlerle model/istem kıyası; üretim koduna ve DB'ye yazmaz.

VM yalnız kimlik doğrulama/üretim için kullanılır. Kod bellekte çalıştırılır.
--calistir olmadan yalnız istemleri hazırlar; ücretli çağrı açık seçenek ister.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK/'app'))
from core import translate as t

# Koşullar, isim/sözlük önceliği, Türkçe ek, deyim ve özel ad ölçütlerini koruyan
# deney kolu. Üretimin varsayılan talimatını DEĞİŞTİRMEZ.
KISA_TALIMAT = """İngilizce web romanını eksiksiz, doğal Türkçeyle çevir; özetleme.
Olayları, betimlemeleri, diyalogları, sayıları, olumsuzlukları ve kesinlik derecesini koru.
Deyimleri anlamlarıyla aktar: turn the tables -> işleri tersine çevirmek; last straw ->
bardağı taşıran son damla. Türkçe ek/kaynaştırma ve özne-yüklem uyumunu doğru kur.
Sözlük karşılıkları öncelikli kuraldır; kişi adı istisnasını da ezer. Koşullu kayıt yalnız
koşul sağlanınca uygulanır; yasak karşılığı kullanma. Kaynakta başka bir sözcüğe taşıma.
Kişiyi adlandıran gerçek ad/lakap İngilizce kalır; lakap tek belirli kişiyi gösterir,
a/an/the ile sınıf anlatan unvan çevrilir. Diğer özel adlar (yer, eşya, lonca, beceri,
yaratık, dünya sistemi) Türkçeleşir. Sıradan sözcük yeni terim değildir. Hiyerarşi
basamakları dizide veya düzene bağlı kullanılıyorsa küçük harfli de olsa terimdir.
Önceki çeviri yalnız bağlamdır. Hiçbir paragrafı İngilizce kopyalama veya yabancı dilde
bırakma. Her kaynak paragrafına tek Türkçe paragraf ver; [[n]] işaretlerini eksiksiz,
aynı sırada koru. Yanıt yalnız JSON: {"translation":"[[1]] ...\\n\\n[[2]] ...",
"detected_names":["İngilizce korunan kişi adı"],"detected_terms":{"kaynak özel ad":"çeviride kullanılan Türkçe karşılık"}}.
Yalnız kaynakta geçen adları öner; kişi dışı adları detected_names'e koyma."""


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--veri', type=Path, required=True)
    p.add_argument('--cikti', type=Path, required=True)
    p.add_argument('--calistir', action='store_true')
    p.add_argument('--kip', choices=['kiyas','onarim'], default='kiyas')
    p.add_argument('--sistem-veri', type=Path, help='Canlı istem görüntüsü JSON; system alanı kullanılır.')
    p.add_argument('--yalniz-mevcut', action='store_true', help='Önceden ölçülen kısa kolu tekrar çağırma.')
    a=p.parse_args()
    ornekler=json.loads(a.veri.read_text(encoding='utf-8'))
    paketler=[]
    for x in ornekler:
        paras=[p.strip() for p in x['source'].split('\n\n') if p.strip()]
        paketler.append(dict(x, paras=paras, user=t._build_user_prompt(paras,x['glossary'],x.get('prev_context',''),x.get('conditions',{})),
                            relevant=t._relevant_glossary(x['glossary'],x['source'])))
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    a.cikti.with_suffix('.istemler.json').write_text(json.dumps(paketler,ensure_ascii=False,indent=2),encoding='utf-8')
    if not a.calistir:
        print('İstemler hazır; API çağrısı yapılmadı.'); return
    if a.cikti.exists():
        raise SystemExit('Ölçüm çıktısı zaten var; farklı --cikti kullanın.')
    from core import ceviri_kalite as q
    system = json.loads(a.sistem_veri.read_text(encoding='utf-8'))['system'] if a.sistem_veri else t.SYSTEM_INSTRUCTION
    payload={'paketler':paketler,'system':system,'compact':KISA_TALIMAT,
             'kalite_kodu':(KOK/'app/core/ceviri_kalite.py').read_text(encoding='utf-8'), 'kip':a.kip,
             'yalniz_mevcut':a.yalniz_mevcut}
    remote='PAYLOAD='+repr(json.dumps(payload,ensure_ascii=True))+'\n'+r'''
import json, os, time, types as pytypes
from dotenv import load_dotenv
from google import genai
from google.genai import types
load_dotenv('/home/OMEREK/novel-cevirmen/.env')
p=json.loads(PAYLOAD)
q=pytypes.ModuleType('deney_kalite'); exec(compile(p['kalite_kodu'],'<kalite-deneyi>','exec'),q.__dict__)
c=genai.Client(vertexai=True,project=os.environ['VERTEX_PROJE'],location=os.getenv('VERTEX_KONUM') or 'global',http_options=types.HttpOptions(timeout=120000,retry_options=types.HttpRetryOptions(attempts=1)))
def cagri(model,user,system):
 cfg=types.GenerateContentConfig(system_instruction=system,response_mime_type='application/json',max_output_tokens=32768,
 safety_settings=[types.SafetySetting(category=k,threshold='BLOCK_NONE') for k in ['HARM_CATEGORY_HATE_SPEECH','HARM_CATEGORY_DANGEROUS_CONTENT','HARM_CATEGORY_SEXUALLY_EXPLICIT','HARM_CATEGORY_HARASSMENT']])
 if model=='gemini-3.6-flash': cfg.temperature=.3
 return c.models.generate_content(model=model,contents=user,config=cfg)
for n,x in enumerate(p['paketler']):
 arms=[(m,label) for m in ['gemini-3.6-flash','gemini-3.8-flash'] for label in ['mevcut','kisa']]
 if p['yalniz_mevcut']: arms=[(m,'mevcut') for m in ['gemini-3.6-flash','gemini-3.8-flash']]
 if n%2: arms.reverse()
 if p['kip']=='onarim': arms=[('gemini-3.6-flash','onarim')]
 for model,label in arms:
  start=time.monotonic(); row={'kitap':x['book_slug'],'bolum':x['chapter_no'],'model':model,'istem':label}
  try:
   if label=='onarim':
    cagrilar=[]
    def uret(user,system,asama):
     bas=time.monotonic(); r=cagri(model,user,system)
     cagrilar.append({'asama':asama,'sure':round(time.monotonic()-bas,2),'usage':r.usage_metadata.model_dump(mode='json',exclude_none=True),'text':r.text})
     return r,model
    tr=x['translation'].split('\n\n')
    try: row['kalite']=q.denetle_ve_onar(tr,x['paras'],x['relevant'],x.get('conditions',{}),uret)
    finally: row['cagrilar']=cagrilar; row['translation']='\n\n'.join(tr)
   else:
    r=cagri(model,x['user'],p['system'] if label=='mevcut' else p['compact'])
    row.update(text=r.text,usage=r.usage_metadata.model_dump(mode='json',exclude_none=True),finish=[str(y.finish_reason) for y in r.candidates or []],model_version=r.model_version)
  except Exception as exc: row.update(error_type=type(exc).__name__,code=getattr(exc,'code',None),error=str(exc)[:200] if isinstance(exc,q.KaliteHatasi) else '')
  row['seconds']=round(time.monotonic()-start,2)
  print(json.dumps(row,ensure_ascii=True),flush=True)
'''
    proc=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-i',str(Path.home()/'.ssh/google_compute_engine'),
                           'OMEREK@100.75.105.102','/home/OMEREK/novel-cevirmen/.venv/bin/python -u -'],
                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    proc.stdin.write(remote.encode());proc.stdin.close()
    with a.cikti.open('x',encoding='utf-8') as f:
        for line in proc.stdout:
            row=json.loads(line);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
            print(json.dumps({k:v for k,v in row.items() if k not in {'text','translation','cagrilar'}},ensure_ascii=False),flush=True)
    if proc.wait(): raise RuntimeError(proc.stderr.read().decode('utf-8','replace'))


if __name__=='__main__': main()
