# ADR-0016: Güvenlik başlıkları, hız sınırı ve MFA adım yükseltme

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §12.2; A-88, A-89, A-90

## Bağlam
SPEC §12.2 güvenlik başlıklarını, oturum açma ve yükleme uçlarında hız sınırını ve admin, medical, performance rolleri için MFA'yı şart koşar. Parola girişi Keycloak'ta yapılır; roller ise Kurgu veritabanında kiracı üyeliği olarak tutulur. Keycloak hangi kullanıcının hangi kiracıda hangi rolde olduğunu bilmez.

## Karar
- **CSP:** Web, `proxy.ts` içinde her istek için rastgele bir nonce üretir ve `script-src 'self' 'nonce-…' 'strict-dynamic'` içeren bir CSP gönderir. Next.js nonce'u kendi betiklerine ekler. Satır içi stil, Next.js ve Tailwind gereği `style-src 'self' 'unsafe-inline'` ile izinlidir. API JSON döndürdüğü için `default-src 'none'` kullanır.
- **HSTS:** Yalnız `staging` ve `production` ortamında gönderilir (`max-age=31536000; includeSubDomains`).
- **Hız sınırı:** API'de Redis üzerinde sabit pencereli sayaç (`INCR` + `EXPIRE`) kullanılır. Anahtar kova adı ve kullanıcı kimliğidir. Sınır aşılınca 429 problem+json ve `Retry-After` döner. Redis yoksa sınır açık başarısız olur, çünkü sınır kötüye kullanımı yavaşlatmak içindir ve erişilebilirliği düşürmemelidir. Parola denemeleri Keycloak'ın kaba kuvvet korumasıyla sınırlanır.
- **MFA:** API, rolü MFA gerektiren kullanıcının token'ında MFA kanıtı arar (`acr` 2 ya da `amr` içinde `otp`). Yoksa 403 `mfa-required` döner. Web bu yanıtı alınca Keycloak'a `acr_values=2` ile yeniden yönlendirir. Keycloak tarayıcı akışı iki düzeyli (Level of Authentication) koşullu akıştır: düzey 1 parola, düzey 2 TOTP. Böylece MFA yalnız gereken kullanıcıdan istenir ve Keycloak'ta rol eşlemesi gerekmez.

## Sonuçlar
- MFA rolü olan kullanıcı ilk girişte iki kez yönlendirilir (parola, sonra TOTP). Keycloak oturumu sürdükçe tekrar sorulmaz.
- Denetim `staging` ve `production` ortamında kapatılamaz. Geliştirmede kiracı ayarıyla açılır.
- Satır içi stil izni kalır. Stil enjeksiyonu riski düşük kabul edildi; betik enjeksiyonu nonce ile kapatıldı.
