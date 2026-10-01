# CLAUDE.md: Kurgu

Kurgu, profesyonel futbol kulüpleri için bir duran top analiz ve hazırlık platformudur. Veri → analiz → öneri → haftalık plan → maç içi kayıt → video → geri bildirim döngüsünü tek yerde kapatır. İlk hedef Süper Lig kulüpleridir.

**Ana şartname:** `docs/SPEC.md`. Karar vermeden önce ilgili bölümü oku. Şartnameyle çelişen bir şey yapman gerekirse önce sor, sonra ADR yaz.

## Yığın
- **Web:** Next.js 16 (App Router; ADR-0006), React 19, TypeScript strict, Tailwind CSS 4, shadcn/ui, TanStack Query/Table, Zustand + zundo, next-intl (tr varsayılan), Serwist (PWA), Dexie.
- **API:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic. **Worker:** Arq + Redis.
- **Analitik:** pandas/polars, socceraction, kloppy, scikit-learn, LightGBM, scipy, mplsoccer, pandera.
- **Altyapı:** PostgreSQL 16 (RLS), Redis, S3 (yerelde MinIO), OIDC (yerelde Keycloak), Playwright ile PDF, ffmpeg ile HLS.
- **Monorepo:** pnpm + Turborepo; Python için `uv`.

## Dizinler
- `apps/web`: arayüz. `apps/api`: REST API ve WebSocket.
- `analytics/kurgu_analytics`: ingestion, canonical, setpieces, metrics, recs, models, reports.
- `packages/ui`: tasarım tokenları ve bileşenler. `packages/pitch`: saha geometrisi ve `zones.json`. `packages/api-client`: üretilmiş istemci.
- `seed/`: tohum verisi. `docs/`: SPEC, `adr/`, `PROGRESS.md`, `assumptions.md`, `validation/`, `runbooks/`.

## Geliştirme ortamı: Windows 11 + WSL 2 (Ubuntu)
- Oturum, Claude masaüstü uygulamasının Code sekmesinde **WSL ortamında** çalışır. Proje Linux dosya sisteminde durur (`~/projects/kurgu`). Windows yolları (`C:\...`, `/mnt/c/...`) kullanılmaz; bu yollar yavaştır ve dosya izlemeyi bozar.
- Docker, Docker Desktop'un WSL 2 motoruyla çalışır ve Ubuntu entegrasyonu açıktır. `docker compose` komutları Ubuntu içinden çalıştırılır.
- Satır sonları LF'dir. Faz 0'da repo köküne `.gitattributes` eklenir (`* text=auto eol=lf`).
- **`sudo` gerektiren komutları kendin çalıştırma.** Komutu açıklamasıyla yaz ve kullanıcıdan Ubuntu terminalinde çalıştırmasını iste (örneğin `apt install`, `npx playwright install --with-deps`).
- Bu oturumda gömülü terminal yoktur. Uzun süren sunucuları (dev server) kullanıcı ayrı bir Ubuntu terminalinde `make dev` ile başlatır; sen yalnızca kısa komutlar çalıştır.
- Uygulama Windows tarayıcısından `localhost` ile açılır. Portlar: web 3000, api 8000, postgres 5432, redis 6379, minio 9000/9001, keycloak 8080, mailpit 8025. Çakışma olursa `.env` üzerinden değiştirilebilir olsun.

