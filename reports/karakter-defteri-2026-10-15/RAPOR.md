# Karakter defteri — pilot, tam doldurma ve Faz 3 ölçümü (2026-10-15)

Romandan metin içermez. Ham veriler (çeviriler, hakem yanıtları) git dışındadır.

## Özet

- Defter Shadow Slave'in 990 bölümünü 9,60 $ ve ~42 dakikada işledi (sunucuda veritabanı
  kopyası; canlı veritabanı değişmedi).
- Hitap ölçütünde hata bulundu ve düzeltildi (`98086a1`): gruba konuşmadaki çoğul "siz",
  tekil çiftin "sen"iyle çelişki sayılıyordu. Eski ölçütün işaretlerinin ~%63'ü bu yanlış
  alarmdı. Canlı çevirilerin genel hitap tutarsızlığı %9,8 değil **%4,3**.
- Düzeltilmiş ölçütle çeviri kartı (`CEVIRI_GRAFIK=1`, kol J) hitap tutarsızlığını
  **%14,5'ten %6,0'a** indirdi (göreli %59; plandaki eşik ≥%30). Anlam, akıcılık,
  tutarlılık, sözlük sızıntısı ve uzunlukta gürültüden büyük kayıp yok.
- Kartlı istemde 3.8 Flash 30 bölümden birini (596) her denemede telif gerekçesiyle reddetti;
  kartsız istem aynı bölümü 5/5 çevirdi. Çözüm (`translate._translate_chunk`): kartlı istem ret
  alırsa parça önce aynı modelde KARTSIZ yeniden denenir. Gerçek modelle 596 böylece çevrildi.
  Ayrıntı: 5. bölüm.
- Plandaki canlıya açma koşullarının hepsi sağlandı. Canlıya açma kullanıcı kararıdır.

## 1. Pilot (20 bölüm, sunucu DB kopyası)

`defter-v2` istemi, `vertex/gemini-3.8-flash`, düşünme `low`, çıkış tavanı 16k.

| Ölçü | Sonuç | Eşik |
|---|---|---|
| Maliyet | 0,0121 $/bölüm | ≤0,02 $ |
| Süre | ~11 sn/bölüm | — |
| Bağ kesinliği (elle) | 38/40 | ≥%90 |
| Hitap konuşan/muhatap (elle) | ~60/60 | ≥%85 |
| Takma ad kesinliği | 3/3 | ≥%90 |
| Geçersiz iddia oranı | ~%5 | <%25 |

Varsayılan düşünme ayarı 8000 tavanında bölümleri yarıda kesiyordu; düşük düşünme ve 16k
tavanla giderildi (`5000cf3`).

## 2. Tam doldurma

990 bölüm, 9,60 $, ~42 dk. 17.650 varlık, 1.767 bağ, 3.679 hitap kaydı; 328 hitap çifti,
122'si kararlı (≥3 kayıt, ≥%80 uyum). Sözlüğe 102 inceleme önerisi: takma ad 58, karşılık
farkı 16, sıradan sözcük 28 (`a8ea07f` küçük harfli cins sözcükleri çıkardıktan sonra).
Öne çıkan örnekler: kayıtta "Oyuk Dağı" olan Hollow Mountain çevirilerde 32/32 "Kovan
Dağları"; İngilizce bırakılan Shadow Saint çevirilerde 22/22 "Gölge Aziz".

## 3. Hitap ölçütü düzeltmesi

Ölçüt (`karakter_defteri.hitap_uyumu`), bir çevirinin her hitap paragrafını önceki
bölümlerin kararlı (konuşan → muhatap) tablosuyla karşılaştırır. Defter gruba konuşmayı
`cogul` diye ayrı işaretliyor, ölçüt bu işareti okumuyordu.

