# İlerleme

**Durum:** Faz 0-2 tamam ve `main`'e birleşti (PR #1-#3, 01.10.2026). Faz 3 (rutin kütüphanesi) `faz-3-rutinler` dalında sürüyor.
**Sonraki adım:** Faz 3 görevleri (aşağıda).

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
- [ ] Editör: oyuncu (rolle), koşu, top yolu, perdeleme, ayna, geri al / yinele ve klavye desteği.
- [ ] Sürümleme çalışır.
- [ ] 7 şablon `seed/routine_templates.json` dosyasından yüklenir ve kütüphaneye eklenebilir.
- [ ] PNG ve PDF dışa aktarım çalışır.

### Görevler

**3.1 Diyagram biçimi ve geometri (ADR-0008, A-39)**
- [ ] Diyagram v1 şeması: oyuncular, çizgiler (koşu, top yolu, perdeleme), bölge vurguları, top ve kareler. Python'da Pydantic doğrulaması, TS'de tip.
- [ ] `packages/pitch`: kavis kontrol noktası, ayna (sol/sağ), ızgaraya hizalama, kare enterpolasyonu, sürüm farkı; ortak test vektörleri Python ile.
- [ ] `packages/pitch/roles.json`: rutin rolleri ve tr/en adları (SPEC §3.4 + şablon rolleri); web ve PDF aynı dosyayı okur.

**3.2 Şema ve şablonlar**
- [ ] Göç `0004_routines`: `routine_templates` (paylaşılan), `routines`, `routine_versions` (değişmez), `set_pieces.routine_id` yabancı anahtarı, `v_routine_stats` (`security_invoker`). RLS ve izinler; göç döngüsü.
- [ ] Şablon yükleme: `make seed` ve ortamdan bağımsız `kurgu-seed --templates` (A-40). 7 şablon v1 diyagramına çevrilir.

**3.3 API (SPEC §11)**
- [ ] `GET /routine-templates`, `GET/POST /routines`, `POST /routines/from-template/{tplId}`, `GET/PUT/PATCH /routines/{id}`, `GET /routines/{id}/versions`, `GET /routines/{id}/versions/{v}`.
- [ ] Sürümleme: her kayıt yeni değişmez sürüm; `base_version` ile çakışma 409; içerik aynıysa sürüm açılmaz; arşivleme (silme yok, A-41). Denetim kaydı.
- [ ] Rutin performansı (SPEC §6.3): kullanım, ilk temas oranı, şut oranı, kullanım başına xG, gol; oranlar beta-binom büzülmesiyle (A-44).
- [ ] Testler: izinler, kiracı izolasyonu, çakışma, doğrulama hataları (problem+json).

**3.4 Dışa aktarım (A-42)**
- [ ] `kurgu_analytics.reports.routine_sheet`: diyagramdan PNG ve A4 PDF (başlık, saha, rol açıklaması, notlar, kareler). Saf fonksiyon, testli.
- [ ] `GET /routines/{id}/versions/{v}/export?format=png|pdf`.

**3.5 Arayüz**
- [ ] `/routines`: kütüphane (tür süzgeci, arşiv) ve şablonlar sekmesi (önizleme, "Kütüphaneye ekle"), yeni rutin.
- [ ] `/routines/[id]` editörü: yarım saha SVG; oyuncu ekleme (takım ve rol), koşu, top yolu (kavisli, noktalı), perdeleme, bölge vurgusu; ızgara, ayna; geri al / yinele (zundo); klavyeyle seçme ve ok tuşlarıyla taşıma; özellik paneli.
- [ ] Kare kare animasyon: kare ekleme, oyuncu ve top konumu, oynatma (`prefers-reduced-motion` desteği).
- [ ] Sürüm geçmişi, eski sürümü görme, geri dönme (yeni sürüm olarak) ve iki sürümü karşılaştırma.
- [ ] Dışa aktarım düğmeleri (PNG, PDF); yalnızca okuma yetkisi olanlar için salt okunur görünüm.
- [ ] Yükleniyor, boş, hata durumları; `tr` ve `en` metinleri.

**3.6 Doğrulama ve kapanış**
- [ ] E2E: şablondan ekle → düzenle (klavye, ayna, geri al) → kaydet → sürüm 2 → karşılaştır → PDF ve PNG indir; axe.
- [ ] `docs/demo/faz3/` ekran görüntüleri; CLAUDE.md komutları güncel.
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
