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

**A-27 · VARSAYIM · SPADL eşleyici (A-16'nın sonucu).** socceraction bağımlılık olarak eklenmedi; ince eşleyici yazıldı ve socceraction ile %100 tür uyumu ölçüldü (ADR-0003 Faz 1 notu). socceraction'dan bilinçli farklar: sentetik `dribble` aksiyonları eklenmez (StatsBomb `Carry` zaten `dribble` olur); sol/sağ ayak `foot_left`/`foot_right` olarak korunur (korner alt türü için gerekli).

**A-28 · VARSAYIM · Nesne deposu.** Ham yükler `raw/<kiracı|shared>/<sağlayıcı>/<sha256>` anahtarıyla yazılır; aynı içerik aynı anahtara gider. Yerelde ve testlerde klasör deposu (`KURGU_STORAGE_BACKEND=local`), compose'da MinIO (`s3`) kullanılır.

**A-29 · VARSAYIM · Yükleme işi sahipliği.** API'den başlatılan iş kaydı isteyen kiracıya aittir (yalnız o görür), yazılan lig verisi paylaşılır ve lisansla okunur. Komut satırından (`kurgu-ingest`) başlatılan iş paylaşılandır (`tenant_id` boş). İşi yalnızca `admin` rolü başlatabilir.

**A-30 · KARAR (2026-09-30, Serhat) · Doğrulama ölçüsü.** `docs/validation/setpiece_extraction.md`: 149 maçta ham `play_pattern` uyumu %74,3, tanım farkları (kısa taç, 20 sn pencere dışı) uyumlu sayıldığında %99,5. StatsBomb etiketi possession boyunca süre sınırsız taşındığı için ham ölçü şartnamedeki tanımla ölçülemez. Karar: kabul ölçüsü tanım uyumlu uyumdur (≥ %95); ham uyum yan yana raporlanır.

**A-31 · VARSAYIM · Şut sonucunun türetilmesi.** SPADL isabet bilgisi taşımaz. Sonuç sağlayıcıdan bağımsız türetilir: rakip kaleci kurtarışı izliyorsa isabetli, top kale çizgisine (x ≥ 104) ulaştıysa isabetsiz, ulaşmadıysa engellenmiş. StatsBomb sonucuyla uyum %94,1; ana karışıklık StatsBomb'un "Wayward" (topu kötü vurma) şutlarının engellenmiş sayılması.

**A-32 · VARSAYIM · İçe aktarımda takımlar.** İçe aktarılan dosyadaki takım adları var olan takımlara eşlenir (önce sezonun takımları; sezonda kayıt yoksa görülebilen tüm takımlar). Uygulama rolü paylaşılan `teams` tablosuna yazamadığı için içe aktarım yeni takım oluşturmaz. Puanı 0,85'in altındaki öneriler yöneticinin onayını bekler. Sezon lisansla görünür olmalıdır; lisansı olmayan kulübün kendi sezonunu tanımlaması sonraki bir fazın işidir.

**A-33 · VARSAYIM · İçe aktarılan olaylarda eksik alanlar.** Olay dosyasında vücut bölgesi yoksa SPADL `other` yazılır; bu durumda korner alt türü `other` olur. Oyuncu adları oyuncu tablosuna eşlenmez, olayın `extra.player` alanında durur. Maç skoru dosyadaki gollerden (başarılı şut, rakibin kendi kalesine golü) hesaplanır. Aynı kiracı aynı sezonda aynı `match_ref` ile yeniden içe aktarırsa eski maç ve dizileri silinip yenisi yazılır; işlem denetim kaydına girer.

**A-34 · VARSAYIM · Rota düzeyi yükleniyor bileşeni kaldırıldı.** Next.js 15.5.27 üretim derlemesinde `(app)/loading.tsx` varken bir üst yoldan alt yola istemci tarafı geçiş (ör. `/admin` → `/admin/imports`, sunucu eylemi sonrası yönlendirme) RSC yanıtı 200 dönmesine rağmen ekrana uygulanmıyordu; geliştirme modunda sorun yok. Belirti, React Flight'taki bir hataya bağlanan [vercel/next.js#83386](https://github.com/vercel/next.js/issues/83386) ile örtüşüyor; 15.x hattında düzeltme yok. Rota düzeyi `loading.tsx` kaldırıldı; bileşen düzeyi yükleniyor durumları (`Skeleton`) yerinde duruyor. Next 16'ya geçiş şartnamedeki yığını değiştirdiği için ayrı bir karar konusu. **Güncelleme 01.10.2026:** Serhat Next 16'ya geçişi seçti; yükseltme yapıldı ve `loading.tsx` geri geldi (ADR-0006). Bu varsayım kapandı.

**A-35 · VARSAYIM · Lig sırası ve büzülme birlikte gösterilir.** Sıra ve yüzdelik kayıttaki ham değerden hesaplanır (SPEC §19 altın kontrolleri ham değerlere dayanıyor: TS 15 golle 1.). Oran metriklerinde yanında beta-binom sonsal ortalaması ve %80 aralık, maç başı sayımlarda gamma-Poisson sonsal ortalaması gösterilir. Deneme sayısı bilinmeyen oranlar (ör. tohumdaki hava topu kazanma %) büzülmez ve "deneme sayısı yok" olarak işaretlenir.

**A-36 · VARSAYIM · Kulübün kendi kaydı paylaşılan veriye öncelik alır.** Aynı takım-sezon-metrik için kiracının içe aktardığı değer (kaynak `import`) varsa o gösterilir ve kaynak rozeti "İçe aktarım" olur; yoksa paylaşılan değer (tohum ya da sağlayıcı). Olay verisi için de aynı kural geçerli: bir takım-sezonda kiracının içe aktardığı maçlar varsa dizi toplamları o maçlardan gelir, paylaşılan dizilerle toplanmaz (çift sayım riski). Sıra, yüzdelik ve lig kıyasları (en düşük, en yüksek, ortalama) bu birleşik tablodan hesaplanır: kulüp, kendi kaydının yerleştiği ligi görür. Lig toplamları (ör. %20,4) yalnızca paylaşılan veriden gelir (ADR-0007).

**A-37 · VARSAYIM · 100 kornere gol tohumda yaklaşık.** Tohumda korner golü yok; SPEC §6.1 notuna uygun olarak tohumda `goals_per_100_corners` = duran top golü / (maç başı korner × maç) × 100 hesaplanır ve "yaklaşık" etiketiyle gösterilir. Olay verisi olan sezonlarda gerçek korner golleri kullanılır.

**A-38 · VARSAYIM · Ana sayfadaki tehdit etiketleri Faz 4'te.** SPEC §13.1 genel bakıştaki "sezon önerileri ve tehdit etiketleri" öneri motoruna (Faz 4) bağlı. Faz 2'de yaklaşan maçlarda rakibin duran top golü ve xG lig sırası gösterilir; öneri ve etiket alanı boş durumla Faz 4'ü işaret eder.

**A-39 · VARSAYIM · Rutin diyagramı biçimi (v1).** SPEC §10 diyagramı `players[], runs[], ball_paths[], frames[]` olarak özetliyor; şablon dosyası ise çizgileri `lines[]` içinde `kind` ile tutuyor. Şablonla uyumlu kalmak için çizgiler tek listede: `kind` ∈ `run`, `ball_path`, `screen` (perdeleme). Ek alanlar: `zones[]` (bölge vurgusu, dikdörtgen), `ball` (başlangıç top konumu) ve `frames[]` (her kare yalnızca konumu değişen oyuncuları ve topu tutar; arası doğrusal enterpolasyon). Kavis: kontrol noktası = orta nokta + `curve` × (−dy, dx); yani pozitif kavis, gidiş yönünün soluna (+90°) bükülür (ikinci dereceden Bézier, şablon notuyla aynı). Ayna `y → 68 − y` yapar ve kavisin işaretini çevirir. Tüm koordinatlar kanonik (SPEC §4). Ayrıntı ADR-0008.

**A-40 · VARSAYIM · Şablonlar ürün içeriğidir.** 7 şablon kulüp verisi değil, şematik başlangıç çizimleridir; `is_demo` ile işaretlenmez. Paylaşılan `routine_templates` tablosunda durur, tüm kiracılar okur, lisans gerekmez. `make seed` yükler; tohumun yalnız geliştirmede çalışması nedeniyle üretimde `kurgu-seed --templates` ayrıca çalıştırılır (idempotent). Şablondan eklenen rutin kulübün kendi kaydıdır.

**A-41 · VARSAYIM · Sürümler değişmez, rutin silinmez.** Her kayıt yeni bir sürüm açar; içerik değişmediyse açmaz. Eski sürüme dönmek, o sürümün kopyasını yeni sürüm olarak kaydeder. Rutinler silinmez, arşivlenir: maç kayıtları ve öneriler rutine bağlanabildiği için geçmiş kaybolmasın. Eşzamanlı düzenlemede `base_version` güncel değilse kayıt 409 ile reddedilir; kullanıcı güncel sürümü açıp yeniden kaydeder.

**A-42 · VARSAYIM · Rutin dışa aktarımı API'de, matplotlib ile.** SPEC §9 PDF için Playwright öngörüyor; o rapor (Faz 6) worker'da üretilecek. Tek rutin sayfası küçük ve anlık olduğundan API'de eşzamanlı üretilir: `kurgu_analytics.reports.routine_sheet` diyagramı matplotlib ile vektör PDF ve PNG'ye çizer. Yazı tipi DejaVu Sans'tır: IBM Plex projede yalnızca web biçiminde (woff2) var ve Türkçe karakterler için gömülebilir TTF gerekiyor. Dışa aktarılan, kaydedilmiş sürümdür; kaydedilmemiş değişiklik varsa düğme önce kaydetmeyi ister.

**A-43 · VARSAYIM · Oyuncu atamaları Faz 4'te.** *(Güncellendi: A-53, Faz 7'ye kaydı.)* `routine_assignments` ve `POST /fixtures/{id}/assignments` maç hazırlığı ekranına (Faz 4) bağlı; Faz 3 kabul kriterlerinde yok. Faz 3'te rutin rollerinde yalnızca serbest metin oyuncu etiketi var.

