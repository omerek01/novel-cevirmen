# Bağlam ve anlam araştırması — 2026-10-11

Amaç: İngilizce→Türkçe web roman çevirisinde bağlam kullanımını (bölümler arası
tutarlılık, gönderge, hitap) ve anlam sadakatini ölçerek iyileştirmek. Kitaplar telifli
olduğu için bu raporda romanlardan metin yoktur; yalnız yöntem, sayı ve hata türü vardır.
Ham deney verisi (çeviriler) takip dışı `reports/anlam-kiyas-2026-10-11/` altındadır.

## Özet

1. **Bağlam müdahaleleri ölçülebilir kazanç vermedi** (bölüm 5). Analiz özeti, üslup
   talimatı ve bölümler arası tutarlılık belleği denendi; hiçbiri anlamda ya da akışta
   ölçülebilir bir fark yaratmadı. Ayarlar arasındaki farklar, aynı ayarın iki koşusu
   arasındaki gürültü kadar.
2. **Asıl kaldıraç model** (bölüm 6.1). Eski yolda 3.6 Flash yerine 3.8 Flash kullanılınca:
   - anlamda 103'e 68 (p 0,009),
   - akıcılıkta 75'e 38 (p 0,001),
   - bölüm başına akış kopukluğu 1,81'den 1,00'a.

   Kör elle kontrol de aynı yönde. Canlı ayar 10 Ekim akşamından beri 3.6. Kullanıcının
   "daha önce böyle değildi" şikâyeti bu geçişe denk geliyor.
3. **Sözlük, anlam hatalarının belirlenimci bir kaynağı** (bölüm 7).
   - Yanlış anlamlı kayıtlar her koşuda aynı hatayı üretiyor ("Divinity" için "İlahiyat").
   - Sıradan kelimeye büyük harfli terim basılıyor ("zırh" yerine "Zırhları"). Bu her kolda
     113 geçişin 7–18'inde oldu.
   - Yeni `SOZLUK_SIRADAN` işareti bunu 1'e indirdi; anlam ve akış kaybı yok (bölüm 6.3).
