# Varsayımlar ve açık sorular

Bu dosya SPEC §0 gereği kod yazılmadan önce hazırlandı (30.09.2026). Her madde: durum, varsayım ve gerekçe. Durumlar: **ENGELLEYİCİ** (kullanıcı yanıtı olmadan ilerlenemez), **VARSAYIM** (makul varsayımla ilerlenir, istenirse değiştirilir), **KULÜP** (SPEC §20; kulüple netleşecek, Faz 0-1'i engellemez).

Kaynak dosyalar: kök `CLAUDE.md`, `SPEC.md`, `BASLANGIC.md` (WSL sürümü) esas alındı. `kurgu-claude-code/` altındaki kopyalar eski sürümdür; aradaki tek anlamlı fark LLM ortam değişkeni adlarıdır (bkz. A-14).

---

## Engelleyici

**A-01 · Kodun yaşayacağı yer.** Repo henüz yok. Faz 0 bir git reposu, CI (GitHub Actions) ve `make dev` ister.
- Seçenek 1: GitHub'da boş bir `kurgu` reposu açılır, projeye bağlanır; Faz 0 PR'larla ilerler. CI orada koşar.
- Seçenek 2: Kullanıcının WSL Ubuntu'sundaki `~/projects/kurgu` klasöründe çalışılır; GitHub sonradan bağlanır.
- **Öneri:** İkisi birlikte. Repo GitHub'da durur (CI için şart), kullanıcı `make dev`'i WSL'de çalıştırır.

## Veri ve tohum

**A-02 · VARSAYIM · Tohum bütünlük kontrolü 1 tutmuyor.** `seed/super_lig.json` şunu vaat ediyor: akan oyun + hızlı hücum + penaltı + duran top golleri = toplam gol (0-1 kendi kalesine gol farkıyla). Hesapladım: 18 takımın 7'sinde fark 2-4 gol (GS 4, IBFK 3, SAM 3, FB 2, KON 2, KAS 2, GEN 2). Diğer iki kontrol tutuyor: toplam 166/812 = %20,4 ve 6. hafta puan tablosu sonuçlardan birebir yeniden hesaplanıyor.
- Varsayım: Fark, kaynaklar arası tanım farkından (FotMob duran top golü ile Mackolik/Opta alt kırılımları) ve kendi kalesine gollerden geliyor. Veri düzeltilmez; `make seed` bu kontrolü **uyarı** olarak raporlar, yüklemeyi durdurmaz. Fark `docs/validation/seed_integrity.md` dosyasına yazılır. Tolerans 0-1 yerine uyarı eşiği olarak kalır.
- Gerekçe: "Veri uydurma yok" kuralı elle düzeltmeyi yasaklıyor; en doğru davranış olduğu gibi yükleyip şeffaf raporlamak.

**A-03 · VARSAYIM · Tohum kayıtlarının işareti.** SPEC §5.7: tohum `is_demo=false`, `source='seed:super_lig.json'`. CLAUDE.md ise demo verisinin `is_demo=true` ve "Örnek veri" rozetiyle gösterileceğini söylüyor. Varsayım: Tohum gerçek kamu verisidir, demo değildir; `is_demo=false` kalır ve arayüzde **kaynak rozeti** ("Tohum: FotMob / Opta / TFF") gösterilir. `is_demo=true` yalnızca uydurma örnekler (ör. örnek canlı kayıtlar, örnek rutin istatistikleri) içindir.

**A-04 · VARSAYIM · Takım kimlikleri.** Tohumda 21 takım var: 2025/26'nın 18 takımı (3'ü küme düştü: ANT, KAR, KAY) ve 2026/27'ye çıkan 3 takım (AMD, ERZ, COR). Kısa kimlikler (`gs`, `ts`…) `provider_id_map` içinde `provider='seed'` olarak tutulur; Kurgu içi kimlik UUID'dir.

**A-05 · VARSAYIM · 2026/27 verisinin kapsamı.** 2026/27 için yalnızca duran top golü ve xG (ilk 6 hafta), puan durumu, sonuçlar ve fikstür var; diğer metrikler yok. `opponent_current` / `club_current` özneli kurallar yalnızca bu alanlarla çalışır; eksik metrik "veri yok" sayılır, kural tetiklenmez ve deneme modunda nedeni gösterilir.