**A-44 · VARSAYIM · Rutin performansı olay kayıtlarından.** SPEC §6.3 rutin metrikleri, rutine bağlı duran top dizilerinden (`set_pieces.routine_id`) hesaplanır. Bu bağı canlı kayıt (Faz 5) kuracak; o zamana kadar panel boş durumda kalır. Kiracı satırı olduğu için materialized view değil, `security_invoker` görünüm (`v_routine_stats`) kullanılır (ADR-0007'deki `mv_routine_stats` yerine). Oranların önseli kulübün tüm rutinlerinden momentler yöntemiyle; veri olan rutin 2'den azsa Beta(1, 1).

**A-45 · VARSAYIM · Editör yarım saha gösterir.** Editör x ∈ [52,5; 105] aralığını çizer (SPEC §4 "yarım saha görünümü"). Şablonların hepsi x ≥ 78. Editörde sürükleme ve ok tuşları bu aralıkta kalır; API tüm sahayı (0-105) kabul eder.


## Faz 4

**A-46 · VARSAYIM · Kural özneleri hangi sezonu okur.** Kural dosyası `opponent` ve `club` için 2025/26, `*_current` için 2026/27 diyor. Bu genelleştirildi: fikstürün sezonu "güncel" sezondur; `opponent` ve `club` aynı yarışmanın bir önceki sezonudur. Önceki sezonda olmayan takım (ör. yeni çıkan) için o öznenin değerleri yoktur. Değeri olmayan koşul tetiklenmez; deneme modu bunu "veri yok" diye gösterir. `league` öznesi önceki sezonun lig toplamlarıdır. Sezon önerileri (`scope: season`), kulübün sıradaki maçının sezonuna göre değerlendirilir.

**A-47 · VARSAYIM · Metrik adları ve biçimlendiriciler.** Kural dosyasındaki `set_piece_goals_per_100_corners_approx`, metrik modülündeki `goals_per_100_corners` metriğidir; tohumda yaklaşık olduğu için kanıtta "yaklaşık" işaretlenir (A-37). Metrik modülü oranları 0-1 tutar. Bu yüzden `pct100` biçimlendiricisi, değer 1'den küçük ya da 1'e eşitse onu oran sayar ve `pct` gibi gösterir. Sıralar 1 = en yüksek değerdir (CLAUDE.md). `{x.rank.m}` o metrikteki lig sırasını yazar.

**A-48 · VARSAYIM · Güven hesabı.** Her koşul için eşikten uzaklık 0-1 arasına çekilir:
- `rank_gte v`: (sıra − v) / (takım sayısı − v). `rank_lte v`: (v − sıra) / (v − 1).
- `gte`/`gt`/`lte`/`lt`: |x − v| / max(|v|, 1), en çok 1. `pctl_*` sıra gibi.
- `eq` ve `exists`: 1.

`all` için en zayıf koşul, `any` için en güçlü tetiklenen koşul alınır. Puan ≥ 0,5 `high`, ≥ 0,2 `medium`, altı `low`. Koşullardan birinin verisinde "az veri" varsa güven bir basamak düşer. Örnek: ATK_WIN_FOULS'ta rakip 4., eşik 6 → (6 − 4)/5 = 0,4 → `medium`.

**A-49 · VARSAYIM · `min_sample`.** Kuralda `min_sample.matches` varsa, koşullardaki öznelerin maç sayısı bunun altındaysa kural tetiklenmez. Deneme modu bunu "örneklem yetersiz" diye gösterir.

**A-50 · VARSAYIM · Öneriler karar anında kaydedilir.** Öneriler her açılışta güncel kural setiyle yeniden hesaplanır; ekranı açmak veritabanına yazmaz. Öneri kimliği belirlenimcidir: fikstür, kural ve (rutin kuralı için) rutinden `uuid5`. Kabul ya da red, öneriyi o anki kanıt, metin ve kural sürümüyle `recommendations` tablosuna yazar. Kararı verilmiş öneri, kural artık tetiklenmese de kendi kanıtıyla görünmeye devam eder. Karar geri alınabilir (öneri tekrar "öneri" olur). Her karar ve geri alma denetim kaydına girer. Red için gerekçe zorunludur.

**A-51 · VARSAYIM · Kural setleri.** Varsayılan set `seed/recommendation_rules.json` dosyasından, paylaşılan ve kiracısız 0. sürüm olarak yüklenir. Kulüp ilk değişiklikte kendi 1. sürümünü açar; her kayıt yeni sürümdür ve `base_version` ile çakışma denetlenir. Arayüzde açma/kapama, öncelik, koşul eşikleri ve `min_sample` düzenlenir. Metinler (başlık, neden, ne yapın) v1'de varsayılandan gelir. API tüm seti şemayla doğrular. Kural ayarlarını admin ve head_coach değiştirir (SPEC §12.1); kural ekranı `/admin/rules` altındadır.

**A-52 · VARSAYIM · MD planı şablonları.** İki şablon var:
- **Standart hafta:** SPEC §8.1'deki gibi MD+1, MD-4, MD-3, MD-2, MD-1, MD.
- **Sıkışık hafta:** iki maçlı hafta için MD+1, MD-2, MD-1, MD. Savunma organizasyonu MD-2'ye, rutin teyidi MD-1'e toplanır.

Plan, fikstür için ilk kez açıldığında seçilen şablondan oluşturulur. Gün tarihleri başlama saatinden Europe/Istanbul gününe göre hesaplanır. MD+1 bu maçın ertesi günüdür; planda maçın video üzerinden duran top incelemesi için yer alır (saha çalışması yok).

Kabul edilen öneri plana madde ekler: hücum ve denge önerileri MD-3'e (sıkışık haftada MD-1'e), savunma önerileri MD-4'e (sıkışık haftada MD-2'ye) gider. Karar geri alınırsa madde, henüz tamamlanmadıysa silinir. Sorumlu, kulüpte plan maddesi işaretleme izni olan üyelerden seçilir.

