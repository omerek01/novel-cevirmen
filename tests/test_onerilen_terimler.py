"""Modelin bölümde önerdiği BÜTÜN terimler künyede saklanır (`chapters.onerilen_terimler`).

Amaç çıkarılma oranı: "terim N bölümde geçti, model kaçında önerdi". `added_terms` yalnız yeni
eklenenleri tuttuğu için bu oran hesaplanamıyordu (reports/sozluk-kalite-arastirma)."""
import json
import re
import sqlite3
from pathlib import Path

from core import cache, db

KOK = Path(__file__).resolve().parents[1]


def _oku(url):
    with sqlite3.connect(db.db_path()) as con:
        return con.execute('SELECT onerilen_terimler FROM chapters WHERE url=?', (url,)).fetchone()[0]


def test_oneri_saklanir_ve_tasimayan_yazim_ezmez():
    url = 'https://ornek.test/kitap/chapter-1'
    temel = dict(book_slug='kitap', title='1', chapter_no=1, translation='çeviri', detected_names=['Mira'])
    cache.save_chapter(url, {**temel, 'onerilen_terimler': {'Ash Crown': 'Kül Tacı', 'Lost': 'Kayıplar'}})
    assert json.loads(_oku(url)) == {'Ash Crown': 'Kül Tacı', 'Lost': 'Kayıplar'}
    cache.save_chapter(url, temel)  # görsel sayfa gibi alan taşımayan yazım
    assert json.loads(_oku(url)) == {'Ash Crown': 'Kül Tacı', 'Lost': 'Kayıplar'}
    cache.save_chapter(url, {**temel, 'onerilen_terimler': {}})  # denetlendi, öneri yok
    assert json.loads(_oku(url)) == {}


def test_iki_metin_yolu_da_oneriyi_kunyeye_koyar():
    """Künye kuralı: `_fetch_translate_save` ve `fetch_into_book` AYNI alanı yazar."""
    kaynak = (KOK / 'app/core/pipeline.py').read_text(encoding='utf-8')
    assert len(re.findall(r'"onerilen_terimler": result\.get\("detected_terms"\)', kaynak)) == 2
