# İlerleme

**Durum:** Faz 0-4 tamam ve `main`'e birleşti (PR #1-#5, 01.10.2026). Faz 5 (canlı kayıt ve video) tamam; `faz-5-canli` dalında, birleştirme onayı bekliyor.
**Sonraki adım:** Faz 8 (sertleştirme).

Kurallar: Her görev küçük bir commit'tir (Conventional Commits, İngilizce). Her commit öncesi `make lint typecheck test` temiz olmalı. Bir görev SPEC §19 DoD'yi karşılamadan işaretlenmez. Faz sonunda kabul kriterleri işaretlenir ve kısa rapor verilir.

İlgili belgeler: [assumptions.md](assumptions.md) · [adr/](adr/)

---

## Faz 0: İskelet

### Kabul kriterleri (SPEC §19)
- [x] Monorepo, docker compose ve `make dev` tek komutla ayağa kalkar.
- [x] CI yeşil.
- [x] Keycloak ile giriş çalışır; `/me` rol döner.
- [x] Tasarım tokenları ve AppShell hazır; tüm rotalar boş durumda erişilebilir.

### Rapor
- **Yapıldı:** Tüm Faz 0 görevleri. Ayrıntı PR #1 açıklamasında.
- **Sapmalar:** MinIO resmi imajları Docker Hub'dan kalktığı için Chainguard MinIO derlemesi kullanılıyor. Yazı tipleri yerelden sunuluyor (A-21). Keycloak `keycloak.localhost` adında (A-22). shadcn/ui bileşenleri ertelendi (A-23).
- **Riskler:** Web geliştirme konteyneri (`make dev`) CI'da değil, üretim derlemesi test ediliyor; WSL'de ilk `make dev` denemesi geri bildirim için önemli.

### Görevler

**0.1 Repo temeli**
- [x] `git init`, `.gitattributes` (`* text=auto eol=lf`), `.gitignore`, `.editorconfig`. (LICENSE, sahibi karar verince eklenir.)
- [x] `CLAUDE.md`, `docs/` (SPEC, assumptions, adr, PROGRESS) ve `seed/` repoya eklenir.
- [x] `.env.example` (tüm portlar ve değişkenler, gizli değer yok; `KURGU_ANTHROPIC_API_KEY`, `KURGU_LLM_MODEL` boş). `.env` git dışı.
- [x] Sürüm sabitleme: `package.json#engines`, `packageManager: pnpm@10`, `.python-version` 3.12.

**0.2 JS monorepo**
- [x] `pnpm-workspace.yaml`, Turborepo (`turbo.json`: build, lint, typecheck, test).
- [x] Ortak `tsconfig.base.json` (strict), ESLint (flat config) + Prettier.
- [x] `packages/ui` (boş iskelet + tokenlar), `packages/pitch` (boş + `zones.json` yer tutucu), `packages/api-client` (üretim betiği).

**0.3 Python çalışma alanı**
- [x] `uv` workspace: `apps/api` ve `analytics/kurgu_analytics` paketleri.
- [x] ruff (lint + format), mypy `--strict`, pytest (+ pytest-asyncio, hypothesis).
- [x] `import-linter` modül sınırı sözleşmesi (ADR-0001), başlangıçta boş modüllerle.

**0.4 Altyapı (docker compose)**
- [x] `infra/docker-compose.yml`: postgres 16, redis 7, minio (+ bucket oluşturucu), keycloak 26 (realm içe aktarımıyla), mailpit, api, worker, web. Portlar `.env`'den.
- [x] Postgres ilk kurulum betiği: `kurgu_owner`, `kurgu_app` (NOBYPASSRLS), `kurgu_worker` rolleri (ADR-0002).
- [x] `infra/keycloak/kurgu-realm.json`: `kurgu-web` istemcisi (PKCE), 8 rol için test kullanıcıları (gizli değerler `.env`'den).
- [x] API ve web için geliştirme Dockerfile'ları (hot reload, volume mount; WSL'de dosya izleme için polling ayarı).
- [x] Sağlık kontrolleri ve `depends_on: condition: service_healthy`.

