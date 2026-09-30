# ADR-0003: SPADL uyumlu kanonik olay modeli

- **Durum:** Önerildi · 30.09.2026
- **İlgili:** SPEC §4, §5.2-5.5, §10 (`events`)

## Bağlam
Veri birden çok kaynaktan gelecek: StatsBomb Open Data (geliştirme), lisanslı API'ler (StatsBomb, Opta, Wyscout; P1), CSV içe aktarım ve kulübün kendi canlı kaydı. Duran top çıkarımı ve metrikler bu kaynakların hepsinde aynı çalışmalı. Sağlayıcıların koordinat sistemleri de farklı (StatsBomb 120×80, y aşağı artar).

## Karar
- **Kanonik model SPADL'dır** (action type, result, bodypart, start/end x-y). Dönüşümler `kloppy` (sağlayıcı ayrıştırma) ve `socceraction` (SPADL) ile yapılır.
- **Koordinatlar tek sistemde:** 105×68 m, hücum edilen kale x = 105, y = 0 hücum edenin sağ taç çizgisi (SPEC §4). Her aksiyon, sahibi olan takımın hücum yönüne normalize edilir. Dönüşüm yalnızca adaptörde yapılır; referans noktaları (direkler, altı pas, ceza sahası, penaltı noktası) için birim test vektörleri yazılır.
- **Katmanlar:** `raw` (değişmez ham yük, object storage + `raw_payloads` meta, `source_hash` benzersiz) → `canonical` (`events`, `matches`, `players`, `teams`) → `marts` (`set_pieces`, metrikler, MV'ler). Yükleme idempotenttir; aynı `source_hash` ikinci kez işlenmez.
- `events` alanları SPEC §5.3'teki gibidir; ek olarak `xg_source`, `provider`, `provider_event_id` (sağlayıcı içinde benzersiz), `raw_ref` (ham yükteki konum).
- **SPADL'ın taşımadığı bilgiler** (StatsBomb `play_pattern`, pas yüksekliği, kafa/ayak ayrıntısı) `events.extra jsonb` alanında tutulur; çıkarım bunlara **bakmaz** (doğrulama için kullanılır), böylece algoritma sağlayıcıdan bağımsız kalır.
- **Kimlik eşleştirme** `provider_id_map` ile; onaylanmamış eşleşmeler metriklere girmez (SPEC §5.4).
- **Bölgeler ve saha geometrisi** `packages/pitch/zones.json` içinde tek kaynaktır; Python (`kurgu_analytics.setpieces.zones`) ve TS (`packages/pitch`) aynı dosyayı okur, ortak test vektörleriyle doğrulanır.
- Kulübün canlı kaydı (`live_tags`) SPADL'a zorlanmaz; doğrudan `set_pieces` satırı üretir (`source='live_tag'`). Böylece olay verisi olmayan maçlarda da duran top metrikleri oluşur.

## Uygulama notu (Faz 1)
- socceraction 1.5.3 numpy<2, pandera<0.18 ve lxml<5 sabitliyor; pandera'nın bu sürümü güncel `multimethod` ile açılmıyor bile. A-16'daki yedek plan uygulandı: StatsBomb açık JSON'u doğrudan okuyan ince bir eşleyici yazıldı (`kurgu_analytics.ingestion.statsbomb`). Tür, sonuç ve vücut bölgesi kuralları socceraction'ın StatsBomb dönüştürücüsünü izler.
- Uyum ayrı, geçici bir ortamda socceraction ile ölçülür (`make spadl-compare`, `docs/validation/spadl_socceraction.md`). 30 maçta ortak olaylarda tür uyumu %100, tür + sonuç + vücut bölgesi uyumu %99,78.
- kloppy StatsBomb için kullanılmıyor; açık JSON yeterli. Takip verisi (P2) geldiğinde kloppy eklenir.
- Kanonik katman en alttadır; `ingestion` onun üstündedir (import-linter sözleşmesi buna göre sıralandı).
- Koordinat dönüşümü parçalı doğrusaldır (A-25).

## Sonuçlar
- **Artı:** Yeni sağlayıcı = yeni adaptör; çıkarım ve metrikler değişmez.
- **Artı:** Açık kaynak futbol ekosistemiyle (VAEP, xT; P2) doğrudan uyum.
- **Eksi:** SPADL bazı duran top ayrıntılarını (ör. inswing/outswing) taşımaz; alt tür, bitiş noktası ve pas kavisinden türetilir ya da `extra` alanından okunur. Türetme doğruluğu Faz 1 doğrulama raporunda ölçülür.
- **Risk:** `socceraction`ın Python 3.12 / pandas 2 uyumu. Uyumsuzsa ince bir kendi SPADL eşleyicisi yazılır (bkz. assumptions A-16).

## Değerlendirilen seçenekler
- **Sağlayıcıya özgü şema:** Her sağlayıcı için ayrı çıkarım. Reddedildi.
- **Kendi olay modelimiz:** Ekosistemden kopuk, belgelemesi pahalı. Reddedildi.
