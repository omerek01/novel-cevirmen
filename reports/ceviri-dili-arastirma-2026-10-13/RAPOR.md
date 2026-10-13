# Roman çevirisinde dil düzeyi ve cilalama araştırması

14 Ekim 2026, Türkiye saati. Çalışma 13 Ekim UTC'de başladı.
Kod dayanağı: `roman-baglam`, `12612d25782f7376a18092ff22e11771817c6e5c`.

## Sonuç ve önerilen yol

Sorun iki katmanda: cilalama, anlaşılır bir ifadeyi daha ağır bir sözcüğe çevirebiliyor;
kalite denetimi de hedeflenen konuşma düzeyinden sapmayı sıradan eş anlamlı tercih
sayarak atlayabiliyor. Çözüm adayı, **açık bir Türkçe dil ölçütü ile yalnız somut kusuru
onaracak cilalamayı birlikte sınamak**. Modeli değiştirmek tek başına bu vakayı çözmedi.

**Denediğimiz daraltılmış cilalama talimatı üretime hazır değil:** şikâyetin anlamına
yaklaşsa da başka bir paragraftaki binlerce kişiyi birkaç kişi düzeyine indiriyor.
Bu adayın doğrudan yayımlanması önerilmiyor. Bir sonraki adım, açık dil ölçütüyle
mevcut hedefli onarımı ve düzenlenen yerde anlam kaybı kontrolünü birlikte ölçmek.

Bu rapor araştırmadır. Uygulama kodu, çalışan servis ayarları, sözlük ve kayıtlı
bölümler değiştirilmedi. Yeni tasarımın üretime alınmasına karar verilmedi.

## Canlı izde doğrulanan sorun

Shadow Slave 983, 21. paragrafın `f18db8c5b0894239b3c6a584d4008998` izinde cilalama
öncesindeki **hevesli**, cilalama sonrasında **gayretkeş** olmuş. Sonraki denetim 36
paragrafı denetlendi saymış ve bulgu vermemiş. Cilalama talimatında az bilinen/eski
sözcük getirmeme kuralı zaten var; bu kural tek başına yeterli olmamış.

Kaynakta konuşmacı, bir kişiyi getirmeye gönderdiği kişinin kırk bin kişi getirmesiyle
alay ederek takılıyor. Yalnız hevesi veya gayreti ifade eden karşılık bu bağlamdaki
beklenenden fazlasını yapma işlevini zayıflatıyor. Bu cümle için editör önerisi:
**“Kim senden bu kadar fazlasını yapmanı istedi?”** Kayıtlı bölümde uygulanmadı.

983, 17. paragrafta ikinci bir somut sorun var: kaynakta bulunan `valiant` nitelemesi
cilalama öncesinde **yiğit** olarak mevcutken sonrasında silinmiş. Paragraf boyu,
ad koruması ve sözlük kontrolleri bu tür küçük anlam kaybını tek başına engelleyemez.

Kalite talimatı, doğru eş anlamlı tercihleri hata saymıyor; somut üslup kusuru
örnekleri tekrar ve yapay cümle kuruluşuyla sınırlı. Okurun istediği güncel,
kolay anlaşılır dil düzeyinden sapma ayrıca ve açıkça tanımlanmamış.

## Kaynakların söylediği ve söylemediği

