"""Öbek modu (hızlı okuma planı Adım C): kural öbekleri, model doğrulaması, saklama, uç."""
import json

from fastapi.testclient import TestClient

from core import cache, library, obekler

P = "Kaan fenerini yaktı ve dar geçidin sonundaki kapıya baktı; kapı yarı açıktı."


def _parcalar(p, sinirlar):
    bas, out = 0, []
    for s in sinirlar:
        out.append(p[bas:s].strip())
        bas = s
    return out


class _Yanit:
    def __init__(self, veri):
        self.text = json.dumps(veri, ensure_ascii=False)
        self.finish_reason = "STOP"


def _uretici(obek_listesi):
    cagri = []

    def uret(user, system, asama):
        cagri.append(json.loads(user))
        return _Yanit({"obekler": obek_listesi}), "sahte-model"
    uret.cagri = cagri
    return uret


def test_kural_obekleri_noktalama_baglac_ve_yan_cumle():
    assert _parcalar(P, obekler.kural_obekleri(P)) == [
        "Kaan fenerini yaktı", "ve dar geçidin", "sonundaki kapıya baktı;", "kapı yarı açıktı."]
    p = "Kapıyı açınca içeri girdi, sonra durdu."
    assert _parcalar(p, obekler.kural_obekleri(p)) == ["Kapıyı açınca", "içeri girdi,", "sonra durdu."]
    # Hiçbir öbek 5 sözcükten uzun değil; birleşince metin aynen geri gelir.
    uzun = "bir iki üç dört beş altı yedi sekiz dokuz on on bir"
    sinir = obekler.kural_obekleri(uzun)
    assert all(len(x.split()) <= 5 for x in _parcalar(uzun, sinir))
    assert " ".join(_parcalar(uzun, sinir)) == uzun
    assert obekler.kural_obekleri("") == []


def test_model_obekleri_kabul_ve_harf_degisince_red():
    iyi = ["Kaan fenerini yaktı", "ve dar geçidin sonundaki", "kapıya baktı;", "kapı yarı açıktı."]
    sinir, model, red = obekler.model_ile_obekle([P], _uretici([iyi]))
    assert _parcalar(P, sinir[0]) == iyi and model == "sahte-model" and red == 0
    # Model bir harf değiştirdi ("baktı" → "bakti"): paragraf reddedilir, kural yedeği.
    bozuk = ["Kaan fenerini yaktı", "ve dar geçidin sonundaki", "kapıya bakti;", "kapı yarı açıktı."]
    sinir, _m, red = obekler.model_ile_obekle([P], _uretici([bozuk]))
    assert red == 1 and sinir[0] == obekler.kural_obekleri(P)
    # 8 sözcükten uzun öbek de reddedilir; eksik metin de.
    for kotu in ([P], ["Kaan fenerini yaktı"]):
        _s, _m, red = obekler.model_ile_obekle([P], _uretici([kotu]))
        assert red == 1


def test_bozuk_yanit_ya_da_eksik_paragraf_hepsi_kural():
    sinir, _m, red = obekler.model_ile_obekle([P, P], _uretici([["Kaan fenerini yaktı"]]))
    assert red == 2 and sinir == [obekler.kural_obekleri(P)] * 2


def test_bolum_yeniden_cevrilince_obekler_bayatlar():
    sha = obekler.ozet_al(P)
    obekler.kaydet("u1", "s", sha, [[4]], "m", 0)
    assert obekler.kayitli("u1", sha) == [[4]]
    assert obekler.kayitli("u1", obekler.ozet_al(P + " Yeni.")) is None


def _bolum(url="https://ornek.test/s/1", slug="kanon", metin=P + "\n\n" + P):
    cache.save_chapter(url, {"book_slug": slug, "book_title": "K", "title": "Bölüm 1",
                             "chapter_no": 1, "translation": metin, "next_url": None,
                             "prev_url": None, "detected_names": [], "chunk_count": 1})
    return url


