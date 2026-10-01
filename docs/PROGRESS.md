# İlerleme

**Durum:** Faz 0 tamam, PR #1 incelemede (30.09.2026). CI'da compose üzerinde e2e dahil tüm işler yeşil.
**Sonraki adım:** PR #1 birleşince Faz 1 (veri çekirdeği).

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
- [ ] Şema, göçler ve RLS kurulu (kiracılar arası erişim testi 403/boş döner).
- [ ] `make seed` tohum verisini yükler; Lig ve takım uçları tohum değerlerini birebir döner.
- [ ] StatsBomb Open Data adaptörü ve SPADL dönüşümü çalışır.
- [ ] Duran top çıkarımı ile doğrulama raporu hazır; `play_pattern` uyumu ≥ %95.
- [ ] CSV içe aktarım sihirbazı ve kalite raporu çalışır; karantina akışı işler.

### Görevler

**1.1 Şema ve göçler (SPEC §10; ADR-0002)**
- [ ] Paylaşılan lig tabloları: `competitions`, `seasons`, `teams`, `players`, `matches`, `standings_snapshots`, `team_season_stats`, `events`, `provider_id_map`, `data_licenses`, `raw_payloads`, `ingestion_runs`.
- [ ] Kiracı tabloları (Faz 1'de boş kalanlar dahil, şema kırılmasın diye): `audit_log`, `set_pieces` (paylaşılan + kiracı kaynaklı ayrımıyla), `tagging_sessions`, `live_tags` (ADR-0004 alanları), `imports`.
- [ ] RLS politikaları (`force row level security`), paylaşılan tablolar için `data_licenses` okuma politikası.
- [ ] Meta test: tüm kiracı tablolarında RLS açık.
- [ ] Kiracılar arası erişim testi: A'nın satırı B ile listede görünmez, kimlikle istenince 404 döner.
- [ ] `audit_log` yalnızca ekleme testi (`kurgu_app` update/delete yapamaz).
- [ ] Her göç geri alınabilir; CI döngüsü yeşil.

**1.2 Saha geometrisi ve bölgeler (SPEC §3.3, §4; ADR-0003)**
- [ ] `packages/pitch/zones.json`: saha ölçüleri, referans noktaları, bölge eşikleri.
- [ ] Python `kurgu_analytics.setpieces.zones` ve TS `packages/pitch` aynı dosyayı okur; ortak test vektörleri (`zones.vectors.json`) iki tarafta da geçer.
- [ ] Koordinat dönüşümleri: StatsBomb 120×80 → 105×68 (y ekseni çevrilir), takım yönüne normalizasyon, `y' = y | 68 − y`. Referans nokta testleri.

**1.3 Tohum yükleme (`make seed`)**
- [ ] Tohum JSON'ları için pandera / Pydantic şemaları.
- [ ] `super_lig.json` → takımlar, sezonlar, 2025/26 `team_season_stats`, 2026/27 duran top verisi, puan durumu, sonuçlar, fikstür, lig kıyas değerleri. `source='seed:super_lig.json'`, `is_demo=false` (A-03).
- [ ] Bütünlük kontrolleri raporu: kontrol 2 ve 3 hata verirse yükleme durur; kontrol 1 uyarı üretir ve `docs/validation/seed_integrity.md` yazılır (A-02).
- [ ] Kiracılar: `Trabzonspor (demo)` ve `Test Kulübü`; `data_licenses` kayıtları; test kullanıcılarının `memberships` kayıtları (A-09, A-10).
- [ ] Idempotent: `make seed` iki kez çalışınca satır sayısı değişmez.
- [ ] `routine_templates.json` ve `recommendation_rules.json` şimdilik yalnızca şema doğrulamasından geçer (yükleme Faz 3 ve Faz 4).

**1.4 Lig ve takım uçları**
- [ ] `GET /seasons/{id}/standings?week=`, `GET /seasons/{id}/team-metrics`, `GET /teams/{id}/profile?season=` (Faz 1'de yalnızca ham tohum değerleri; türetilmiş metrikler Faz 2).
- [ ] Altın testler: uç yanıtları tohum değerleriyle birebir (ör. 6. hafta sonu AMD 13 puanla 1.; TS 2025/26 duran top golü 15; GÖZ duran top xG 15,4).
- [ ] İmleç sayfalama, ETag.

**1.5 Ingestion çerçevesi (SPEC §5.2)**
- [ ] Adaptör arayüzü (`Provider` protokolü: `list_matches`, `fetch_events`, `to_canonical`).
- [ ] `raw_payloads` + MinIO'ya ham yük; `source_hash` ile idempotent yükleme.
- [ ] `ingestion_runs` durum makinesi: `pending → running → succeeded | quarantined | failed`.
- [ ] Worker işleri ve API'den tetikleme.

**1.6 StatsBomb Open Data adaptörü ve SPADL (ADR-0003)**
- [ ] `make statsbomb-fetch`: seçili yarışmaları indirir, repoya eklemez (A-06). Atıf `docs/validation/` ve `/methodology` notuna yazılır.
- [ ] kloppy ile ayrıştırma → SPADL → kanonik `events` (koordinat dönüşümü dahil). `play_pattern` `extra` alanına.
- [ ] socceraction uyum kontrolü; uyumsuzsa ince SPADL eşleyici (A-16) ve ADR notu.
- [ ] Oyuncu/takım kimlik eşleştirmesi `provider_id_map`'e (`provider='statsbomb'`).
- [ ] Testler: bilinen bir maçta olay sayısı, gol sayısı ve birkaç örnek aksiyonun koordinatları.

**1.7 Duran top çıkarımı (SPEC §5.5)**
- [ ] `setpieces/extract.py`: algoritma aynen; `WINDOW_S=20`, `PHASE1_S=5` ayarlanabilir.
- [ ] Yardımcılar: `classify` (alt tür), `side_of`, `zone`, `is_touch`, `lost_possession`, `ball_left_final_third`, `derive_outcome`.
- [ ] Penaltılar ayrı; duran top dizilerine girmez.
- [ ] Birim testler: el yapımı küçük olay dizileriyle her dal (uzun taç filtresi, 2. faz geçişi, pencere dışı, yeni duran top ile kesilme, doğrudan serbest vuruş şutu).
- [ ] hypothesis ile değişmezler: faz 1 + faz 2 xG = toplam; her şut en fazla bir diziye ait.
- [ ] `set_pieces` tablosuna yazım (`source='provider'`).

**1.8 Doğrulama raporu (SPEC §5.5; A-07)**
- [ ] Şut düzeyi karşılaştırma: çıkarım ↔ StatsBomb `play_pattern`.
- [ ] `docs/validation/setpiece_extraction.md`: uyum oranı (hedef ≥ %95), tür bazında kırılım, karışıklık matrisi, uyumsuz örnekler ve nedenleri, kullanılan veri ve atıf.
- [ ] Rapor üretimi `make validate` ile yeniden üretilebilir.

**1.9 CSV/Excel içe aktarım (SPEC §5.6; A-08)**
- [ ] `POST /imports` (dosya; tür ve boyut doğrulaması), `GET /imports/{id}` (eşleştirme + kalite raporu), `POST /imports/{id}/commit`.
- [ ] Sütun eşleştirme önerisi ve takım/oyuncu kimlik eşleştirme (bulanık, eşik altı elle onay).
- [ ] pandera kontrolleri: zorunlu alanlar, koordinat aralıkları, periyot/zaman tutarlılığı, yinelenenler, referans bütünlüğü, maç başına makul olay sayısı.
- [ ] Kritik hata → `quarantined`; metriklere girmez. Düzeltip yeniden yükleme akışı.
- [ ] Web: `/admin/imports` sihirbazı (yükle → eşleştir → rapor → işle), tüm durumlarla.
- [ ] E2E (SPEC §16 akış 4'ün Faz 1 kısmı): CSV yükle → hata gör → düzelt → işle.

**1.10 Faz kapanışı**
- [ ] `docs/demo/faz1/` ekran görüntüleri; CLAUDE.md komutları güncel.
- [x] Kabul kriterleri işaretlendi, kısa rapor verildi.

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
