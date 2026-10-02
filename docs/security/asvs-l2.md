# OWASP ASVS 4.0.3 Düzey 2 kontrol listesi

- **Kapsam:** Kurgu web (`apps/web`), API (`apps/api`), worker, PostgreSQL, Redis, nesne deposu, Keycloak yapılandırması (`infra/keycloak/kurgu-realm.json`).
- **Tarih:** 01.10.2026 (Faz 8). Gözden geçiren: geliştirme ekibi. Bağımsız sızma testi yapılmadı; canlıya çıkıştan önce önerilir.
- **Durum:** ✅ karşılanıyor · 🟡 kısmen (açık iş var) · ➖ kapsam dışı ya da başka sistemin sorumluluğu.

Her bölüm ASVS'nin ilgili denetimlerini özetler. Kanıt sütunu kodu, testi ya da belgeyi gösterir.

## V1 Mimari ve tehdit modeli
| Denetim | Durum | Kanıt |
|---|---|---|
| Güvenlik mimarisi belgeli, bileşenler ve güven sınırları tanımlı | ✅ | `docs/SPEC.md` §12, ADR-0001 (modüler monolit), ADR-0002 (RLS), ADR-0005 (OIDC), ADR-0016 |
| Erişim denetimi tek noktada uygulanır | ✅ | `identity/deps.py` yetki bağımlılıkları; veritabanında RLS (ADR-0002), `test_permissions.py`, `test_rls.py` |
| Modül sınırları zorlanır | ✅ | `lint-imports` (CI "Module boundaries") |
| Tehdit modeli | 🟡 | SPEC §12 riskleri listeler; ayrı STRIDE belgesi yok. Canlı öncesi yazılacak. |

## V2 Kimlik doğrulama
| Denetim | Durum | Kanıt |
|---|---|---|
| Kimlik doğrulama tek bir güvenilir sağlayıcıda (OIDC) | ✅ | Keycloak 26, ADR-0005; Kurgu parola saklamaz |
| Kaba kuvvet koruması | ✅ | Realm `bruteForceProtected: true`, `failureFactor: 5` (`docs/runbooks/deploy.md`) |
| Ayrıcalıklı roller için çok faktörlü doğrulama | ✅ | admin, medical, performance rolleri `acr=2`/TOTP ister; API 403 `mfa-required` (ADR-0016), `test_security.py`, `e2e/security.spec.ts` |
| Parola politikası (≥ 12 karakter, kullanıcı adı içermez) | 🟡 | Geliştirme realm'inde politika yok (geliştirme kimlikleri kısa parolalı). Üretimde Keycloak'ta `length(12) and notUsername and notEmail` ayarlanır: `docs/runbooks/deploy.md`. |
| Kurtarma ve sıfırlama | ✅ | Yalnız yönetici sıfırlaması; kimlik başka kanaldan doğrulanır (`docs/runbooks/users-mfa.md`) |

## V3 Oturum yönetimi
| Denetim | Durum | Kanıt |
|---|---|---|
| Oturum belirteci sunucu tarafında imzalı ve şifreli, tarayıcıda okunamaz | ✅ | Auth.js JWT oturumu şifreli, `httpOnly` çerezde (`apps/web/src/auth.ts`); `AUTH_SECRET` yalnız `.env` |
| Çerez bayrakları | ✅ | `httpOnly`, `sameSite=lax`, HTTPS'te `secure` (`apps/web/src/lib/actions.ts`) |
| Kısa ömürlü erişim belirteci, yenileme | ✅ | `accessTokenLifespan: 600`, yenileme hatası oturumu düşürür (`auth.ts`) |
| Boşta kalma ve çıkış | ✅ | `ssoSessionIdleTimeout: 36000`; çıkış Keycloak oturumunu da kapatır, sonraki giriş parola ister (`auth.ts` `events.signOut`, `e2e/security.spec.ts`) |

