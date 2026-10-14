"""Karakter defteri: deterministik doğrulama, birikim, hitap tablosu, kuyruk (sahte model)."""
import json
import time

import pytest

from core import db, glossary, karakter_defteri as kd, translate, varlik_grafigi as vg

KITAP = "defter-kitap"

BOLUM1_EN = [
    'Sunny looked at Nephis. "You are late, Changing Star," he said.',
    "Julius had been Sunny's teacher for years.",
    '"Yes, sir, I was waiting for you," Nephis answered Captain Kai.',
    "The hollow tree creaked in the wind.",
]
BOLUM1_TR = [
    'Sunny, Nephis\'e baktı. "Geç kaldın, Değişen Yıldız," dedi.',
    "Julius yıllardır Sunny'nin öğretmeniydi.",
    '"Evet efendim, sizi bekliyordum," diye cevap verdi Nephis, Yüzbaşı Kai\'ye.',
    "Kovuk ağaç rüzgârda gıcırdadı.",
]
BOLUM2_EN = ['"Again, Sunny," Julius said. Julius was Sunny\'s teacher, after all.', "Nothing else happened."]
BOLUM2_TR = ['"Tekrar, Sunny," dedi Julius. Ne de olsa Julius, Sunny\'nin öğretmeniydi.', "Başka bir şey olmadı."]


def _bolum_ekle(no, en, tr):
    from core import cache

    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"https://x/{no}", KITAP, no, "\n\n".join(tr), "\n\n".join(en), time.time()),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def kitap():
    terimler = {
        "Sunny": ("Sunny", "kisi"), "Nephis": ("Nephis", "kisi"), "Julius": ("Julius", "kisi"),
        "Changing Star": ("Değişen Yıldız", "kisi"), "Hollow": ("Kovuk", "yer"), "Kai": ("Kai", "kisi"),
        "Captain": ("Yüzbaşı", "rutbe"),
    }
    for kaynak, (hedef, _t) in terimler.items():
        glossary.set_term(KITAP, kaynak, hedef)
    conn = db.connect()
    for kaynak, (_h, tur) in terimler.items():
        conn.execute("UPDATE glossary SET tur = ? WHERE book_slug = ? AND source = ?", (tur, KITAP, kaynak))
    conn.commit()
    conn.close()
    _bolum_ekle(1, BOLUM1_EN, BOLUM1_TR)
    _bolum_ekle(2, BOLUM2_EN, BOLUM2_TR)
    return KITAP


def _idler(user):
    return {k["ad"]: k["id"] for k in json.loads(user)["kayitli"]}


def _sahte(yanitlar):
    """Bölüm numarasına göre yanıt; çağrıları kaydeder."""
    cagrilar = []

    def cagir(user, model):
        istem = json.loads(user)
        cagrilar.append(istem)
        yanit = yanitlar[istem["bolum"]]
        veri = yanit(_idler(user)) if callable(yanit) else yanit
        return json.dumps(veri), {"model": model, "giris": 1000, "cikis": 200, "dusunme": 0}

    cagir.cagrilar = cagrilar
    return cagir


def _bolum1(idler):
    return {
        "v": [
            {"ad": "Nephis", "tr": "Nephis", "t": "kisi", "asil": None, "p": 1, "a": "Sunny looked at Nephis"},
            {"ad": "Changing Star", "tr": "Değişen Yıldız", "t": "kisi", "asil": "Nephis", "p": 1,
             "a": "You are late, Changing Star"},
            {"ad": "Kai", "tr": "Kai", "t": "kisi", "p": 1, "a": "Sunny looked at Nephis"},  # ad_yok
            {"ad": "Nephis", "tr": "Nephis", "t": "kisi", "p": 1, "a": "Nephis smiled warmly"},  # alinti_yok
            {"ad": "he", "tr": "o", "t": "kisi", "p": 1, "a": "he said"},  # yer_tutucu
            {"ad": "Nephis", "tr": "Neferet", "t": "kisi", "p": 1, "a": "Sunny looked at Nephis"},  # tr_yok
            {"ad": "Nephis", "tr": "Nephis", "t": "kisi", "p": 99, "a": "x"},  # paragraf_yok
        ],
        "g": [idler["Hollow"]],
        "b": [
            {"o": "Sunny", "r": "ogretmeni", "n": "Julius", "p": 2, "a": "Julius had been Sunny's teacher",
             "s": "anlatici"},
            {"o": "Sunny", "r": "sevgilisi", "n": "Nephis", "p": 1, "a": "Sunny looked at Nephis"},  # iliski_yok
            {"o": "Nephis", "r": "yoldasi", "n": "Sunny", "p": 1, "a": "Sunny looked at Nephis", "s": "konusma"},
        ],
        "h": [
            {"p": 1, "ko": "Sunny", "mu": "Nephis", "f": "sen", "tra": "Geç kaldın", "en": ""},
            {"p": 1, "ko": "Sunny", "mu": "Nephis", "f": "siz", "tra": "Geç kaldın", "en": ""},  # hitap_celiski
            {"p": 3, "ko": "Nephis", "mu": "Kai", "f": "siz", "tra": "Evet efendim, sizi bekliyordum", "en": "sir"},
            {"p": 3, "ko": "Nephis", "mu": "Kai", "f": "sen", "tra": "sizi bekliyordum"},  # hitap_celiski (ters yön)
            {"p": 3, "ko": "Nephis", "mu": "Kai", "f": "resmi", "tra": "Evet efendim"},  # bicim_yok
        ],
    }


