# ADR-0005: OIDC ile kimlik doğrulama ve RBAC

- **Durum:** Önerildi · 30.09.2026
- **İlgili:** SPEC §9.1, §12.1-12.2; §20.3 (açık soru)

## Bağlam
Kulüpler kurumsal kimlik kullanır (Microsoft 365 / Google Workspace; hangisi olduğu açık soru). Yerelde bağımlılıksız çalışan bir kimlik sağlayıcı gerekir. 8 rol var (SPEC §12.1); admin, medical ve performance için MFA zorunlu.

## Karar
- **Protokol OIDC** (Authorization Code + PKCE). Yerelde **Keycloak** (docker compose, `kurgu` realm'i JSON olarak repoda, gizli değer içermeden), canlıda Entra ID ya da Google. Kod sağlayıcıya özgü değildir; yalnızca `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` değişir.
- **Web:** Auth.js v5 oturumu yönetir (HTTP-only, `SameSite=Lax` çerez). Erişim token'ı kısa ömürlü (5-15 dk), yenileme token'ı ile yenilenir. Token tarayıcı JS'ine verilmez; API çağrıları Next.js sunucu tarafından ya da Route Handler vekiliyle Bearer eklenerek yapılır.
- **API:** JWT imzası JWKS ile (önbellekli), `iss`, `aud`, `exp` doğrulanır. Kimlik = `sub` + `iss`; ilk girişte `users` satırı oluşturulur.
- **Yetki Kurgu'da tutulur, IdP'de değil.** Roller `memberships (user_id, tenant_id, role, player_id)` tablosundadır; böylece kulübün IdP'sinde grup düzeni bilmemiz gerekmez. Bir kullanıcı birden çok kiracıda farklı rollere sahip olabilir. Keycloak'taki test kullanıcıları yalnızca giriş için vardır; roller `make seed` ile `memberships`e yazılır.
- **İzin denetimi:** SPEC §12.1 matrisi koda tek bir `permissions.py` sözlüğü olarak girer; uçlar `require(Permission.X)` bağımlılığıyla korunur. Matris için tablo tabanlı test yazılır (her rol × her izin).
- **`GET /me`:** kullanıcı, üyelikler, seçili kiracı ve rol listesi döner (Faz 0 kabul kriteri).
- **MFA:** IdP'de zorlanır; API, admin/medical/performance rolleri için token'da `amr`/`acr` içinde MFA kanıtı arar (yerelde bayrakla kapatılabilir).
- **Oyuncu rolü:** `memberships.player_id` ile kendi kaydına bağlıdır; "kendi verisi" kuralı hem izin katmanında hem RLS'ye ek bir politikayla uygulanır.

## Sonuçlar
- **Artı:** Kulübün IdP'si ne olursa olsun yapılandırmayla bağlanır (SSO P1 kolaylaşır).
- **Artı:** Rol yönetimi Kurgu admin ekranında; IdP yöneticisine bağımlılık yok.
- **Eksi:** Keycloak yerelde ağır (~500 MB bellek). Kabul edilebilir; testlerde JWT'ler yerel anahtarla üretilir, Keycloak yalnızca e2e ve `make dev`'de çalışır.
- **Eksi:** SCIM olmadan kullanıcı kapatma IdP ile senkron değildir (P2); token süresi kısa tutularak risk sınırlanır.

## Değerlendirilen seçenekler
- **Kendi parola sistemimiz:** Güvenlik ve MFA yükü, kurumsal SSO'ya uyumsuz. Reddedildi.
- **Rolleri IdP gruplarından okumak:** Her kulübün IdP düzeni farklı. Reddedildi.