**A-53 · VARSAYIM · Oyuncu atamaları Faz 7'ye.** A-43 bunları Faz 4'e almıştı, ancak tohumda kadro (oyuncu listesi) yok ve atama ekranı markaj optimizasyonuyla (Faz 7, SPEC §7.3) aynı oyuncu verisine dayanıyor. Faz 4'te plan maddeleri bir rutine bağlanabilir ("Rutin provası"); oyuncu-rol ataması Faz 7'de oyuncu verisiyle gelir.

**A-54 · VARSAYIM · Öneri geri beslemesi Faz 5'te.** SPEC §7.1'deki "maçtan sonra öneriyle ilişkili duran top sonuçları", maç içi kayda (Faz 5) bağlı. Faz 4'te karar geçmişi tutulur; sonuç paneli, "ilişki, neden değil" uyarısıyla birlikte Faz 5'te eklenir.

**A-55 · VARSAYIM · Genel bakış önerileri tek uçtan.** SPEC §11'deki `GET /recommendations/season` yerine `GET /prep/overview` kullanılır. Tek çağrı hem sezon önerilerini hem yaklaşan maçların tehdit etiketlerini (en çok iki savunma önerisi) ve fikstür bilgisini döner; `/prep` listesi de aynı ucu okur. Sezon önerileri karar almaz, yalnızca gösterilir.

