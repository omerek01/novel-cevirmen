"""Test yalıtımı: toplama (collection) aşaması gerçek veritabanına dokunmaz.

`server` modülü içe aktarılırken `library.backfill_from_cache()` koşuyor ve bu,
autouse `temp_db` fikstüründen ÖNCE oluyor (pytest modülleri fikstürlerden önce
toplar). O an NOVEL_DB_PATH boşsa yazım kullanıcının GERÇEK `cache/chapters.db`
dosyasına giderdi. Yol aşağıda toplama anında, fikstür koşmadan yakalanır.
"""
from core import db

_TOPLAMA_ANINDAKI_YOL = db.db_path()


def test_toplama_aninda_gercek_db_kullanilmaz():
    assert _TOPLAMA_ANINDAKI_YOL.resolve() != db._DEFAULT_DB.resolve()
