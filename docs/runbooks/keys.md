# Anahtar ve sır yönetimi

İlgili: ADR-0014 (alan şifreleme), ADR-0018 (yedek), CLAUDE.md "Güvenlik" ve "LLM".

Sırlar yalnız sunucudaki `.env` dosyasında (ya da bir sır yöneticisinden enjekte edilen ortam değişkenlerinde) durur; repoya, bilete, sohbete yazılmaz. `.env` dosyası `kurgu` kullanıcısına aittir ve `chmod 600`'dür.

## Envanter
| Sır | Ne korur | Kaybolursa | Döndürme sıklığı |
|---|---|---|---|
| `KURGU_DATA_KEYS` | İyi oluş zarflarının KEK'leri | Şifreli iyi oluş verisi **geri gelmez** | Yılda bir ya da şüphede |
| age özel anahtarı (kasada) | Veritabanı yedekleri | Yedekler açılamaz | Personel değişiminde |
| `AUTH_SECRET` | Web oturum çerezleri | Tüm oturumlar düşer (veri kaybı yok) | Yılda bir ya da şüphede |
| `OIDC_CLIENT_SECRET` | Web ↔ Keycloak | Giriş durur | Yılda bir |
| `KURGU_METRICS_TOKEN` | `/metrics` | Gözlem durur | Yılda bir |
| `KURGU_ANTHROPIC_API_KEY` | LLM brifingi | Brifing durur (PDF'ler etkilenmez) | Sağlayıcı politikasına göre |
| Veritabanı rol parolaları | PostgreSQL | Servisler bağlanamaz | Yılda bir |
| `S3_*`, `KURGU_SENTRY_DSN` | Depo, hata izleme | İlgili özellik durur | Yılda bir |

`ANTHROPIC_API_KEY` ve `ANTHROPIC_MODEL` adları hiçbir yerde kullanılmaz; CI `scripts/check-forbidden-env.sh` ile denetler.

## Veri anahtarı (`KURGU_DATA_KEYS`) döndürme
Biçim: virgülle ayrılmış `kid:base64` listesi; ilk anahtar yazar, diğerleri yalnız okur.
1. Yeni anahtar: `uv run kurgu-keys generate 2027-01` → çıktıyı kasaya kaydedin.
2. `.env`: yeni girdiyi listenin **başına** ekleyin, eskisini bırakın: `KURGU_DATA_KEYS=2027-01:...,2026-10:...`. API ve worker'ı yeniden başlatın. Yeni kayıtlar yeni anahtarla yazılır.
3. Eski zarfları yeni anahtara taşıyın (şifreli değer değişmez, yalnız DEK yeniden sarılır):
   `uv run kurgu-keys rewrap --admin-url "$DRILL_ADMIN_URL" --dry-run` ardından `--dry-run` olmadan. Her kulüp için `keys.rewrap` denetim kaydı yazılır.
4. Kontrol: `select scores->>'kid', count(*) from wellness_entries group by 1;` yalnız yeni kimliği göstermeli.
5. Bir sonraki başarılı yedek ve geri yükleme tatbikatından **sonra** eski anahtarı listeden çıkarın. Eski yedekler eski anahtarı ister: eski anahtar, en eski saklanan yedek süresi dolana kadar kasada kalır.

Anahtar sızıntısı şüphesinde aynı adımlar hemen uygulanır ve olay müdahalesi başlatılır ([incident.md](incident.md)).

## age yedek anahtarı döndürme
1. Yeni çift üretin (`age-keygen`), açık anahtarı `infra/backup/recipients.txt` dosyasına yazın. Geçiş süresince dosyada iki satır (eski ve yeni) bulunabilir; age her alıcı için şifreler.
2. Yeni anahtarla ilk tatbikat başarılı olunca eski açık anahtarı dosyadan çıkarın. Eski özel anahtar, eski yedeklerin saklama süresi bitene kadar kasada kalır.

## Diğer sırlar
- `AUTH_SECRET`: `openssl rand -base64 32`; değiştirince herkes yeniden giriş yapar.
- `OIDC_CLIENT_SECRET`: Keycloak yönetim konsolunda `kurgu-web` istemcisinin sırrını yeniden üretin, `.env`'e yazın, web'i yeniden başlatın. Yerelde realm içe aktarıldığı için Keycloak konteyneri yeniden oluşturulmalıdır (`docker compose ... up -d --force-recreate keycloak`).
- Veritabanı parolaları: `alter role kurgu_app password '...'`; `.env` ardından servisler yeniden başlatılır.