## Faz 5

**A-56 · VARSAYIM · Maç başına tek kayıt oturumu.** Bir kulüpte bir maç için tek `tagging_session` vardır; aynı maçı kaydeden tüm cihazlar ona katılır. `POST /tagging-sessions {match_id}` oturum yoksa açar, varsa var olanı döner. Böylece çoklu cihaz senkronizasyonu tek bir sıra numarası (`server_seq`) üzerinden yürür.

**A-57 · VARSAYIM · Çoklu cihaz bildirimi WebSocket yerine çekmeyle.** SPEC §11 `WS /ws/tagging/{id}` diyor. Erişim token'ı tarayıcıya verilmediği için (ADR-0005) tarayıcı API'ye doğrudan WebSocket açamaz. Bu fazda istemci çevrimiçiyken 5 saniyede bir `since=server_seq` ile değişiklikleri web sunucusu üzerinden çeker. Protokol ADR-0004'teki gibidir; ileride WebSocket eklenirse yalnızca bildirim katmanı değişir.

**A-58 · VARSAYIM · Canlı kayıt alanları ve kısayollar.** Bir kayıt şunları taşır: tür (`C` korner, `F` serbest vuruş, `T` uzun taç), kullanan takım (`H` ev sahibi, `A` deplasman), sonuç, isteğe bağlı rutin (`R`), isteğe bağlı ilk temas (hücum ya da savunma takımı), devre ve maç saati (saniye). SPEC §3.2 sekiz sonuç tanımlar; kısayollar `1-8`: gol, isabetli şut, isabetsiz şut, engellenen şut, ilk temas şutsuz, uzaklaştırma, top kontrolde kaldı, kontra yendi. Sonuca basmak kaydı tamamlar (tür ve takım bir sonraki kayıt için seçili kalır), yani bir kayıt en fazla üç dokunuştur. Rutin yalnızca kulübün kendi duran toplarında seçilebilir.

