# Yerel geliştirme

## İlk kurulum
1. BASLANGIC.md §1-2'deki araçları kurun. Sonra repo kökünde: `make doctor`.
2. `make dev` çalıştırın. `.env` yoksa `.env.example`'dan oluşturulur, tüm servisler ayağa kalkar ve sağlık kontrolleri beklenir. İlk çalıştırma imajları indirdiği için uzun sürer.
3. Tarayıcıda http://localhost:3000 adresini açın ve "Giriş yap"a basın.

## Test kullanıcıları (yalnız yerel)
Parola: `.env` içindeki `KURGU_DEV_USER_PASSWORD` (varsayılan `change-me-dev-user`).

| Kullanıcı adı | Rol |
|---|---|
| `admin` | Yönetici |
| `head-coach` | Teknik direktör |
| `sp-coach` | Duran top antrenörü |
| `analyst` | Analist |
| `performance` | Performans antrenörü |
| `medical` | Sağlık ekibi |
| `player` | Oyuncu |
| `viewer` | İzleyici |

Hepsi `Trabzonspor (demo)` kiracısının üyesidir. Kullanıcılar `infra/keycloak/kurgu-realm.json`, üyelikler `kurgu-dev-identities` ile oluşturulur (`make dev` bunu otomatik çalıştırır).

## Adresler
| Servis | Adres |
|---|---|
| Web | http://localhost:3000 |
| API ve belgeler | http://localhost:8000/api/v1/docs |
| Keycloak | http://keycloak.localhost:8080 (yönetici: `.env` içindeki `KEYCLOAK_ADMIN`) |
| MinIO konsolu | http://localhost:9001 |
| Mailpit | http://localhost:8025 |

Keycloak'ın adresi `keycloak.localhost`'tur: tarayıcı ve konteynerler aynı adresi kullanır, böylece token'daki `iss` alanı her yerde aynı kalır. Chrome, Edge ve Firefox `*.localhost` adreslerini kendiliğinden 127.0.0.1'e çözer.

## Sık işler
- Testler: `make test` (PostgreSQL ve Redis `make dev` ile açık olmalı). Uçtan uca: `make e2e`.
- Göç: `make migrate`. Döngü kontrolü: `make migrate-cycle`.
- API şeması değişti: `make openapi` ve üretilen dosyaları commit edin.
- Sıfırdan başlamak (veriyi siler): `docker compose --env-file .env -f infra/docker-compose.yml down -v`. Bu komut veritabanını siler; yalnızca yerelde kullanın.

## Sorunlar
- **Port dolu:** `.env` içinde ilgili `*_PORT` değerini değiştirin. Keycloak portunu değiştirirseniz tarayıcıdaki adres de değişir.
- **Giriş sonrası hata sayfası:** `make logs` ile `api` ve `keycloak` loglarına bakın. En sık neden, `.env` içindeki `OIDC_CLIENT_SECRET` değerinin Keycloak ilk açıldıktan sonra değiştirilmesidir; realm yalnızca ilk açılışta içe aktarılır. Çözüm: Keycloak konteynerini yeniden oluşturun (`docker compose ... up -d --force-recreate keycloak`).
- **Dosya değişikliği algılanmıyor:** Proje `/mnt/c/...` altındaysa `~/projects/kurgu` altına taşıyın.