## Komutlar (bu listeyi güncel tut)
- `make dev`: tüm servisleri ayağa kaldırır (göç ve geliştirme kimlikleri dahil). `make down`, `make logs`, `make ps`.
- `make doctor`: araçları, satır sonu ayarını ve portları kontrol eder.
- `make seed`: tohum verisini yükler (geliştirme kimlikleri, lig verisi, lisanslar; idempotent) ve metrik görünümlerini yeniler (ADR-0007). `make seed-report`: bütünlük raporunu yeniden üretir. `uv run kurgu-seed --templates`: yalnızca rutin şablonlarını yükler (her ortamda; A-40).
- `make statsbomb-fetch` (StatsBomb Open Data'yı `data/statsbomb` önbelleğine indirir, repoya girmez) · `make statsbomb-load` (worker ile yükler) · `make validate` (duran top doğrulama raporu) · `make spadl-compare` (socceraction karşılaştırması).
- Rutinler: web `/routines` (kütüphane, şablonlar, editör, sürüm karşılaştırma); kart indirme `GET /routines/{id}/versions/{v}/export?format=pdf|png`.
- CSV/Excel içe aktarım: web `/admin/imports` (yalnız yönetici); API `POST /imports`, `PUT /imports/{id}/mapping`, `POST /imports/{id}/commit`.
- `make test` (`test-py`, `test-js`) · `make lint` · `make typecheck` · `make e2e`
- `make migrate`: Alembic upgrade. `make migrate-cycle`: upgrade → downgrade → upgrade.
- `make openapi`: OpenAPI şemasını ve TS istemcisini yeniden üretir.
- Python bağımlılıkları: `uv sync --all-packages` (workspace üyeleri için `--all-packages` şart).
- Test kullanıcıları ve adresler: `docs/runbooks/local-dev.md`.

## Çalışma biçimi
1. Önce planla, sonra küçük adımlarla ilerle. Her adımda kodu ve testini yaz, lint/typecheck/test çalıştır, sonra commit at (Conventional Commits, İngilizce).
2. Her fazın sonunda `docs/PROGRESS.md` içindeki kabul kriterlerini işaretle ve kısa bir rapor ver.
3. Engelleyici belirsizlikte sor. Diğer belirsizliklerde makul bir varsayım yap ve `docs/assumptions.md` dosyasına yaz.
4. Yıkıcı işlemlerden önce onay al: veri silme, göç geri alma, force push.

## Kesin kurallar
- **Veri uydurma yok.** Arayüzdeki her sayı bir kayda dayanır. Demo verisi `is_demo=true` ile işaretlenir ve "Örnek veri" rozetiyle gösterilir.
- **Web kazıma yok.** FotMob, Mackolik, Sofascore, Transfermarkt vb. kullanılmaz. Yalnızca lisanslı API'ler, StatsBomb Open Data (lisans ve atıf koşullarıyla, geliştirme için) ve kullanıcının içe aktardığı dosyalar kullanılır.
- **Formüller tek yerde.** Metrik formülleri yalnızca `analytics/kurgu_analytics/metrics/` altında bulunur. Her fonksiyonda docstring (formül, birim, kaynak) ve birim test olur. Fonksiyonlar saf olmalıdır.
- **Küçük örneklem uyarısı.** Oranlar beta-binom, sayımlar gamma-Poisson ile büzülür. n < 8 ya da maç < 5 ise "Az veri" rozeti gösterilir.
- **Dolaylı göstergeler etiketlenir.** Hava topu, faul ve uzaklaştırma savunma için "dolaylı" etiketiyle gösterilir. Takım bazında yenilen duran top golü yalnızca kulübün kendi kaydından ya da lisanslı olay verisinden gelir.
- **Penaltı duran top metriklerine dahil değildir;** ayrı raporlanır.
- **Güvenlik.** Kiracıya ait her tabloda `tenant_id` ve RLS bulunur. API her istekte `SET LOCAL app.tenant_id` çalıştırır. Sağlık ve iyi oluş alanları şifreli tutulur ve her erişim denetim kaydına yazılır. Sırlar yalnızca `.env` dosyasında durur; repoya asla girmez.
- **Mimari.** Modüler monolit kullanılır; mikroservis yoktur. API REST'tir, hatalar RFC 9457 problem+json biçimindedir.
- **LLM.** Model adı `KURGU_LLM_MODEL`, anahtar `KURGU_ANTHROPIC_API_KEY` değişkeninden okunur ve yalnızca proje `.env` dosyasında durur. `ANTHROPIC_API_KEY` ve `ANTHROPIC_MODEL` adlarını hiçbir yerde kullanma ve kabuğa export etme; Claude Code bunları okuyup aboneliği API faturasına çevirebilir. Çıktıdaki her sayı girdi JSON'unda bulunmalıdır; bulunmuyorsa çıktı reddedilir.

## Alan sözlüğü (kısa)
| Terim | Anlamı |
|---|---|
| DT | Duran top: korner, serbest vuruş ve hücum üçte birlik bölgesinden ceza sahasına atılan uzun taç. Penaltı hariç. |
| Birinci / ikinci faz | Birinci faz: teslimden sonra ≤ 5 sn ya da ≤ 1 ek pas. İkinci faz: toplam pencere ≤ 20 sn (ayarlanabilir). |
| İlk temas | Teslimden sonra topa dokunan ilk oyuncu ve takım. |
| Bölgeler | NP yakın direk, C6 altı pas merkezi, FP arka direk, PS penaltı noktası, ED ceza sahası önü, SH kısa, OT diğer (§3.3). |
| Koordinat | 105 × 68 m; hücum edilen kale x = 105; y = 0 hücum eden takımın sağ taç çizgisi (§4). |
| MD kodları | MD-4 … MD-1, MD, MD+1 (haftalık döngü, §8.1). |
| Lig sırası | 1 = en yüksek değer; eşit değerler aynı sırayı alır. |

## Arayüz ilkeleri
- **Tasarım tokenları.** Koyu yeşil yan menü (`--brand #0E3B2E`), vurgu rengi amber `#E3A008` ("sizin kulübünüz" işareti). Yazı ailesi IBM Plex Sans ve Condensed; rakamlar tabular.
- **Cihazlar.** Tablet önceliklidir (bank ve analiz odası). Mobilde alt sekme ve çekmece menü, masaüstünde yan menü kullanılır.
- **Durumlar.** Her veri bileşeninin yükleniyor, boş, hata ve az veri durumları vardır. Renk tek başına anlam taşımaz; form rozetlerinde G/B/M harfleri yazar.
- **Görseller.** Kulüp logosu kullanılmaz; kısa kod rozeti (GS, TS, GÖZ…) kullanılır.
