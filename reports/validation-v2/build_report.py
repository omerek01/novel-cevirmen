"""Kaydedilmiş doğrulama çıktısından Türkçe rapor üretir; API/DB yazımı yapmaz."""
import hashlib
import json
import re
from pathlib import Path

P = Path(__file__).resolve().parent
KOK = P.parents[1]
v1 = json.loads((P / "v1.json").read_text(encoding="utf-8"))
v2 = json.loads((P / "v2.json").read_text(encoding="utf-8"))
a = json.loads((P / "v2.audit.json").read_text(encoding="utf-8"))
original = json.loads((P / "v2.initial.json").read_text(encoding="utf-8"))
assert len(v2) == 19 and a["completed"] == 19 and a["protected_tables_unchanged"]
assert [r["ham_yanit"] for r in v2] == [r["ham_yanit"] for r in original]
assert a["before"] == json.loads((P / "v2.model-audit.json").read_text(encoding="utf-8"))["before"]
m1, m2 = a["v1"], a["v2"]
retro = a["v1_duplicate_reanalysis_totals"]
out = []

def yaz(s=""):
    out.append(s)

def kod(x):
    return "```json\n" + json.dumps(x, ensure_ascii=False, indent=2) + "\n```"


yaz("# Faz 2A — Validation v2\n\n7 Ekim 2026 · Shadow Slave · **Karar: REPEAT VALIDATION**")
yaz("V2 değişiklikleri uygulandı ve v1 ile aynı 19 bölüm aynı Vertex modeliyle çalıştırıldı. "
    "Şema hatası **14 → 0**. Buna rağmen 670'te yönü ters bir öğretmen ilişkisi doğrulayıcıdan "
    "geçti; 691'de sıradan ad/True Name ayrımı ve kimlik önerileri sorunlu. "
    "**1–100 backfill başlatılmadı.** Bu rapor bir geçiş onayı değildir.")
yaz("## Yöntem ve kapsam")
yaz("- Bölümler: **" + ", ".join(map(str, a["chapters"])) + "**. Başka bölümde model çıkarımı yapılmadı.\n"
    "- Model: `vertex/gemini-3.6-flash`; çeviri modeli/zinciri değiştirilmedi.\n"
    "- Çıkarıcı/istem/şema: `2 / 2 / delta-2`. Structured output API düzeyinde uygulandı.\n"
    "- Sunucunun canlı SQLite verisi `sqlite3.backup` ile ayrı kopyaya alındı. Model koşusu "
    "`/tmp/novel-validation-v2-20261007` içindeki ayrı kod ve DB ile çalıştı. Canlı servise dağıtım/restart yapılmadı.\n"
    "- Her bölüm N−1 bağlamıyla bağımsız değerlendirildi. Bu set, 1→100 kronolojik pilotunun yerine geçmez.\n"
    "- 19 mantıksal model çağrısı, 21 sağlayıcı denemesi. 106'da iki HTTP **429**, sonra başarı; "
    "model değişikliği yok. Gerçek HTTP kodları `provider_attempts.json` dosyasında.\n"
    "- Son doğrulayıcıdaki canonical eşleştirme ve sayaç düzeltmeleri için kaydedilmiş yanıtlar "
    "API çağırmadan tekrar denetlendi. `v2.initial.json` ilk kararları, `v2.json` son kararları saklar. "
    "19 ham yanıt byte düzeyinde aynı. Son denetim, aynı sunucu DB kopyasında yerelde tamamlandı.")
