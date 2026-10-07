"""v6 genellik temizliği: konum ve canlılık doğrulaması genel kurallarla (adlar KURGU).

Bölüme özgü ifade kalıntıları (`stood in its middle`, `walked in, alive`) kaldırıldı;
`test_bolume_ozgu_ifade_kalintisi_yok` geri gelmelerini tutar."""
from __future__ import annotations

from pathlib import Path

import pytest

from core import bilgi_kanit as k


def konum(s, o, e):
    return k.semantik_sonuc({"ozne": s, "iliski": "bulundugu_yer", "nesne": o, "kanit": e}, {})


def canli(ad, e):
    x = {"varlik": ad, "anahtar": "Yaşam", "makine_anahtari": "life_status", "deger": "alive",
         "durum_bilgisi": "confirmed", "kanit": e}
    return k.state_kaniti(x, e, {}, [])[0]


def olu(ad, e):
    x = {"varlik": ad, "anahtar": "Yaşam", "makine_anahtari": "life_status", "deger": "dead",
         "durum_bilgisi": "confirmed", "kanit": e}
    return k.state_kaniti(x, e, {}, [])[0]


def test_bolume_ozgu_ifade_kalintisi_yok():
    kod = (Path(__file__).resolve().parent.parent / "app" / "core" / "bilgi_kanit.py").read_text(encoding="utf-8")
    assert "stood in its middle" not in kod and "walked in, alive" not in kod


# ---------- konum: olumlu ----------
@pytest.mark.parametrize("s,o,e", [
    ("Arden", "Silver Tower", "Arden remained in the Silver Tower."),
    ("Mira", "Citadel", "Mira was inside the Citadel."),
    ("Boran", "Eastern Camp", "Boran stayed at the Eastern Camp."),
    ("Lina", "Temple", "Lina stood within the Temple."),
    ("Arden", "Deep Vault", "Arden had fallen into the Deep Vault."),
    ("Mira", "Silver Tower", "Mira arrived at the Silver Tower at dawn."),
    ("Boran", "Citadel", "Boran entered the Citadel."),
    ("Lina", "Old Harbor", "The Old Harbor, where Lina lived, was quiet."),
    ("Glass Tower", "Hollow", "The Hollow lay beyond the ridge. Some people believed that the Glass Tower had once stood in its center."),
    ("Arden", "Silver Tower", "Arden’s fate was sealed when Arden remained in the Silver Tower."),
])
def test_konum_olumlu(s, o, e):
    assert konum(s, o, e)[0] == "verified", e


# ---------- konum: olumsuz ----------
@pytest.mark.parametrize("s,o,e", [
    # `remained` içindeki "in" (v5.1'de gözlenen sahte eşleşme)
    ("Arden", "Altar Isle", "Arden remained silent for a few moments. The Altar Isle was calm."),
    ("Arden", "Silver Tower", "Arden remained silent near the stairs; the Silver Tower loomed."),
    ("Mira", "Citadel", "Mira had to begin the Citadel report."),
    ("Boran", "Citadel", "Boran increased the Citadel garrison."),
    ("Lina", "Silver Tower", "Lina had a deep interest in the Silver Tower."),
    ("Arden", "Old Gods", "Arden believed in the Old Gods."),
    # hedef varlık yalnız başka bir cümlecikte
    ("Arden", "Silver Tower", "Arden smiled and Mira remained in the Silver Tower."),
    # yer başka bir varlığa bağlı
    ("Arden", "Silver Tower", "Arden met Lina, who lived in the Silver Tower."),
    ("Arden", "Silver Tower", "Arden saw Lina in the Silver Tower."),
    ("Mira", "Temple", "Mira remembered her life in the Temple."),
])
def test_konum_olumsuz(s, o, e):
    assert konum(s, o, e)[0] != "verified", e


def test_konum_ters_yon_yanlis():
    assert konum("Silver Tower", "Arden", "Arden remained in the Silver Tower.") == ("wrong", "direction_reversed")


@pytest.mark.parametrize("parca", ["Arden remained loyal to the Order.", "The king of the Order spoke."])
def test_parcasi_alt_dizge_in_eslesmez(parca):
    r = k.semantik_sonuc({"ozne": "Arden" if "Arden" in parca else "king", "iliski": "parcasi", "nesne": "Order",
                          "kanit": parca}, {})
    assert r[0] != "verified"


# ---------- canlılık ----------
@pytest.mark.parametrize("ad,e", [
    ("Arden", "Arden was still alive."),
    ("Mira", "Mira survived the attack."),
    ("Boran", "Boran had survived."),
    ("Lina", "Lina was not dead."),
    ("Arden", "Arden remained alive."),
    ("Mira", "Mira returned from the pass, still alive."),
])
def test_canli_olumlu(ad, e):
    assert canli(ad, e), e


@pytest.mark.parametrize("ad,e", [
    ("Arden", "Arden walked into the room."),
    ("Mira", "Mira spoke."),
    ("Boran", "Boran moved."),
    ("Lina", "Lina appeared at the gate."),
    ("Arden", "Arden walked in, smiling."),
    ("Mira", "Mira stood and looked around."),
])
def test_canli_olumsuz(ad, e):
    assert not canli(ad, e), e


# ---------- ölüm güvenliği değişmedi ----------
@pytest.mark.parametrize("e", ["Arden was dead.", "Arden died.", "Mira had slain Arden.", "Arden, who was now dead, smiled once."])
def test_olum_olumlu(e):
    assert olu("Arden", e)


@pytest.mark.parametrize("e", ["Mira stabbed Arden.", "Arden was wounded.", "Mira defeated Arden.", "Arden fell.",
                               "Arden disappeared.", "Arden stopped moving.",
                               "The blade cut the parasite inside Arden in half. Then the body crumbled."])
def test_olum_olumsuz(e):
    assert not olu("Arden", e)