**0.5 Makefile**
- [x] `dev`, `down`, `test`, `lint`, `typecheck`, `e2e`, `migrate`, `seed` (Faz 1'de dolar), `openapi`.
- [x] `make doctor`: docker, node, pnpm, uv sürümlerini ve portları kontrol eder.

**0.6 API iskeleti**
- [x] FastAPI uygulaması, `/api/v1` öneki, ayarlar (pydantic-settings), yapılandırılmış JSON log.
- [x] RFC 9457 problem+json hata işleyicisi ve testi.
- [x] `/healthz`, `/readyz` (DB ve Redis kontrolü).
- [x] Async SQLAlchemy oturumu; istek başına işlem ve `SET LOCAL app.tenant_id` bağımlılığı (tablolar Faz 1'de).
- [x] Alembic kurulumu, boş ilk göç; `upgrade → downgrade → upgrade` döngü betiği.
- [x] Arq worker iskeleti ve bir `ping` işi (test edilir).

**0.7 Kimlik (ADR-0005)**
- [x] JWT doğrulama (JWKS önbelleği, `iss`/`aud`/`exp`). Testlerde yerel anahtarla imzalanmış token üreteci.
- [x] `users`, `tenants`, `memberships` tabloları (Faz 0'ın tek göçü; RLS'li).
- [x] `permissions.py` (SPEC §12.1 matrisi) ve rol × izin tablo testi.
- [x] `GET /api/v1/me`: kullanıcı, üyelikler, rol. Test: token yoksa 401 problem+json, geçerliyse rol döner.

**0.8 Web iskeleti**
- [x] Next.js 15 (App Router, React 19), Tailwind 4. shadcn/ui bileşenleri ilk gerektiği fazda eklenir (A-23).
- [x] Tasarım tokenları (SPEC §13.3; açık ve koyu tema), IBM Plex Sans / Condensed, tabular rakamlar.
- [x] next-intl (`tr` varsayılan, `en`), tüm metinler anahtarla.
- [x] Auth.js v5 + Keycloak; giriş/çıkış, oturum, token yenileme; API vekili (token tarayıcıya çıkmaz).
- [x] AppShell: masaüstünde koyu yeşil yan menü, mobilde alt sekme + çekmece; aktif kulüp göstergesi (amber).
- [x] SPEC §13.1'deki tüm rotalar `EmptyState` ile (ne yapılacağını söyleyen boş durum). Rol dışı rota 403 sayfası.
- [x] Ortak durum bileşenleri: iskelet (yükleniyor), EmptyState, ErrorState (tekrar dene), SampleSizeBadge, SourceBadge (Faz 2'de dolacak).
- [x] `packages/api-client`: OpenAPI'den `openapi-typescript` ile üretim; `make openapi`. `/me` bununla çağrılır.

**0.9 Test ve CI**
- [x] Vitest + Testing Library (AppShell, EmptyState).
- [x] Playwright duman testi: giriş (Keycloak) → AppShell → `/me` rolü görünür → her rota açılır. axe taraması (0 ciddi ihlal).
- [x] GitHub Actions: lint (ruff, eslint), typecheck (mypy, tsc), birim testler (Postgres servis konteyneriyle), göç döngüsü, OpenAPI farkı (üretilen istemci güncel mi), build, e2e (compose), pip-audit, osv-scanner, Trivy.
- [x] `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` adlarını yasaklayan grep kontrolü (assumptions A-14).

**0.10 Faz kapanışı**
- [x] `docs/demo/faz0/` ekran görüntüleri (Playwright ile).
- [x] CLAUDE.md "Komutlar" bölümü güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 1: Veri çekirdeği

### Kabul kriterleri (SPEC §19)
- [x] Şema, göçler ve RLS kurulu (kiracılar arası erişim testi 403/boş döner).
- [x] `make seed` tohum verisini yükler; Lig ve takım uçları tohum değerlerini birebir döner.
- [x] StatsBomb Open Data adaptörü ve SPADL dönüşümü çalışır.
- [x] Duran top çıkarımı ile doğrulama raporu hazır; `play_pattern` uyumu ≥ %95.
- [x] CSV içe aktarım sihirbazı ve kalite raporu çalışır; karantina akışı işler.

### Rapor
- **Yapıldı:** 1.1–1.10. Şema ve RLS (lig tabloları paylaşılan + kiracı satırı alabilen karma yapıda), tohum yükleme ve altın testler, StatsBomb adaptörü ve SPADL, duran top çıkarımı, doğrulama raporu, CSV/Excel içe aktarım API'si ve `/admin/imports` sihirbazı. Python 245 test, web birim 7 test, e2e 12 senaryo (masaüstü ve tablet) geçiyor.
- **Doğrulama:** 149 maçta tanım uyumlu `play_pattern` uyumu %99,5 (kabul ölçüsü, Serhat'ın kararı, A-30); ham uyum %74,3 yan yana raporlanıyor. Şut sonucu türetmesi StatsBomb ile %94,1 uyumlu (A-31).
- **Sapmalar:** kloppy ve socceraction yerine ince SPADL eşleyici; socceraction ile %100 tür uyumu (A-27). İçe aktarımda oyuncu adları oyuncu tablosuna eşlenmiyor, olayın `extra` alanında duruyor; takımlar var olan takımlara eşleniyor, yeni takım açılmıyor (A-32, A-33). Rota düzeyi `loading.tsx` Next 15.5 üretim derlemesindeki gezinme hatası yüzünden kaldırıldı (A-34).
- **Riskler:** Next 16'ya geçiş şartnamedeki yığını değiştirir, karar gerekiyor (A-34). Tohum dosyasında 7 takımın gol kırılımı tutmuyor, uyarı olarak raporlanıyor (A-02).

### Görevler

**1.1 Şema ve göçler (SPEC §10; ADR-0002)**
- [x] Paylaşılan lig tabloları: `competitions`, `seasons`, `teams`, `players`, `matches`, `standings_snapshots`, `team_season_stats`, `events`, `provider_id_map`, `data_licenses`, `raw_payloads`, `ingestion_runs`.
- [x] Kiracı tabloları (Faz 1'de boş kalanlar dahil, şema kırılmasın diye): `audit_log`, `set_pieces` (paylaşılan + kiracı kaynaklı ayrımıyla), `tagging_sessions`, `live_tags` (ADR-0004 alanları), `imports`.
- [x] RLS politikaları (`force row level security`), paylaşılan tablolar için `data_licenses` okuma politikası.
- [x] Meta test: tüm kiracı tablolarında RLS açık.
- [x] Kiracılar arası erişim testi: A'nın satırı B ile listede görünmez, kimlikle istenince 404 döner.
- [x] `audit_log` yalnızca ekleme testi (`kurgu_app` update/delete yapamaz).
- [x] Her göç geri alınabilir; CI döngüsü yeşil.

**1.2 Saha geometrisi ve bölgeler (SPEC §3.3, §4; ADR-0003)**
- [x] `packages/pitch/zones.json`: saha ölçüleri, referans noktaları, bölge eşikleri.
- [x] Python `kurgu_analytics.setpieces.zones` ve TS `packages/pitch` aynı dosyayı okur; ortak test vektörleri (`zones.vectors.json`) iki tarafta da geçer.
- [x] Koordinat dönüşümleri: StatsBomb 120×80 → 105×68 (y ekseni çevrilir), takım yönüne normalizasyon, `y' = y | 68 − y`. Referans nokta testleri.

**1.3 Tohum yükleme (`make seed`)**
- [x] Tohum JSON'ları için pandera / Pydantic şemaları.
- [x] `super_lig.json` → takımlar, sezonlar, 2025/26 `team_season_stats`, 2026/27 duran top verisi, puan durumu, sonuçlar, fikstür, lig kıyas değerleri. `source='seed:super_lig.json'`, `is_demo=false` (A-03).
- [x] Bütünlük kontrolleri raporu: kontrol 2 ve 3 hata verirse yükleme durur; kontrol 1 uyarı üretir ve `docs/validation/seed_integrity.md` yazılır (A-02).
- [x] Kiracılar: `Trabzonspor (demo)` ve `Test Kulübü`; `data_licenses` kayıtları; test kullanıcılarının `memberships` kayıtları (A-09, A-10).
- [x] Idempotent: `make seed` iki kez çalışınca satır sayısı değişmez.
- [x] `routine_templates.json` ve `recommendation_rules.json` şimdilik yalnızca şema doğrulamasından geçer (yükleme Faz 3 ve Faz 4).

**1.4 Lig ve takım uçları**
- [x] `GET /seasons/{id}/standings?week=`, `GET /seasons/{id}/team-metrics`, `GET /teams/{id}/profile?season=` (Faz 1'de yalnızca ham tohum değerleri; türetilmiş metrikler Faz 2).
- [x] Altın testler: uç yanıtları tohum değerleriyle birebir (ör. 6. hafta sonu AMD 13 puanla 1.; TS 2025/26 duran top golü 15; GÖZ duran top xG 15,4).
- [x] İmleç sayfalama, ETag.

**1.5 Ingestion çerçevesi (SPEC §5.2)**
- [x] Adaptör arayüzü (`Provider` protokolü: `list_matches`, `fetch_events`, `to_canonical`).
- [x] `raw_payloads` + MinIO'ya ham yük; `source_hash` ile idempotent yükleme.
- [x] `ingestion_runs` durum makinesi: `pending → running → succeeded | quarantined | failed`.
- [x] Worker işleri ve API'den tetikleme.

**1.6 StatsBomb Open Data adaptörü ve SPADL (ADR-0003)**
- [x] `make statsbomb-fetch`: seçili yarışmaları indirir, repoya eklemez (A-06). Atıf `docs/validation/` ve `/methodology` notuna yazılır.
- [x] (kloppy yerine ince eşleyici, A-27) ayrıştırma → SPADL → kanonik `events` (koordinat dönüşümü dahil). `play_pattern` `extra` alanına.
- [x] socceraction uyum kontrolü; uyumsuzsa ince SPADL eşleyici (A-16) ve ADR notu.
- [x] Oyuncu/takım kimlik eşleştirmesi `provider_id_map`'e (`provider='statsbomb'`).
- [x] Testler: bilinen bir maçta olay sayısı, gol sayısı ve birkaç örnek aksiyonun koordinatları.

**1.7 Duran top çıkarımı (SPEC §5.5)**
- [x] `setpieces/extract.py`: algoritma aynen; `WINDOW_S=20`, `PHASE1_S=5` ayarlanabilir.
- [x] Yardımcılar: `classify` (alt tür), `side_of`, `zone`, `is_touch`, `lost_possession`, `ball_left_final_third`, `derive_outcome`.
- [x] Penaltılar ayrı; duran top dizilerine girmez.
- [x] Birim testler: el yapımı küçük olay dizileriyle her dal (uzun taç filtresi, 2. faz geçişi, pencere dışı, yeni duran top ile kesilme, doğrudan serbest vuruş şutu).
- [x] hypothesis ile değişmezler: faz 1 + faz 2 xG = toplam; her şut en fazla bir diziye ait.
- [x] `set_pieces` tablosuna yazım (`source='provider'`).

**1.8 Doğrulama raporu (SPEC §5.5; A-07)**
- [x] Şut düzeyi karşılaştırma: çıkarım ↔ StatsBomb `play_pattern`.
- [x] `docs/validation/setpiece_extraction.md`: uyum oranı (hedef ≥ %95), tür bazında kırılım, karışıklık matrisi, uyumsuz örnekler ve nedenleri, kullanılan veri ve atıf.
- [x] Rapor üretimi `make validate` ile yeniden üretilebilir.

**1.9 CSV/Excel içe aktarım (SPEC §5.6; A-08)**
- [x] `POST /imports` (dosya; tür ve boyut doğrulaması), `GET /imports/{id}` (eşleştirme + kalite raporu), `POST /imports/{id}/commit`.
- [x] Sütun eşleştirme önerisi ve takım kimlik eşleştirme (bulanık, eşik altı elle onay). Oyuncu eşleştirme sonraki faza (A-33).
- [x] pandera kontrolleri: zorunlu alanlar, koordinat aralıkları, periyot/zaman tutarlılığı, yinelenenler, referans bütünlüğü, maç başına makul olay sayısı.
- [x] Kritik hata → `quarantined`; metriklere girmez. Düzeltip yeniden yükleme akışı.
- [x] Web: `/admin/imports` sihirbazı (yükle → eşleştir → rapor → işle), tüm durumlarla.
- [x] E2E (SPEC §16 akış 4'ün Faz 1 kısmı): CSV yükle → hata gör → düzelt → işle.

**1.10 Faz kapanışı**
- [x] `docs/demo/faz1/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 2: Metrikler ve analiz ekranları

### Kabul kriterleri (SPEC §19)
- [x] Metrik modülü formülleri ve testleriyle hazır.
- [x] Materialized view'ler yenileniyor.
- [x] Genel bakış, Lig ve Rakip analizi sayfaları tohum verisiyle doğru sayıları gösterir (2025/26 lig duran top payı %20,4; Trabzonspor 15 duran top golüyle 1.; Göztepe 15,4 duran top xG'si ile 1.).
- [x] Az veri rozeti ve kaynak rozetleri görünür.

### Rapor
- **Yapıldı:**
  - Next 16'ya geçildi ve yükleniyor ekranı geri geldi (ADR-0006).
  - Metrik modülü hazır: 22 metrik, beta-binom ve gamma-Poisson büzülmesi, lig sırası, az veri bayrağı.
  - Metrik görünümleri eklendi; tohum ve sağlayıcı yüklemesinden sonra yenileniyor (ADR-0007).
  - Lig uçları genişletildi; kıyaslar, takım dizileri ve fikstür uçları eklendi.
  - Genel bakış, Lig ve Rakip analizi sayfaları hazır.
  - Altın değerler hem API testlerinde hem e2e'de doğrulanıyor: %20,4 (166/812), TS 15 golle 1., GÖZ 15,4 xG ile 1.
- **Sapmalar:**
  - Lig kıyasları materialized view'de değil, istek anında hesaplanıyor; formüller Python'da tek yerde kalsın diye (ADR-0007).
  - Ana sayfadaki öneri ve tehdit etiketleri Faz 4'e kaldı (A-38).
- **Riskler:**
  - Kulübün kendi kaydı paylaşılan değerin yerine geçiyor (A-36). İçe aktarımda yanlış bir dosya, kulübün gördüğü sıraları değiştirir. Kayıt, kaynak rozetiyle görünür kalıyor.
  - Profil çubuğu ve tablo bileşenleri şimdilik uygulama içinde; `packages/ui`'ye taşınması Faz 3'te.

### Görevler

**2.0 Yığın**
- [x] Next.js 16'ya geçiş, rota düzeyi yükleniyor ekranı geri geldi (ADR-0006, A-34 kapandı).

**2.1 Metrik modülü (`analytics/kurgu_analytics/metrics/`)**
- [x] Katalog: kimlik, tür (sayım, oran, maç başı, fark), birim, "dolaylı" bayrağı, kaynak gereksinimi (SPEC §6.1).
- [x] Türetilmiş takım metrikleri: duran top payı, gol eksi xG, maç başı oranlar, ilk temas %, dizi başına şut ve xG, ikinci faz payı, 100 kornere gol, yenilen DT golü (yalnız olay verisi ya da kulüp kaydı).
- [x] Büzülme: beta-binom (momentler yöntemiyle önsel, sonsal ortalama, %80 aralık) ve gamma-Poisson (maç başı sayımlar).
- [x] Lig sırası (eşitler aynı sıra) ve yüzdelik; az veri bayrağı (n < 8 ya da maç < 5).
- [x] Docstring (formül, birim, kaynak), birim testler ve `hypothesis` değişmezleri (fazların toplamı, oranlar [0, 1], sıralama tutarlılığı).

**2.2 Materialized view'ler**
- [x] `mv_team_setpiece_season` (olay verisinden takım-sezon ham toplamları) ve `mv_league_benchmarks` (lig toplamları). Yalnızca paylaşılan satırlar; lisans süzgeçli görünümle okunur. Formüller Python'da kalır (ADR-0007).
- [x] Yenileme işi (worker, `CONCURRENTLY`), yükleme ve tohumdan sonra tetiklenir; göç döngüsü testi.

**2.3 API**
- [x] `GET /seasons/{id}/team-metrics`: ham değerlere ek olarak türetilmiş metrikler, sıra, yüzdelik, büzülmüş değer, az veri ve kaynak.
- [x] `GET /seasons/{id}/benchmarks`: metrik başına lig en düşük, en yüksek, ortalama; lig toplamları ve referans kıyaslar.
- [x] `GET /teams/{id}/profile`: aynı metrik değerleri, kıyaslar ve form (G/B/M).
- [x] `GET /teams/{id}/set-pieces?season=&type=`: takımın duran top dizileri (imleçli).
- [x] `GET /fixtures?team=&from=`: yaklaşan maçlar (genel bakış için).

**2.4 Arayüz**
- [x] Bileşenler: KPI kartı, ProfileBar, DataTable (yapışkan ilk sütun, sıralama), FormChips (G/B/M), TeamBadge, SourceBadge, SampleSizeBadge, "dolaylı" etiketi.
- [x] `/league`: puan durumu, duran top tablosu, xG–gol dağılım grafiği; sezon seçimi.
- [x] `/opponents` ve `/opponents/[teamId]`: takım listesi; profil çubukları (lig en düşük–en yüksek, lig ortalaması ve kendi kulübümüz işaretli), sıra, kaynak ve dolaylı etiketleri.
- [x] `/`: kulüp durumu, duran top KPI'ları ve sıraları, sıradaki ve yaklaşan maçlar (rakibin DT sırasıyla).
- [x] Her bileşende yükleniyor, boş, hata ve az veri durumları; `tr` ve `en` metinleri.

**2.5 Doğrulama ve kapanış**
- [x] Altın kontroller (API ve e2e): %20,4 (166/812); TS 15 golle 1.; GÖZ 15,4 xG ile 1.
- [x] E2E ve axe; `docs/demo/faz2/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 3: Rutin kütüphanesi

### Kabul kriterleri (SPEC §19)
- [x] Editör: oyuncu (rolle), koşu, top yolu, perdeleme, ayna, geri al / yinele ve klavye desteği.
- [x] Sürümleme çalışır.
- [x] 7 şablon `seed/routine_templates.json` dosyasından yüklenir ve kütüphaneye eklenebilir.
- [x] PNG ve PDF dışa aktarım çalışır.

### Rapor
- **Yapıldı:** Diyagram v1 biçimi (TS ve Python, ortak test vektörleri), şablon yükleme, rutin API'si ve değişmez sürümler, `v_routine_stats`, PNG/PDF rutin kartı, `/routines` kütüphane ve şablonlar, editör (klavye, ayna, geri al/yinele, kareler, oynatma), sürüm geçmişi, geri yükleme ve karşılaştırma. E2E 24/24 (masaüstü ve tablet), Python 332, web 28, pitch 61 test.
- **Sapmalar:** `mv_routine_stats` yerine `security_invoker` görünüm (A-44). Rutin atamaları Faz 4'e (A-43). Editör her zaman yarım sahayı gösterir, kart görünümü kaleye yakınlaşır (A-45). Dışa aktarım API'de eşzamanlı üretilir (A-42).
- **Riskler:** Rutin performansı maç içi kayıt (Faz 5) rutin seçene kadar boş görünür. Koyu temada etkin düğme kontrastı (pri üstünde açık yazı) genel bir token sorunu; Faz 8 erişilebilirlik turunda ele alınmalı.

### Görevler

**3.1 Diyagram biçimi ve geometri (ADR-0008, A-39)**
- [x] Diyagram v1 şeması: oyuncular, çizgiler (koşu, top yolu, perdeleme), bölge vurguları, top ve kareler. Python'da Pydantic doğrulaması, TS'de tip.
- [x] `packages/pitch`: kavis kontrol noktası, ayna (sol/sağ), ızgaraya hizalama, kare enterpolasyonu, sürüm farkı; ortak test vektörleri Python ile.
- [x] `packages/pitch/roles.json`: rutin rolleri ve tr/en adları (SPEC §3.4 + şablon rolleri); web ve PDF aynı dosyayı okur.

**3.2 Şema ve şablonlar**
- [x] Göç `0004_routines`: `routine_templates` (paylaşılan), `routines`, `routine_versions` (değişmez), `set_pieces.routine_id` yabancı anahtarı, `v_routine_stats` (`security_invoker`). RLS ve izinler; göç döngüsü.
- [x] Şablon yükleme: `make seed` ve ortamdan bağımsız `kurgu-seed --templates` (A-40). 7 şablon v1 diyagramına çevrilir.

**3.3 API (SPEC §11)**
- [x] `GET /routine-templates`, `GET/POST /routines`, `POST /routines/from-template/{tplId}`, `GET/PUT/PATCH /routines/{id}`, `GET /routines/{id}/versions`, `GET /routines/{id}/versions/{v}`.
- [x] Sürümleme: her kayıt yeni değişmez sürüm; `base_version` ile çakışma 409; içerik aynıysa sürüm açılmaz; arşivleme (silme yok, A-41). Denetim kaydı.
- [x] Rutin performansı (SPEC §6.3): kullanım, ilk temas oranı, şut oranı, kullanım başına xG, gol; oranlar beta-binom büzülmesiyle (A-44).
- [x] Testler: izinler, kiracı izolasyonu, çakışma, doğrulama hataları (problem+json).

**3.4 Dışa aktarım (A-42)**
- [x] `kurgu_analytics.reports.routine_sheet`: diyagramdan PNG ve A4 PDF (başlık, saha, rol açıklaması, notlar, kareler). Saf fonksiyon, testli.
- [x] `GET /routines/{id}/versions/{v}/export?format=png|pdf`.

**3.5 Arayüz**
- [x] `/routines`: kütüphane (tür süzgeci, arşiv) ve şablonlar sekmesi (önizleme, "Kütüphaneye ekle"), yeni rutin.
- [x] `/routines/[id]` editörü: yarım saha SVG; oyuncu ekleme (takım ve rol), koşu, top yolu (kavisli, noktalı), perdeleme, bölge vurgusu; ızgara, ayna; geri al / yinele (zundo); klavyeyle seçme ve ok tuşlarıyla taşıma; özellik paneli.
- [x] Kare kare animasyon: kare ekleme, oyuncu ve top konumu, oynatma (`prefers-reduced-motion` desteği).
- [x] Sürüm geçmişi, eski sürümü görme, geri dönme (yeni sürüm olarak) ve iki sürümü karşılaştırma.
- [x] Dışa aktarım düğmeleri (PNG, PDF); yalnızca okuma yetkisi olanlar için salt okunur görünüm.
- [x] Yükleniyor, boş, hata durumları; `tr` ve `en` metinleri.

**3.6 Doğrulama ve kapanış**
- [x] E2E: şablondan ekle → düzenle (klavye, ayna, geri al) → kaydet → sürüm 2 → karşılaştır → PDF ve PNG indir; axe.
- [x] `docs/demo/faz3/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 4: Maç hazırlığı ve öneri motoru

### Kabul kriterleri (SPEC §19)
- [x] Kural değerlendirici güvenli (eval yok) ve testli.
- [x] `seed/recommendation_rules.json` yüklenir; deneme modu çalışır.
- [x] Öneriler kanıt ve güvenle gösterilir; kabul/red gerekçesi kaydedilir.
- [x] MD planı şablonları, sorumlu atama ve ilerleme çalışır.
- [x] Kabul testi: Trabzonspor seçiliyken 7. hafta Samsunspor deplasmanında en az şu iki öneri görünür: "Ceza sahası çevresinde faul kazanın" (rakip faul yapmada 4.) ve "Korner savunması haftanın öncelikli çalışması" (rakip korner/maç'ta 2.).

### Rapor
- **Yapıldı:** Güvenli kural değerlendirici (`kurgu_analytics.recs`, üç değerli mantık, güven, Türkçe biçimlendirici), göç `0005_prep`, varsayılan kural seti yükleme, hazırlık/karar/plan/kural seti/deneme uçları, `/prep`, `/prep/[fixtureId]`, genel bakışta sezon önerileri ve tehdit etiketleri, `/admin/rules`. Kabul testi API'de ve E2E'de geçiyor: SAM–TS 7. haftada "Korner savunması haftanın öncelikli çalışması" (yüksek güven, rakip 2.) ve "Ceza sahası çevresinde faul kazanın" (orta güven, rakip 4.) görünür. Python 389, web 31, pitch 61 test; E2E 28 geçti, 2 atlandı (karar ve kural yazan iki senaryo yalnız masaüstünde çalışır).
- **Sapmalar:** Öneriler saklanmaz, her istekte hesaplanır; yalnızca karar verilenler anlık görüntüyle yazılır (A-50). Oyuncu atamaları Faz 7'ye (A-53), öneri geri bildirimi Faz 5'e (A-54). Genel bakış ucu `/prep/overview` (A-55).
- **Riskler:** Rakip sıraları önceki sezondan geldiği için yeni sezonun ilk haftalarında güncel form yansımaz; güncel sezon değerleri eşleşme tablosunda ayrıca gösteriliyor. Demo kiracısında E2E her çalıştırmada iki kural seti sürümü yayımlar; geliştirme veritabanında geçmiş uzar.

### Görevler

**4.1 Değerlendirici (ADR-0009, A-47 … A-49)**
- [x] `kurgu_analytics.recs`: kural şeması (Pydantic), operatörler, `all`/`any`/`not`, `min_sample`, güven, şablon metinleri ve biçimlendiriciler (tr yerel ayar). `eval` yok; bilinmeyen yer tutucu kuralı geçersiz kılar.
- [x] Rutin kuralları rutin başına değerlendirilir; aynı şablona işaret eden önerilerde tekilleştirme; öncelik ve güvene göre sıralama.
- [x] Testler: tohum değerleriyle 25 kuralın tümü ayrıştırılır; kabul örneği (SAM: faul 4., korner/maç 2.) tetiklenir; eksik veri ve az veri yolları.

**4.2 Şema**
- [x] Göç `0005_prep`: `rule_sets` (kiracısız varsayılan + kulüp sürümleri), `recommendations`, `fixture_plans`, `plan_items`. RLS, izinler, göç döngüsü.
- [x] Varsayılan kural seti `make seed` ve `kurgu-seed --rules` ile yüklenir (idempotent).

**4.3 API (SPEC §11)**
- [x] Olgu derleme (A-46): önceki ve güncel sezon metrikleri, lig toplamları, rutin istatistikleri, savunma özeti.
- [x] `GET /fixtures/{id}/prep` (fikstür, öneriler, eşleşme notları, plan, sorumlu adayları), `POST /recommendations/{id}/decision` (kabul, red ve gerekçe, geri alma).
- [x] `POST /fixtures/{id}/plan` (şablondan), `POST /fixtures/{id}/plan/items`, `PATCH /plan-items/{id}`, `DELETE /plan-items/{id}`.
- [x] `GET/PUT /rule-sets/current`, `GET /rule-sets/versions`, `POST /rule-sets/dry-run`.
- [x] `GET /prep/overview` (genel bakış; SPEC'teki `/recommendations/season` yerine, A-55) ve yaklaşan maçlar için tehdit etiketleri (A-38).
- [x] Testler: izinler, kiracı izolasyonu, karar anlık görüntüsü, çakışma, kabul örneği.

**4.4 Arayüz**
- [x] `/prep`: kulübün yaklaşan maçları.
- [x] `/prep/[fixtureId]`: hücum, savunma ve denge öneri kartları (alan, öncelik, güven, neden, ne yapın, şablon bağlantısı, kanıt), kabul ve gerekçeli red, eşleşme notları, MD planı (şablon seçimi, sorumlu, durum, ilerleme çubuğu, madde ekleme).
- [x] Genel bakış: sezon önerileri ve yaklaşan rakiplerde tehdit etiketleri.
- [x] `/admin/rules`: kural listesi, eşik/öncelik/açma-kapama düzenleme, sürüm geçmişi, fikstür için deneme modu.
- [x] Yükleniyor, boş, hata ve az veri durumları; `tr` ve `en` metinleri.

**4.5 Doğrulama ve kapanış**
- [x] E2E: SAM–TS 7. hafta hazırlığında iki kabul önerisi → kabul (plana madde eklenir) → gerekçeli red → plan şablonu, sorumlu ve tamamlama → ilerleme; kural eşiği değiştir → deneme modu; axe.
- [x] `docs/demo/faz4/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

## Faz 5: Canlı kayıt ve video

### Kabul kriterleri (SPEC §19)
- [x] PWA kurulabilir. Uçak modu E2E testi geçer. Çoklu cihaz senkronizasyonu çalışır.
- [x] Video yükleme → HLS → klip → duran topa bağlama → rutin istatistiğinde klip görünür.

### Rapor
- **Yapıldı:** Göç `0006_live_video`; senkronizasyon uçları (maç başına tek oturum, toplu ve idempotent gönderim, son yazan ve silme kazanır, `since` ile çekme); kayıt → `set_pieces` ve metrik görünümü yenileme; imzalı parçalı video yükleme (S3/MinIO ve HMAC imzalı yerel depo), worker'da ffmpeg ile HLS, oynatma listesi, klipler. Web: PWA (bildirim, simgeler, hizmet çalışanı), `/live` ve tablet öncelikli kayıt ekranı (Dexie kuyruğu, kısayollar, 10 sn geri al, maç saati, iki cihaz), `/video` (yükleme ilerlemesi, durum, hls.js oynatıcı, klip kesme ve duran topa bağlama), rutin sayfasında klipler, hazırlık sayfasında maçtan geri bildirim paneli. Python 409, web 40, pitch 61, ui 5 test; E2E 34 geçti, 2 atlandı. Uçak modu testinde 20 kayıt çevrimdışı yazılıyor, sayfa çevrimdışı yenileniyor, çevrimiçine dönünce sunucuda tam 20 kayıt var ve yeniden gönderim kopya üretmiyor.
- **Sapmalar:** Çoklu cihaz bildirimi WebSocket yerine 5 sn çekmeyle (A-57). Hizmet çalışanı Serwist yerine elle yazıldı (ADR-0011). Tek tekil fikstür ucu eklendi (`GET /fixtures/{id}`). Maçın duran topları okuma izniyle açık (A-66). Kısayollarda SPEC'teki `1-6` yerine sekiz sonuç için `1-8` ve geri alma için `Z` (A-58).
- **Riskler:** Canlı kayıt A-36 gereği o takım-sezonun olay toplamlarını kulübün kendi kaydına çevirir; tek maç kaydedilmiş bir takımın değerleri ilk maçlarda "Az veri" ile görünür. Playwright'ın Chromium'u H.264 çözemediği için oynatma E2E'de yalnız teslim düzeyinde doğrulanıyor (A-65); gerçek Chrome, Edge ve Safari'de oynar. MinIO CORS ayarı (`MINIO_API_CORS_ALLOW_ORIGIN`) bu ortamda değil, CI'daki compose'da sınanacak. Uzun maç videolarının dönüştürme süresi ölçülmedi; iş süre sınırı 4 saat.

### Görevler

**5.1 Senkronizasyon (ADR-0004, A-56 … A-59)**
- [x] Göç `0006_live_video`: `live_tags.server_seq`, maç başına tek oturum, `video_assets`, `video_clips`. RLS, izinler, göç döngüsü.
- [x] `POST /tagging-sessions` (maç başına al ya da aç), `POST /tagging-sessions/{id}/sync` (toplu, idempotent, son yazan kazanır, silme kazanır), `GET /tagging-sessions/{id}/tags?since=`.
- [x] Kayıt → `set_pieces` (`source='live_tag'`); metrik görünümü yenileme işi.
- [x] Testler: idempotentlik, sıralama, mezar taşı, iki cihaz, izinler, kiracı izolasyonu.

**5.2 Video (ADR-0010, A-60 … A-62)**
- [x] Depo: imzalı çok parçalı yükleme (S3/MinIO) ve HMAC imzalı yerel adresler.
- [x] `POST /video/uploads`, `POST /video/assets/{id}/complete`, `GET /video/assets`, oynatma listesi, `GET/POST /clips`, `PATCH/DELETE /clips/{id}`.
- [x] Worker: ffmpeg ile HLS ve süre; durum makinesi.
- [x] Rutin istatistiğinde klipler.
- [x] Testler: imza, parça birleştirme, HLS üretimi (gerçek ffmpeg), klip doğrulaması.

**5.3 Arayüz**
- [x] PWA: manifest, simgeler, servis çalışanı (uygulama kabuğu ve `/live/*` önbelleği).
- [x] `/live` ve `/live/[fixtureId]`: büyük dokunma hedefleri (≥ 56 px), kısayollar, Dexie kuyruğu, çevrimiçi/çevrimdışı ve bekleyen sayısı, 10 sn geri al, maç saati, diğer cihazların kayıtları.
- [x] `/video`: yükleme (parçalı, ilerleme), dönüştürme durumu, oynatıcı (hls.js), klip kesme ve duran topa bağlama.
- [x] Rutin sayfasında klipler; hazırlık sayfasında öneri geri bildirimi (A-63).

**5.4 Doğrulama ve kapanış**
- [x] E2E: uçak modunda 20 kayıt → çevrimiçi → sunucuda 20 kayıt, yineleme yok; iki cihaz senkronizasyonu; video yükleme → HLS → klip → duran top → rutin sayfasında klip; axe.
- [x] `docs/demo/faz5/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 6: Raporlar ve LLM

### Kabul kriterleri (SPEC §19)
- [x] Rakip raporu ve maç planı PDF'leri 15 sn içinde üretilir.
- [x] LLM brifingi sayı eşleştirme kontrolünden geçer; kontrol başarısız olursa kullanıcıya gösterilmez.

### Rapor
- **Yapıldı:** Göç `0007_reports_llm` (`reports`, `llm_runs`, RLS). Rapor isteği kuyruğa girer; worker HTML'i Jinja2 ile üretir, Chromium (Playwright) ile A4 PDF'e çevirir (JavaScript ve ağ kapalı, IBM Plex gömülü) ve nesne deposuna yazar. Rakip raporu 2 sayfa: özet, form, profil (önceki sezon, sıra, lig ortalaması ve bu sezon sütunu), bulgular, öneriler, bölge ısı haritası, klip QR kodları, kaynak ve veri tarihi. Maç planı: kabul edilen öneriler, savunma organizasyonu, rutin diyagramları, MD planı ve görev atamaları. LLM brifingi resmi Anthropic SDK'sıyla; girdi JSON'u, Türkçe sayı biçimlerini tanıyan eşleştirme, bir yeniden deneme, her denemenin `llm_runs` kaydı, kiracı başına aç/kapa ve aylık istek/token sınırı. Web: `/reports` (istek, ilerleme çubuğu, arşiv, her tıklamada yenilenen imzalı indirme), hazırlık sayfasında PDF düğmeleri ve brifing paneli, `/admin/llm`. Gerçek Samsunspor verisiyle PDF üretimi 0,7-2 sn; E2E'de istekten "hazır"a 5 sn altında.
- **Sapmalar:** Oyuncu görev kartları Faz 7'ye kaldı (A-68). Maç planındaki görev atamaları plan sorumluları ve rutin rol etiketleri (A-69). Brifing eşzamanlı üretilir (A-75). Brifing izni matriste olmadığı için `edit_routines` rollerine açıldı (A-76).
- **Riskler:** Sayı denetimi yazıyla yazılmış sayıları ve anlamsal hatayı (doğru sayı, yanlış takım) yakalamaz; istem rakam ister ve metin "sayılar kayıtla eşleşti" etiketiyle gösterilir (ADR-0013). Gerçek model bu ortamda çağrılmadı; testler sahte ve enjekte istemciyle. API imajına Chromium eklendi; imaj büyür ve `make dev` ilk derlemesi uzar. İmaj bu ortamda derlenmedi, CI'daki compose derlemesinde sınanır.

### Görevler

**6.1 Rapor altyapısı (ADR-0012, A-68 … A-72)**
- [x] Göç `0007_reports_llm`: `reports`, `llm_runs`. RLS, izinler, göç döngüsü.
- [x] `POST /reports {type, fixture_id}` (202, iş kuyruğu), `GET /reports`, `GET /reports/{id}` (ilerleme ve imzalı indirme adresi).
- [x] Worker: HTML şablonu (Jinja2) → Chromium (Playwright) ile PDF → nesne deposu. Süre `duration_ms` olarak kaydedilir.
- [x] Docker imajı Chromium içerir; yazı tipi IBM Plex (OFL) repoda.

**6.2 Rapor içerikleri (SPEC §14)**
- [x] Rakip raporu (2-4 sayfa): özet, profil (sıra ve lig ortalaması), bulgular, öneriler, bölge ısı haritası, varsa klip QR kodları, kaynak ve veri tarihi.
- [x] Maç planı: kabul edilen öneriler ve rutinleri (diyagramlarıyla), savunma organizasyonu, görev atamaları (plan sorumluları), MD planı.
- [x] Az veri, dolaylı ve örnek veri etiketleri PDF'te de görünür.

**6.3 LLM brifingi (SPEC §15, ADR-0013, A-73 … A-76)**
- [x] Girdi JSON'u (metrikler, tetiklenen öneriler, plan) ve sistem istemi.
- [x] Sayı eşleştirme: çıktıdaki tüm sayılar girdide bulunmalı; eşleşmezse bir kez yeniden dene, yine olmazsa gösterme.
- [x] `llm_runs` kaydı; kiracı başına aylık istek ve token sınırı; kiracı ayarından kapatma.
- [x] `KURGU_LLM_MODEL` ve `KURGU_ANTHROPIC_API_KEY` yoksa özellik "yapılandırılmamış" görünür.

**6.4 Arayüz**
- [x] `/reports`: rapor oluşturma, ilerleme, arşiv ve indirme.
- [x] Hazırlık sayfasında "PDF" düğmeleri ve brifing paneli.
- [x] `/admin/llm`: LLM ayarı ve bu ayki kullanım.

**6.5 Doğrulama ve kapanış**
- [x] Testler: şablon içerikleri, sayı eşleştirme (Türkçe biçimler), bütçe, izinler, kiracı izolasyonu, PDF üretimi (gerçek Chromium).
- [x] E2E: iki PDF 15 sn içinde hazır ve iniyor; brifing (sahte model) gösteriliyor; axe.
- [x] `docs/demo/faz6/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

## Faz 7: Spor bilimi ve markaj optimizasyonu

### Kabul kriterleri (SPEC §19)
- [x] sRPE, Hooper ve EWMA hesaplamaları testli.
- [x] Sıçrama ve kafa yükü uyarıları çalışır.
- [x] Rol izinleri doğrulanır.
- [x] Macar algoritması önerisi elle düzeltilebilir ve kaydedilir.

### Rapor
- **Yapıldı:** Göç `0008_squad_load_marking` (yedi tablo, RLS, göç döngüsü). Kulüp kadrosu ve rakip hedef oyuncuları elle girilir (`/admin/squad`, hazırlık sayfası). Saf metrikler: sRPE, Hooper, akut ve kronik EWMA, ACWR (yalnız bağlam), z-skorları, haftalık sıçrama ve kafa uyarısı (kişisel ortalama + 2 SD), hava skoru ve Macar algoritmasıyla markaj. Hooper puanları AES-256-GCM zarf şifrelemesiyle saklanır, her okuma ve yazma denetim kaydına girer; anahtarlar `KURGU_DATA_KEYS`, üretimde anahtarsız başlamaz. Kapsamlar: performans ve sağlık tam, yönetici takım özeti, oyuncu yalnız kendi verisi, diğer roller 403. Markaj önerisi elle düzeltilir, sürümlü kaydedilir (eşzamanlı kayıtta 409). Rutin rolleri kadroya atanır, oyuncu `/me` sayfasında görev kartını görür. Web: `/performance`, `/performance/players/[id]`, hazırlık sayfasında markaj ve rol atama bölümleri. Geliştirme kimliklerinde 16 oyunculuk örnek kadro ve 42 günlük örnek yük (`is_demo`, "Örnek veri" rozeti).
- **Sapmalar:** SPEC §12.1 matrisine `edit_squad` satırı eklendi (A-79). Rakip hedefleri kulüp kaydıdır, lisanslı oyuncu verisi yok (A-80). Cihaz entegrasyonu, dosyadan yük içe aktarımı ve görev kartı PDF'i bu fazda yok (A-83, A-87).
- **Riskler:** Hava skoru elle girilen boy, oran ve sıçrama skoruna dayanır; bileşeni olmayan oyuncu atamaya girmez. Anahtar döndürme için yeniden şifreleme komutu yok; eski anahtarlar `KURGU_DATA_KEYS` içinde tutulmalı (ADR-0014). Uyarı eşiği en az 4 haftalık geçmiş ister; yeni oyuncuda uyarı çıkmaz.

### Görevler

**7.1 Kadro ve rakip hedefleri (A-79, A-80)**
- [x] Göç `0008_squad_load_marking`: `squad_players`, `opponent_targets`, `training_sessions`, `session_loads`, `wellness_entries`, `marking_plans`, `routine_assignments`. RLS, göç döngüsü.
- [x] Kadro ve rakip hedef uçları; `/admin/squad`; geliştirme kimliklerinde örnek kadro (`is_demo`).

**7.2 Yük ve iyi oluş (SPEC §8.2, A-83 … A-85)**
- [x] Saf metrikler (`metrics/load.py`): sRPE, Hooper, EWMA (akut ve kronik), ACWR, z-skorları, haftalık sıçrama ve kafa uyarısı. Birim ve özellik tabanlı testler.
- [x] `POST /sessions`, `GET /sessions`, `POST /wellness`, `GET /players/{id}/load`, `GET /load/overview` (uyarılar).

**7.3 Gizlilik ve izinler (SPEC §8.3, ADR-0014, A-86)**
- [x] Zarf şifreleme (`core/crypto.py`), Hooper alanları şifreli, her erişim denetim kaydında.
- [x] Kapsamlar: performans ve sağlık tam, yönetici özet, oyuncu yalnız kendi verisi; diğer roller 403. Testli.

**7.4 Markaj (SPEC §7.3, ADR-0015, A-81, A-82)**
- [x] Hava skoru ve atama (saf, testli); `GET /fixtures/{id}/marking`, `PUT /fixtures/{id}/marking` (sürümlü, denetimli).
- [x] Hazırlık sayfasında markaj bölümü: rakip hedefleri, öneri, elle düzeltme ve kaydetme.

**7.5 Rol atamaları ve görev kartı (A-87)**
- [x] Fikstür rutinlerinde rol → oyuncu ataması; `/me` görev kartları.

**7.6 Arayüz, doğrulama ve kapanış**
- [x] `/performance` (seans ve iyi oluş girişi, takım yük tablosu, uyarılar), `/performance/players/[id]` (yük, EWMA ve Hooper grafiği).
- [x] E2E (seans → uyarı, iyi oluş, rol izinleri, markaj düzeltme), axe; `docs/demo/faz7/` ekran görüntüleri; CLAUDE.md komutları.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Faz 8: Sertleştirme

### Kabul kriterleri (SPEC §19)
- [ ] Güvenlik gözden geçirmesi (OWASP ASVS L2 kontrol listesi) tamam.
- [ ] Performans bütçeleri k6 ve Lighthouse ile doğrulandı.
- [ ] axe taramasında 0 ciddi ihlal.
- [ ] Türkçe kullanıcı kılavuzu yazıldı.
- [ ] Runbook'lar ve geri yükleme tatbikatı tamam.

### Görevler

**8.1 Güvenlik (SPEC §12.2, ADR-0016, A-88 … A-90)**
- [ ] API güvenlik başlıkları; web'de nonce'lu CSP; HSTS yalnız staging ve production'da.
- [ ] Redis tabanlı hız sınırı (yükleme, içe aktarma, video, rapor, brifing) ve 429 problem+json; Keycloak kaba kuvvet koruması.
- [ ] MFA: Keycloak'ta iki düzeyli (parola, TOTP) koşullu akış; web'de `mfa-required` yanıtında adım yükseltme; production'da denetim zorunlu. E2E: MFA'lı kullanıcı TOTP ile girer.
- [ ] Yükleme denetimi gözden geçirmesi (tür, boyut, imzalı adres).

**8.2 Gözlem (SPEC §17, ADR-0017, A-91)**
- [ ] OpenTelemetry (isteğe bağlı), Sentry (isteğe bağlı, kişisel veri yok), `X-Request-ID`, `/metrics` (istek ve kuyruk metrikleri, token korumalı).

**8.3 KVKK (SPEC §12.3, ADR-0019, A-92)**
- [ ] Göç `0009_privacy`: `health_consents`, `privacy_requests`, RLS, göç döngüsü.
- [ ] Rıza (oyuncunun kendisi ya da kâğıt rıza), rızasız iyi oluş kaydının reddi.
- [ ] Kişisel veri envanteri (kodda tek kayıt, test), saklama süreleri ve gecelik silme görevi.
- [ ] Veri sahibi talepleri: dışa aktarma, silme talebi ve yönetici onayı; `/admin/privacy`; `docs/compliance.md`.

**8.4 Erişilebilirlik ve performans (SPEC §13.4, A-93, A-94)**
- [ ] axe taraması tüm rotalarda, açık ve koyu tema, masaüstü ve tablet; 0 ciddi ihlal.
- [ ] Rota başına ilk JS yükü ≤ 200 KB (gzip) denetimi CI'da.
- [ ] k6 ile özet uçlarında p95 ≤ 300 ms; Lighthouse ile kritik sayfalarda LCP ≤ 2,5 sn; canlı kayıtta dokunuştan yerel kayda ≤ 50 ms. Sonuçlar `docs/validation/performance.md`.

**8.5 Yedekleme ve runbook'lar (SPEC §17, ADR-0018, A-95)**
- [ ] Şifreli yedek ve geri yükleme tatbikatı betikleri; tatbikat kaydı.
- [ ] Runbook'lar: yedekleme ve geri yükleme, anahtar yönetimi ve döndürme, dağıtım, olay müdahalesi, kullanıcı ve MFA yönetimi.

**8.6 Belgeler ve kapanış (A-96, A-97)**
- [ ] Türkçe kullanıcı kılavuzu (`docs/kilavuz/`).
- [ ] ASVS L2 kontrol listesi (`docs/security/asvs-l2.md`).
- [ ] Kabul kriterleri işaretlendi, kısa rapor verildi.

---

## Kullanıcının çalıştıracağı `sudo` komutları (Ubuntu terminali)

Faz 0-1 için yalnızca biri gerekiyor. Faz 0.9'dan önce çalıştırılmalı:

```bash
cd ~/projects/kurgu && sudo npx playwright install-deps chromium
```

(Playwright'ın Chromium'u için sistem kütüphanelerini kurar. Tarayıcının kendisi sudo'suz `pnpm exec playwright install chromium` ile iner.)

BASLANGIC.md §1-2'deki kurulumlar (WSL, Docker Desktop, git/make/node/pnpm/uv) önceden yapılmış olmalı; `make doctor` bunu kontrol edecek.

---

## Sonraki fazlar (özet)
Faz 2 metrikler ve analiz ekranları · Faz 3 rutin kütüphanesi · Faz 4 hazırlık ve öneri motoru · Faz 5 canlı kayıt ve video · Faz 6 raporlar ve LLM · Faz 7 spor bilimi ve markaj · Faz 8 sertleştirme. Ayrıntılı görev listeleri ilgili faz başlarken yazılır.

Not: Faz 4 kabul testi tohumla doğrulandı. 7. hafta Samsunspor–Trabzonspor (10.10.2026) fikstürde var; Samsunspor 2025/26'da yapılan faulde 4., korner/maçta 2. Yani `ATK_WIN_FOULS` ve `DEF_CORNER_PRIORITY` kurallarının tetiklenmesi için veri hazır.