**A-06 · VARSAYIM · StatsBomb Open Data erişimi.** Faz 1 doğrulaması için veriler GitHub'daki `statsbomb/open-data` deposundan indirilir (lisans ve atıf koşullarıyla). İndirme `make` hedefiyle yapılır, repoya **eklenmez** (`.gitignore`). Doğrulama için 1-2 yarışma seçilir (öneri: FIFA Dünya Kupası 2022 ve bir Premier Lig/La Liga sezonu); tüm arşiv gerekmez.

**A-07 · VARSAYIM · `play_pattern` uyum ölçütü.** Şut düzeyinde: StatsBomb'da `play_pattern ∈ {From Corner, From Free Kick, From Throw In}` olan şutlar ile bizim çıkarımımızın duran top dizisine atadığı şutlar karşılaştırılır. Penaltılar iki taraftan da çıkarılır. Rapor hem uyum oranını (≥ %95 hedef) hem de iki yönlü karışıklık matrisini verir. Uzun taç tanımımız StatsBomb'dan dar olduğu için (tüm taçları değil, yalnız ceza sahasına atılanları sayıyoruz) taç kaynaklı uyum ayrıca raporlanır ve ana ölçüte "tüm taçlar" ayarıyla da bakılır.

**A-08 · VARSAYIM · CSV içe aktarım biçimi.** Faz 1'de iki şablon desteklenir: (1) takım-sezon metrikleri (`team_season_stats` biçimi), (2) olay düzeyi SPADL benzeri CSV. Excel (`.xlsx`) aynı eşleştirme sihirbazından geçer. Sağlayıcıya özgü dışa aktarım biçimleri P1'dir.

## Ürün ve kiracı

**A-09 · VARSAYIM · İlk kiracı.** Faz 1 kabul testleri ve Faz 4 kabul testi Trabzonspor'u kulüp olarak kullanıyor. Yerel ortamda iki kiracı tohumlanır: `Trabzonspor (demo)` ve RLS testleri için ikinci bir kiracı `Test Kulübü`. Lig verisi paylaşılan tablolarda (`tenant_id` null) durur ve `data_licenses` ile her iki kiracıya da açılır.

**A-10 · VARSAYIM · Roller ve test kullanıcıları.** Keycloak realm'i `kurgu` adıyla, SPEC §12.1'deki 8 rolle ve her rol için bir test kullanıcısıyla (`admin@kurgu.local` …) içe aktarılır. Parolalar yalnızca yerel `.env` / realm dışa aktarımında durur. MFA yerelde kapalı, staging/prod'da zorunludur.

**A-11 · KULÜP · Kimlik sağlayıcı (§20.3).** Microsoft Entra ID mi Google Workspace mi bilinmiyor. Engellemez: kod genel OIDC ile yazılır, yerelde Keycloak kullanılır.

**A-12 · KULÜP · Barındırma ve veri bölgesi (§20.2).** Engellemez; Faz 0-1 yalnız yerel docker compose. `tenants.data_region` alanı `tr` varsayılanla açılır.

**A-13 · KULÜP · Lisanslı veri sağlayıcı (§20.1), video kaynağı (§20.4), kapsam (§20.5), oyuncu hesabı (§20.6).** Faz 0-1'i engellemez. Adaptör arayüzü sağlayıcıdan bağımsız kurulur; `teams` tablosu takım türü (A takımı / U19 / kadın) için alan taşır.

## Teknik

**A-14 · VARSAYIM · LLM ortam değişkenleri.** Kök CLAUDE.md ve SPEC §15 geçerli: `KURGU_LLM_MODEL` ve `KURGU_ANTHROPIC_API_KEY`. `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` hiçbir yerde kullanılmaz; CI'da bu adları arayan bir lint kuralı eklenir. (Eski `kurgu-claude-code/` kopyası `ANTHROPIC_MODEL` diyor; geçersiz sayıldı.)

**A-15 · VARSAYIM · Sürümler.** Node LTS (22.x), pnpm 10 (corepack; `packageManager` alanında sabit), Python 3.12 (`uv`), PostgreSQL 16, Redis 7, Keycloak 26, MinIO güncel kararlı. Sürümler `.tool-versions` / `package.json#engines` / `pyproject.toml` ile sabitlenir.

