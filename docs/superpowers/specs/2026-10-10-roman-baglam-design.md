# B?l?m analizi ve kaynak ba?l? roman ?evirisi

Kullan?c? 2026-10-10 tarihinde ?zet/terim analizi, ?nceki b?l?m ?zeti ve ara?t?rmadaki 1?4 ?nerilerini planlay?p uygulamay? istedi. Ama? kaynak anlam? korunurken tutarl? ve do?al T?rk?e ?retmek; daha ?ok model ?a?r?s?n? ba?ar? saymak de?il.

## Tasar?m

Mevcut FastAPI/SQLite/PWA ak??? korunur, 7cdc6a0 canl? taban?ndan ayr? roman-baglam dal?nda ?al???l?r. Kod ve belgeler T?rk?e; NovelLink kontrol merkezine dosya yaz?lmaz. Yeni ?cretli sa?lay?c?ya otomatik ge?i? eklenmez. Se?ili model zinciri analiz/?eviri/denetimde kullan?l?r; modeller a?ama baz?nda kaydedilir. ?cretsiz se?im ?cretliye ge?mez. Push/da??t?m bu g?revin uygulama yetkisinden ayr? onaya ba?l?d?r.

Yeni metin ?evirilerinde CEVIRI_ANALIZ=1 varsay?land?r; 0 eski ?eviri yoluna d?ner. Cache hit yeni analiz/?eviri yapmaz. PDF/manga HTML yolu kapsam d???d?r. ?zet eski kaynak ve kendi hash'iyle ba?l?d?r; ayn? kitap, exact N-1 ve kaynak hash'i do?rulanmadan kullan?lmaz. N-1 yoksa daha eski/yeni/ba?ka kitap yerine ba?lam yok denir. Eski N-1 kaynak varsa ?zeti bir kez olu?turulur; kaynak de?i?irse tekrar ?retilir. Kaynakta tamamlanm?? yan?t, paragraf kimli?i ve ger?ek al?nt? olmadan analiz kabul edilmez. ?zet en fazla 6 kaynak ba?l? madde, toplam 1800 karakterdir. Terim adaylar? en fazla 30; kaynak terim/alinti ger?ek metinde bulunur; ki?i / yer / grup / nesne / yetenek / kategori / di?er ?zel ad t?rleri. S?radan kelimeler terim diye zorlanmaz. Analiz ?zetleri birer yard?mc? ipucudur, ?zg?n kaynak en ?st do?ruluk yetkisidir. ??pheli model ??kar?m? bilgi grafi?ine veya kal?c? s?zl??e otomatik yaz?lmaz.

?retim a?amas? yaln?z translation JSON alan?n? ?retir, ayr? detected_names/terms i?i istemez. Ana ?evirinin mevcut isim/ko?ul/hiyerar?i/deyim/ek/eksiksizlik kurallar? korunur. ?nceki ve g?ncel ?zet ayr? JSON veri olarak sunulur. K?sa sabit T?rk?e ?slup: do?al c?mle, ba?lamdaki deyim/anlam, olay ekleme veya ?zetleme yok. Aktif s?zl?k kar??l??? temel bi?imdir; dilbilgisel ?ekim/k?k de?i?imi serbesttir. Yeni analiz adaylar? b?l?mde yerel ?neri olarak kullan?l?r, kay?tl? s?zl??? ezmez; yaln?z ?eviride ger?ekten kullan?lanlar? normal bekleme/onay kap?s?na g?nderilir.

G?zlemlenebilirlik: b?l?m ba??na kaynak/istem/s?zl?k ?zeti, a?ama/model/token/finish bilgisi, ilk ham ?eviri, her a?ama ?ncesi/sonras?, bulgular, nihai sonu? ve hata g?venli yerel SQLite kay?tlar?nda tutulur. API anahtar?/kimlik bilgisi yok. URL ba??na son 5 deneme, ba?ar?s?z deneme dahil; ba?ar?s?z kalite kap?s? eski chapter/ar?ivi de?i?tirmez. Bu izler okuyucu payload'?na y?klenmez. Ayr? salt-okunur teknik inceleme arac? ??kt? verir.

Kalite anlam sadakati ve T?rk?e ak?c?l??? ayr? boyutlarda raporlan?r. Yeni rapor v2 source-bound bulguyu korur; ?slup ?nerisi otomatik anlam hatas? say?lmaz. Mevcut v1 rapor okuyucu uyumlu kal?r. Onar?m tek tur ve atomik, mevcut denetimleri korur. Farkl? hakem modeli otomatik se?ilmez; kar??la?t?rma arac?nda ayr? deneydir. Her paragraf ko?ulsuz redakte edilmez.

## Kabul ve ?l??m

?evrimd??? testler: N-1 eksik/yanl?? kitap/gelecek/hash de?i?imi; ham kaynak/paragraf b?t?nl???; yanl?? al?nt?/STOP/JSON/numeric limit; kay?tl? terim ezilmemesi; saf ?retim; eski bayrak kapal? yol; failed run trace vs chapter preservation; iki pipeline metin yolu; paralel ba?lam izolasyonu; anlam/ak?c?l?k ayr?m?. Ger?ek taray?c?: mevcut 67 test, ek izler payload ?i?irmeyecek. 961 ve 957 dahil en az iki farkl? kitab?n ?rnekleriyle ayn? model/s?zl?k sabit a??k/kapal? kar??la?t?rma; canl? DB'ye yazma yok. Otomatik onar?m kazanc? ayr?ca raporlan?r; kalite art??? ancak okunan ?rneklerde s?ylenir, genellenmez.
