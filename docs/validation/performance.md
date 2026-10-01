# Performans doğrulaması (Faz 8)

İlgili: SPEC §13.4 (bütçeler), §18 (ölçek), A-93, A-99. Ölçüm tarihi: 01.10.2026.

**Ortam:** 4 çekirdekli Linux geliştirme konteyneri; PostgreSQL 16, Redis, Keycloak, API ve web aynı makinede; web üretim derlemesi (`next build`, standalone, gzip). Tohum verisi ve geliştirme kimlikleri (Trabzonspor demo kiracısı). Üretim donanımında yeniden ölçülmelidir.

## Özet
| Bütçe | Hedef | Ölçülen | Araç | Sonuç |
|---|---|---|---|---|
| API p95 (özet uçları) | ≤ 300 ms | **201 ms** (15 kullanıcı, 2 dk) | k6 | Geçti |
| İlk JS yükü (gzip, rota başına) | ≤ 200 KB | **148-161 KB** | Playwright E2E (`perf.spec.ts`) | Geçti |
| LCP (4G, orta tablet) | ≤ 2,5 sn | **1,9-2,1 sn** (Lighthouse, uygulanan yavaşlatma); 0,9-1,4 sn (E2E) | Lighthouse 12, Playwright | Geçti (bkz. not) |
| Canlı kayıt: dokunuştan yerel kayda | ≤ 50 ms | **p95 25,5 ms** (20 kayıt) | Playwright E2E (`live.spec.ts`) | Geçti |

## API yükü (k6)
Betik: `infra/perf/api-load.js`. 15 eşzamanlı sanal kullanıcı (SPEC §18), 15 sn artış, 2 dk sabit, sayfalar arasında 1-3 sn bekleme. Her döngü: `/me`, `/prep/overview`, puan durumu, takım metrikleri, takım profili, duran top listesi, fikstürler, maç hazırlığı, rutin listesi ve rutin.

| Gruplar | Tek süreç, iyileştirme öncesi | Tek süreç, iyileştirme sonrası | 2 işçi (üretim ayarı) |
|---|---|---|---|
| Tümü p95 | 9,8 sn (20 kullanıcı, beklemesiz) | 339 ms | **201 ms** |
| Genel bakış p95 | | 360 ms | 217 ms |
| Rakip p95 | | 322 ms | 180 ms |
| Maç hazırlığı p95 | | 334 ms | 220 ms |
| Rutinler p95 | | 322 ms | 175 ms |
| Hata oranı | %9,9 | %0 | %0 |

Bulgu ve düzeltmeler (A-99): `/prep/overview` tek istekte 1,4 sn sürüyordu; altı fikstür için sezon metrikleri ayrı ayrı hesaplanıyordu. Metrikler istek içinde paylaşıldı ve saf metrik fonksiyonları içerik özetine göre önbelleğe alındı: 160 ms. Kalan gecikme tek olay döngüsünde CPU'ya bağlı pandas işinden gelen kuyruklanmadır; üretim imajı iki uvicorn işçisiyle çalışır.

Yeniden çalıştırma: `K6_TOKEN=<sp-coach belirteci> K6_TENANT=<kulüp id> k6 run infra/perf/api-load.js`.

## İlk JS yükü
`apps/web/e2e/perf.spec.ts`, tablet projesinde her kritik sayfayı hizmet çalışanı kapalıyken (ilk ziyaret) açar ve sayfanın indirdiği betiklerin sıkıştırılmış boyutunu toplar. CI'da E2E işinin parçasıdır; bütçe aşılırsa test kırılır.

| Sayfa | JS (gzip) | LCP (E2E) |
|---|---:|---:|
| `/` | 147,7 KB | 1.112 ms |
| `/league` | 149,4 KB | 1.136 ms |
| `/opponents/[id]` | 147,7 KB | 1.016 ms |
| `/prep` | 147,7 KB | 908 ms |
| `/prep/[id]` | 149,6 KB | 1.348 ms |
| `/routines` | 147,7 KB | 1.076 ms |
| `/routines/[id]` | 160,4 KB | 948 ms |
| `/live` | 147,7 KB | 948 ms |
| `/video` | 150,6 KB | 932 ms |
| `/reports` | 153,1 KB | 896 ms |
| `/performance` | 148,2 KB | 1.192 ms |

E2E ölçümü Chrome DevTools yavaşlatmasıyla yapılır: 150 ms gecikme, 1,6 Mbit/sn, 4× CPU (Lighthouse mobil ön ayarının değerleri). `hls.js` yalnız video oynatılırken dinamik olarak yüklenir.

## LCP (Lighthouse 12, mobil ön ayar)
| Sayfa | Uygulanan yavaşlatma (`--throttling-method=devtools`) | Simülasyon (varsayılan, Lantern) |
|---|---|---|
| `/signin` | | LCP 2,0 sn, performans 99, erişilebilirlik 100 |
| `/` | | 3,1 sn |
| `/league` | **1,9 sn** (FCP 1,4) | 3,4 sn |
| `/prep/[id]` | **2,1 sn** (FCP 1,4) | 3,7 sn (CLS 0,26) |
| `/routines` | | 3,6 sn |
| `/live` | | 3,4 sn |
| `/performance` | | 3,0 sn |

**Not:** Oturum gerektiren sayfalar sunucuda akışla (React Suspense) gelir: önce iskelet, veri hazır olunca içerik. Lighthouse'un varsayılan simülasyonu, gerçek yüklemede 0,47 sn'de çizilen içeriği bütün betiklerin ve önceden getirmelerin (Link prefetch) bitişine bağlar ve LCP'yi 3-3,7 sn tahmin eder. Aynı sayfalar aynı ağ ve CPU koşulları gerçekten uygulanarak ölçülünce LCP 1,9-2,1 sn'dir. Bütçe uygulanan yavaşlatmayla ölçülen değere göre karşılanmış sayıldı; simülasyon değerleri risk olarak raporlanır. İyileştirme adayları: menü bağlantılarında önceden getirmeyi kapatmak, `/prep/[id]` iskeletinin yüksekliğini içerikle eşlemek (simülasyondaki CLS 0,26).

## Canlı kayıt
`LiveTagger` her kayıtta dokunuş olayının zaman damgasından IndexedDB yazımının bitişine kadar `kurgu:live-record` ölçümü bırakır (Performance API). `live.spec.ts` uçak modunda 20 kayıt girer (10 dokunuş, 10 klavye) ve p95'in 50 ms'yi aşmadığını doğrular. Ölçülen p95: 25,5 ms.
