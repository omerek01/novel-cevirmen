# Claude Code'dan devralınan çalışmanın tamamlanması

2026-10-13; dal `roman-baglam`; başlangıç `61106bc`. Yerel çalışma; push, dağıtım ve canlı ayar değişikliği yapılmadı.

## Değişiklikler

- `e6c75c4`: Onaylı planın eksik kapak → kitap geçişi. Native View Transitions varsa seçili kapak paylaşılır; azaltılmış hareket/API yok/hata durumunda normal gezinme sürer. Yavaş bölüm listesi geçişi bekletmez; geçici adlar temizlenir.
- Aynı commit: Alt Önceki/Sonraki geçmişi büyütmez; geri düğmesi kitap ekranına döner. Yeni/yeniden açılan bölüm kapalı hapla başlar. Ayarlar varsayılan Literata'yı Georgia ile ezmez. Küçük metin kontrastı üç temada düzeltildi. Kabuk `v127`; bölüm önbelleği adı sabit.
- `e88f183`: Cilalama `STOP` dışındaki yanıtı uygulamaz. Aynen korunan adın paragraftaki geçiş sayısı azalırsa paragraf özgün kalır; yeni `detected_names` de geçici koruma listesine girer. Kaynak varyantları ortak eşleştiriciyle bulunur. Kalıcı sözlük kaydı/karşılığı değiştirilmez.

## Cilalama kanıtı

Önceki "12 terim kaybı" şüphesi 12 doğrulanmış hata değildir. Alt dizi sayımı `Anı`yı `tırmanıp/canına`, `Büyü`yü `büyük/büyüdü` içinde sayabiliyordu; ek/yazım değişiklikleri de sayımı etkiliyordu.

Somut hata: Shadow Slave 974, **20. paragraf** (indeks 19), P3K çıktısında `Sunny` kaldırılmıştı. Eski üretim filtresi bunu kabul ediyordu. Yeni kodla aynı kayıt tekrar işlendi: o paragraf geri alındı, özgün metin ve `Sunny` korundu. [Kanıt](cilalama-replay.json): sıfır sağlayıcı çağrısı, canlı DB'ye yazma yok.

Yeni sayım yalnız İngilizce aynen korunan adları kapsar. Türkçe karşılıkların koşulları/ekleri ham sayımla karara bağlanmaz; mevcut denetimler ve kalite katmanı sürer. Cilalama varsayılan **kapalıdır**. Önceki akıcılık/anlam kıyasları tarihsel deney sonuçlarıdır; bu düzeltmelerden sonra yeni model kıyası yapılmadı.

## Doğrulama

| Kontrol | Sonuç |
|---|---|
| `../../.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` | 1184 geçti, 1 atlandı; 5 mevcut kullanımdan kaldırma uyarısı |
| `NOVEL_TARAYICI_TEST=1` ile `pytest tests/tarayici -q -p no:cacheprovider` | 99 geçti |
| `node --test "tests/js/*.test.mjs"` | 46 geçti |
| Başarısız test → düzeltme → başarılı test | Kapak, yavaş liste, alt history/reset, ad kaybı/bitiriş, kontrast, Literata |
| Bağımsız inceleme | Kritik bulgu yok; önemli bulgular testle düzeltilmiş |
| Sunucu gerçekten kapatılarak çevrimdışı kabuk | Bağımsız incelemede geçti |
| 390×844, 2x; 7 ekran × 3 tema | 21 PNG; yatay taşma/JS hatası yok; görsel olarak incelendi |

Test verili görüntüler (roman metni içermez, PNG'ler commit'e girmez): [açık](tum-ekranlar-light.png), [sepya](tum-ekranlar-sepia.png), [koyu](tum-ekranlar-dark.png).

## Bekleyenler ve sınırlar

- Gerçek Android cihazda kullanım/PWA güncellemesi denenmedi.
- Küçük görsel eksik: inceleme sayısı büyük `review-count` biçimi yerine mevcut metin içinde gösteriliyor; işlev çalışıyor, biçim değişikliği ertelendi.
- `roman-baglam` push ve canlıya alma kullanıcı onayı bekliyor. Cilalamayı canlıda açmak ayrıca açık bir karar gerektirir.
- Ana çalışma ağacındaki eski commit edilmemiş işler korunmuştur.