yaz("## Uygulanan v2 kontratı")
yaz("1. API response JSON schema: nesne/dizi tipleri, zorunlu alanlar, enum'lar, NULL zaman alanları "
    "ve ek alan yasağı. Model çıktısı ayrıca uygulamada denetleniyor.\n"
    "2. Şema, prompt ve doğrulayıcı enum'ları aynı sabitlerden üretiyor. Life status için ayrı "
    "`anyOf` dalı kullanılıyor. [Vertex JSON schema sözleşmesi](https://docs.cloud.google.com/java/docs/reference/google-cloud-vertexai/latest/com.google.cloud.vertexai.api.GenerationConfigOrBuilder).\n"
    "3. İzinli durum anahtarları: `shadow_cores`, `shadow_fragments`, `soul`, `memory_tier`, "
    "`role`, `type`, `life_status`. Depolamadaki mevcut adlara eşleme var; veri göçü yok. "
    "Desteklenmeyen anahtar ölçülüp reddediliyor; kendiliğinden review oluşturmuyor.\n"
    "4. `life_status` yalnız `alive/dead/missing/presumed_dead/unknown`. Değer ile epistemik durum ayrı; "
    "eski believed iddia sonradan alive+confirmed gelince tarihçede korunuyor.\n"
    "5. Konum state değil; `bulundugu_yer`. Sözlükte olmayan uçlar düşük önemle varlık adayı; otomatik sözlük/entity yazımı yok.\n"
    "6. N−1 bilgisi ile N'nin zaten kayıtlı deterministik/rün bilgisi ayrı prompt bölümleri. "
    "İkisi **toplam 4.000 token** bütçesini paylaşıyor.\n"
    "7. Normalizasyon ve mevcut grafik/aynı bölüm kontrolü kanıttan önce. Eski alias'lar çözülürken "
    "gelecekteki kimlik bağları kullanılmıyor; ortak kanıt doğrulayıcısına bölüm sınırı geçiriliyor.\n"
    "8. Alias, unvan, True Name ve okur düzeyindeki identity revelation promptta ayrılıyor; "
    "epistemik durumların anlamları açık. NULL hikâye zamanları korunuyor. Şema hatalarında "
    "model output/API uyumsuzluğu/şema tasarım hatası ayrımı var; kör şema tekrarı yok.")
yaz("## V1–V2 karşılaştırması")
yaz("`accepted_*`, doğrulayıcının **planladığı** yazımları sayar; gerçek yazım veya insan tarafından "
    "onaylanmış doğruluk anlamına gelmez. V1 yalnız beş bölümün deltasını değerlendirebildi; "
    "bu nedenle ret sayıları bir doğruluk yüzdesi gibi kıyaslanamaz.")
yaz("| Metrik | V1 | V2 |\n|---|---:|---:|")
keys = ["schema_failures", "raw_relationships", "accepted_relationships", "evidence_failures",
        "already_known_proposals", "deterministic_same_chapter_duplicates", "unsupported_state_keys",
        "new_entity_candidates", "identity_revelations", "epistemic_non_confirmed", "review_items",
        "future_knowledge_violations", "context_dropped", "model_retries"]
for k in keys:
    x = str(m1.get(k, 0))
    if k == "deterministic_same_chapter_duplicates":
        x = f"ölçülmedi; ham yeniden eşleşme {retro.get(k, 0)}*"
    if k == "unsupported_state_keys":
        x = f"ölçülmedi; ham yeniden eşleşme {retro.get(k, 0)}*"
    if k == "already_known_proposals":
        x += " (v1 sayacı güvenilmez)"
    if k == "epistemic_non_confirmed":
        x = "1 ham / 0 değerlendirilen"
    yaz(f"| `{k}` | {x} | {m2.get(k, 0)} |")
yaz(f"| `cost` (başarılı yanıt tokenlarından tahmin) | ${m1['cost_usd_estimate']:.3f} | ${m2['cost_usd_estimate']:.3f} |")
yaz("\n* V1'in bozuk pozisyonlu dizi öğeleri yalnız tekrar eşleşmesi için alan adlarına çevrildi; "
    "Türkçe durum anahtarları v2'deki karşılıklarına eşlendi. Bu retrospektif denetim, v1'in "
    "şema/acceptance sonuçlarını değiştirmez. V1'in bütün ham önerileri güvenle normalleştirilemediğinden "
    "sayılar tam bir lore doğruluk ölçümü değildir. Ayrıntılar audit dosyasında.")
den1 = sum(len((r.get("model_deltasi") or {}).get(k) or []) for r in v1 for k in ("new_relationships", "new_aliases", "state_changes"))
den2 = sum(len((r.get("model_deltasi") or {}).get(k) or []) for r in v2 for k in ("new_relationships", "new_aliases", "state_changes"))
yaz(f"Aynı bölümün **gerçekten kayıtlı deterministik** verisiyle eşleşen tekrarlar, ham yeniden "
    f"eşleştirmede v1'de **{retro.get('deterministic_same_chapter_duplicates',0)}/{den1}**, "
    f"v2'de **{m2.get('deterministic_same_chapter_duplicates',0)}/{den2}**. "
    "Rün metninden gelmek tek başına 'zaten kayıtlı' demek değildir: 15 ve 106'da "
    "rün bloğunun bazı bilgileri mevcut deterministik kayıtta bulunmuyor.")