def _bolum2(_idler):
    return {"v": [], "g": [], "h": [],
            "b": [{"o": "Sunny", "r": "ogretmeni", "n": "Julius", "p": 1, "a": "Julius was Sunny's teacher",
                   "s": "konusma"}]}


def _iddialar(bolum=None):
    conn = db.connect()
    sorgu = "SELECT tur, ozne_ad, nesne_ad, iliski, gecerli, red_nedeni FROM defter_iddia WHERE book_slug = ?"
    arg = [KITAP]
    if bolum is not None:
        sorgu += " AND bolum = ?"
        arg.append(bolum)
    out = conn.execute(sorgu, arg).fetchall()
    conn.close()
    return out


# ---------- Türkçe hitap işaretleri ----------
@pytest.mark.parametrize("metin,beklenen", [
    ("Geç kaldın.", (True, False)), ("Sen de gel.", (True, False)), ("Nasılsın?", (True, False)),
    ("Siz de gelin, efendim.", (False, True)), ("Biliyor musunuz?", (False, True)),
    ("Yaşlı kadın baktı.", (False, False)), ("Altın parladı.", (False, False)),
])
def test_hitap_isaretleri(metin, beklenen):
    assert kd.hitap_isaretleri(metin) == beklenen


def test_hitap_adaylari_konusma_ve_ikinci_kisi_ister():
    assert kd.hitap_adaylari(BOLUM1_EN, BOLUM1_TR) == [1, 3]  # 2 ve 4: konuşma yok


def test_run_mesaji_hitap_adayidir():
    assert kd.hitap_adaylari(["[You have received a Memory.]"], ["[Bir Anı aldın.]"]) == [1]


# ---------- bölüm işleme ve doğrulama ----------
def test_her_red_nedeni_ayri_kaydedilir(kitap):
    sonuc = kd.bolum_isle(kitap, 1, cagir=_sahte({1: _bolum1}))
    assert sonuc["durum"] == "completed"
    red = {r[5] for r in _iddialar(1) if not r[4]}
    assert red == {"ad_yok", "alinti_yok", "yer_tutucu", "tr_yok", "paragraf_yok", "iliski_yok",
                   "hitap_celiski", "bicim_yok"}
    # Çelişki iki yönde de: "siz" dendi ama alıntı sen; "sen" dendi ama alıntı siz.
    assert sum(1 for r in _iddialar(1) if r[5] == "hitap_celiski") == 2
    assert ("hitap", "Nephis", "Kai") in {(r[0], r[1], r[2]) for r in _iddialar(1) if r[4]}
    gecerli = {(r[0], r[1], r[2]) for r in _iddialar(1) if r[4]}
    assert ("varlik", "Changing Star", "Nephis") in gecerli
    assert ("bag", "Sunny", "Julius") in gecerli
    assert ("hitap", "Sunny", "Nephis") in gecerli
    assert ("genel", "Hollow", None) in gecerli


def test_istem_kaynagi_bir_kez_tasir_ve_hitap_adaylarini_verir(kitap):
    cagir = _sahte({1: _bolum1})
    kd.bolum_isle(kitap, 1, cagir=cagir)
    istem = cagir.cagrilar[0]
    assert [p[0] for p in istem["paragraflar"]] == [1, 2, 3, 4]
    assert istem["hitap_adaylari"] == [1, 3]
    assert {"Sunny", "Nephis", "Julius", "Changing Star", "Kai", "Captain", "Hollow"} <= {
        k["ad"] for k in istem["kayitli"]}


