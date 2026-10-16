"""Hizalama onarımı (Faz A5): hizalanmayan parça bir kez daha denenir.

Hizasız parça bütün paragraf denetimlerinden kaçıyordu; yeni hâl ancak hizalanır
ve kısalmamışsa alınır."""
from core import translate


class _Sahte:
    def __init__(self, *ciktilar):
        self.ciktilar = list(ciktilar)
        self.cagri = 0

    def __call__(self, *a, **k):
        self.cagri += 1
        metin = self.ciktilar.pop(0) if self.ciktilar else ""
        if isinstance(metin, Exception):
            raise metin
        return {"translation": metin, "detected_names": [], "detected_terms": {},
                "model": f"sahte-{self.cagri}"}


KAYNAK = "\n\n".join(f"P{i} " + "x" * 300 for i in range(3))


def _hizali(oran=1.0):
    return "\n\n".join(f"[[{i + 1}]] " + p[: max(1, int(len(p) * oran))]
                       for i, p in enumerate(KAYNAK.split("\n\n")))


def _hizasiz():
    return "\n\n".join(p for p in KAYNAK.split("\n\n"))  # işaretçi yok


def _cevir(monkeypatch, sahte, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(translate, "_translate_chunk", sahte)
    monkeypatch.setattr(translate, "_split_paragraphs", lambda t: [t])
    return translate.translate_chapter(KAYNAK, "anahtar", models=("m",))


def test_hizasiz_parca_yeniden_denenir_ve_hizali_hal_alinir(monkeypatch):
    sahte = _Sahte(_hizasiz(), _hizali())
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 2
    assert sonuc["source"] is not None  # hizalandı: kaynak saklanır, denetimler koşar
    assert sonuc["karsilik_sapmasi"] == {}


def test_hizali_parcada_onarim_tetiklenmez(monkeypatch):
    sahte = _Sahte(_hizali())
    _cevir(monkeypatch, sahte)
    assert sahte.cagri == 1


def test_kisalmis_yeniden_deneme_alinmaz(monkeypatch):
    sahte = _Sahte(_hizasiz(), _hizali(0.3))
    sonuc = _cevir(monkeypatch, sahte)
    assert sahte.cagri == 2
    assert sonuc["source"] is None  # ilk hâl kaldı: hizasız


def test_yeniden_deneme_hatasi_ilk_ceviriyi_kaybettirmez(monkeypatch):
    sahte = _Sahte(_hizasiz(), RuntimeError("503"))
    sonuc = _cevir(monkeypatch, sahte)
    assert sonuc["translation"] and sonuc["source"] is None


def test_bayrakla_kapatilir(monkeypatch):
    sahte = _Sahte(_hizasiz(), _hizali())
    sonuc = _cevir(monkeypatch, sahte, CEVIRI_HIZALAMA_ONARIM="0")
    assert sahte.cagri == 1 and sonuc["source"] is None
