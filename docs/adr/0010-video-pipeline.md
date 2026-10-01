# ADR-0010: Video yükleme, HLS ve klipler

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §9, §10 (`video_assets`, `video_clips`), §11 Video, §12.2, §19 Faz 5; ADR-0004, ADR-0005; A-60 … A-62

## Bağlam
Kulüp başına sezonda yaklaşık 60 maç videosu ve video başına 2-4 GB bekleniyor (SPEC §18). Videonun API ya da web sunucusundan geçmesi hem yavaş hem pahalı olur. Tarayıcı ise erişim token'ını görmez (ADR-0005). Analist tablette akıcı oynatma, klip kesme ve klibi bir duran topa bağlama ister.

## Karar
- **Doğrudan depoya yükleme.**
  - `POST /video/uploads` bir `video_assets` satırı açar ve parça başına imzalı PUT adresleri döner.
  - Tarayıcı parçaları doğrudan depoya yükler.
  - `POST /video/assets/{id}/complete` parçaları birleştirir ve dönüştürme işini kuyruğa alır.
  - Uç `Idempotency-Key` ister.
- **İki depo uygulaması.**
  - S3/MinIO'da gerçek çok parçalı yükleme kullanılır; tarayıcı için ayrı bir genel uç adresi (`S3_PUBLIC_ENDPOINT_URL`) vardır.
  - Yerel depoda (geliştirme ve test) API, HMAC ile imzalanmış kısa ömürlü yükleme ve okuma adresleri sunar. Bu adresler token istemez; imza, anahtar ve son kullanma zamanını bağlar.
- **Dönüştürme worker'da.**
  - Arq işi kaynağı indirir ve ffmpeg ile tek kaliteli HLS üretir (A-61).
  - ffmpeg süreyi de okur; çıktı depoya yazılır.
  - Durumlar: `uploading → processing → ready | failed`.
- **Oynatma.**
  - Web sunucusu `GET /video/assets/{id}/playlist` ucunu çağırır. API, parça satırlarını kısa ömürlü imzalı adreslerle yeniden yazar.
  - Tarayıcı hls.js ile oynatır.
- **Klipler.**
  - `GET/POST /clips`, `PATCH/DELETE /clips/{id}`.
  - Klip başlangıç ve bitişi video saniyesidir.
  - `set_piece_id` isteğe bağlıdır ve aynı maçın, aynı kiracının duran topunu göstermelidir.
  - Rutin istatistikleri klipleri listeler.
- **Güvenlik.** Tür ve boyut sınırı (A-60), kiracı ön ekli anahtarlar (`video/<kiracı>/<varlık>/…`), imzalı adreslerin kısa ömrü ve her yazma işleminin denetim kaydı.

## Sonuçlar
- **Artı:** Büyük dosyalar uygulama sunucularından geçmez; yükleme parçalı olduğu için kesintide yalnızca eksik parçalar yeniden gönderilir.
- **Artı:** Yerel depo ile S3 aynı sözleşmeyi uygular. Testler MinIO olmadan çalışır.
- **Eksi:** Tek kalite, zayıf bağlantıda takılabilir; ABR sonraki iş.
- **Eksi:** Oynatma listesi her açılışta API'den geçer; listeler küçük olduğu için kabul edilebilir.

## Değerlendirilen seçenekler
- **Videoyu API'ye yüklemek:** 4 GB'lık dosyalarda bellek ve zaman aşımı riski. Reddedildi.
- **Depo nesnelerini herkese açık yapmak:** Kiracı izolasyonunu bozar. Reddedildi.