def test_yeniden_isleme_kopya_uretmez(kitap):
    cagir = _sahte({1: _bolum1})
    kd.bolum_isle(kitap, 1, cagir=cagir)
    ilk = len(_iddialar(1))
    kd.bolum_isle(kitap, 1, cagir=cagir)
    assert len(_iddialar(1)) == ilk


def test_kayit_defteri_gelecek_bolumun_kaydini_vermez(kitap):
    conn = db.connect()
    conn.execute("UPDATE glossary SET first_chapter = 5 WHERE book_slug = ? AND source = 'Julius'", (KITAP,))
    conn.commit()
    conn.close()
    adlar = {k["ad"] for k in kd.kayit_defteri(KITAP, 1, "\n\n".join(BOLUM1_EN))}
    assert "Julius" not in adlar and "Sunny" in adlar


def test_hizasiz_bolum_model_cagirmaz(kitap):
    _bolum_ekle(3, ["a", "b"], ["tek paragraf"])
    cagir = _sahte({})
    assert kd.bolum_isle(kitap, 3, cagir=cagir)["durum"] == "hizasiz"
    assert cagir.cagrilar == []


def test_kuru_calisma_api_cagirmaz(kitap):
    cagir = _sahte({})
    sonuc = kd.bolum_isle(kitap, 1, cagir=cagir, kuru=True)
    assert sonuc["durum"] == "kuru" and sonuc["tahmini_giris"] > 0 and cagir.cagrilar == []


def test_hata_denemeyi_sayar_ve_ucuncude_birakir(kitap):
    def bozuk(user, model):
        raise translate.TranslateError("vertex 503")

    durumlar = []
    for _ in range(3):
        kd.bolum_isle(kitap, 1, cagir=bozuk)
        conn = db.connect()
        durumlar.append(conn.execute(
            "SELECT durum, deneme FROM defter_isleme WHERE book_slug = ? AND bolum = 1", (KITAP,)).fetchone())
        conn.close()
    assert durumlar == [("pending", 1), ("pending", 2), ("failed", 3)]


def test_bozuk_json_hata_sayilir(kitap):
    sonuc = kd.bolum_isle(kitap, 1, cagir=lambda u, m: ("bu json değil", {}))
    assert sonuc["durum"] == "hata"


# ---------- birikim ----------
def _bag(kaynak, iliski, hedef):
    for b in vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi")):
        if (b["kaynak"], b["iliski"], b["hedef"]) == (kaynak, iliski, hedef):
            return b
    return None


def test_guven_kademeleri():
    assert kd.guven_hesapla({1, 2}, {"konusma"}) == 1.0
    assert kd.guven_hesapla({1}, {"anlatici"}) == 0.8
    assert kd.guven_hesapla({1}, {"konusma"}) == 0.5


def test_uzlastir_birikimle_guveni_artirir_ve_aday_yazar(kitap):
    cagir = _sahte({1: _bolum1, 2: _bolum2})
    kd.bolum_isle(kitap, 1, cagir=cagir)
    kd.uzlastir(kitap)
    assert _bag("Sunny", "ogretmeni", "Julius")["guven"] == 0.8
    kd.bolum_isle(kitap, 2, cagir=cagir)
    kd.uzlastir(kitap)
    bag = _bag("Sunny", "ogretmeni", "Julius")
    assert bag["guven"] == 1.0 and bag["durum"] == "aday" and bag["ilk_bolum"] == 1
    # takma ad: asıl -> takma_adi -> ad
    assert _bag("Nephis", "takma_adi", "Changing Star")["durum"] == "aday"