def test_uc_model_sonucunu_saklar_ikinci_istekte_cagri_yok(monkeypatch):
    import server

    url = _bolum()
    uret = _uretici([["Kaan fenerini yaktı", "ve dar geçidin sonundaki", "kapıya baktı;",
                      "kapı yarı açıktı."]] * 2)
    monkeypatch.setattr(server.translate_mod, "obek_uretici", lambda *_a: uret)
    client = TestClient(server.app)
    ilk = client.get("/api/chapter/obekler", params={"url": url}).json()
    assert ilk["kaynak"] == "model" and len(ilk["sinirlar"]) == 2
    ikinci = client.get("/api/chapter/obekler", params={"url": url}).json()
    assert ikinci == {"sinirlar": ilk["sinirlar"], "kaynak": "kayit"} and len(uret.cagri) == 1


def test_uc_model_hatasinda_kural_obekleri(monkeypatch):
    import server

    url = _bolum()

    def patlayan(*_a):
        def uret(*_b):
            raise RuntimeError("429")
        return uret
    monkeypatch.setattr(server.translate_mod, "obek_uretici", patlayan)
    res = TestClient(server.app).get("/api/chapter/obekler", params={"url": url}).json()
    assert res == {"sinirlar": [obekler.kural_obekleri(P)] * 2, "kaynak": "kural"}


def test_uc_bilinmeyen_bolum_404_ve_kitap_silinince_obekler_gider(monkeypatch):
    import server

    client = TestClient(server.app)
    assert client.get("/api/chapter/obekler", params={"url": "yok"}).status_code == 404
    library.upsert_book("kanon", "K", "u", "B", 1)
    url = _bolum()
    obekler.kaydet(url, "kanon", obekler.ozet_al(P + "\n\n" + P), [[4], [4]], "m", 0)
    library.delete_book("kanon")
    assert obekler.kayitli(url, obekler.ozet_al(P + "\n\n" + P)) is None


def test_model_paragrafi_cumlelere_bolse_de_oebekler_sirayla_yerlesir():
    """Canlı vaka (Argon, 2026-11-08): 46 paragraf 88 listeye bölündü, hepsi reddedilmişti."""
    p2 = "Mira durdu. Sonra geri döndü."
    cevap = [["Kaan fenerini yaktı", "ve dar geçidin sonundaki"], ["kapıya baktı;", "kapı yarı açıktı."],
             ["Mira durdu."], ["Sonra geri döndü."]]
    sinir, _m, red = obekler.model_ile_obekle([P, p2], _uretici(cevap))
    assert red == 0
    assert _parcalar(P, sinir[0]) == ["Kaan fenerini yaktı", "ve dar geçidin sonundaki",
                                      "kapıya baktı;", "kapı yarı açıktı."]
    assert _parcalar(p2, sinir[1]) == ["Mira durdu.", "Sonra geri döndü."]
    # Ortadaki paragraf bozuksa yalnız o kurala düşer, sonraki yeniden hizalanır.
    bozuk = [["Kaan fenerini yaktı", "ve dar geçidin sonundaki", "kapıya baktı;", "kapı yarı açıktı."],
             ["Yanlış metin."], ["Kaan fenerini yaktı", "ve dar geçidin sonundaki"],
             ["kapıya baktı;", "kapı yarı açıktı."]]
    sinir, _m, red = obekler.model_ile_obekle([P, p2, P], _uretici(bozuk))
    assert red == 1 and sinir[1] == obekler.kural_obekleri(p2)
    assert _parcalar(P, sinir[2])[0] == "Kaan fenerini yaktı"


def test_uzun_bolum_gruplar_halinde_gider():
    paraflar = [P] * 30
    uret = _uretici(None)

    def grup_uret(user, system, asama):
        n = len(json.loads(user)["paragraflar"])
        uret.cagri.append(n)
        return _Yanit({"obekler": [[P]] * n}), "m"
    sinir, _m, red = obekler.model_ile_obekle(paraflar, grup_uret)
    assert uret.cagri == [12, 12, 6] and len(sinir) == 30