- [MQM Core](https://www.themqm.org/mqm-pillars/the-mqm-core-typology/), dilbilgisi
  kabul edilebilir olduğu hâlde belirtilen dil düzeyine uymayan anlatımı ayrı bir
  üslup kusuru sayıyor. Buradaki yararı hata türünü tanımlamak; roman kalitesini
  tek bir otomatik puanla ölçebildiğimiz anlamına gelmiyor.
- [Lost in Literalism](https://arxiv.org/html/2503.04369v1), GPT modelleriyle
  İngilizce–Çince ve Almanca–İngilizce deneylerinde ayrı cilalama geçişini de sınamış.
  Bazı koşullarda düz çeviriden daha iyi sonuç buluyor; yalnız akıcılık talimatı
  eklemek tutarlı kazanç vermiyor. Bulgular Türkçe/Gemini için doğrudan kanıt değil.
- [Iterative Translation Refinement](https://aclanthology.org/2024.eamt-1.17/),
  yinelemeli düzenlemenin insan değerlendirmesinde akıcılık ve doğallığı
  geliştirebildiğini bildiriyor; kaynakla bağ ve başlangıç çevirisi önem taşıyor.
  Cilalamanın her değişikliğinin güvenli olacağını göstermiyor.
- [Guiding LLMs to Post-Edit with Error Annotations](https://aclanthology.org/2024.findings-naacl.265/),
  hata açıklamalarıyla sonradan onarımı araştırıyor. Ayrıntılı hata geri bildiriminin
  ek yararı, model eğitimi olmadan net değil. “Önce bul, sonra yalnız orayı onar”
  bizim uygulamamız için sınanacak bir tasarım; kanıtlanmış evrensel çözüm değil.
- [LITEVAL](https://aclanthology.org/2025.naacl-long.548/), edebî çeviride otomatik
  ölçütlerin ve değerlendirici deneyiminin ciddi sınırlılıklarını gösteriyor.
  Bu nedenle aşağıdaki model hakemi insan çevirmen veya okur kararının yerini tutmaz.

## Deneyin kapsamı

Canlı veritabanı salt okunur bağlantıyla incelendi. 978–984 arasındaki hizalı
kaynak/önceki çeviri/cilalanmış çeviri izlerinden 11 paragraf seçildi: şikâyet
paragrafı, en fazla değişen beş paragraf ve cilalamada değişmemiş beş kontrol adayı.
Komşu paragraflar mümkün olduğunda aynı İngilizce bağlam olarak sağlandı.

Örnekler: 983/21, 983/17, 984/1, 983/24, 984/30, 984/9, 978/1, 978/3, 978/5,
978/8, 978/11. Seçim kusur ağırlıklı ve küçüktür; rastgele kitap örneklemi değildir.
Değişmemiş kontrol adayları insan tarafından doğrulanmış hatasız metin değildir.

Çağrılar Vertex üzerinden sırayla, sıcaklık 0 ile yapıldı. Model geri dönüş zinciri
ve otomatik tekrar kullanılmadı. STOP dışı yanıt kabul edilmedi. Canlı çeviri API'si
ve bölüm kaydetme akışı çalıştırılmadı. Özel ham örnekler ve yanıtlar bu klasörde
yerelde tutuldu, git dışında bırakıldı; bu rapor tam roman paragrafları içermez.

### Denetim karşılaştırması

Aynı 11 cilalanmış paragraf üzerinde eski talimat ile dil ölçütü eklenmiş talimat
karşılaştırıldı. Üslup kuralı, kaynakta sıradan olan konuşmanın günümüzün genel
okuruna anlaşılır konuşma düzeyinde kalmasını istedi. Şikâyetteki sözcük örnek
olarak talimata verilmedi. Özel adlar, dünya terimleri ve bilerek resmî kaynak sesi
istisna tutuldu. Bu karşılaştırmada sözlük/koşul girdileri bütün kollarda boştu;
tam üretim akışının ölçümü değildir.

| Model ve talimat | Tekrar | Alıntısı doğrulanan bulgu | 983/21 yakalandı mı? |
|---|---:|---:|---|
| 3.8 Flash, eski | 1 | 0 | Hayır |
| 3.8 Flash, dil ölçütlü | 1 | 1 | Hayır |
| 3.8 Flash, eski | 2 | 0 | Hayır |
| 3.8 Flash, dil ölçütlü | 2 | 2 | Evet |
| 2.5 Pro, eski | 1 | 1 | Hayır |
| 2.5 Pro, dil ölçütlü | 1 | 7 | Evet |

Alıntı doğrulaması yalnız metindeki kanıtın gerçek olduğunu gösterir; açıklamanın
doğru olduğunu kanıtlamaz. Örneğin 2.5 Pro, **kara** ifadesini karın üzerine inmek
yerine toprak parçasına inmek diye yorumlayarak yanlış bulgu verdi. Aracın tavanı,
araçların yorgunluğu ve iflas etmesi gibi diğer bulgular da bağlam/metafor bakımından
editör incelemesi gerektiriyor. Yedi bulgu iki bulgudan daha iyi demek değildir.

Ölçüt eklenince 983/17'deki niteleme kaybı da görünür oldu. Buna rağmen 3.8 Flash
şikâyeti iki tekrarın birinde kaçırdı. 2.5 Pro'ya yalnız model değişikliğiyle geçmek
şikâyeti yakalatmadı. Aynı sıcaklık, aynı yanıt veya kusursuz denetim garantisi vermedi.

### Cilalama ve kör karşılaştırma

Aynı cilalama öncesi 11 paragraf, ilgili sözlükteki korunacak karşılıklarla verildi.
Eski talimat ile somut kusur/minimum değişiklik ve açık dil ölçütü eklenmiş talimat
ikişer kez sınandı. Bu deney iki kuralı birlikte değiştirir; her birinin ayrı
etkisini ölçen bir deney değildir. Sonrasında tam kalite onarım döngüsü çalıştırılmadı.

| Talimat | Tekrar | Değişen paragraf | STOP / 11 numaranın tamlığı | Korunan İngilizce ad kaybı |
|---|---:|---:|---|---:|
| Eski | 1 | 11 | Doğrulandı | 0 |
| Daraltılmış | 1 | 9 | Doğrulandı | 0 |
| Eski | 2 | 10 | Doğrulandı | 0 |
| Daraltılmış | 2 | 10 | Doğrulandı | 0 |

İlgili sözlüğün aynen korunan İngilizce adları, üretimdeki sözcük eşleştiricisiyle
çevrimdışı sayıldı. Bu kontrol bütün sözlük koşullarını, yeni ad çıkarımını ve tam
üretim kabul döngüsünü yeniden çalıştırmak anlamına gelmez.

Daraltılmış kol 983/21'de iki kez **fazlasını yapmak** yönünde çıktı verdi; eski
talimat bir kez **işgüzar**, bir kez **hevesli** kullandı. Daraltılmış cümleler de
Türkçe kuruluş bakımından editör düzeltmesi istiyor. Canlıdaki **gayretkeş** bu küçük
yeniden deneyde eski talimatta tekrarlanmadı; tam bölüm ile küçük paket aynı değildir.

983/17'de bütün yeni kollar **yiğit** nitelemesini korudu. Dolayısıyla küçük pakette
daraltılmış kolun bu sıfat açısından eski kola üstünlüğü gösterilmiş değildir;
canlı izdeki önce/sonra kaybı ise doğrudan doğrulanmıştır.

En önemli ret gerekçesi 983/24: kaynağın birkaç **bin** deneyimli denizciyi anlattığı
yerde daraltılmış iki çıktı **birkaç kişi** anlamına kaydı. Eski kolun ikinci tekrarı
da bu anlam kaybını üretti. İlk çevirideki asker sayısının belirsizliği ayrıca
korunuyor. Bir sorunu iyileştirmek başka bir anlam kaybını kabul etme gerekçesi değil.

22 eşleştirmeyi X/Y olarak sırası karıştırılmış biçimde ayrı model 2.5 Pro'ya veren
tek kör hakem çağrısı **ServerError** ile tamamlanamadı. Otomatik tekrar veya yedek
model çağrısı yapılmadı. Kör hakem puanı ve kazanma oranı yoktur; bu rapor böyle bir
üstünlük iddiası içermez. Yukarıdaki anlam kaybı, kaynak ve dört adayın doğrudan
editör incelemesine dayanır; insan tarafından hazırlanmış altın veri değildir.

Toplam: 11 çağrı denendi; altı denetim ve dört cilalama çağrısı STOP ile tamamlandı,
bir hakem çağrısı başarısız oldu. Denetimlerde kapsam ve alıntı doğrulaması yapıldı.
Cilalama yanıtlarının hepsinde 0–10 numaraları tam ve birer kez bulunuyordu.
Metinsiz makine özeti: [`ozet.json`](ozet.json).

## Uygulama için önerilen sıra

1. **Dil ölçütünü ortaklaştır:** çeviri, cilalama, hata denetimi ve onarım aynı
   kısa kurala uysun: güncel ve kolay anlaşılır Türkçe; sade konuşmayı ağırlaştırma;
   ironi/mizahı, terimleri ve karakterin bilerek resmî konuşmasını koru.
2. **Cilalamayı somut kusurla sınırla:** doğal metni aynen bırak; bir kusur varsa
   en küçük değişiklikle gider. Eş anlamlı sözcük değişikliği tek başına iyileştirme
   gerekçesi olmasın. Tam yeniden yazma yerine mevcut hedefli onarım döngüsünü
   kullanmak ayrıca ölçülsün; yeni bir sürekli model çağrısı eklemek ilk adım değil.
3. **Değişiklikleri kaynakla karşılaştır:** cilalama öncesi ve sonrası metni birlikte
   değerlendiren denetimle yeni eksiltme/ekleme aranmalı. Bulgu yokluğu doğru anlamın
   kanıtı değildir. STOP, ad, sözlük ve paragraf korumaları devam etmeli; bu kontroller
   sıradan sıfat ve anlam ayrıntısı kaybının semantik doğrulaması sayılmamalı.
4. **Bölüm üzerinde dene:** en azından 983/984 tam bölüm, diğer bir kitaptan bölüm ve
   resmî konuşma/dünya terimi içeren örnekler; aynı kaynak ve sözlük anlık görüntüsüyle
   eski/yeni karşılaştırması. Anlam ve okunurluk ayrı değerlendirilmeli. Okur örnekleri
   görmeden küçük model pilotundan genel başarı kararı çıkarılmamalı.
5. **Sonra yayımla ve eski bölümü onar:** yerel doğrulama ve kullanıcı değerlendirmesi
   sonrası dağıtım. 983'ün sorunlu yerlerini kaynakla karşılaştırarak hedefli düzeltmek,
   bölümün tamamını sebepsiz yeniden çevirmekten daha denetlenebilir bir işlemdir.

Bu sıra öneridir; henüz uygulanmadı. Genel bir yasaklı sözcük listesi önerilmiyor:
eski veya resmî sözcük kaynağın bilinçli sesi olduğunda doğru olabilir. Sorun,
bağlama ve hedeflenen okuma diline uygunlukla değerlendirilmelidir.