def test_uzlastir_idempotent_ve_reddedileni_diriltmez(kitap):
    kd.bolum_isle(kitap, 1, cagir=_sahte({1: _bolum1}))
    kd.uzlastir(kitap)
    once = len(vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi")))
    kd.uzlastir(kitap)
    assert len(vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi"))) == once
    kimlik = {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(KITAP)}
    vg.bag_durumu(KITAP, kimlik["Nephis"], "takma_adi", kimlik["Changing Star"], "reddedildi")
    kd.uzlastir(kitap)
    assert _bag("Nephis", "takma_adi", "Changing Star")["durum"] == "reddedildi"


def test_cins_ad_gibi_kullanilan_takma_ad_dusuk_guvende_kalir(kitap):
    _bolum_ekle(4, ["Nephis walked to the Hollow.", "The hollow was dark. A hollow log.", "hollow"],
                ["Nephis Kovuk'a yürüdü.", "Kovuk karanlıktı.", "kovuk"])
    kd.bolum_isle(kitap, 4, cagir=_sahte({4: {"v": [{"ad": "Hollow", "tr": "Kovuk", "t": "yer", "asil": "Nephis",
                                                     "p": 1, "a": "Nephis walked to the Hollow"}],
                                              "g": [], "b": [], "h": []}}))
    kd.uzlastir(KITAP)
    assert _bag("Nephis", "takma_adi", "Hollow")["guven"] <= 0.6


# ---------- hitap ----------
def _hitap_bolumu(no, bicim):
    _bolum_ekle(no, [f'"Sunny, listen," Nephis said. ({no})'], [f'"Sunny, dinle{"yin" if bicim == "siz" else ""}," dedi Nephis. ({no})'])
    tra = "dinleyin" if bicim == "siz" else "Sunny, dinle"
    return {"v": [], "g": [], "b": [], "h": [{"p": 1, "ko": "Nephis", "mu": "Sunny", "f": bicim, "tra": tra}]}


def test_hitap_tablosu_kararlilik_gelecek_ve_elle_karar(kitap):
    yanitlar = {no: _hitap_bolumu(no, "sen") for no in (10, 11, 12)}
    yanitlar[13] = _hitap_bolumu(13, "siz")
    cagir = _sahte(yanitlar)
    for no in (10, 11, 12, 13):
        assert kd.bolum_isle(KITAP, no, cagir=cagir)["durum"] == "completed"
    kimlik = {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(KITAP)}
    cift = (kimlik["Nephis"], kimlik["Sunny"])
    assert kd.hitap_tablosu(KITAP, 11)[cift]["kararli"] is False  # yalnız 2 kayıt
    t = kd.hitap_tablosu(KITAP, 12)[cift]
    assert (t["bicim"], t["n"], t["kararli"]) == ("sen", 3, True)
    sapma = kd.hitap_denetle(KITAP, 13)
    assert [(s["bicim"], s["beklenen"]) for s in sapma] == [("siz", "sen")]
    kd.hitap_karari_yaz(KITAP, *cift, "siz", ilk_bolum=1)
    assert kd.hitap_tablosu(KITAP, 12)[cift]["bicim"] == "siz"
    assert kd.hitap_sapmalari(KITAP, 13) == []


# ---------- kuyruk ve bayraklar ----------
def test_kuyruk_bayrak_kapaliyken_hicbir_sey_yapmaz(kitap, monkeypatch):
    baslatilan = []
    monkeypatch.setattr(kd, "arka_planda_isle", lambda s: baslatilan.append(s))
    assert kd.kuyruga_ekle(KITAP, 1) is False
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    assert kd.kuyruga_ekle(KITAP, 1) is False  # kitap listede değil
    monkeypatch.setenv("KARAKTER_DEFTERI_KITAPLAR", KITAP)
    assert kd.kuyruga_ekle(KITAP, 1) is True and baslatilan == [KITAP]
    assert kd.durum(KITAP)["bolumler"] == {"pending": 1}


def test_kuyruk_asla_firlatmaz(monkeypatch):
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    monkeypatch.setenv("KARAKTER_DEFTERI_KITAPLAR", KITAP)
    monkeypatch.setattr(kd, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("db yok")))
    assert kd.kuyruga_ekle(KITAP, 1) is False


def test_arka_plan_isci_bekleyeni_isler_ve_uzlastirir(kitap, monkeypatch):
    monkeypatch.setenv("KARAKTER_DEFTERI", "1")
    monkeypatch.setenv("KARAKTER_DEFTERI_KITAPLAR", KITAP)
    monkeypatch.setattr(kd, "_model_cagir", _sahte({1: _bolum1, 2: _bolum2}))
    kd.kuyruga_ekle(KITAP, 1)
    kd.kuyruga_ekle(KITAP, 2)
    for _ in range(200):
        if not kd.durum(KITAP)["calisiyor"] and kd.durum(KITAP)["bolumler"].get("completed") == 2:
            break
        time.sleep(0.05)
    assert kd.durum(KITAP)["bolumler"] == {"completed": 2}
    assert _bag("Sunny", "ogretmeni", "Julius")["guven"] == 1.0


def test_dusunme_ayari_yalniz_verilince_gonderilir(monkeypatch):
    monkeypatch.setattr(translate, "GEMINI_DUSUNME_BUTCESI", None)
    assert translate._gemini_yapilandirmasi("s", 10).thinking_config is None
    jeton = translate._DUSUNME_AYARI.set({"thinking_level": "low"})
    try:
        ayar = translate._gemini_yapilandirmasi("s", 10).thinking_config
    finally:
        translate._DUSUNME_AYARI.reset(jeton)
    assert str(getattr(ayar.thinking_level, "value", ayar.thinking_level)).lower() == "low"
    assert translate._gemini_yapilandirmasi("s", 10).thinking_config is None


@pytest.mark.parametrize("deger,beklenen", [
    ("", {"thinking_level": "low"}), ("varsayilan", None), ("high", {"thinking_level": "high"}),
    ("0", {"thinking_budget": 0}),
])
def test_dusunme_ayari_ortamdan(monkeypatch, deger, beklenen):
    monkeypatch.setenv("DEFTER_DUSUNME", deger)
    assert kd.dusunme_ayari() == beklenen


def test_yarim_yanitin_harcamasi_kayda_gecer_ve_basarida_birikir(kitap):
    def yarim(user, model):
        raise kd.YarimYanit("bitiş: MAX_TOKENS", {"model": model, "giris": 100, "cikis": 50, "dusunme": 40})

    kd.bolum_isle(KITAP, 1, cagir=yarim)
    kd.bolum_isle(KITAP, 1, cagir=_sahte({1: _bolum1}))  # sahte: 1000/200
    conn = db.connect()
    satir = conn.execute("SELECT durum, giris_token, cikis_token, dusunme_token FROM defter_isleme "
                         "WHERE book_slug = ? AND bolum = 1", (KITAP,)).fetchone()
    conn.close()
    assert satir == ("completed", 1100, 250, 40)


class _Yanit:
    def __init__(self, neden):
        self.candidates = [type("A", (), {"finish_reason": neden})()]
        self.text = "{}"
        self.usage_metadata = type("M", (), {"prompt_token_count": 10, "candidates_token_count": 5,
                                             "thoughts_token_count": 3})()


@pytest.mark.parametrize("neden,yarim", [("STOP", False), ("MAX_TOKENS", True)])
def test_model_cagrisi_bitis_nedenini_denetler(monkeypatch, neden, yarim):
    monkeypatch.setattr(translate, "_generate_with_fallback", lambda *a, **k: (_Yanit(neden), "m"))
    if yarim:
        with pytest.raises(kd.YarimYanit) as hata:
            kd._model_cagir("u", "m")
        assert "MAX_TOKENS" in str(hata.value) and hata.value.kullanim["giris"] == 10
    else:
        assert kd._model_cagir("u", "m")[1] == {"model": "m", "giris": 10, "cikis": 8, "dusunme": 3}


# ---------- ölçüm ve betik ----------
def test_taban_olcumu_captain_ve_hitap_sayar(kitap):
    taban = kd.taban_olcumu(KITAP)
    assert taban["bolum"] == 2 and taban["hizasiz"] == 0
    assert taban["captain"] == {"yüzbaşı": 1}
    assert taban["diyalog"].get("sen") == 1 and taban["diyalog"].get("siz") == 1


def test_metrik_maliyet_ve_hitap_sapmasini_ozetler(kitap):
    yanitlar = {no: _hitap_bolumu(no, "sen") for no in (10, 11, 12)}
    yanitlar[13] = _hitap_bolumu(13, "siz")
    cagir = _sahte(yanitlar)
    for no in (10, 11, 12, 13):
        kd.bolum_isle(KITAP, no, cagir=cagir, model="vertex/gemini-3.8-flash")
    kd.bolum_isle(KITAP, 1, cagir=_sahte({1: _bolum1}))
    kd.uzlastir(KITAP)
    m = kd.metrik(KITAP)
    json.dumps(m)  # rapor dosyasına yazılabilmeli
    assert m["model_baglari"]
    assert m["tamamlanan"] == 5 and m["token"]["giris"] == 5000
    assert m["hitap"]["sapma"] == 1 and m["hitap"]["kararli_karsi_kayit"] == 1
    assert m["maliyet_usd"] > 0


def test_denetim_ornegi_paragraf_metnini_tasir(kitap):
    kd.bolum_isle(KITAP, 1, cagir=_sahte({1: _bolum1}))
    ornek = kd.denetim_ornegi(KITAP, {"bag": 5, "hitap": 5})
    assert {o["tur"] for o in ornek} == {"bag", "hitap"}
    assert all(o["en"] and o["tr"] for o in ornek)


def _betik(monkeypatch, *argv):
    import karakter_defteri as betik  # scripts/

    monkeypatch.setattr("sys.argv", ["karakter_defteri.py", *argv])
    return betik


def test_betik_kuru_api_cagirmaz(kitap, monkeypatch, tmp_path):
    monkeypatch.setattr(kd, "_model_cagir", lambda *a: pytest.fail("kuru çalışma model çağırdı"))
    betik = _betik(monkeypatch, "--kitap", KITAP, "--kuru", "--rapor", str(tmp_path / "r.json"))
    assert betik.main() == 0
    rapor = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert rapor["kuru"]["islenebilir"] == 2 and rapor["secilen"] == [1, 2]


def test_betik_calistir_tamamlananı_atlar_ve_bozugu_bir_kez_yeniden_dener(kitap, monkeypatch):
    sayac = {}

    def cagir(user, model):
        no = json.loads(user)["bolum"]
        sayac[no] = sayac.get(no, 0) + 1
        if no == 2:
            raise translate.TranslateError("bozuk")
        return json.dumps(_bolum1(_idler(user))), {"model": model, "giris": 1, "cikis": 1, "dusunme": 0}

    monkeypatch.setattr(kd, "_model_cagir", cagir)
    betik = _betik(monkeypatch, "--kitap", KITAP, "--calistir", "--bekleme", "0")
    betik.main()
    assert sayac == {1: 1, 2: 2}  # 2 bir kez yeniden denendi, döngü yok
    betik = _betik(monkeypatch, "--kitap", KITAP, "--calistir", "--bekleme", "0", "--bolumler", "1")
    betik.main()
    assert sayac[1] == 1  # tamamlanan atlandı


def test_pilot_secimi_rastgele_ve_diyalog_yogununu_karistirir(kitap):
    import karakter_defteri as betik

    assert betik.pilot_secimi(KITAP, [1, 2], 2, 7) == [1, 2]


# ---------- v2 kuralları (pilot elle denetiminden) ----------
def _dogrula(tur, oge, en, tr):
    return kd.dogrula(tur, oge, en, tr, kd._Cozucu(KITAP, []))


def test_rutbe_yalniz_rutbe_adina_baglanir(kitap):
    en = ["Captain Kai, the Archer of the company, nodded."]
    tr = ["Bölüğün okçusu Yüzbaşı Kai başını salladı."]
    gecer = _dogrula("bag", {"o": "Kai", "r": "rutbesi", "n": "Captain", "p": 1, "a": "Captain Kai"}, en, tr)
    rol = _dogrula("bag", {"o": "Kai", "r": "rutbesi", "n": "Archer", "p": 1, "a": "the Archer of the company"},
                   en, tr)
    assert gecer["gecerli"] == 1 and rol["red_nedeni"] == "rutbe_degil"


def test_gercek_ad_true_name_kaniti_ister(kitap):
    tr = ["x"]
    yok = _dogrula("bag", {"o": "Sunny", "r": "gercek_adi", "n": "Nephis", "p": 1, "a": "Sunny met Nephis"},
                   ["Sunny met Nephis."], tr)
    var = _dogrula("bag", {"o": "Sunny", "r": "gercek_adi", "n": "Nephis", "p": 1, "a": "True Name was Nephis"},
                   ["Sunny's True Name was Nephis."], tr)
    assert yok["red_nedeni"] == "gercek_ad_kanitsiz" and var["gecerli"] == 1


def test_kucuk_harfli_gecis_ozel_ad_sayilmaz(kitap):
    en = ["Sunny hid inside the hollow tree."]
    tr = ["Sunny kovuk ağacın içine saklandı."]
    v = _dogrula("varlik", {"ad": "Hollow", "tr": "kovuk", "t": "yer", "p": 1, "a": "inside the hollow tree"}, en, tr)
    b = _dogrula("bag", {"o": "Sunny", "r": "dusmani", "n": "Hollow", "p": 1, "a": "Sunny hid inside the hollow"},
                 en, tr)
    assert v["red_nedeni"] == "ad_kucuk" and b["red_nedeni"] == "ad_kucuk"


def test_turkce_alinti_harf_isaretsiz_de_bulunur(kitap):
    k = _dogrula("hitap", {"p": 1, "ko": "Nephis", "mu": "Sunny", "f": "sen", "tra": "Oyle degil mi, Sunny"},
                 ['"Right, Sunny?" Nephis asked.'], ['"Öyle değil mi, Sunny?" diye sordu Nephis.'])
    assert k["gecerli"] == 1


def test_konusan_bolumde_uzakta_adlandirilsa_da_gecerli(kitap):
    en = ["Nephis turned to Sunny."] + ["..."] * 12 + ['"Why are you here?"']
    tr = ["Nephis, Sunny'ye döndü."] + ["..."] * 12 + ['"Neden buradasın?"']
    k = _dogrula("hitap", {"p": 14, "ko": "Nephis", "mu": "Sunny", "f": "sen", "tra": "Neden buradasın?"}, en, tr)
    assert k["gecerli"] == 1


def test_bolumde_hic_gecmeyen_konusan_reddedilir(kitap):
    k = _dogrula("hitap", {"p": 1, "ko": "Julius", "mu": "Sunny", "f": "sen", "tra": "Neden buradasın?"},
                 ['"Why are you here, Sunny?"'], ['"Neden buradasın, Sunny?"'])
    assert k["red_nedeni"] == "ad_yok"


def test_cogul_hitap_gecerli_ama_tabloya_girmez(kitap):
    for no in (20, 21, 22):
        _bolum_ekle(no, [f'"Both of you, listen," Sunny told Kai and Effie. ({no})'],
                    [f'"İkiniz de dinleyin," dedi Sunny, Kai ile Effie\'ye. ({no})'])
    cagir = _sahte({no: {"v": [], "g": [], "b": [], "h": [
        {"p": 1, "ko": "Sunny", "mu": "Kai", "f": "cogul", "tra": "İkiniz de dinleyin"}]} for no in (20, 21, 22)})
    for no in (20, 21, 22):
        kd.bolum_isle(KITAP, no, cagir=cagir)
    assert all(r[4] for r in _iddialar(20))
    kimlik = {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(KITAP)}
    assert kd.hitap_tablosu(KITAP)[(kimlik["Sunny"], kimlik["Kai"])]["bicim"] is None


# ---------- Faz 2: sözlüğe katkı ----------
def _kimlik():
    return {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(KITAP)}


def _iddia_yaz(tur, ozne, bolum, nesne=None, deger=None, iliski=None):
    kd._connect().close()
    k = _kimlik()
    conn = db.connect()
    conn.execute(
        "INSERT INTO defter_iddia (book_slug, bolum, tur, ozne_ad, ozne_kimlik, iliski, nesne_ad, nesne_kimlik, "
        "deger, gecerli, istem_surumu, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'test', 0)",
        (KITAP, bolum, tur, ozne, k.get(ozne), iliski, nesne, k.get(nesne) if nesne else None,
         json.dumps(deger or {}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def _nedenler(kaynak):
    return [n["tur"] for n in kd.sozluk_nedenleri(KITAP).get(kaynak, [])]


def test_genel_sozcuk_uc_bolum_ve_hic_ad_olmama_ister(kitap):
    for b in (1, 2):
        _iddia_yaz("genel", "Hollow", b)
    assert "grafik_genel_sozcuk" not in _nedenler("Hollow")
    _iddia_yaz("genel", "Hollow", 3)
    assert "grafik_genel_sozcuk" in _nedenler("Hollow")
    _iddia_yaz("varlik", "Hollow", 4, deger={"tr": "Kovuk", "t": "yer"})
    assert "grafik_genel_sozcuk" not in _nedenler("Hollow")


def test_takma_ad_onerisi_karar_verilince_kaybolur_ve_dirilmez(kitap):
    for b in (1, 2):
        _iddia_yaz("varlik", "Changing Star", b, nesne="Nephis", deger={"tr": "Değişen Yıldız", "t": "kisi"},
                   iliski="takma_adi")
    neden = kd.sozluk_nedenleri(KITAP)["Changing Star"][0]
    k = _kimlik()
    assert (neden["tur"], neden["asil_kimlik"], neden["takma_kimlik"]) == (
        "grafik_takma_ad", k["Nephis"], k["Changing Star"])
    kd.takma_ad_karari(KITAP, k["Nephis"], k["Changing Star"], "ayri")
    assert "grafik_takma_ad" not in _nedenler("Changing Star")
    kd.uzlastir(KITAP)
    assert _bag("Nephis", "takma_adi", "Changing Star")["durum"] == "reddedildi"


def test_takma_ad_ayni_karari_onaylar(kitap):
    k = _kimlik()
    kd.takma_ad_karari(KITAP, k["Nephis"], k["Changing Star"], "ayni")
    assert _bag("Nephis", "takma_adi", "Changing Star")["durum"] == "onaylandi"
    with pytest.raises(ValueError):
        kd.takma_ad_karari(KITAP, k["Nephis"], k["Changing Star"], "belki")


def test_kosul_onerisi_yerlesmis_farkli_karsiligi_bildirir(kitap):
    _iddia_yaz("varlik", "Captain", 1, deger={"tr": "Yüzbaşı'ya", "t": "rutbe"})
    for b in (2, 3, 4):
        _iddia_yaz("varlik", "Captain", b, deger={"tr": "Kaptan", "t": "rutbe"})
    nedenler = kd.sozluk_nedenleri(KITAP)["Captain"]
    assert nedenler[0]["tur"] == "grafik_kosul_onerisi" and "kaptan" in nedenler[0]["aciklama"]


def test_kayitla_ayni_karsilik_ekli_olsa_da_oneri_uretmez(kitap):
    for b, tr in ((1, "Yüzbaşı"), (2, "Yüzbaşı'nın"), (3, "yüzbaşıya"), (4, "Yuzbasi")):
        _iddia_yaz("varlik", "Captain", b, deger={"tr": tr, "t": "rutbe"})
    assert _nedenler("Captain") == []


def test_celiski_iki_iliskinin_ikisi_de_iki_bolum_ister(kitap):
    for b in (1, 2):
        _iddia_yaz("bag", "Sunny", b, nesne="Kai", iliski="yoldasi")
    _iddia_yaz("bag", "Kai", 3, nesne="Sunny", iliski="dusmani")
    assert "grafik_celiski" not in _nedenler("Sunny")
    _iddia_yaz("bag", "Sunny", 4, nesne="Kai", iliski="dusmani")
    assert "grafik_celiski" in _nedenler("Sunny") and "grafik_celiski" in _nedenler("Kai")


def test_tur_doldur_yalniz_bos_turu_ve_kararli_cogunlugu_yazar(kitap):
    conn = db.connect()
    conn.execute("UPDATE glossary SET tur = NULL WHERE book_slug = ? AND source IN ('Julius', 'Kai')", (KITAP,))
    conn.commit()
    conn.close()
    for b in (1, 2):
        _iddia_yaz("varlik", "Julius", b, deger={"tr": "Julius", "t": "kisi"})
        _iddia_yaz("varlik", "Sunny", b, deger={"tr": "Sunny", "t": "yer"})  # tur dolu: ezilmez
    _iddia_yaz("varlik", "Kai", 1, deger={"tr": "Kai", "t": "kisi"})  # tek bölüm: yazılmaz
    assert kd.tur_doldur(KITAP) == 1
    turler = {r["source"]: r["tur"] for r in glossary.get_glossary_rows(KITAP)}
    assert (turler["Julius"], turler["Sunny"], turler["Kai"]) == ("kisi", "kisi", None)


def test_inceleme_listesine_ek_alanlariyla_girer_onaylida_girmez(kitap):
    for b in (1, 2):
        _iddia_yaz("varlik", "Changing Star", b, nesne="Nephis", deger={"tr": "Değişen Yıldız"}, iliski="takma_adi")
    liste = {x["source"]: x for x in glossary.inceleme_listesi(KITAP)}
    neden = next(n for n in liste["Changing Star"]["nedenler"] if n["tur"] == "grafik_takma_ad")
    assert neden["asil_kimlik"] == _kimlik()["Nephis"] and neden["ilgili"] == ["Nephis"]
    glossary.onayla(KITAP, "Changing Star")
    assert "Changing Star" not in {x["source"] for x in glossary.inceleme_listesi(KITAP)}


def test_takma_ad_ucu(kitap):
    from fastapi.testclient import TestClient

    import server

    k = _kimlik()
    istemci = TestClient(server.app)
    uc = f"/api/book/{KITAP}/defter/takma-ad"
    assert istemci.post(uc, json={"asil_kimlik": k["Nephis"], "takma_kimlik": k["Changing Star"],
                                  "karar": "ayni"}).status_code == 200
    assert _bag("Nephis", "takma_adi", "Changing Star")["durum"] == "onaylandi"
    assert istemci.post(uc, json={"asil_kimlik": "yok", "takma_kimlik": k["Nephis"],
                                  "karar": "ayni"}).status_code == 404
    assert istemci.post(uc, json={"asil_kimlik": k["Nephis"], "takma_kimlik": k["Kai"],
                                  "karar": "belki"}).status_code == 400


def test_dogrulama_karti_baglam_hashini_degistirmez(kitap):
    from core import sozluk_dogrulama

    satir = next(r for r in glossary.get_glossary_rows(KITAP) if r["source"] == "Nephis")
    bolumler = [{"chapter_no": 1, "text": "\n\n".join(BOLUM1_EN)}]
    once = sozluk_dogrulama._hazirla(KITAP, satir, bolumler, [satir])
    assert once["kart"] is None
    for b in (1, 2):
        _iddia_yaz("varlik", "Nephis", b, deger={"tr": "Nephis", "t": "kisi"})
    sonra = sozluk_dogrulama._hazirla(KITAP, satir, bolumler, [satir])
    assert sonra["kart"]["tur"] == {"kisi": 2} and sonra["baglam_hash"] == once["baglam_hash"]
