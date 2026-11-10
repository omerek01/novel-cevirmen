"""`kayit_bul`: tek satır sorgusu, bütün sözlüğü Python'a taşımadan (2026-11-10).

SQL katlaması (`_FOLD_SQL`) ile Python `fold_term` aynı anahtarı üretmeli; aksi hâlde
yazım varyantı sözlük ekranında "kayıt yok" görünür ve ikinci satır açılır.
"""
from core import glossary

SLUG = "shadow-slave"


def test_yazim_varyantlari_ayni_kaydi_bulur():
    glossary.set_term(SLUG, "Ore Empire", "Cevher İmparatorluğu")
    for varyant in ("Ore Empire", "ore-empire", "OreEmpire", "ORE  EMPIRE", "Ore Empire's", "Ore·Empire"):
        kayit = glossary.kayit_bul(SLUG, varyant)
        assert kayit and kayit["source"] == "Ore Empire", varyant


def test_ascii_disi_anahtar_eski_yoldan_bulunur():
    glossary.set_term(SLUG, "Café Noir", "Kara Kahve")
    assert glossary.kayit_bul(SLUG, "café-noir")["target"] == "Kara Kahve"


def test_baska_kitap_ve_yok_kayit():
    glossary.set_term(SLUG, "Awakened", "Uyanmış")
    assert glossary.kayit_bul("baska-kitap", "Awakened") is None
    assert glossary.kayit_bul(SLUG, "Sleeper") is None


def test_ic_satir_sonu_sql_katlamasinda_da_silinir():
    # `normalize_source` yalnız kenarları kırpar; içteki satır sonu kayıtta kalır.
    glossary.set_term(SLUG, "Ore\nEmpire", "Cevher İmparatorluğu")
    assert glossary.kayit_bul(SLUG, "ore empire")["target"] == "Cevher İmparatorluğu"
    assert glossary.kayit_bul(SLUG, "Ore\r\nEmpire")["target"] == "Cevher İmparatorluğu"