## V4 Erişim denetimi
| Denetim | Durum | Kanıt |
|---|---|---|
| Varsayılan reddet; her uçta rol denetimi | ✅ | `require_permission` bağımlılıkları; `test_permissions.py` rol matrisi |
| Kiracı yalıtımı (IDOR) | ✅ | Her kiracı tablosunda `tenant_id` + RLS (FORCE); istek başına `SET LOCAL app.tenant_id`; `test_rls.py`, `test_rls_data.py` |
| Sağlık ve iyi oluş verisine erişim denetimli | ✅ | Her okuma `audit_log`'a yazılır; `audit_log` yalnız ekleme (`0002_data_core.py`) |
| Yönetim arayüzü MFA arkasında | ✅ | V2 |

## V5 Doğrulama, temizleme ve kodlama
| Denetim | Durum | Kanıt |
|---|---|---|
| Tüm girdi şemayla doğrulanır | ✅ | Pydantic v2 modelleri; hatalar RFC 9457 (`core/problems.py`, `test_problems.py`) |
| SQL enjeksiyonu | ✅ | Parametreli sorgular (asyncpg/SQLAlchemy); dinamik tablo adları sabit listeden (ruff S608 notlu) |
| XSS | ✅ | React kaçışlama; `dangerouslySetInnerHTML` yok; nonce'lu CSP |
| LLM çıktısı güvenilmez girdi | ✅ | Metindeki her sayı girdi JSON'unda aranır, yoksa reddedilir (ADR-0013); çıktı düz metin olarak gösterilir |
| Komut enjeksiyonu | ✅ | ffmpeg, pg_dump, age argüman listesiyle çağrılır (kabuk yok); ffmpeg protokol ve biçim beyaz listesi (`video/hls.py`) |

## V6 Saklanan kriptografi
| Denetim | Durum | Kanıt |
|---|---|---|
| Hassas alanlar onaylı algoritmayla şifreli | ✅ | AES-256-GCM zarf şifreleme, kiracı başına veri anahtarı (ADR-0014, `core/crypto.py`) |
| Anahtar yönetimi ve döndürme | ✅ | `KURGU_DATA_KEYS` anahtarlığı, `kurgu-keys generate|rewrap` (`docs/runbooks/keys.md`, `test_crypto.py`) |
| Yedekler şifreli | ✅ | `age` ile şifreli dökümler (ADR-0018, `test_backup.py`) |
| Rastgelelik | ✅ | `secrets`/`os.urandom`, Web Crypto (CSP nonce) |

## V7 Hata ve günlük kaydı
| Denetim | Durum | Kanıt |
|---|---|---|
| Hata yanıtları iç ayrıntı sızdırmaz | ✅ | problem+json; 500'de `internal-error` ve istek kimliği (`core/problems.py`) |
| Yapılandırılmış günlük, istek kimliği | ✅ | JSON log, `X-Request-ID` (ADR-0017, `core/logging.py`) |
| Günlükte sır ve kişisel veri yok | ✅ | Uygulama istek başlığı ve gövdesi loglamaz; Sentry `send_default_pii=False` ve `_scrub` (`core/observability.py`) |
| Güvenlik olayları denetim kaydında | ✅ | Giriş dışı tüm yetkili değişiklikler `audit_log`'da; saklama süresi kiracı ayarı (ADR-0019) |

## V8 Veri koruma
| Denetim | Durum | Kanıt |
|---|---|---|
| Kişisel veri envanteri ve saklama süreleri | ✅ | `/admin/privacy` envanter ve saklama; gece temizliği (`privacy/jobs.py`, ADR-0019) |
| Veri sahibi hakları (erişim, silme) | ✅ | JSON dışa aktarım, silme talebi akışı (`test_privacy.py`, `e2e/privacy.spec.ts`) |
| Hassas yanıtlar önbelleğe alınmaz | ✅ | Kendi kuralı olmayan her API yanıtı `Cache-Control: no-store`; dosya ve video yanıtları `private` (`core/security.py`, `test_security.py`); servis çalışanı API yanıtlarını önbelleğe almaz (ADR-0011) |
| Çevrimdışı cihaz verisi | 🟡 | Canlı kayıt kuyruğu IndexedDB'de şifresiz (yalnız duran top olayları, kişisel sağlık verisi yok). Kabul edilen risk (ADR-0004). |

