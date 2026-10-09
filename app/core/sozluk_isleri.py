"""Sözlük doğrulamasının kalıcı işleri; ağ çağrısı DB işlemi dışında yapılır."""
import hashlib
import json
import time
import uuid
from contextlib import contextmanager

from . import db

SURUM = 'baglam-v2'
LEASE_SN = 1200


def json_metin(veri):
    return json.dumps(veri, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def ozet(veri):
    return hashlib.sha256(json_metin(veri).encode('utf-8')).hexdigest()


def kayit_ozeti(k):
    return ozet({a: k.get(a) for a in ('source','target','kimlik','kosul','tur','first_chapter')})


@contextmanager
def connect():
    conn = db.connect()
    conn.execute('''CREATE TABLE IF NOT EXISTS sozluk_api_is (
        id TEXT PRIMARY KEY, book_slug TEXT NOT NULL, kimlik TEXT NOT NULL,
        imza TEXT NOT NULL, son_kayit_hash TEXT, durum TEXT NOT NULL,
        istek TEXT NOT NULL, sonuc TEXT, sahibi TEXT, lease REAL,
        deneme INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
        UNIQUE(book_slug,kimlik,imza))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sozluk_api_deneme (
        id TEXT PRIMARY KEY, is_id TEXT NOT NULL, baslangic REAL NOT NULL,
        bitis REAL, durum TEXT NOT NULL, model TEXT, yanit TEXT, hata TEXT)''')
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def hazirla(book_slug, kayit):
    """Aynı girdi/bağlam/sürüm aynı işi üretir; eşzamanlı tek sahibi olur."""
    imza = ozet({'sozlesme':SURUM, 'kayit':kayit_ozeti(kayit),
                 'baglam':kayit['baglam_hash'], 'ekler':kayit.get('ekler'),
                 'politika':kayit.get('politikalar')})
    with connect() as conn:
        conn.row_factory = __import__('sqlite3').Row
        conn.execute('BEGIN IMMEDIATE')
        mevcut = conn.execute('''SELECT * FROM sozluk_api_is WHERE book_slug=? AND kimlik=?
            AND (imza=? OR (son_kayit_hash=? AND durum='tamamlandi')) ORDER BY updated DESC''',
            (book_slug,kayit['kimlik'],imza,kayit_ozeti(kayit))).fetchall()
        for row in mevcut:
            eski = json.loads(row['istek'])
            if (eski['baglam_hash'] != kayit['baglam_hash'] or
                    eski.get('ekler') != kayit.get('ekler') or
                    eski.get('politikalar') != kayit.get('politikalar')):
                continue
            if row['durum']=='tamamlandi':
                return dict(row),False
            if row['durum']=='calisiyor' and (row['lease'] or 0)>time.time():
                return dict(row),False
        conn.execute('INSERT OR IGNORE INTO sozluk_api_is(id,book_slug,kimlik,imza,durum,istek,updated) VALUES(?,?,?,?,?,?,?)',
                     (uuid.uuid4().hex,book_slug,kayit['kimlik'],imza,'bekliyor',json_metin(kayit),time.time()))
        row=conn.execute('SELECT * FROM sozluk_api_is WHERE book_slug=? AND kimlik=? AND imza=?',
                         (book_slug,kayit['kimlik'],imza)).fetchone()
        sahibi=uuid.uuid4().hex
        conn.execute("UPDATE sozluk_api_is SET durum='calisiyor',sahibi=?,lease=?,deneme=deneme+1,updated=? WHERE id=?",
                     (sahibi,time.time()+LEASE_SN,time.time(),row['id']))
        return {**dict(row),'sahibi':sahibi,'durum':'calisiyor'},True


def deneme_baslat(isler):
    ids=[]
    with connect() as conn:
        for job in isler:
            id_=uuid.uuid4().hex
            conn.execute('INSERT INTO sozluk_api_deneme(id,is_id,baslangic,durum) VALUES(?,?,?,?)',
                         (id_,job['id'],time.time(),'ucusta'))
            ids.append(id_)
    return ids


def deneme_bitir(ids, durum, model=None, yanit=None, hata=None):
    with connect() as conn:
        for id_ in ids:
            conn.execute('UPDATE sozluk_api_deneme SET bitis=?,durum=?,model=?,yanit=?,hata=? WHERE id=?',
                         (time.time(),durum,model,yanit,hata,id_))


def bitir(job, sonuc, son_kayit=None, hata=False):
    with connect() as conn:
        conn.execute('UPDATE sozluk_api_is SET durum=?,sonuc=?,son_kayit_hash=?,lease=NULL,updated=? WHERE id=? AND sahibi=?',
                     ('hata' if hata else 'tamamlandi',json_metin(sonuc),
                      kayit_ozeti(son_kayit) if son_kayit else None,time.time(),job['id'],job['sahibi']))


def durum(book_slug):
    with connect() as conn:
        rows=conn.execute('SELECT durum,COUNT(*) FROM sozluk_api_is WHERE book_slug=? GROUP BY durum',(book_slug,)).fetchall()
        ucusta=conn.execute('''SELECT COUNT(*) FROM sozluk_api_deneme d JOIN sozluk_api_is i ON i.id=d.is_id
            WHERE i.book_slug=? AND d.durum='ucusta' ''',(book_slug,)).fetchone()[0]
    return {'isler':dict(rows),'sonucu_bilinmeyen_deneme':ucusta}
