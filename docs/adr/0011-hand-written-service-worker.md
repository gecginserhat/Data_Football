# ADR-0011: Elle yazılmış hizmet çalışanı (Serwist yerine)

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §13.1 (`/live/[fixtureId]` çevrimdışı çalışır), CLAUDE.md yığın listesi (Serwist), ADR-0004, ADR-0006

## Bağlam
Yığın listesi PWA için Serwist diyor. Proje Next.js 16 ve Turbopack ile derleniyor (ADR-0006). Serwist'in Next eklentisi webpack derlemesine bağlı; Turbopack desteği ayrı ve yeni bir paketle geliyor. Faz 5'te çevrimdışı gereksinim dar: canlı kayıt sayfası ve onun statik dosyaları. Kayıtların kendisi IndexedDB'de (Dexie) duruyor, yani hizmet çalışanı veri önbelleklemiyor.

## Karar
- `apps/web/public/sw.js` elle yazılır (yaklaşık 100 satır), derleme adımı yoktur.
  - `/_next/static/*` ve simgeler: önce önbellek (dosya adları içerik özeti taşır).
  - `/live` ve `/live/*` sayfa gezintileri: önce ağ, ağ yoksa son kaydedilen sayfa; hiç açılmamışsa kısa bir çevrimdışı sayfa.
  - `/api/*` ve diğer istekler önbelleğe alınmaz.
- Sayfa her gezintide açtığı yolu ve yüklediği dosyaları çalışana bildirir (`warm` mesajı). Böylece ilk ziyaretten sonra da maç sayfası çevrimdışı açılır.
- Kayıt yalnız üretim derlemesinde yapılır. Önbellek adı sürümlüdür (`kurgu-v1`); değişince eski önbellekler silinir.
- Bildirim `app/manifest.ts` ile üretilir; 192, 512 ve maskelenebilir 512 simgeleri `public/icons/` altındadır.

## Sonuçlar
- Turbopack derlemesi değişmez, ek bağımlılık yoktur; davranış tek dosyada okunur.
- Önbellek kuralları elle bakım ister. Arka planda senkronizasyon (Background Sync) yoktur; senkronizasyon sayfa açıkken çalışır (5 sn çekme, `online` olayı, her kayıttan sonra).
- Serwist'in Turbopack desteği olgunlaşırsa bu dosya ona taşınabilir; davranış sözleşmesi bu ADR'dir.