4. **Kalite katmanı akıcılığı anlamlı biçimde iyileştiriyor** (48'e 28). Anlamda yalnız
   eğilim var (bölüm 6.2).
5. **Öneriler** (bölüm 8):
   - modeli 3.8 Flash'a geri al,
   - `SOZLUK_SIRADAN`'ı aç,
   - kalite katmanını tut,
   - analiz ve belleği kapalı bırak,
   - sözlük inceleme listesindeki öncelikli kayıtlara karar ver.

## 1. Literatür (doğrulanan kaynaklar)

| Çalışma | Bulgu | Bizim için anlamı |
|---|---|---|
| Karpinska ve Iyyer, 2023 ([arXiv 2304.03245](https://arxiv.org/abs/2304.03245)) | Paragraf/belge düzeyinde çeviri, cümle düzeyinden daha iyi ve üslup açısından daha tutarlı; ağır hatalar yine de kalıyor | Bölümü tek istekte çevirmemiz doğru; bölüm İÇİ bağlam zaten var |
| DelTA, ICLR 2025 ([arXiv 2410.08143](https://arxiv.org/abs/2410.08143)) | Çok katmanlı bellek: özel ad kaydı, iki dilli özet, uzun/kısa vadeli kaynak→çeviri çiftleri. Ablasyonda kısa vadeli iki dilli bellek kaliteyi, özel ad kaydı tutarlılığı en çok artırdı | Sözlüğümüz özel ad kaydının karşılığı; eksik olan bölümler ARASI iki dilli bellek |
| Choudhary vd., EMNLP 2025 Findings ([ACL Anthology](https://aclanthology.org/2025.findings-emnlp.1324/)) | Kaynağa modelin kendi önceki çevirileri eklenince hitap, zamir ve sözcük tutarlılığı referanssız artıyor | Önceki bölümlerin bizim çevirilerimiz bağlam olarak kullanılabilir |
| Mohammed ve Niculae, MT Summit 2025 ([arXiv 2410.14391](https://arxiv.org/abs/2410.14391)) | LLM'lerin belge düzeyi kazancı zamir çevirisine yansımıyor | Gönderge/zamir hataları ayrı ölçülmeli |
| Briakou vd., WMT 2024 ([arXiv 2409.06790](https://arxiv.org/abs/2409.06790)) | Araştır→taslak→düzelt→son okuma adımları kaliteyi artırdı (Gemini 1.5 Pro) | Bizim "analiz" adımımızın dayanağı |
| "Please Translate Again", 2025 ([arXiv 2506.04521](https://arxiv.org/abs/2506.04521)) | Kazancın açık ayrıştırmadan geldiğine dair net kanıt yok; basit "yeniden çevir/düzelt" adım adım istemi geçti | Analiz adımının faydası varsayılmamalı, ölçülmeli |
| Belge düzeyi edebi çeviride düzeltme, 2026 ([arXiv 2605.13368](https://arxiv.org/abs/2605.13368)) | Düzeltme turu akıcılık/üslup/terminolojiyi iyileştiriyor, anlam doğruluğuna katkısı sınırlı; basit genel düzeltme istemi hataya özel istemleri geçti | Kalite onarımımız anlam hatası için tek başına yeterli sayılmamalı |
| Bağlama duyarlı çeviride akıl yürütme, 2025 ([arXiv 2510.18077](https://arxiv.org/abs/2510.18077)) | Akıl yürütme güçlü modellerde gönderge/bağdaşıklık sonucunu daha çok artırıyor | Gemini'de düşünmenin açık tutulması (proje kararı) bununla uyumlu |
| Kalite tahminli seçim, 2025 ([arXiv 2510.08870](https://arxiv.org/abs/2510.08870)) | Birden çok aday üretip kalite ölçütüyle seçmek belge düzeyinde iki adayla bile kazanç verdi | Anlam için en güçlü kanıtlı yöntem; maliyeti iki kat çeviri |

## 2. Canlı veride gözlenen bağlam boşluğu

`shadow-slave` 850–967 hizalı paragraflarında (yalnız sayım):

- Askerî rütbe `Captain`: 64 yerde "Yüzbaşı", 5 yerde "Kaptan".
- Hitap `sir`: 54 paragrafın 48'inde "efendim"; arada "yüzbaşım", "komutanım", "kaptanım".
- Bu sözcükler sıradan sözcük sayıldığı için sözlükte yok; model her bölümde yeniden karar veriyor.

## 3. Yapılanlar

1. **Bozuk JSON kurtarma düzeltmesi** (`a9dc40b`): yalnız-çeviri biçiminde bozuk yanıt
   kurtarılırken JSON kapanışı son paragrafa yapışıyordu (2026-10-10 deneyinde görüldü).
2. **Tutarlılık belleği** (`74dbe00`, `CEVIRI_BELLEK`, varsayılan kapalı): önceki 30 bölümün
   hizalı paragraflarından bu bölümdeki ad ve hitap/rütbe sözcüklerini taşıyan en fazla 10
   kısa çift + önceki bölümün son üç çifti. Ek model çağrısı yok; istem bölüm başına ~5–7 bin
   karakter büyüyor.
3. **Üslup bayrağı** (`CEVIRI_STIL`): analiz özetini tutup kısa üslup talimatını kaldırır.
4. **Kör hakemli kıyas aracı** (`1f4c22b`, `scripts/anlam_kiyas.py`). Sonradan eklenenler:
   - bölüm düzeyi akış hakemi (`1475b52`),
   - Faz 2 kolları (`ddb7c99`),
   - hakem yanıtı çözücü düzeltmeleri (`3512439`, `87f1cfd`).
5. **Sözlük sıradan kelime işareti** (`c4ac4cf`, `SOZLUK_SIRADAN`, varsayılan kapalı).
   Büyük harfli bir kayıt parçada cümle ortasında hiç büyük harfle geçmiyorsa, sözlük satırına
   "sıradan kelime olabilir" işareti konur. Kayıt istemden atılmaz; karar bağlamla modele
   kalır. Bayrak kapalıyken prompt bayt bayt aynıdır.

## 4. Deney

Shadow Slave'in farklı dönemlerinden 8 bölüm (150, 300, 450, 600, 720, 840, 905, 950); model
`vertex/gemini-3.6-flash`; kalite onarımı bütün kollarda kapalı. Kollar:

| Kol | Analiz özeti | Üslup talimatı | Tutarlılık belleği |
|---|---|---|---|
| A (deney başındaki canlı yol) | var | var | yok |
| A2 (A tekrarı, gürültü tabanı) | var | var | yok |
| B (eski yol; 2026-10-11'den beri canlı) | yok | — | yok |
| C | var | yok | yok |
| D | yok | — | var |
| E | var | yok | var |

İki hakem kullanıldı, ikisi de `gemini-2.5-pro`:

- **Paragraf hakemi:** yalnız iki kolun belirgin ayrıştığı paragrafları görür. X/Y sırası
  rastgeledir; anlam, akıcılık ve tutarlılık ayrı oylanır.
- **Bölüm hakemi:** kullanıcının "akış kopuk" şikâyetini ölçmek için eklendi. İki çeviriyi
  baştan sona bütün olarak okur ve her çeviri için en fazla 3 somut akış kopukluğu yazar.
  Aynı karşılaştırma X/Y yer değiştirilerek iki kez sorulur.

Bütün çiftlerde işaret testi kullanıldı; eşitlikler teste katılmadı.

## 5. Sonuçlar — Faz 1: bağlam müdahaleleri

**Kısa sonuç:** Analiz özeti, üslup talimatı ve tutarlılık belleğinin hiçbiri anlamda ya da
akışta ölçülebilir bir iyileşme getirmedi. Kollar arasındaki farklar, aynı ayarın iki ayrı
koşusu (A ile A2) arasındaki farktan büyük değil.

### 5.1 Paragraf hakemi

"a" ve "b" sütunları, çiftteki ilk ve ikinci kolun kaç paragrafta kazandığını gösterir.

| Çift (a:b) | Anlam a / b / eşit | p | Akıcılık a / b / eşit | p | Tutarlılık a / b / eşit | p |
|---|---|---:|---|---:|---|---:|
| B:A (eski yol : analiz) | 60 / 55 / 96 | 0,71 | 37 / 38 / 136 | 1,00 | 7 / 9 / 195 | 0,80 |
| C:A (üslupsuz : üsluplu) | 57 / 67 / 93 | 0,42 | 33 / 27 / 157 | 0,52 | 10 / 13 / 194 | 0,68 |
| D:B (bellek : eski yol) | 59 / 70 / 98 | 0,38 | 31 / 28 / 168 | 0,80 | 12 / 14 / 201 | 0,85 |
| E:C (bellek : belleksiz, analizli) | 60 / 71 / 92 | 0,38 | 35 / 42 / 146 | 0,49 | 11 / 11 / 201 | 1,00 |
| **A2:A (aynı ayar iki kez)** | **50 / 62 / 101** | **0,30** | 35 / 42 / 136 | 0,49 | 9 / 10 / 194 | 1,00 |

- Bütün çiftler 8 bölümün tamamını kapsıyor. B:A'da 600. bölüm, E:C'de 905. bölüm ilk
  koşuda üç denemede de düşmüştü. Sonradan kaydedilen reddedilmiş bir yanıt nedeni gösterdi:
  hakem yanıtı kimi zaman tek elemanlı bir listeye sarılı geliyor. İlk düşüşler bu biçimle
  uyumlu ama ham yanıtları saklanmadığı için kesin değil. Çözücü `87f1cfd` ile düzeltildi.
  İki bölüm aynı maddelerle yeniden yargılandı ve bu kez geçerli yanıt geldi.
- Gürültü tabanı satırı (A2:A) belirleyici. Aynı ayar iki kez koşturulduğunda anlamda
  50'ye 62 fark çıkıyor. Ayarlar arasındaki farklar da bu büyüklükte.
- Bölüm bazında oynaklık büyük. Örneğin A, 600. bölümde hem A2'yi (16'ya 9) hem C'yi (16'ya
  3) yendi. Buna karşılık A2, 450 ve 840. bölümlerde A'yı yendi. Yani aynı ayar bir bölümde
  iyi, ötekinde kötü çıkabiliyor.

### 5.2 Bölüm hakemi (akış)

- **Konum yanlılığı çok güçlü.** Akış sorusunda hakem 80 kararın 65'inde önce gösterilen
  çeviriyi seçti (%81). İki yönün aynı kolu seçtiği karşılaştırma 40'ta yalnız 11.
  Bu yüzden "kazanan" kararları kullanılmadı.
- **Kopukluk sayısı konumdan bağımsızdır,** çünkü iki yönün ortalaması alınır. Bu sayı
  kullanıldı. Bölüm başına ortalama kopukluk (kolun girdiği bütün karşılaştırmalar):

| Kol | A | A2 | B | C | D | E |
|---|---:|---:|---:|---:|---:|---:|
| Kopukluk / bölüm | 1,42 | 1,50 | 1,34 | 1,16 | 2,00 | 1,44 |

Aynı çift içinde, bölüm bölüm "hangisi daha az kopuk":

| Çift | a daha az | b daha az | eşit | p |
|---|---:|---:|---:|---:|
| B:A | 6 | 2 | 0 | 0,29 |
| C:A | 5 | 2 | 1 | 0,45 |
| D:B | 2 | 5 | 1 | 0,45 |
| E:C | 3 | 4 | 1 | 1,00 |
| A2:A | 2 | 3 | 3 | 1,00 |

Hiçbiri anlamlı değil. Yine de iki eğilim not edilmeli:

- Eski yol (B), analizli yoldan (A) 8 bölümün 6'sında daha az kopuktu. Analizin akışı
  iyileştirdiğine dair hiçbir işaret yok.
- Bellekli kol (D), 5 bölümde eski yoldan daha kopuktu.

### 5.3 Hakemler ne kadar güvenilir?

- **Paragraf hakeminde konum yanlılığı küçük.** Kararlı oylarda önce gösterilenin payı
  anlamda %54, akıcılıkta %50, tutarlılıkta %59.
- **Elle kontrol (B:A, anlam boyutu, 8 rastgele kararlı madde).** Hakemin seçtiği yöne
  8'inde de katıldım. Ancak:
  - 3'ünde fark hafifti, daha çok üslup farkıydı.
  - 1'inde bir yazım hatasını "anlam" boyutunda saymıştı.

  Sonuç olarak hakem tek tek kararlarda isabetli. Kollar arasındaki farkın kaynağı ayarlar
  değil, koşudan koşuya değişen rastlantısal çeviri farkı.
- **Bölüm hakeminin kopukluk notlarından 6'sını kaynakla karşılaştırdım; altısı da
  gerçekti:**
  - uçan gemi için "su üstünde tutmak",
  - kuşatma silahının mermisi için "cıvata",
  - bir niteliğin yanlış adı,
  - İngilizce bırakılmış bir cümle sonu,
  - cümle ortasında büyük harfli sıradan kelime,
  - ordu rütbesi için "Kaptan".

### 5.4 Akışı ne bozuyor?

Bölüm hakemi 6 kolda toplam 227 not yazdı. Bu notlar 107 ayrı paragrafa düşüyor. Aşağıdaki
dağılım anahtar kelimeyle yapılmış kaba bir sınıflamadır:

| Tür | Not | Pay |
|---|---:|---:|
| Doğallık / sözcük seçimi (diğer) | 90 | %40 |
| Sahneye aykırı sözcük anlamı (uçan gemi "su üstünde", "cıvata") | 41 | %18 |
| Yazım / dilbilgisi | 30 | %13 |
| Kişi, hitap, zamir, tekil-çoğul (sen/siz geçişi, 3. → 2. şahıs) | 20 | %9 |
| Büyük harf / sözlük taşması | 18 | %8 |
| Terim ve ad tutarsızlığı | 14 | %6 |
| Kelimesi kelimesine / deyim | 8 | %4 |
| Çevrilmemiş ya da atlanmış | 6 | %3 |

Kopukluk yerlerinin 14'ü üç ya da daha çok kolda ortak. Ayrı ayarlarla, birbirinden habersiz
koşan kollar aynı paragrafta aynı hatayı yapıyor. Bu, hatanın bağlam eksikliğinden değil
modelin o ifadedeki varsayılan seçiminden ya da sözlükten geldiğini gösterir. Bağlam
müdahalelerinin fark yaratmaması da bununla tutarlı.

## 6. Sonuçlar — Faz 2: model, kalite katmanı, sözlük işareti

Faz 1'in sonucu, hataların bağlamdan çok modelden ve sözlükten geldiğini gösterdi. Faz 2 bu
üç kaldıracı eski yola (B) karşı tek değişkenle ölçtü. Bölümler, sözlük ve hakemler Faz 1 ile
aynı.

| Kol | Eski yola (B) eklenen tek değişiklik | Süre medyanı |
|---|---|---:|
| F | çeviri modeli `vertex/gemini-3.8-flash` (B: 3.6) | 33 sn (B: 38) |
| G | canlıdaki kalite katmanı (`CEVIRI_KALITE=1`) | 70 sn |
| H | sözlükte sıradan kelime işareti (`SOZLUK_SIRADAN=1`, bölüm 7.2) | 34 sn |

Bütün kollar 8/8 hizalı çıktı. Hiçbirinde sözlük ihlali ya da İngilizce kalıntı ölçülmedi.
Uzunluk oranları 0,959–0,964.

### 6.1 F: 3.8 Flash — tek anlamlı kazanç

| | Anlam F / B / eşit | p | Akıcılık F / B / eşit | p | Tutarlılık F / B / eşit | p |
|---|---|---:|---|---:|---|---:|
| F:B (8 bölüm) | **103 / 68** / 130 | **0,009** | **75 / 38** / 188 | **0,001** | 10 / 23 / 268 | 0,035 |

- **Paragraf hakemi:** F, anlamda 8 bölümün 6'sında önde. 905'te eşit, 600'de geride
  (7'ye 14). Akıcılıkta 8 bölümün 7'sinde önde.
- **Tutarlılıkta B önde.** B'nin 23 kazancının çoğu 600. bölümden geliyor. Gerekçe çoğunlukla
  B'nin sıradan kelimelere bastığı büyük harfli terimlerin ("Yarık", "Ruh Özü") "tutarlı"
  sayılması. Bu, hakemin bilinen yanlılığıdır (bölüm 6.3). Kalan birkaçında hakem B'nin
  kendi içinde tutarlı ama yanlış seçimlerini ödüllendirdi: "phalanx" için "kemik boğumu",
  ordu rütbesi için "Kaptan".
- **Bölüm hakemi:** bölüm başına kopukluk F'de 1,00, B'de 1,81. F 8 bölümün 5'inde daha az
  kopuk, B 2'sinde (1 eşit).
  - İki yönün aynı kolu seçtiği akış kararlarında F 3, B 0.
  - Konum yanlılığı bu kadar güçlüyken (bölüm 5.2), F ikinci gösterildiğinde de seçildi.
- **Kör elle kontrol:** hangi çevirinin hangi kola ait olduğunu bilmeden 13 madde
  değerlendirildi. 2'si eşit bulundu; kalan 11 kararlı maddenin 8'inde F seçildi.
  Hakemle 11'in 9'unda aynı yöndeyim. Hakemin kendi model ailesinin yeni sürümünü
  kayırdığına dair işaret yok.
- **Maliyet ve süre:** iki model aynı fiyat sınıfında (uygulamadaki not: ~0,032 $/bölüm).
  F bu koşuda daha yavaş değildi (33'e 38 sn). Ancak 10 Ekim kalite kıyasında 3.8 biraz daha
  yavaş çıkmıştı (48'e 39 sn). Süre farkı koşudan koşuya değişiyor.

**Canlıdaki karşılığı:** canlı model ayarı (`settings.ceviri_modeli`) şu an
`vertex/gemini-3.6-flash`. Shadow Slave'de bölümler şöyle çevrilmiş:

- 950–960 (9–10 Ekim sabahı): 3.8 Flash.
- 961–969 (10 Ekim akşamından itibaren): 3.6.

Kullanıcının 968–969'da "daha önce böyle değildi" şikâyeti bu geçişle aynı zamana denk
geliyor. Aynı günlerde analiz de açıktı, ama Faz 1'de analizin etkisi ölçülemeyecek kadar
küçük çıktı.

### 6.2 G: kalite katmanı — akıcılıkta kazanç, anlamda eğilim

| | Anlam G / B / eşit | p | Akıcılık G / B / eşit | p | Tutarlılık | p |
|---|---|---:|---|---:|---|---:|
| G:B (8 bölüm) | 72 / 59 / 90 | 0,29 | **48 / 28** / 145 | **0,029** | 7 / 6 / 208 | 1,00 |

- Akıcılık kazancı anlamlı. Anlam kazancı anlamlı değil.
- Bölüm hakemi: kopukluk G'de 1,25, B'de 1,44. G 3 bölümde, B 4 bölümde daha az kopuk.
- Literatürle uyumlu bir tablo: düzeltme turu akıcılığı iyileştiriyor, anlam doğruluğuna
  katkısı sınırlı (bölüm 1, 2026 çalışması).
- Bedeli: süre medyanı 38 sn'den 70 sn'ye çıkıyor.
- Taşmayı çözmüyor: G'de de 113 geçişin 9'u taştı.

### 6.3 H: sıradan kelime işareti — taşmayı kesiyor, anlamı bozmuyor

| Ölçü | H | B |
|---|---:|---:|
| Sözlük taşması (113 küçük harfli geçiş) | **1** | 18 |
| Diğer kollarda taşma aralığı | — | 7–18 |
| Paragraf hakemi, anlam (H / B / eşit) | 58 / 68 / 88 (p 0,42) | |
| Paragraf hakemi, akıcılık | 31 / 39 / 144 (p 0,40) | |
| Bölüm hakemi, kopukluk / bölüm | 1,38 | 1,50 |
| Bölüm hakeminin "gereksiz büyük harf" notu | 1 | 5 |
| Sözlük ihlali / İngilizce kalıntı / hizasız | 0 / 0 / 0 | 0 / 0 / 0 |

- **Taşma 18'den 1'e indi.** Kalan tekinde ("not really" → "Pek Sayılmaz") kayıt işaretliydi;
  model işarete rağmen terimi büyük harfle yazdı. İşaret olasılığı düşürüyor, sıfırlamıyor.
- **Hiyerarşi adlarına dokunmadı.** Küçük harfli sınıf adlarının 8 geçişinin 7'si ("monster",
  "tyrant", "demon") H'de de B ile aynı karşılık ve yazımla çevrildi. Ayrılan tek geçiş
  "beast" kaydına aitti; bu kaydın kaynağı küçük harfli olduğu için işaretin kapsamı dışında,
  yani fark rastlantısal. Bu sekiz bölümde rütbeli kullanım ("Fallen monster") yok. Canlı
  veride de bu kullanım bütün kitapta yalnız 21 bölümde geçiyor; ayrıca ölçülmedi.
- **Paragraf hakemi farkı görmüyor, ve bunun bir nedeni var.** Hakem notlarında sıradan
  kelimeye basılmış büyük harfli terim çoğu kez "önceki çevirilerle tutarlı" diye
  ödüllendirildi:
  - "Yarık"ı tutarlı yazmış,
  - oyun terimi olan "Beceri"yi büyük harfle yazmış.

  Oysa sözlüğün kendi doğrulama aracı ikisini de sıradan sözcük olarak tanımış: `Rift`'i
  "sorunlu" saymış (bölüm 7.3), `Skill`'i "genel sözcük" notuyla geçirmiş.
- **Bütün bölümü okuyan hakem aynı büyük harfleri akış kopukluğu saydı:** B'de 5 not, H'de 1.
- **Hakemin kendi sözcük bilgisi de kusursuz değil.** Bir notta kuşatma silahının mermisi
  için "cıvata"yı doğru saydı.

## 7. Sözlük kaynaklı anlam hataları

Deneyin en net bulgusu bağlam değil sözlükle ilgili. Sözlük istemde kuraldır: hatalı bir
kayıt her kolda, her koşuda ve kitabın her bölümünde aynı hatayı üretir.

### 7.1 Yanlış anlamlı kayıtlar

- `Ember of Divinity -> İlahiyat Koruğu` kaydını 6 kolun 6'sı da aynen kullandı.
  - "İlahiyat" teoloji demektir; "Divinity" ise tanrısallık ya da ilahilik.
  - "Koruk" olgunlaşmamış üzümdür; doğru sözcük "kor" olmalıydı.
  - Aynı bölümdeki küçük harfli açıklamada kayıt yine uygulandı ve anlamsız bir imge çıktı.
  - Aynı aileden `Flame / Mark / Spark of Divinity` kayıtlarının hepsi "İlahiyat" ile kurulmuş.
- Sözlüğün kendi doğrulama aracı (`sozluk_dogrula.py`) bu dört kayıttan yalnız ikisini
  işaretlemiş: biri sorunlu, biri incelemede. Öbür ikisi "geçti". Araç ücretsiz modelle
  çalıştığı için tutarsız.
- Aynı sınıftan bir örnek daha: `Hollow -> Kovan` (araç bunu "sorunlu" diye işaretlemiş:
  "kovan" arı ya da mermi kovanıdır).

### 7.2 Sıradan kelimeye büyük harfli terim basılması (sözlük taşması)

`Armor -> Zırh`, `Hope -> Umut` gibi Türkçe karşılıklı kayıtlar kaynakta küçük harfle, yani
sıradan kelime olarak geçtiğinde de isteme girer. Bu bilinçli bir tasarım:
`_terim_metinde`, hiyerarşi adlarını korumak için küçük harfli geçişi de sayar. İstemdeki
"BİREBİR kullan" kuralı ise modeli sıradan kelimeye büyük harfli terimi basmaya itiyor:

- "zırh" yerine "Zırhları",
- "umut" yerine "Umut'u",
- "seven chains" için "Yediler zincir",
- "skill" için "Beceri'siyle".

| Kol | A | A2 | B | C | D | E | F (3.8) | G (kalite) | **H (işaret)** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Taşan / küçük harfli geçiş (8 bölüm) | 9/113 | 15/113 | 18/113 | 9/113 | 7/113 | 12/113 | 8/113 | 9/113 | **1/113** |

- Sorun bağlam ayarından, modelden (F) ve kalite katmanından (G) bağımsız. Yalnız sözlük
  satırını işaretleyen H onu kesiyor (bölüm 6.3).
- Ölçüt belirlenimci ve kaba: "kaynakta kayıt yalnız küçük harfle geçiyor, çeviride
  karşılığı cümle ortasında büyük harfle geçiyor". Hiyerarşi gibi meşru büyük harfli
  kullanımları da sayabilir.
- Bölüm hakeminin büyük harf notlarının çoğu bu sınıftan.
- Canlı veride de tutarsızlık yaratıyor. Shadow Slave'in bütün hizalı paragraflarında
  rütbesiz, küçük harfli sınıf adlarına bakıldı:
  - "monster": 598 kez küçük harfle, 93 kez cümle ortasında büyük harfle yazılmış.
  - "beast": 146 kez küçük, 79 kez büyük harfle.

  Aynı kelime kitap boyunca iki türlü yazılıyor.

### 7.3 Doğrulama aracının incelemeyi bekleyen kayıtları

Shadow Slave sözlüğündeki 805 kaydın 143'ü doğrulama aracında işaretli (113 inceleme,
30 sorunlu). Bunların 92'si son 200 bölümde (770–969) geçiyor.

**Etkisi en büyük, sıradan kelime şüphesi taşıyan kayıtlar.** Parantez içindekiler: son 200
bölümde kaç bölümde geçtiği ve geçişlerin kaçının küçük harfli olduğu.

- `Lost -> Kayıp` (59 bölüm, 73 geçişin 71'i küçük harfli)
- `Hope -> Umut` (54; 70'in 63'ü)
- `Fire -> Ateş` (44; 62'nin 32'si)
- `Not Really -> Pek Sayılmaz` (31; 35'in 34'ü)
- `Desire -> Arzu` (20; 25'in 25'i)
- `Cursed -> Lanetli` (19; 26'nın 22'si)
- `Crushing -> Ezilme` (18; 21'in 18'i)
- `Eyeless -> Gözsüzler` (10; 18'in 17'si)
- `Rift -> Yarık` (9; 14'ün 14'ü)

**Anlam ya da çakışma şüphesi taşıyan kayıtlar:**

- `Fallen -> Düşmüş` ("Fallen One" ile aynı karşılık)
- `Memory -> Anı` (büyü eşyası mı, hatıra mı)
- `Call -> Çağrı`
- `Devil -> Şeytan` ("daemon" ile aynı karşılık)
- `Guardian -> Muhafız` ("Guard" ile karışıyor)
- `Legacy -> Mirasçı`
- `class -> sınıf`
- `Hollow -> Kovan`
- `Pride -> Pride`
- `Serpent -> Yılan`
- `Changing Star -> Değişen Yıldız` (lakap politikası)

Bu kayıtlar sözlük ekranındaki inceleme listesinde kullanıcı kararı bekliyor. Kayıtları
değiştirmek kullanıcı kararıdır. Bu çalışmada hiçbir kayda dokunulmadı.

## 8. Öneriler

Etki sırasına göre. Canlı ayar değişikliği ve push kullanıcı onayına bağlıdır.

1. **Çeviri modelini 3.8 Flash'a geri al.** Bu araştırmadaki tek anlamlı anlam kazancı bu.
   - Etki: anlamda 103'e 68, akıcılıkta 75'e 38; bölüm başına kopukluk 1,00'a 1,81.
   - Bedel: aynı fiyat sınıfı.
   - Nasıl: okuyucudaki model seçiminde "3.8 Flash (Vertex, kredi)". Kod değişikliği
     gerekmez.
   - Dikkat: ayar bütün kitapları etkiler; RSSG'de ölçülmedi.
2. **Sıradan kelime işaretini aç (`SOZLUK_SIRADAN=1`).**
   - Etki: sözlük taşması 18'den 1'e iniyor; anlamda ve akışta kayıp yok. Kapalıyken
     prompt bayt bayt eskisi gibi kalır.
   - Nasıl: `roman-baglam` dalı push edilir, sunucuda systemd ek dosyasıyla
     (`Environment=SOZLUK_SIRADAN=1`) açılır. Geri almak için dosya silinir.
3. **Kalite katmanı açık kalsın.**
   - Etki: akıcılıkta anlamlı kazanç (48'e 28), anlamda olumlu eğilim.
   - Bedel: bölüm başına ~30 sn. Okumada çoğunlukla ön yüklemenin arkasında kalır.
4. **Analiz ve tutarlılık belleği kapalı kalsın.** Ölçülebilir katkıları yok. Analiz süreyi
   ~%70 uzatıyor.
5. **Sözlük inceleme listesinden şu kayıtlara karar ver.** Hepsi kullanıcı kararıdır:
   - **`Divinity` ailesi** (Ember / Flame / Mark / Spark of Divinity): "İlahiyat" (teoloji)
     yanlış anlam. Örneğin "İlahilik" ya da "Tanrısallık" olabilir. Ayrıca "Koruğu" yazımı
     yanlış.
   - **`Hollow -> Kovan`:** anlam hatası ("kovan" arı ya da mermi kovanıdır).
   - **`Seven` / `The seven -> Yediler`:** sayı olarak geçtiğinde de uygulanıyor. "Grup adı
     olarak geçtiğinde" koşulu gerekli.
   - **Sıradan kelime şüphesi taşıyanlar:** `Lost`, `Hope`, `Fire`, `Not Really`, `Desire`,
     `Cursed`, `Crushing`, `Rift`, `Call`. 2. madde açılırsa bunların aciliyeti azalır ama
     koşul eklemek yine en kesin çözüm.
   - **Sözlükte olmayan iki karar:**
     - Ordu rütbesi `Captain`: canlıda çoğunluk "Yüzbaşı", arada "Kaptan".
     - Büyü'nün (Spell) sistem mesajlarındaki hitap: "sen" mi, "siz" mi? Kollar arasında
       değişiyor ve hakemler bile çelişiyor.
6. **Sonraki ölçüm: canlıya en yakın bileşim.** 3.8 Flash + kalite katmanı + işaret
   birlikte, bugünkü canlıya karşı ölçülmeli. Böylece etkilerin toplanıp toplanmadığı
   görülür. Paragraf hakeminin talimatına da "sıradan kelimeye basılan büyük harf tutarlılık
   değildir" eklenmeli.

## 9. Sınırlılıklar

- **Örneklem küçük:** tek kitap (Shadow Slave), 8 bölüm, her kol tek koşu (A dışında).
  Yalnız büyük etkiler görülebilir. Faz 1'in "fark yok" sonucu "etki küçük" demektir,
  "etki sıfır" değil.
- **Hakemler model:** `gemini-2.5-pro`. Gözlenen yanlılıklar:
  - bölüm hakeminde güçlü konum yanlılığı,
  - paragraf hakeminde büyük harfli terimi tutarlılık sayma,
  - ara sıra yanlış sözcük bilgisi.

  Kör elle kontrol 13 maddeyle sınırlı.
- **F yalnız modeli değiştirdi:** 3.8'in kalite katmanıyla birlikte davranışı ölçülmedi.
- **RSSG kapsam dışı:** kullanıcı talimatıyla bu araştırmada RSSG incelenmedi. Önerilen model
  ve işaret değişiklikleri RSSG'yi de etkiler.
- **Taşma ölçütü kaba:** belirlenimci ve meşru büyük harfli kullanımı da sayabilir.

## 10. Tekrar üretme

Bütün adımlar `scripts/anlam_kiyas.py` ile yapılır. Ham veri takip dışıdır ve romandan metin
içerir; git'e eklenmez.

```
D=reports/anlam-kiyas-2026-10-11
anlam_kiyas.py hazirla  --bolumler 150,300,450,600,720,840,905,950 --cikti $D/ornekler.json
anlam_kiyas.py calistir --veri $D/ornekler.json --kollar A,A2,B,C,D,E --es 1 --cikti $D/ceviriler.jsonl
anlam_kiyas.py calistir --veri $D/ornekler.json --kollar F --model vertex/gemini-3.8-flash --es 1 --cikti $D/ceviriler-f.jsonl
anlam_kiyas.py calistir --veri $D/ornekler.json --kollar G --es 1 --cikti $D/ceviriler-g.jsonl   # H de aynı biçimde
anlam_kiyas.py yargila       --veri $D/ornekler.json --sonuc <birleşik> --ciftler F:B --es 2 --cikti <çıktı>
anlam_kiyas.py yargila-bolum --sonuc <birleşik> --ciftler F:B --es 2 --cikti <çıktı>
anlam_kiyas.py ozet --yargi <çıktı>;  anlam_kiyas.py ozet-bolum --yargi <çıktı>
```

Deney koşuları canlı okumayla aynı Vertex kotasını paylaşır. Eşzamanlılık düşük tutulmalı
ve kullanıcı okurken koşturulmamalı.

## 11. Ek ölçüm: bölüm özeti zinciri (AI Novel Translation yöntemi)

2026-10-11 akşamı, kullanıcı isteğiyle. Yöntem `darkautism/ai-novel-translation`'dan
alındı (kaynak kodu okundu: `config.yml`, `src/main.rs`). Her bölümde çeviriden önce tek
bir özet çağrısı yapılır. Girdisi önceki bölümün kayıtlı özeti, ilgili sözlük ve bölümün
kendisidir; çıktısı bu bölümün kısa Türkçe özetidir (en çok ~1000 karakter). Özet
saklanır ve sonraki bölümün özet çağrısına gider. Çeviriye yalnız bu bölümün özeti girer.
Bilinçli fark: yeni adlar sözlüğe otomatik yazılmaz. Kod: `core/ozet_zinciri.py`,
`CEVIRI_OZET=1` (`a1e7887`, varsayılan kapalı).

**Neden ayrı ölçüm:** 5. bölümdeki analiz kolları da özetleri bölümden bölüme
aktarabiliyordu. Ama ölçülen bölümler ardışık olmadığı için zincir hiç kurulmadı; hep
tek adımlı hâli ölçüldü.

**Deney:**

- Bölümler: 600–603, 840–843 ve 966–969 (üç blok, her blokta dört ardışık bölüm).
  Her bloğun ilk bölümünde zincir boş başlar, sonraki üçü önceki özeti alır.
- Kollar:
  - H: canlıya en yakın yol (analiz kapalı, işaret açık, kalite kapalı).
  - I: H + özet zinciri.
- Model ve koşu: 3.6 Flash; her kolda bölümler sırayla çevrildi.
- Yeniden çevrilenler:
  - H-600: ilk koşuda modelin reddiyle düştü, yeniden çevrildi.
  - I-969: özet çağrısı geçici hatayla düştü (çeviri özetsiz kaydedilmişti). 968'in özetiyle
    tohumlanıp yeniden çevrildi (`19f5d38`).
- Sonuç: 12 bölümün tamamında zincir kesintisiz kuruldu. Özet bloğu hiçbir çeviriye
  sızmadı; bütün çeviriler hizalı.

**Sonuç: ölçülebilir kazanç yok.**

| Ölçü (I:H) | I | H | eşit | p |
|---|---:|---:|---:|---:|
| Paragraf: anlam | 71 | 88 | 129 | 0,20 |
| Paragraf: akıcılık | 51 | 68 | 169 | 0,14 |
| Paragraf: tutarlılık | 12 | 16 | 260 | 0,57 |
| Bölüm: akış (iki yön aynı) | 2 | 0 | 10 | 0,50 |

Bölüm başına akış kopukluğu, zincirin konumuna göre:

| | I | H |
|---|---:|---:|
| Önceki özeti olan 9 bölüm | 1,33 | 1,72 |
| Blok başındaki 3 bölüm | 1,83 | 1,50 |
| Hepsi | 1,46 | 1,67 |

- **Akışta küçük olumlu eğilim var.** Önceki özeti olan bölümlerde I, 4 bölümde daha az
  kopuk, H 1 bölümde (4 eşit; p 0,38).
- **Paragraf düzeyinde hafif olumsuz eğilim var.** Anlamda 49'a 59, akıcılıkta 31'e 40.
- **İkisi de gürültü düzeyinde.** Aynı ayarın iki koşusu anlamda 50'ye 62 ayrışıyordu
  (5.1).
- **Bedel:** bölüm başına bir ek çağrı, ~10–40 sn.

**Öneri:** `CEVIRI_OZET` kapalı kalsın. Bu yöntem de 5. bölümdeki analiz kolları gibi
ölçülebilir kazanç getirmedi. Akıştaki eğilimi doğrulamak istenirse daha geniş bir ölçüm
gerekir: daha çok blok ve H'nin kendi tekrarıyla gürültü tabanı. Ölçülen tek anlamlı
kaldıraç yine model (6.1).

Tekrar üretme (`D=reports/anlam-kiyas-2026-10-11-zincir`, takip dışı):

```
anlam_kiyas.py hazirla  --bolumler 600,601,602,603,840,841,842,843,966,967,968,969 --cikti $D/ornekler.json
anlam_kiyas.py calistir --veri $D/ornekler.json --kollar H,I --es 1 --cikti $D/ceviriler.jsonl
anlam_kiyas.py yargila       --veri $D/ornekler.json --sonuc $D/ceviriler.jsonl --ciftler I:H --es 2 --cikti $D/yargi-paragraf.jsonl
anlam_kiyas.py yargila-bolum --sonuc $D/ceviriler.jsonl --ciftler I:H --es 2 --cikti $D/yargi-bolum.jsonl
```
