# ADR-0017: Gözlemlenebilirlik

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §17; A-91

## Bağlam
SPEC OpenTelemetry iz takibi, Sentry, `/healthz` ve `/readyz` uçları ve iş kuyruğu metrikleri ister. Yerel ve CI ortamında toplayıcı (collector) ya da Sentry projesi yoktur. Sağlık verisi işlendiği için hata raporlarına kişisel veri sızmamalıdır.

## Karar
- OpenTelemetry SDK'sı API ve worker'da yalnız `OTEL_EXPORTER_OTLP_ENDPOINT` tanımlıysa başlatılır. Standart `OTEL_*` değişkenleri (servis adı, örnekleme) geçerlidir. Otomatik araçlama: FastAPI, SQLAlchemy, Redis, HTTPX.
- Sentry yalnız `KURGU_SENTRY_DSN` tanımlıysa başlatılır. `send_default_pii=False` ayarlanır, istek gövdeleri gönderilmez, ortam adı `KURGU_ENV` olur.
- Her isteğe `X-Request-ID` verilir; gelen değer geçerliyse korunur. Değer yanıta ve yapılandırılmış JSON loglara eklenir. İz kimliği de loglara yazılır.
- `/metrics` Prometheus metin biçiminde istek sayısı ve süre histogramı (rota şablonuna göre), Arq kuyruk derinliği, tamamlanan ve başarısız iş sayısını yayınlar. Uç `KURGU_METRICS_TOKEN` taşıyıcı token'ıyla korunur. Token tanımlı değilse uç 404 döner.

## Sonuçlar
- Gözlem bileşenleri isteğe bağlıdır; yapılandırılmadığında maliyet ve bağımlılık yoktur.
- Web istemcisindeki hatalar bu fazda merkezi olarak toplanmaz. Bu bir risk olarak raporlanır.