- Elle denetim (eski ölçüt, 30 rastgele uyumsuzluk): ~19 yanlış alarm (gruba hitap, "you
  guys", "you all"), 2 kesin gerçek tutarsızlık, 9 bağlamsız karar verilemez.
- Doğrulama: işaretlenen paragrafların defter kayıtları `cogul` çıktı.
- Düzeltme: `cogul` ve `belirsiz` kayıtlar ile gruba konuşulan paragraf sayılmaz.
- Elle denetim (yeni ölçüt, 30 rastgele uyumsuzluk): 13 gerçek tutarsızlık (tekil muhatap,
  önceki kullanımla çelişen biçim), 2 kesin yanlış alarm (defterin `cogul` diye işaretlemediği
  "citizens"), 15 bağlamsız karar verilemez. Karar verilebilenlerde isabet ~%87.
- Canlı çeviriler (≥100. bölüm, 891 bölüm): 1.942 değerlendirilen hitabın 84'ü tutarsız, %4,3.

`hitap_sapmalari` (künyedeki sonradan denetim) zaten yalnız `sen`/`siz` kayıtlarına
bakıyordu; bu hatadan etkilenmedi.

## 4. Faz 3 A/B: çeviri kartı

Örneklem: 30 SS bölümü (eski ölçüte göre en sapmalı 20 + rastgele 10), 3.8 Flash.
Kollar: H (canlıya yakın yol), H2 (H'nin tekrarı, gürültü tabanı), J (H + kart). J'nin 596'sı
ret yedeği eklendikten sonra yeniden çevrildi; aşağıdaki tablolar 30 bölümün hepsini kapsar.

### Hedefli hitap ölçütü (düzeltilmiş)

| Kol | Değerlendirilen | Tutarsız | Oran |
|---|---:|---:|---:|
| H | 172 | 21 | %12,2 |
| H2 | 172 | 28 | %16,3 |
| J (kart) | 170 | 10 | %5,9 |

H ve H2 ortalamasına (%14,2) göre göreli düşüş %58. J ile H+H2 havuzu arasında iki oran
z-testi p≈0,005; J ile yalnız H arasında p≈0,05. Yeni ölçütün J'de işaretlediği örnekler
elle denetimde çoğunlukla "bağlamsız karar verilemez" sınıfındaydı; gerçek tutarsızlıkların
çoğu H/H2'deydi.

Gruba konuşan paragraflarda kart yanlış tekil "sen"e itmiyor: yalnız "sen" taşıyan gruba
hitap H 2, H2 1, J 3 (her kolda ~76 paragraf).

Eski (hatalı) ölçütle aynı veri: H %33,8, H2 %36,8, J %28,8 (göreli ~%18).

### Kör hakem (gemini-2.5-pro, paragraf düzeyi, işaret testi)

| Çift (a:b) | Boyut | a | b | eşit | p |
|---|---|---:|---:|---:|---:|
| J:H | anlam | 206 | 198 | 404 | 0,73 |
| J:H | akıcılık | 137 | 103 | 568 | 0,03 |
| J:H | tutarlılık | 26 | 40 | 742 | 0,11 |
| H2:H | anlam | 200 | 229 | 418 | 0,18 |
| H2:H | akıcılık | 109 | 147 | 591 | 0,02 |
| H2:H | tutarlılık | 17 | 34 | 796 | 0,02 |

Aynı ayarın iki koşusu (H2:H) bile akıcılık ve tutarlılıkta "anlamlı" fark veriyor; hakem
gürültüsü yüksek. J:H farkları bu tabanın içinde ya da J lehine (akıcılık). Tutarlılıkta
J:H (26–40) ile H2:H (17–34) aynı yönde ve büyüklükte; kart kaynaklı kayıp görülmüyor.
LLM hakemi hitap hatasını çoğunlukla kaçırır (arXiv 2412.01340); hitap kararı yukarıdaki
hedefli ölçüte dayanır.

### Sözlük sızıntısı ve uzunluk (30 bölüm)

| Kol | Sözlük taşması | TR/EN uzunluk | Hizasız |
|---|---:|---:|---:|
| H | 7 / 251 | 0,976 | 0 |
| H2 | 8 / 251 | 0,978 | 0 |
| J | 6 / 251 | 0,978 | 0 |

### Canlıya açma kuralı (plan)

| Koşul | Sonuç |
|---|---|
| Hitap sapması göreli ≥%30 düşmeli | Sağlandı (%58) |
| Anlam/tutarlılıkta H/H2 gürültüsünden büyük kayıp yok | Sağlandı |
| Sözlük sızıntısı ve uzunluk gerilemesin | Sağlandı |
| Başlangıç sapması <%3 ise sor | Genel %4,3; sorulması gerekmez |
| (Ek) Çeviri başarısızlığı artmasın | Ret yedeğiyle sağlandı (5. bölüm) |

## 5. Telif reddi (J-596)

Ham yanıt: model "telif hakkıyla korunan bu eserin satır satır çevirisini sağlayamıyorum"
deyip bölümün özetini veriyor. Kartsız H ve H2 aynı bölümü ilk denemede çevirdi. Kart bu
bölümde ad eşleşmeleri (takma adlar), hitap çiftleri ve "önceki bölümlerden çıkarıldı / N
kayıt, son bölüm M" bilgisi taşıyordu; bu bağlamın modelin eseri tanımasını kolaylaştırması
olası bir açıklamadır, kanıtlanmadı.

Canlıda zincir 3.8 → 3.6 → 3.5 → … olduğundan ret alt modele inerek çevrilebilir; ama bu
daha düşük kaliteli modelle çeviri demektir ve aynı ret alt modellerde de olabilir.

Denemeler (aynı bölüm, 3.8 Flash; her koşu aynı modelde 2 deneme):

| İstem | Başarılı koşu |
|---|---:|
| Kartsız (H) | 5/5 |
| Tam kart | 0/4 |
| Tam kart, nötr başlık, sayaçlar çıkarılmış | 0/1 |
| Yalnız hitap satırları | 2/3 |

Ret kartla ilişkili ve kart biçimini sadeleştirmek tek başına yetmiyor. Bu yüzden kart
içeriği değiştirilmedi (ölçülen kazanç bu kartla); onun yerine ret yedeği eklendi: kartlı
istem ret alırsa parça önce aynı modelde kartsız yeniden denenir, o da ret alırsa mevcut
zincir kuralı sürer. Kartsız istem bayrak kapalıyken gönderilen istemle aynıdır. Yeni kodla
gerçek model J-596'yı çevirdi (83,8 sn). Bedeli: ret alan parçada boşa giden bir çağrı.

## 6. Sınırlılıklar

- Örneklem tek kitap (Shadow Slave), 29–30 bölüm; seçim eski ölçütle sapmalı bölümlere ağırlık verdi.
- Hitap ölçütü yalnız tek biçim taşıyan paragrafları sayar; konuşan/muhatap defterin model
  çıkarımıdır. Elle denetimde örneklerin yarısı bağlamsız karara bağlanamadı.
- Hakem tek model; H2:H farkları hakem gürültüsünün büyük olduğunu gösteriyor.
