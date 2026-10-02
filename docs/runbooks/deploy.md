# Dağıtım

İlgili: SPEC §14 (mimari), ADR-0012 (PDF), ADR-0016 (güvenlik), ADR-0017 (gözlem), A-99.

v1 tek kulüp için tek sunucuda (ya da küçük bir VM'de) docker compose ile çalışır; veritabanı yönetilen PostgreSQL 16 olabilir. Ortamlar: `staging` ve `production` (`KURGU_ENV`). İkisinde de güvenlik sertleştirmesi açıktır: HSTS, MFA zorunluluğu, veri anahtarı zorunluluğu.

## Ön koşullar
- Alan adı ve TLS sonlandırması (Caddy, nginx ya da yük dengeleyici). Uygulama yalnız HTTPS arkasında yayınlanır; `FORWARDED_ALLOW_IPS` ters vekilin adresine ayarlanır.
- `.env` sunucuda (bkz. [keys.md](keys.md)). Zorunlu: `KURGU_ENV`, `KURGU_DATA_KEYS`, `AUTH_SECRET`, `OIDC_*`, veritabanı parolaları, `S3_*`. İsteğe bağlı: `KURGU_SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `KURGU_METRICS_TOKEN`, `KURGU_ANTHROPIC_API_KEY` ve `KURGU_LLM_MODEL`.
- Yedekleme kurulmuş ve bir tatbikat geçmiş olmalı ([backup-restore.md](backup-restore.md)).

## Sürüm çıkarma
1. `main` dalında CI yeşil olmalı (Python, web, E2E, güvenlik taramaları).
2. Sürüm etiketi: `git tag vYYYY.MM.N && git push --tags`.
3. İmajlar: `docker build -f infra/docker/api.Dockerfile --target prod`, `infra/docker/web.Dockerfile --target prod`. Worker aynı API imajıyla `arq kurgu_api.worker.WorkerSettings` komutuyla çalışır.
4. Dağıtımdan önce yedek: `make backup` (manifesti kontrol edin).
5. Göç: `docker compose run --rm migrate` (Alembic `upgrade head`). Göçler geri alınabilir yazılır, ama üretimde geri alma veri kaybettirebilir; geri almadan önce onay ve yedek gerekir.
6. Servisler: `docker compose up -d api worker web`. API, `KURGU_API_WORKERS` (varsayılan 2) uvicorn işçisiyle başlar.
7. Duman testi:
   - `curl -fsS https://<alan>/api/v1/readyz` → `{"status":"ok"}`.
   - Tarayıcıda giriş (MFA'lı bir yönetici hesabıyla), `/prep` ve bir PDF raporu.
   - `/metrics` (token ile) istek sayaçlarını gösteriyor.
8. Ürün içeriği değiştiyse: `uv run kurgu-seed --templates` ve `--rules` (idempotent).

## Geri dönüş
- Kod hatası, şema değişmediyse: önceki etiketin imajlarıyla `docker compose up -d`.
- Göç içeren sürüm: önce önceki imaja dönün; şemayı geri almak gerekiyorsa `alembic downgrade <revizyon>` **yalnız onayla** ve yedekten sonra. Veri kaybı riski varsa geri alma yerine ileri düzeltme tercih edilir.

## Ortam ayarları
| Ayar | staging | production |
|---|---|---|
| `KURGU_ENV` | `staging` | `production` |
| MFA (yönetici, sağlık, performans) | zorunlu | zorunlu |
| `KURGU_LLM_BACKEND` | `fake` ya da gerçek | gerçek (anahtar varsa) |
| Sentry örnekleme | %100 | hatalar %100, izler %10 |
| Yedek | günlük | günlük + WAL-G |

## Keycloak
Realm `infra/keycloak/kurgu-realm.json` dosyasından yalnız ilk açılışta içe aktarılır. Realm dosyasındaki değişiklikler (akış, parola politikası) var olan kurulumda yönetim konsolundan uygulanır ya da Keycloak konteyneri `--force-recreate` ile yeniden oluşturulur (yalnız yerelde; üretimde kullanıcılar silinir). Kaba kuvvet koruması: 5 hatalı denemede 60 sn'den başlayıp 15 dk'ya kadar kilit.

**Üretimde parola politikası (ASVS V2.1):** geliştirme realm'inde kısa geliştirme parolaları yüzünden politika yoktur. Canlıya çıkmadan önce yönetim konsolunda `kurgu` realm → Authentication → Policies → Password policy: `length(12) and notUsername and notEmail and passwordHistory(3)`.