**A-59 · VARSAYIM · Canlı kaydın duran top satırına dönüşmesi.** Senkronize kayıt, aynı kimlikle `set_pieces` satırı olur (`source='live_tag'`). Şut sayısı sonuçtan türetilir (gol ve şut sonuçları 1). Canlı kayıtta xG yoktur ve 0 yazılır; arayüz bunu "xG yok" diye gösterir. Silinen kayıt (mezar taşı) duran top satırını da siler. Senkronizasyondan sonra metrik görünümlerinin yenilenmesi worker kuyruğuna alınır.

**A-60 · VARSAYIM · Video yükleme.** Tarayıcı dosyayı parçalar halinde doğrudan depoya yükler: S3/MinIO'da imzalı çok parçalı yükleme, yerel depoda API'nin HMAC ile imzaladığı kısa ömürlü yükleme adresleri (geliştirme ve test). Sınırlar: en çok 8 GB, parça 16 MB, türler `video/mp4`, `video/quicktime`, `video/x-matroska`, `video/webm`. Video bir maça bağlanır; `offset_s` maç saatinin videodaki başlangıcıdır ve elle girilir.

**A-61 · VARSAYIM · HLS dönüştürme.** Worker videoyu tek kalitede (720p, H.264/AAC, 6 sn parça) HLS'ye çevirir. ffmpeg, `imageio-ffmpeg` paketinin içindeki derlenmiş ikiliyle gelir; böylece WSL'de ya da CI'da `sudo apt` gerekmez. Çoklu kalite (ABR) sonraya bırakıldı. Oynatma listesi web sunucusu üzerinden verilir ve parçalar 10 dakikalık imzalı adreslerle okunur.