yaz(f"Ek ayrım: `same_chapter_existing_proposals = {m2.get('same_chapter_existing_proposals',0)}`. "
    "Bunlar N'de eski model/elle grafik kaydında zaten var, ama N−1 bilgisi veya rün kaydı değiller. "
    "İki ana tekrar metriğine katılmadılar; kanıt kontrolünden önce ALREADY_EXISTS olarak atlandılar.")
yaz("V1 raporunun 'bütün öneriler confirmed' cümlesi ham veriyle tam uyuşmuyor: "
    "61'de bir `believed` önerisi var, ancak şemadan düştü. V2'de **tüm epistemik öneriler confirmed**; "
    "doğal epistemik çeşitlilik bu sette hâlâ gösterilemedi. Yapay çeşitlilik zorlanmadı.")
yaz("V1'de modelin ham review önerisi 6, değerlendiricinin üretebildiği review 0; "
    "v2'de ham review önerisi 3, doğrulayıcının simüle ettiği review 9. Kalıcı review iki "
    "koşuda da 0. Ham identity sayısı 2 → 2, fakat 670'teki kesin yanlış identity önerisi "
    "1 → 0; v2'nin iki identity önerisi 691'de inceleme adayı. Tüm yeni ilişki/güncelleme "
    "`gecerli_baslangic/gecerli_bitis` alanları NULL; tahmini tarih üretilmedi.")