## V9 İletişim
| Denetim | Durum | Kanıt |
|---|---|---|
| TLS 1.2+ ve HSTS | ✅ | Ters vekil TLS'i sonlandırır (`docs/runbooks/deploy.md`); HSTS staging ve üretimde (ADR-0016) |
| İç servis bağlantıları | ➖ | Tek sunucuda Docker ağı; dışarıya yalnız vekil açık |

## V10 Kötü amaçlı kod
| Denetim | Durum | Kanıt |
|---|---|---|
| Bağımlılık açıkları taranır | ✅ | CI "Security scans": pip-audit, osv-scanner, Trivy |
| Kilit dosyaları | ✅ | `uv.lock`, `pnpm-lock.yaml`; CI `--frozen` |
| Yasak ortam değişkenleri | ✅ | `scripts/check-forbidden-env.sh` |

## V11 İş mantığı
| Denetim | Durum | Kanıt |
|---|---|---|
| Kötüye kullanıma karşı hız sınırı | ✅ | Yükleme, video, rapor, brifing kovaları (`core/ratelimit.py`); LLM aylık istek ve token sınırı (`/admin/llm`) |
| Eşzamanlı düzenleme | ✅ | Rutinlerde sürüm çakışması denetimi (409); canlı kayıtta istemci kimliğiyle tekilleştirme |

## V12 Dosya ve kaynaklar
| Denetim | Durum | Kanıt |
|---|---|---|
| Boyut sınırları | ✅ | İçe aktarma ve video boyut sınırları; xlsx açılmış boyut 100 MB, en çok 2000 giriş (A-98) |
| İçerik türü doğrulaması | ✅ | xlsx zip imzası, CSV'de NUL bayt reddi, video ffprobe ile (`ingestion/imports.py`, `video/`) |
| Dosyalar web kökünde değil; imzalı, süreli adresler | ✅ | Nesne deposu + imzalı URL (`reports/router.py`) |
| Karantina | ✅ | İçe aktarımlar işlenene kadar karantinada |
| Virüs taraması | 🟡 | ClamAV yok. Yüklenen dosyalar yalnız ayrıştırılır, çalıştırılmaz ve başkasına dağıtılmaz; canlı öncesi değerlendirilecek. |

## V13 API ve web servisleri
| Denetim | Durum | Kanıt |
|---|---|---|
| Her uç kimlik ve yetki ister | ✅ | Sağlık ve metrik uçları dışında; `/metrics` `KURGU_METRICS_TOKEN` ister |
| CORS | ✅ | Yalnız web kaynağı izinli (`config.py`) |
| CSRF | ✅ | API taşıyıcı belirteç kullanır, çerez kabul etmez; web sunucu eylemleri Next.js kaynak denetimi + `sameSite=lax` |
| OpenAPI şeması güncel | ✅ | CI "OpenAPI schema is up to date" |

## V14 Yapılandırma
| Denetim | Durum | Kanıt |
|---|---|---|
| Sırlar repoda değil | ✅ | Yalnız `.env`; `.gitignore`, `.env.example` örnekleri boş |
| Güvenlik başlıkları | ✅ | CSP (nonce), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, COOP/CORP (`core/security.py`, `apps/web/src/lib/csp.ts`, `e2e/security.spec.ts`) |
| Üretimde hata ayrıntısı ve belge sayfası | ✅ | Staging ve üretimde `/docs` ve `/openapi.json` kapalı; 500 yanıtı yalnız istek kimliği taşır (`main.py`, `test_security.py`) |
| Konteyner sertleştirme | ✅ | Kök olmayan kullanıcı, Trivy misconfig taraması |

## Açık işler
1. Üretim Keycloak realm'inde parola politikası (V2).
2. Tehdit modeli belgesi (V1).
3. Yüklemeler için virüs taraması kararı (V12).
4. Bağımsız sızma testi.
