# ADR-0002: PostgreSQL 16 ve RLS ile çok kiracılık

- **Durum:** Önerildi · 30.09.2026
- **İlgili:** SPEC §10, §12, §18; CLAUDE.md "Güvenlik"

## Bağlam
v1 tek kulüp için dağıtılır, ancak şema en fazla 20 kiracıyı desteklemeli. Kulüp verisi (rutinler, öneri kararları, canlı kayıt, sağlık) kesinlikle izole olmalı. Lig verisi ise lisans kapsamındaki kiracılar arasında paylaşılır. Uygulama kodundaki bir `WHERE tenant_id = ...` unutkanlığı veri sızıntısına dönüşmemeli.

## Karar
- **Tek veritabanı, paylaşılan şema, satır düzeyi güvenlik (RLS).**
- Kiracıya ait her tabloda `tenant_id uuid not null`, `enable row level security` **ve** `force row level security`, ve politika:
  `using (tenant_id = current_setting('app.tenant_id', true)::uuid)` + aynı ifadeyle `with check`.
- Ayar yoksa `current_setting(..., true)` null döner ve politika hiçbir satırı göstermez (güvenli varsayılan).
- API her istekte işlemi açar ve `SET LOCAL app.tenant_id = :tid` çalıştırır; kiracı JWT'deki üyelikten ve seçili kulüpten gelir. Bunu bir SQLAlchemy oturum bağımlılığı yapar; elle çağrılmaz.
- **Roller:** `kurgu_owner` (tabloların sahibi, göçleri çalıştırır), `kurgu_app` (uygulama, `NOBYPASSRLS`, sahip değil), `kurgu_worker` (worker; kiracıya özgü işlerde yine `SET LOCAL` kullanır). Süper kullanıcı uygulamada kullanılmaz.
- **Paylaşılan lig verisi** (`competitions`, `seasons`, `teams`, `players`, `matches`, `events`, `team_season_stats`, `standings_snapshots`): `tenant_id` null. Okuma politikası: `exists (select 1 from data_licenses l where l.tenant_id = current_setting('app.tenant_id', true)::uuid and l.source = <tablonun source'u>)`. Yazma yalnızca worker/ingestion rolüne açık.
- **Materialized view'ler RLS taşımaz.** Bu yüzden kiracıya özgü MV'ler (`mv_routine_stats`) doğrudan sorgulanmaz; üstüne `tenant_id` filtresi zorunlu olan `security_barrier` bir görünüm ya da service katmanı fonksiyonu konur. Lig MV'leri yalnızca lisanslı kaynaklardan beslenir.
- Hassas alanlar (Hooper, sağlık notları) `pgcrypto` değil **uygulama düzeyinde zarf şifrelemeyle** saklanır (anahtar KMS / yerelde anahtar dosyası); veritabanı düz metni hiç görmez.
- `audit_log` yalnızca ekleme: `kurgu_app` rolüne `update`/`delete` yetkisi verilmez.

## Doğrulama
- Kiracılar arası erişim testi: A kiracısıyla oluşturulan satır B kiracısıyla okunduğunda boş liste, doğrudan kimlikle istendiğinde 404/403 döner (Faz 1 kabul kriteri).
- Her yeni tablo için bir "RLS açık mı" meta testi: `pg_class.relrowsecurity` ve `relforcerowsecurity` kiracı tablolarında true olmalı.

## Sonuçlar
- **Artı:** İzolasyon veritabanında zorlanır; unutulan filtre sızıntı değil boş sonuç üretir.
- **Artı:** 20 kiracı için tek şema yeterli; göçler bir kez çalışır.
- **Eksi:** Bağlantı havuzunda `SET LOCAL` zorunluluğu (işlem dışı sorgu yasak). Test ve lint ile korunur.
- **Eksi:** MV'ler için ek katman gerekir.

## Değerlendirilen seçenekler
- **Kiracı başına veritabanı / şema:** 20 kiracıda yönetilebilir ama göç, MV ve paylaşılan lig verisi karmaşıklaşır. Reddedildi.
- **Yalnız uygulama filtresi:** Tek hata sızıntıya dönüşür. Reddedildi.
