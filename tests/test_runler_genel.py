"""Genel sistem mesajı algılayıcı (`core.runler.genel`) — yapay metinler, roman metni değil."""
from core import runler
from core.runler import genel


def _ozet(metin, sesler=(), anahtarlar=()):
    return [(s["tur"], s["anahtar"]) for s in genel.sistem_satirlari(metin, sesler, anahtarlar)]


def test_koseli_satir_ve_kart_basligi():
    metin = "Ada walked in.\n\n[You found a key.]\n\n[Iron Crown] (Head, Rare Rank)\n\nShe smiled [a lot]."
    assert _ozet(metin) == [("koseli", None), ("koseli", None)]


def test_ses_satiri_iki_noktali_anahtar_ister():
    metin = "System: You leveled up.\n\nSystem Announcement: A war began.\n\nSystems were old here."
    assert _ozet(metin, ("System",)) == [("ses", "System"), ("ses", "System Announcement")]
    assert _ozet(metin) == []  # profilde ses yoksa ses satırı da yok


def test_kunye_ve_diyalog_alinmaz():
    # Diyalog satırı anahtar desenine uyuyor ve bloğun penceresinde: tırnak yüzünden alınmaz.
    metin = "[Notice]\n\nTranslator: Someone\n\nEditor: Other\n\nAda: \"Come here,\" she said."
    assert _ozet(metin) == [("koseli", None)]


def test_anahtar_satiri_blok_penceresinde_kabul():
    metin = "\n\n".join(["[Iron Crown] (Head, Rare Rank)", "Level 30", "Defense: 120", "Active Skill 1-",
                         "Cooldown: 5 minutes", "The wind blew.", "x.", "y.", "z.", "Duration: 9 hours"])
    assert _ozet(metin) == [("koseli", None), ("anahtar", "Defense"), ("anahtar", "Cooldown")]


def test_koseli_degerli_anahtar_bloku_acar():
    metin = "He looked.\n\nMemory: [Old Bell].\n\nMemory Rank: Dormant.\n\nIt was quiet."
    assert _ozet(metin) == [("koseli", "Memory"), ("anahtar", "Memory Rank")]


def test_anahtar_satiri_guclu_satirdan_once_gelirse_kabul():
    assert _ozet("Name: Ada\n\n[Rank: Novice]") == [("anahtar", "Name"), ("koseli", None)]


def test_profil_anahtarlari_her_yerde_kabul_digerleri_hic():
    metin = "The wind blew.\n\nCooldown: 5 minutes\n\nDefense: 120\n\n[Crown]\n\nWeight: 3"
    assert _ozet(metin, anahtarlar=("Cooldown",)) == [("anahtar", "Cooldown"), ("koseli", None)]


def test_anahtar_sozlugu():
    satirlar = genel.sistem_satirlari("System: a\n\nSystem: b\n\n[x]\n\nPrice: 3", ("System",))
    assert genel.anahtar_sozlugu(satirlar) == {"System": 2, "Price": 1}


def test_bicim_secici():
    assert runler.bicim({"run_bicimi": "shadow_slave"}).__name__.endswith("shadow_slave")
    assert runler.bicim({"run_bicimi": "bilinmeyen"}) is None and runler.bicim(None) is None
    assert runler.payda("870/4000") == 4000 and runler.payda("870") is None
