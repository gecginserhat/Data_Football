# Olay müdahalesi

İlgili: ADR-0017 (gözlem), ADR-0019 (KVKK), [keys.md](keys.md), [backup-restore.md](backup-restore.md).

## Önem dereceleri
| Derece | Örnek | İlk yanıt |
|---|---|---|
| S1 | Veri sızıntısı şüphesi, kiracılar arası erişim, giriş tamamen kapalı, maç günü canlı kayıt çalışmıyor | Hemen; kulüp yöneticisi ve sorumlu geliştirici |
| S2 | Rapor/PDF ya da video işleme durdu, API p95 > 1 sn | Aynı gün |
| S3 | Tek sayfada hata, görsel kusur | Sonraki sürüm |

Maç günü kuralı: canlı kayıt çevrimdışı çalışır (PWA). Sunucu kapalıysa analistler kayda devam eder; kuyruk bağlantı gelince bir kez gönderilir. Maç sırasında dağıtım yapılmaz.

## İlk 15 dakika
1. Olay kaydı açın: zaman, belirti, etkilenen kulüp ve kullanıcılar, olay sorumlusu.
2. Durum: `GET /readyz` (veritabanı, Redis), `docker compose ps`, `docker compose logs --since 30m api worker web`.
3. Metrikler (`/metrics`): `kurgu_http_requests_total{status=~"5.."}`, `kurgu_http_request_duration_seconds`, `kurgu_queue_depth`, `kurgu_jobs_total{outcome="failed"}`.
4. İzleme: hata yanıtlarındaki `X-Request-ID` loglarda ve Sentry'de aynı istekle eşleşir; OpenTelemetry açıksa `trace_id` da loglarda yazar.

## Senaryolar
- **API 5xx artışı:** son dağıtımı geri alın ([deploy.md](deploy.md) "Geri dönüş"). Veritabanı bağlantısı doluysa `pg_stat_activity` ile uzun sorguları bulun.
- **Kuyruk birikiyor:** worker loglarına bakın; `kurgu_queue_depth` artıyor ve `kurgu_jobs_total` artmıyorsa worker'ı yeniden başlatın. PDF işleri Chromium'a, video işleri ffmpeg'e bağlıdır.
- **Giriş yapılamıyor:** Keycloak sağlığı, saat kayması (token `iat`/`exp`), `OIDC_CLIENT_SECRET` uyumu. Kilitlenen hesap için [users-mfa.md](users-mfa.md).
- **Hız sınırı şikâyeti (429):** `Retry-After` süresi bekletilir; meşru yoğun kullanımda sınırlar `core/ratelimit.py`'dedir (A-89) ve sürümle değişir.
- **Şüpheli erişim / sızıntı (S1):**
  1. İlgili hesapları Keycloak'ta devre dışı bırakın, oturumlarını sonlandırın.
  2. `audit_log` üzerinde kapsamı belirleyin: `select at, actor_id, action, entity, entity_id from audit_log where tenant_id = ... and at > ... order by at;` İyi oluş okumaları `wellness.read` olarak yazılır.
  3. Sır sızıntısı şüphesinde [keys.md](keys.md) adımlarıyla ilgili sırları döndürün.
  4. KVKK: kişisel veri ihlali Kişisel Verileri Koruma Kurulu'na öğrenildiği andan itibaren en geç **72 saat** içinde bildirilir; ilgili kişilere makul sürede bildirim yapılır. Bildirim kararını veri sorumlusu (kulüp) verir; teknik ekip kapsam ve zaman çizelgesini sağlar ([../compliance.md](../compliance.md)).
- **Veri bozulması ya da yanlış silme:** yazmaları durdurun, [backup-restore.md](backup-restore.md) "Gerçek geri yükleme". Geri yükleme noktasından sonraki kayıtlar (ör. canlı kayıt) cihazlarda kuyrukta duruyorsa yeniden gönderilir.

## Kapanış
Olay kapanınca 5 iş günü içinde suçlamasız bir değerlendirme yazılır: zaman çizelgesi, kök neden, ne iyi gitti, aksiyonlar (sahibi ve tarihiyle). Kişisel veri içermez.