**A-62 · VARSAYIM · Klip ve duran top bağı.** Bağ `video_clips.set_piece_id` alanındadır; `set_pieces.video_clip_id` kullanılmaz. Bir duran topun birden fazla klibi olabilir. Rutin sayfası, o rutinle kaydedilmiş duran topların kliplerini listeler.

**A-63 · VARSAYIM · Öneri geri bildirimi (A-54'ün devamı).** Oynanmış bir maçın hazırlık sayfasında, kabul edilen her öneri için maçtaki ilgili canlı kayıtlar gösterilir: hücum önerilerinde kulübün, savunma önerilerinde rakibin duran topları. Panelde "ilişki, neden değil" uyarısı bulunur; başarı puanı hesaplanmaz.

**A-64 · VARSAYIM · Test videosu.** E2E testi için ffmpeg'in `testsrc` deseniyle üretilmiş 10 saniyelik sentetik bir video repoya eklenir. Gerçek maç görüntüsü kullanılmaz.

**A-65 · VARSAYIM · E2E'de canlı kayıt ve video en sona.** Canlı kayıt duran top satırı yazar ve A-36 gereği kulübün o takım-sezon olay toplamlarını geçici olarak değiştirir. Bu yüzden `live` ve `video` E2E dosyaları ayrı bir Playwright projesinde (`pwa`, tablet) masaüstü ve tablet projelerinden sonra çalışır ve oluşturdukları kayıtları siler. Playwright'ın Chromium'unda H.264/AAC çözücü yok; video E2E testi HLS teslimini (oynatma listesi ve parça) her tarayıcıda, oynatmayı yalnız çözücü varsa doğrular.

**A-66 · VARSAYIM · Maçın duran topları okuma iznidir.** `GET /fixtures/{id}/set-pieces` canlı kayıt izni yerine `read_analysis` ister; hazırlık sayfasındaki geri bildirim paneli (A-63) teknik direktör ve izleyici rollerine de görünür. Kayıt yazma uçları `live_tagging_video` izninde kalır.

**A-67 · VARSAYIM · Video silme depoyu da temizler.** Videoyu silmek kliplerini (yabancı anahtarla) ve depodaki kaynak ile HLS dosyalarını siler. Yarım kalan yükleme iptal edilir. Silme denetim kaydına yazılır.

## Faz 6

**A-68 · VARSAYIM · Rapor türleri.** Faz 6'da iki tür vardır: `opponent` (rakip raporu) ve `match_plan` (maç planı). İkisi de kulübün bir fikstürüne bağlıdır; rakip, fikstürdeki diğer takımdır. Oyuncu görev kartları (SPEC §14, P1) oyuncu-rol atamasına bağlı olduğundan Faz 7'ye kalır (A-53). Rapor oluşturma ve indirme `read_analysis` ister: rapor, kullanıcının zaten okuyabildiği verinin dökümüdür.

**A-69 · VARSAYIM · Maç planındaki "görev atamaları".** Oyuncu atamaları Faz 7'de (A-53). Faz 6 maç planında görev atamaları, MD planı maddelerinin sorumlu kişileri ve rutinlerdeki rol etiketleridir. "Savunma organizasyonu" kabul edilen savunma önerileri ve bağlı savunma rutinleridir.

**A-70 · VARSAYIM · Rapor indirme.** PDF nesne deposunda durur; `GET /reports/{id}` hazır raporda 10 dakikalık imzalı adres döner (SPEC §14). Arşiv sayfası adresi her açılışta yeniler. Rapor silme Faz 6'da yoktur.

**A-71 · VARSAYIM · 15 saniye ölçümü.** Kabul ölçütü işin başlangıcından PDF'in depoya yazılmasına kadar geçen süredir (`reports.duration_ms`). E2E testi ayrıca isteğin gönderilmesinden "hazır" durumuna kadar geçen süreyi ölçer ve 15 sn sınırını orada da uygular.

**A-72 · VARSAYIM · Isı haritası ve klip QR kodları.** Isı haritası rakibin sezon duran toplarının hedef bölgelerinden (§3.3) sayılır; bölgesi olmayan diziler sayılmaz, hiç bölge yoksa "Bölge verisi yok" yazar. QR kodu, rakibin duran toplarına bağlı kliplerin web adresini (`KURGU_PUBLIC_WEB_URL` + `/video/{id}?clip=`) taşır; en çok 6 klip.

**A-73 · VARSAYIM · Brifing girdisi.** Brifing bir fikstür içindir. Girdi: fikstür (hafta, tarih, ev/deplasman), rakibin ve kulübün eşleşme metrikleri (ham değer, gösterim, sıra, takım sayısı, lig ortalaması, dolaylı işareti, az veri işareti), reddedilmemiş öneriler (başlık, gerekçe, aksiyon, kanıt) ve MD planı özeti. Oyuncu adı girdide yoktur.

**A-74 · VARSAYIM · Sayı eşleştirme kuralları.** Metindeki her sayı (ondalık virgül, binlik nokta, yüzde, sıra noktası ve tarih biçimleri dahil) girdideki bir sayının aynı ya da gösterim biçimindeki karşılığı olmalıdır. Girdideki oranlar hem 0-1 hem yüzde biçiminde kabul edilir. Yuvarlama serbest değildir: girdide `15,4` varsa metinde `15` kabul edilmez. Tek basamaklı `0` ve `1` de denetlenir.

**A-75 · VARSAYIM · Brifing eşzamanlı üretilir.** `POST /fixtures/{id}/briefing` modeli çağırır ve sonucu döner (en çok iki deneme). Brifing kısadır; ayrı iş kuyruğu kullanılmaz. Son doğrulanmış brifing `GET /fixtures/{id}/briefing` ile okunur ve rakip raporuna eklenir.

**A-76 · VARSAYIM · LLM kiracı ayarı.** `tenants.settings.llm = {enabled, monthly_requests, monthly_tokens}`; varsayılan açık, ayda 200 istek ve 2.000.000 token. Ay, UTC takvim ayıdır; her deneme (yeniden deneme dahil) bir istek sayılır. Ayarı yönetici (`user_admin_audit`) değiştirir. İzinler matriste yok (SPEC §12.1): brifing üretmek hazırlık içeriği yazan rollere (`edit_routines`: yönetici, teknik direktör, duran top antrenörü, analist) açıktır, okumak `read_analysis` ister.