yaz("## Bölüm sonuçları")
yaz("| Bölüm | Ham ilişki | Planlanan ilişki | Planlanan durum | Kanıt reddi | Önceki bilgi | Aynı bölüm rün | Aynı bölüm eski grafik | Review | Bağlam token | Kesilen |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for r in v2:
    d, o, q = r["model_deltasi"], r["olcum"], r["degerlendirme"]
    props, c = q["oneriler"], q["sayac"]
    ac = sum(p["tur"] == "new_relationships" and p["karar"] == "işle" for p in props)
    st = sum(p["tur"] == "state_changes" and p["karar"] == "işle" for p in props)
    ev = sum(p["karar"].startswith("reddedildi:") and "kanıt" in p["karar"] for p in props)
    yaz(f"| {r['bolum']} | {len(d['new_relationships'])} | {ac} | {st} | {ev} | {c['already_known_proposals']} | "
        f"{c['deterministic_same_chapter_duplicates']} | {c['same_chapter_existing_proposals']} | "
        f"{len(q['inceleme'])} | {o['baglam_tokeni']} | {o['kesilen_satir']} |")
yaz("## Yazmasız çalışma ve bütçe kanıtı")
yaz("Grafik, durum, çeviri, sözlük, review, kronoloji başı ve işleme/öneri kayıtlarının içerik SHA-256 "
    "özetleri **önce = sonra**. Son yerel denetimin başlangıç özetleri model koşusunun başlangıç "
    "özetleriyle de aynı. Özellikle bağ sayısı **1.036 → 1.036**, durum **48 → 48**; "
    "`bilgi_bas`, `bilgi_inceleme`, `bilgi_isleme`, `bilgi_oneri` satırları **0 → 0**. "
    "Yıkıcı merge ve kalıcı graph/review/head/translation yazımı **0**. Sağlayıcı/kullanım "
    "telemetrisi yalnız ayrı çalışma DB'sinde tutuldu.")
yaz("| Korunan tablo | Önce | Sonra | İçerik özeti |\n|---|---:|---:|---|")
for t, before in a["before"].items():
    after = a["after"][t]
    if before:
        yaz(f"| `{t}` | {before['rows']} | {after['rows']} | aynı |")
yaz(f"Bağlamın en yüksek değeri **{max(r['olcum']['baglam_tokeni'] for r in v2)} token**. "
    "Kesilenlerin tamamı eski doğrudan bağlar; varlık, kimlik, durum, yakın geçmiş ve "
    "aynı bölüm deterministik satırları bu koşuda korunmuş. 848'de **372** satır kesildi "
    "(v1: 366); aynı bölüm verisinin de bütçeye katılması bu farkı açıklıyor. "
    "Saptanan yön/kanıt/True Name hataları eski bağlam eksikliğinden kaynaklanmıyor; bütçe artırılmadı.")
yaz("## Altı bölümün ayrıntılı incelemesi")
manual = {
    15: (
        "Sunny Dreamer olur, Lost from Light True Name'ini alır; görünüşü Shadow Slave'e "
        "evrilir ve Shadow Bond yeteneğini edinir. Puppeteer's Shroud bir Memory olarak verilir.",
        "Dreamer/True Name/Shroud türü tekrar edilmiyor; iki eski rün bağının kapatılması "
        "yıkıcı işlem yerine review'e yönlendiriliyor. Hikâye zamanları tahmin edilmemiş.",
        "Görünüş, Aspect rank ve yetenek için model, özneyi içermeyen rün satırlarını kanıt "
        "gösteriyor; üç öneri katı denetimde reddediliyor. Bunlar bu bölümün deterministik "
        "veri listesinde yok; 'model tekrar etti' diye saymak hatalı olur.",
        "First Seal özel varlık mı, sistem olayı/kavramı mı? Düşük önemli aday olarak kaldı. "
        "Rün parser kapsamı tamamlanmadan bu ilk bölümlerin önemli lore'u eksik kalabilir."),
    106: (
        "Stone Saint bir Echo'dan Shadow'a dönüştürülür. Nitelik listesi ve 0/200 sayacı "
        "gölgenin yeni durum rününde görünür.",
        "Kayıtlı Shadow türü ve Sunny'nin gölgesi bağı yeniden çıkarılmıyor. "
        "`shadow_fragments` depoda `Shadow Fragments` anahtarına eşleniyor.",
        "Spark of Divinity'nin kanıt rününde Stone Saint adı yok; ilişki reddediliyor. "
        "Aynı bölüm deterministik listesinde nitelik ve sayaç kaydı bulunmuyor. "
        "V1 raporunun bunların tamamının zaten kayıtlı olduğu varsayımı bu snapshot'ta doğrulanmıyor.",
        "Sayaç için kabul planı, rün cümlesinin bağlamından özne tayini gerektiriyor. "
        "Model state kanıtında entity adının geçmesini zorunlu tutan ilişki denetimi uygulanmıyor; "
        "state evidence bağlamı ayrıca incelenmeli."),
    360: (
        "Cassie, Sunny'nin sırrını bir vizyondan öğrendiğini ve Nephis'e verdiğini anlatır. "
        "Sunny ile Cassie'nin güven/dostluk bağı kırılır; hastanede Nephis'in bedeni gösterilir.",
        "V1'deki hospital complex entity/serbest fiziksel durum önerileri yok. "
        "Karaktere özel bilgi aktarımı mevcut graph modeline zorla yazılmıyor.",
        "Review kanıtı yalnız 'When you killed that spy from the Castle.' cümlesi. "
        "Bu tek cümle açıklamadaki bütün True Name/Nephis iddialarını desteklemiyor. "
        "Review'lerin kanıt kapsamı ilişki denetimi kadar sıkı değil.",
        "Friendship kırılması otomatik ilişki kapanışı olarak çıkarılmadı; bunun 'aynı anda "
        "düşman oldular' diye otomatik temsil edilmemesi temkinli. Retroactive revelation review'i "
        "olay/karakter bilgisi kuyruğunu büyütmemeli."),
    670: (
        "Effie'nin Sunny'ye mızrak kullanmayı öğrettiği hatırlatılır. Kılık değiştirmiş "
        "Sunny'yi Effie tanır; okur onun Sunny olduğunu baştan bilir.",
        "Yanlış `Effie = Sunny` kimlik önerisi kalktı. Doofus lakabı, zayıf tek cümle "
        "kanıtı nedeniyle otomatik alias yerine düşük önemli review olarak bırakıldı.",
        "**Kesin hata:** `Effie → ogretmeni → Sunny` kabul planına girdi. İlişki etiketi "
        "'öğretmeni', ters etiketi 'öğrencisi'; doğru yön **Sunny → ogretmeni → Effie**. "
        "Kanıtta iki adın bulunması yönün doğruluğunu garanti etmiyor.",
        "Bu hatanın nedeni bağlam bütçesi değil, ilişki rol/yön denetiminin eksikliği. "
        "Graph'a yazılmadı, fakat gerçek pilotta yanlış bağ yaratabilecek bir kabul hatası."),
    691: (
        "Noctis, Nether'ın Demon of Destiny olduğunu ve Hope'un Demon of Desire olarak "
        "bilindiğini anlatır. Prince of the Underworld ile Nether bağlantısı açıklanır.",
        "Kimlik önerileri yalnız review: birleştirme yapılmıyor. Kaynağa uymayan veya "
        "aynı canonical düğüme çözülen alias önerileri yazılmıyor.",
        "`Prince of the Underworld → gercek_adi → Nether` sıradan kişisel adı büyülü "
        "True Name ile karıştırıyor. Nether'ın unvanı için kanıt 'Then there' yerine "
        "'There' ile başlıyor; birebir kaynak koşulunu karşılamıyor, fakat son doğrulayıcı "
        "bu unvanın aynı bölüm eski grafikte zaten var olduğunu kanıttan önce saptayıp atlıyor. Ellipsis içeren "
        "Nether alıntısı ise cümle havuzunun sınırını aşıyor ve reddediliyor.",
        "İki çift hem alias hem identity revelation olarak öneriliyor. Prince/Nether "
        "okur düzeyinde açıklama için makul aday; Hope/Demon of Desire'ın ayrı yeni kimlik "
        "mi, unvan mı olduğu önceki metinle denetlenmeli. İki kritik review'i iki doğrulanmış "
        "identity revelation gibi saymamak gerekir."),
    848: (
        "Sunny'nin geniş durum rünü, yeni Memories ve 777/4000 sayacı gösterilir. "
        "Düzyazı Soul Serpent'in Rain'e verildiğini ve hayatta olduğunu da belirtir.",
        "N'nin kayıtlı yedi bağı ve fragment sayacı tekrar edilmiyor; boş delta bu "
        "rün ağırlıklı bölüm için önemli iyileşme. 372 eski bağ kesilirken öncelikli "
        "bilgi ve aynı bölüm verisi korunuyor.",
        "Bu örnekte açık bir yanlış öneri yok. Ancak boş delta tek başına recall "
        "başarısı kanıtı değil: düzyazının bütün yeni lore'unun kapsandığı ayrıca ölçülmedi.",
        "Soul Serpent'in Rain'e verildiği veya alive durumu önceki graph'ta temsil "
        "edilmiyorsa eksik delta olabilir. Rün tekrarlarını bastırma hedefi tüm düzyazıyı "
        "susturmak anlamına gelmemeli; sonraki denetimde bu kapsama kontrol edilmeli."),
}
for n, (text, good, wrong, unsure) in manual.items():
    r = next(r for r in v2 if r["bolum"] == n)
    yaz(f"### Bölüm {n}\n\n**Metnin kurduğu:** {text}\n\n**Doğru:** {good}\n\n**Yanlış / eksik:** {wrong}\n\n**Tartışmalı:** {unsure}")
    yaz("**Aynı bölüm deterministik veri:**\n\n```text\n" + ("\n".join(r["deterministik_bilgi"]) or "(yok)") + "\n```")
    yaz("**Ham model deltası:**\n\n" + kod(r["model_deltasi"]))
    yaz("**Doğrulayıcı sonucu:**\n\n| Öneri | Sınıf | Karar |\n|---|---|---|")
    for q in r["degerlendirme"]["oneriler"]:
        x = q["veri"]
        label = " / ".join(str(x[k]) for k in ("ozne", "iliski", "nesne", "varlik", "anahtar", "deger", "ad_1", "ad_2", "ad") if k in x)
        yaz(f"| {q['tur']}: {label} | {q['sinif']} | {q['karar']} |")
    for q in r["degerlendirme"]["inceleme"]:
        yaz(f"| review: {q[0]} | {q[1]} | {q[2]} |")
    if not r["degerlendirme"]["oneriler"] and not r["degerlendirme"]["inceleme"]:
        yaz("| boş delta | — | yazım/review planı yok |")
yaz("## Planlanan bütün mutasyonlar için ek denetim")
yaz("Dört ilişki ve üç durum yazımı önerildi; **hiçbiri uygulanmadı**. 670'teki ters yön "
    "kesin hatadır. 162'de `Sunny oldurdu Harper` için seçilen düzyazı cümlesi bıçaklamayı "
    "kanıtlıyor, tek başına ölümü açıkça kanıtlamıyor; bölümdeki ayrı 'slain' rünü Harper'ın "
    "dead state'ini güçlü biçimde destekliyor. 313'te Lord of the Dead'in bedeninden çıkan "
    "parazitin öldürülmesiyle kişinin life status'u ayrılmalı. 381'de vassal clan için `grubu` "
    "etiketinin doğru ilişki sınıfı olup olmadığı gözden geçirilmeli. 394'te Leo Striker'ın "
    "Colosseum'da bulunması seçilen cümleyle açık biçimde destekleniyor.")
yaz("## 670 false-belief testi mi?")
yaz("**NO.** Bu sahnede okur düzeyinde önceki yanlış inancın düzeltilmesi yok. Sunny'nin "
    "kimliğini okur zaten biliyor; Effie'nin onu tanıması karaktere özel bilgidir. "
    "670'i false-belief örneği diye seçen özgün doğrulama-seti varsayımı yanlıştı.")
yaz("### Sonraki epistemik mini-test için adaylar — çalıştırılmadı")
yaz("Kaydedilmiş kaynaklar kalıp taramasıyla bulundu ve çevre cümleleri okundu. Bunlar "
    "doğrulanmış model başarıları değil, sonraki mini-test adaylarıdır; hiçbiri v2 model koşusuna eklenmedi.")
yaz("| Bölüm | Metindeki ayrım | Ne sınanabilir? |\n|---|---|---|\n"
    "| 412 | Kurtulanlar arkadaşlarının görsel yanılsama yapan bir yaratığa yenildiğini yanlış sanıyor; anlatı gerçek kopyalama yeteneğini açıklıyor. | `believed` ile anlatının düzelttiği bilgi; hayali otomatik kimlik merge olmadan. |\n"
    "| 431 | Bazı insanlar Ivory Tower'ın Tear'ın ortasında bulunduğuna ve ilk kopan ada olduğuna inanıyor. | Tarihsel konum iddiasının `believed` olarak korunması; NULL zaman ve tahmin yasağı. |\n"
    "| 685 | Sun Prince'in ruhunun metal colossus'ta bulunduğu halk inancı; Kai sentience/ceset yorumunda emin değil. | `believed` ile `uncertain` ayrımı ve akrabalık iddiasının kesinleştirilmemesi. Konum state yapılmamalı. |\n"
    "| 686 | Sisten gelen ses ve kaybolmalar önce söylenti; sonrasında araştırma ekibi gerçekten kayboluyor. | `rumor` → desteklenen gözlem ayrımı. Event/karakter bilgisi zorla graph'a yazılmamalı. |")
yaz("209'da 'ölü sanma' kalıbı var ama yanıt 'teknik olarak ölü' ve ontolojik ayrım içeriyor; "
    "temiz alive/dead kontrolü değil. 798'de ise annenin ölü olduğu doğrulanıyor, yanlış inanç "
    "düzeltilmiyor. Salt kalıp eşleşmesi bu ikisini iyi false-belief vakası yapmaz.")
yaz("## Maliyet ve çalışma süresi")
pre = json.loads((P / "preflight.json").read_text(encoding="utf-8"))
pre_cost = sum((r["olcum"].get("giris_tokeni",0)*.75+(r["olcum"].get("cikis_tokeni",0)+r["olcum"].get("dusunme_tokeni",0))*3.75)/1e6 for r in pre)
yaz(f"19 bölümlük ana koşu: **{m2['giris_tokeni']:,} giriş**, **{m2['cikis_tokeni']:,} yanıt**, "
    f"**{m2['dusunme_tokeni']:,} düşünme tokenı**. Bölüm işlem sürelerinin toplamı "
    f"**{sum(r['olcum']['sure_sn'] for r in v2):.2f} sn** (~7,7 dakika). "
    "Son çevrimdışı yeniden denetim bu süreden ayrıdır ve API maliyeti yaratmaz.")
yaz(f"Tahmin, projenin kayıtlı fiyat tablosunu kullanır: giriş **$0,75/M**, "
    f"yanıt+düşünme **$3,75/M**. Ana koşu **${m2['cost_usd_estimate']:.6f}** (~$0,385). "
    f"Structured-output ön kontrolündeki tamamlanmış tek ek çağrı **${pre_cost:.6f}**; "
    f"kayıtlı başarılı yanıtların toplam tahmini **${m2['cost_usd_estimate']+pre_cost:.6f}** (~$0,397). "
    "Bütçe hesabı düzeltildiğinde kesilen bir hazırlık çağrısı da vardır. İki 429 denemesi ve "
    "kesilen çağrının faturalanmış tokenları alınamadı; bu rakam sağlayıcı faturası veya tüm "
    "denemelerin kesin toplamı değildir. Canlı kullanım göstergesine bu izole koşu aktarılmadı.")
yaz("## Kabul kararı ve kalan iş")
yaz("**REPEAT VALIDATION.** Graph mimarisini yeniden tasarlamak gerekmiyor; structured output "
    "ve yazmasız güvenlik sınırları çalışıyor. Ancak tek bir ters yönün `işle` kabulü bile "
    "1–100'e geçmek için yeterince önemli bir doğruluk hatasıdır.")
yaz("Sonraki turda, yeni kronolojik backfill öncesinde:\n\n"
    "1. Öğretmen/öğrenci gibi yönlü ilişkilerin semantic rol denetimini ekle; 670'i negatif kontrol yap.\n"
    "2. Sıradan ad, unvan ve büyülü True Name ayrımını daha dar uygula; 691'deki çift alias/identity önerilerini denetle.\n"
    "3. 15/106 rün parser kapsamını ve state evidence özne bağlamını denetle; ilişki kanıt kurallarını genel olarak gevşetme.\n"
    "4. Review açıklamasının kanıtla gerçekten desteklendiğini doğrula; salt olay/karakter bilgisi review gürültüsünü sınırla.\n"
    "5. Dört epistemik aday için ayrı küçük testi raporla; mevcut sette diversity üretmek için confirmed olguları düşürme.\n"
    "6. Aynı 19 bölümlük karşılaştırmayı koru; 4.000 token bütçesini sırf kesilen satır sayısı büyüdü diye artırma.\n\n"
    "Bu maddeler yeni bir v3/mini-test kararı için raporlandı. **1–100 çalıştırılmadı ve otomatik başlatılmayacak.**")
yaz("## Testler ve dosyalar")
yaz("Son kodda **976 test geçti** (`python -m pytest tests -q`); bilgi-delta çekirdeğinin "
    "20 testi arasında kontrollü life status geçmişi, gelecek alias izolasyonu, same-chapter "
    "sayacının ayrılması, bilinmeyen varlıklar, desteklenmeyen state ve response schema "
    "bağlamının çeviriye sızmaması var. `git diff --check` temiz.")
yaz("- `v1.json`: özgün 19 v1 ham kayıt.\n- `v2.initial.json`: ilk v2 model çıktı/kararları.\n"
    "- `v2.json`: aynı ham yanıtlarla son doğrulayıcı sonuçları.\n- `v2.audit.json`: karşılaştırma, "
    "bölüm kaynakları, candidate taraması, DB parmak izleri ve v1 ham tekrar analizi.\n"
    "- `v2.model-audit.json`: sunucudaki ilk model koşusunun audit'i.\n"
    "- `provider_attempts.json`: aynı işlem kimliği altındaki 21 gerçek sağlayıcı denemesi.\n"
    "- `sources.json`, `candidate-sources.json`: elle incelenen kaynaklar.\n"
    "- `manifest.json`: kod ve ham yanıt SHA-256 özetleri.\n"
    "- `scripts/validation_v2.py`: tekrar çalıştırılabilir sabit-set koşucu; `--replay` API çağırmaz.")
metin = re.sub(r"(?m)(\|[^\n]*\|)\n\n(?=\|)", r"\1\n", "\n\n".join(out))
(P / "RAPOR.md").write_text(metin + "\n", encoding="utf-8")
files = ("app/core/bilgi_delta.py", "app/core/translate.py", "app/core/varlik_cikarim.py", "tests/test_bilgi_delta.py", "scripts/validation_v2.py")
manifest = {"model": a["model"], "versions": {"extractor": "2", "prompt": "2", "schema": "delta-2"},
            "chapters": a["chapters"], "raw_outputs_unchanged_on_replay": True,
            "code_sha256": {f: hashlib.sha256((KOK / f).read_bytes()).hexdigest() for f in files},
            "raw_response_sha256": {str(r["bolum"]): hashlib.sha256(r["ham_yanit"].encode()).hexdigest() for r in v2}}
(P / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"report": str(P / "RAPOR.md"), "metrics": m2, "v1_reanalysis": retro}, ensure_ascii=False, indent=1))