**A-16 · VARSAYIM · socceraction ve Python 3.12.** `socceraction` güncel sürümü pandas 2 ve Python 3.12 ile çalışmazsa SPADL dönüşümü için yalnızca `kloppy` + kendi ince SPADL eşleyicimiz kullanılır; karar ADR-0003'e ek olarak yazılır.

**A-17 · VARSAYIM · Auth.js ve Next.js 15.** Web oturumu Auth.js v5 (Keycloak sağlayıcısı) ile açılır; API'ye erişim token'ı Bearer olarak gider. API, JWKS ile imzayı ve `aud`/`iss` alanlarını doğrular.

**A-18 · VARSAYIM · Göç ve RLS rolü.** Uygulama veritabanına RLS'yi atlayamayan ayrı bir rol (`kurgu_app`, `NOBYPASSRLS`, tablo sahibi değil) ile bağlanır. Göçler sahip rolüyle (`kurgu_owner`) çalışır. Aksi halde tablo sahibi RLS'yi atlar ve izolasyon testleri yanlış geçer.

**A-19 · VARSAYIM · Windows/WSL ayrıntıları.** `.gitattributes` (`* text=auto eol=lf`) Faz 0'ın ilk commit'indedir. `sudo` gerektiren kurulumlar (Playwright sistem bağımlılıkları) kullanıcıya liste olarak verilir; Faz 0-1'de gereken tek şey `npx playwright install --with-deps chromium` (Faz 0 e2e dumanı için).

**A-21 · VARSAYIM · Yazı tipleri yerelden sunulur.** IBM Plex, Google Fonts yerine `@fontsource` paketleriyle uygulamayla birlikte sunulur. Gerekçe: derleme dış ağa bağlı kalmaz, PWA çevrimdışı çalışır ve kullanıcı IP'si üçüncü tarafa gitmez (KVKK).

**A-22 · VARSAYIM · Keycloak adresi `keycloak.localhost`.** Tarayıcı ve konteynerler aynı OIDC adresini kullanmalı, yoksa token'daki `iss` tutmaz. Tarayıcılar `*.localhost`'u 127.0.0.1'e çözer; compose içinde aynı ad ağ takma adıdır. Test kullanıcılarının Keycloak kimlikleri sabittir (`infra/keycloak/kurgu-realm.json`), böylece üyelikler girişten önce açılabilir.

**A-23 · VARSAYIM · shadcn/ui.** Faz 0'da yalnız tasarım tokenları ve durum bileşenleri (`packages/ui`) yazıldı. shadcn/ui bileşenleri (dialog, select, table…) ilk ihtiyaç duyulduğu fazda eklenir.

**A-20 · VARSAYIM · Portlar.** web 3000, api 8000, postgres 5432, redis 6379, minio 9000/9001, keycloak 8080, mailpit 8025. Hepsi `.env` üzerinden değiştirilebilir.

## Faz 1

**A-24 · VARSAYIM · Bölge tanımlarındaki boşluk.** SPEC §3.3 eşikleriyle x ∈ [97, 99,5) ve y' ∈ [31,5, 36,5] alanı (altı pasın hemen önü, merkez) hiçbir bölgeye girmez; ceza sahası içinde olduğu için `SH` de olamaz ve `OT` sayılır. Eşikler şartnameye sadık bırakıldı; kulüp analistleri isterse `zones.json` üzerinden `C6` alt sınırı 97'ye çekilebilir. Test vektörü bu davranışı sabitler.

**A-25 · VARSAYIM · StatsBomb koordinat dönüşümü parçalı doğrusaldır.** SPEC §4 "120 × 80 → 105 × 68, y çevrilir" diyor. Düz ölçekleme ceza sahası çizgisini 88,5 m yerine 89,25 m'ye taşıdığı için bölge sınırlarında hata yapar. Dönüşüm saha çizgilerini (altı pas, penaltı noktası, ceza sahası, orta çizgi, direkler) kanonik karşılıklarına oturtan parçalı doğrusal eşlemedir (`kurgu_analytics.canonical.coords`); referans nokta testleriyle doğrulanır. kloppy'nin standart saha dönüşümüyle aynı fikirdir.

**A-26 · VARSAYIM · `zones.json` konumu.** Dosya `packages/pitch/zones.json` içinde tek kopyadır. Python tarafı `KURGU_ZONES_PATH` değişkenini, yoksa repo kökündeki yolu okur. API imajı dosyayı kopyalar ve değişkeni ayarlar; geliştirme konteyneri klasörü bağlar.
