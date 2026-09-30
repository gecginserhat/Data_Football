# Kurgu: Profesyonel Duran Top Analiz Platformu
## Claude Code için ürün ve teknik şartname · v1.0 · 28.09.2026

> Bu belge, Claude Code'un Kurgu'yu sıfırdan, üretim kalitesinde inşa etmesi için hazırlanmış ana talimattır. Kalıcı çalışma kuralları `CLAUDE.md` dosyasındadır. Tohum verisi `seed/` klasöründedir.

---

## 0. Claude Code için çalışma talimatı

**Rolün:** Kıdemli full-stack yazılım mühendisi, veri mühendisi ve futbol veri analistisin. Kararlarında bir spor bilimcinin ve profesyonel bir duran top antrenörünün bakışını kullanırsın. Kullanıcıların teknik direktörler, analistler ve performans ekipleri; zamanları kısıtlı, yanlış veriye tahammülleri yok.

**Çalışma sırası (ZORUNLU):**
1. Bu belgenin tamamını ve `CLAUDE.md` dosyasını oku. `seed/` altındaki dosyaları incele.
2. Kod yazmadan önce:
   - `docs/assumptions.md` dosyasına belirsizlikleri yaz. Engelleyici olanları bana sor. Diğerleri için makul bir varsayım yap ve gerekçesini yaz.
   - `docs/adr/` altına mimari karar kayıtlarını (ADR) yaz. En az şunlar olmalı: modüler monolit, veritabanı ve çok kiracılık, kanonik olay modeli, offline senkronizasyon, kimlik doğrulama.
   - Faz 0 ve Faz 1 için görev listesini `docs/PROGRESS.md` dosyasına çıkar ve onayımı bekle.
3. Fazları (bkz. §19) sırayla, küçük ve test edilebilir adımlarla uygula. Her adımda kodu yaz, testini yaz, lint/typecheck/test çalıştır, ardından commit at (Conventional Commits).
4. Her fazın sonunda kabul kriterlerini `docs/PROGRESS.md` içinde tek tek işaretle ve bana kısa bir rapor ver: ne yapıldı, ne kaldı, riskler.

**Kesin kurallar:**
- **Veri uydurma YASAK.** Arayüzde gösterilen her sayı veritabanındaki bir kayda dayanmalı. Demo verisi `is_demo=true` ile işaretlenir ve arayüzde "Örnek veri" rozetiyle gösterilir.
- **Web kazıma (scraping) YASAK.** FotMob, Mackolik, Sofascore, Transfermarkt ve benzeri sitelerin kullanım şartları bunu yasaklar. Yalnızca lisanslı sağlayıcı API'leri, açık veri (StatsBomb Open Data; atıf ve lisans koşullarıyla, yalnız geliştirme ve test için) ve kullanıcının içe aktardığı dosyalar kullanılır.
- **Formüller tek yerde durur.** Alan formülleri `analytics/kurgu_analytics/metrics/` altında bulunur. Her fonksiyonun docstring'inde formülü, birimi ve kaynağı yazar; her biri birim testle doğrulanır.
- **Mikroservis yok.** Modüler monolit kurulur: API ve worker aynı Python paketinden çalışır.
- **Güvenlik varsayılan olarak açıktır.** Her kiracı tablosunda RLS bulunur, sağlık verisi şifreli saklanır, sırlar yalnızca ortam değişkenlerindedir.
- **Dil kuralı.** Arayüz Türkçedir ve tüm metinler i18n anahtarlarıyla yazılır; İngilizce ikinci dildir. Kod, tablo ve alan adları İngilizcedir.

---

## 1. Ürün özeti

### 1.1 Problem
Süper Lig'de 2025/26 sezonunda atılan 812 golün 166'sı (%20,4) penaltı dışındaki duran toplardan geldi. Maç başına 0,54 duran top golü düştü; aynı sezon Premier Lig'de bu sayı 0,71'di (FotMob). Buna rağmen çoğu kulüpte duran top işi bir yardımcı antrenörün yan görevi olarak kalıyor. Veri dağınık halde duruyor: videolar bir klasörde, çizimler bir defterde, sonuçlar ise hiçbir yerde kayıtlı değil. Teknik ekip değişince bu bilgiyle birlikte kurumsal hafıza da kayboluyor.

### 1.2 Çözüm
Kurgu, bir kulübün **duran top işletim sistemidir**: veri → analiz → öneri → haftalık plan → antrenman → maç içi kayıt → video → geri bildirim döngüsünü tek yerde kapatır.

### 1.3 Hedefler (ölçülebilir)
| # | Hedef | Ölçüm |
|---|---|---|
| G1 | Analist, rakip duran top raporunu 30 dakikanın altında hazırlar | Rapor oluşturma süresi (telemetri) |
| G2 | Maç içinde bir duran top kaydı en fazla 3 dokunuş ve 5 saniye sürer | Canlı kayıt olay zaman damgaları |
| G3 | Her önerinin kanıtı ve güven düzeyi görünür; öneriler %100 izlenebilir | Öneri kayıtlarında `evidence` alanı dolu |
| G4 | Kulübün maçlarının en az %90'ı sezon boyunca duran top kaydıyla işlenir | Kayıtlı maç / oynanan maç |
| G5 | Teknik ekip haftalık planı her maç için kullanır | Planı tamamlanan fikstür oranı ≥ %80 |

### 1.4 Kapsam dışı (v1)
- Yayın görüntüsünden bilgisayarlı görü ile takip verisi üretmek: sermaye yoğun, lisanslı sağlayıcılar var.
- Genel event verisi toplama: Kurgu yalnızca duran top etiketler; genel event verisi sağlayıcıdan gelir.
- Oyuncu transfer ve scouting modülü: ayrı bir ürün.
- Taraftara açık site, bahis ya da tahmin özellikleri.
- Tıbbi kayıt sistemi (EMR): yalnızca yük ve iyi oluş verisi tutulur; tanı ve tedavi bilgisi tutulmaz.

### 1.5 Personalar ve yapılacak işleri
| Persona | Ana işi | Kurgu'da ne yapar |
|---|---|---|
| Teknik direktör | Maç planına karar vermek | Hazırlık özetini okur, önerileri onaylar ya da reddeder |
| Duran top antrenörü / yardımcı antrenör | Rutin tasarlamak ve çalıştırmak | Rutin kütüphanesi, oyuncu atamaları, haftalık plan |
| Maç analisti | Rakibi çözmek, maçı kaydetmek | Rakip analizi, canlı kayıt, video klipleri, raporlar |
| Performans antrenörü / spor bilimci | Yükü yönetmek | Antrenman yükü, sıçrama ve kafa vuruşu hacmi, iyi oluş |
| Sağlık ekibi | Sağlık riskini izlemek | Yalnızca kendi rolüne açık alanlar |
| Oyuncu | Görevini bilmek | Telefonda kendi görev kartı |
| Sportif direktör / yönetim | Sonucu izlemek | Salt okunur sezon raporu |
| Kulüp yöneticisi | Sistemi yönetmek | Kullanıcılar, roller, veri kaynakları, kural ayarları |

---

## 2. Kapsam ve öncelikler

| Modül | P0 (MVP) | P1 | P2 |
|---|---|---|---|
| Kimlik, kiracılık, roller | OIDC, RBAC, RLS | SSO (Entra ID / Google) | SCIM |
| Veri çekirdeği | Tohum verisi, CSV/Excel içe aktarım, StatsBomb Open Data adaptörü, kanonik model | Lisanslı sağlayıcı adaptörleri (StatsBomb API, Opta, Wyscout) | Takip verisi (SkillCorner vb.) |
| Duran top çıkarımı ve metrikler | Olaylardan duran top dizileri, takım metrikleri, lig kıyası | Bayes büzülmesi, rakibe göre düzeltilmiş puanlar | VAEP/xT ile duran top değerleme |
| Analiz ekranları | Genel bakış, Lig, Rakip analizi | Oyuncu duran top profilleri | Sezonlar arası trendler |
| Rutin kütüphanesi | SVG taktik tahtası, şablonlar, sürümleme | Kare kare animasyon, rol atamaları | Rakip rutin kütüphanesi (gözlem) |
| Maç hazırlığı | Kural motoru, öneriler, haftalık plan (MD döngüsü), onay | Markaj atama optimizasyonu | Öneri sonuç analizi |
| Maç kaydı | PWA canlı kayıt, çevrimdışı çalışma, senkronizasyon | Çoklu analist gerçek zamanlı oturum | Kısayol profilleri |
| Video | Yükleme, klip, olaya bağlama | HLS dönüştürme, oynatma listesi | Otomatik zaman senkronizasyonu |
| Raporlar | Rakip raporu PDF, maç planı PDF | Oyuncu görev kartları | Sezon raporu |
| LLM | — | Kanıta bağlı brifing metni | Soru-cevap asistanı |
| Spor bilimi | — | sRPE, iyi oluş, sıçrama ve kafa hacmi, EWMA | Giyilebilir cihaz entegrasyonu |

---

## 3. Alan modeli ve sözlük

### 3.1 Duran top sınıflandırması
| Tür (`sp_type`) | Alt tür (`sp_subtype`) | Not |
|---|---|---|
| `corner` | `inswing`, `outswing`, `driven`, `short`, `other` | Kullanıldığı taraf `side`: `left` / `right` (hücum yönüne göre) |
| `free_kick` | `direct_shot`, `crossed`, `short`, `other` | Bölge: `wide`, `central`, `deep` (x < 70) |
| `throw_in` | `long` | Yalnızca hücum üçte birlik bölgesinden ceza sahasına atılanlar |
| `penalty` | — | **Duran top metriklerine dahil edilmez**, ayrı raporlanır |

### 3.2 Faz, temas ve sonuç
- **Birinci faz:** Teslimden sonraki ilk temas ve ondan doğan şut. Varsayılan pencere: teslimden itibaren 5 saniye içinde ya da en fazla 1 ek pas.
- **İkinci faz:** Birinci fazdan sonra, top hâlâ hücum üçte birlik bölgesindeyken ve pencere süresi içindeyken gelen aksiyonlar. Varsayılan toplam pencere 20 saniyedir; ayarlanabilir.
- **İlk temas (`first_contact`):** Teslimden sonra topa dokunan ilk oyuncu ve takımı. Bu, duran topun en önemli ara metriğidir.
- **Sonuç (`outcome`):** `goal`, `shot_on_target`, `shot_off_target`, `shot_blocked`, `first_contact_no_shot`, `cleared`, `possession_retained`, `counter_conceded`.

### 3.3 Teslim hedef bölgeleri
Bölgeler, teslim her zaman `y < 34` tarafından geliyormuş gibi normalize edilmiş koordinatta (`y' = y` ya da `68 − y`) tanımlanır. Tüm eşikler ayarlanabilir.

| Kod | Ad | Tanım (metre, hücum edilen kale x = 105) |
|---|---|---|
| `NP` | Yakın direk | x ≥ 97 ve y' ∈ [20, 31,5) |
| `C6` | Altı pas merkezi | x ≥ 99,5 ve y' ∈ [31,5, 36,5] |
| `FP` | Arka direk | x ≥ 97 ve y' ∈ (36,5, 48] |
| `PS` | Penaltı noktası bölgesi | x ∈ [91, 97) ve y' ∈ [26, 42] |
| `ED` | Ceza sahası önü / yay | x ∈ [80, 91) ve y' ∈ [24, 44] |
| `SH` | Kısa | Ceza sahası dışında, köşe bayrağına en fazla 25 m mesafede |
| `OT` | Diğer | Yukarıdakilerin dışında kalanlar |

### 3.4 Rutin rolleri
`taker` (kullanan), `near_post_runner`, `far_post_runner`, `target` (hedef), `blocker` (perdeleyici), `decoy` (aldatıcı koşu), `second_ball` (ceza yayı / ikinci top), `rest_defense` (geride kalanlar). Savunmada: `zonal_1..n`, `man_marker`, `near_post_guard`, `edge_guard`, `counter_outlet`.

### 3.5 Savunma şemaları
`zonal`, `man`, `hybrid` (örneğin 3 alan + 4 adam adama). Hem gözlemlenen şema (rakip) hem uygulanan şema (kendi takımınız) ayrı ayrı kaydedilir.

---

## 4. Koordinat sistemi (kanonik)
- Saha 105 × 68 m. **x**, hücum yönündedir; hücum edilen kale x = 105'tedir. **y ∈ [0, 68]**: y = 0 hücum eden takımın sağ taç çizgisi, y = 68 sol taç çizgisidir. Kale merkezi (105, 34).
- Referans noktaları: kale direkleri y = 30,34 ve 37,66; altı pas x ≥ 99,5 ve y ∈ [24,84, 43,16]; ceza sahası x ≥ 88,5 ve y ∈ [13,84, 54,16]; penaltı noktası (94, 34); yay yarıçapı 9,15 m.
- Sağlayıcı koordinatları adaptörde dönüştürülür. Örneğin StatsBomb 120 × 80'dir ve y ekseni aşağı doğru artar. Dönüşümler birim testle doğrulanır.
- Rutin çizimleri de bu koordinatlarda saklanır; arayüz yarım saha görünümünde çizer.

---

## 5. Veri mimarisi

### 5.1 Kaynaklar ve hukuki çerçeve
| Kaynak | Kullanım | Durum |
|---|---|---|
| `seed/super_lig.json` | Geliştirme ve demo: takım bazında özet (2025/26 ve 2026/27 ilk 6 hafta), puan durumu, fikstür | Kamuya açık sayfalardan elle derlenmiş özet. **Canlı kullanımda lisanslı veriyle değiştirilir.** |
| StatsBomb Open Data | Olay düzeyinde geliştirme ve test, çıkarım algoritmasının doğrulanması | Lisans ve atıf koşullarına uyulur; Süper Lig'i kapsamaz |
| CSV/Excel içe aktarım | Kulübün elindeki veriler (sağlayıcı dışa aktarımları, kendi tabloları) | Eşleştirme sihirbazı ve doğrulama raporuyla |
| Lisanslı API'ler (P1) | StatsBomb API, Opta/Stats Perform, Wyscout | Adaptör arayüzü üzerinden, sözleşme koşullarına göre |
| Takip verisi (P2) | SkillCorner, TRACAB, Second Spectrum | kloppy ile |
| Kulübün kendi kaydı | Canlı kayıt ve video etiketleme | Birincil veri: duran toptan yenilen goller dahil |

> Kamuya açık kaynaklarda takım bazında "duran toptan yenilen gol" verisi bulunamadı. Bu boşluğu kulübün kendi kaydı doldurur. Arayüz, dolaylı göstergeleri (hava topu, faul, uzaklaştırma) her zaman "dolaylı" etiketiyle gösterir.

### 5.2 Katmanlar
```
raw (bronze)    → sağlayıcıdan gelen ham yük; değişmez, sürümlü (object storage + meta tablo)
canonical (silver) → SPADL uyumlu olaylar, maçlar, oyuncular, takımlar (Postgres)
marts (gold)    → duran top dizileri, metrikler, lig kıyasları (tablolar + materialized view)
```
Her yükleme idempotent olmalı: aynı `source_hash` iki kez yüklenmez. Yükleme işleri worker'da çalışır; durumları `ingestion_runs` tablosunda tutulur.

### 5.3 Kanonik olay modeli
- Olay modeli **SPADL** ile uyumludur. Dönüşüm için `socceraction` ve `kloppy` kütüphaneleri kullanılır (StatsBomb, Opta, Wyscout ve diğerleri).
- `events` tablosunun alanları: `match_id`, `period`, `time_s`, `team_id`, `player_id`, `type`, `result`, `bodypart`, `start_x`, `start_y`, `end_x`, `end_y`, `sequence_id`, `set_piece_id` (boş olabilir), `xg` (boş olabilir), `provider`, `provider_event_id`, `raw_ref`.
- Sağlayıcının kendi xG'si varsa `xg` alanına yazılır; hangi sağlayıcıdan geldiği `xg_source` ile kaydedilir.

### 5.4 Kimlik eşleştirme
`provider_id_map (entity_type, provider, provider_id, kurgu_id, confidence, confirmed_by)` tablosu tutulur. İsim ve doğum tarihi üzerinden bulanık eşleştirme yapılır; eşik altındaki adaylar yönetim ekranında elle onaylanır. Onaylanmamış eşleşmeler metriklere girmez.

### 5.5 Duran top çıkarım algoritması
```
RESTARTS = {corner_crossed, corner_short, freekick_crossed, freekick_short, shot_freekick, throw_in}
for i, a in actions (maç ve periyoda göre sıralı):
    if a.type not in RESTARTS: continue
    if a.type == throw_in and not (a.start_x >= 70 and (a.end_x >= 88.5 or length(a) >= 20)): continue
    sp = SetPiece(team=a.team, type/subtype=classify(a), side=side_of(a), taker=a.player,
                  target_zone=zone(a.end_x, a.end_y, side), start_time=a.time_s)
    phase = 1; passes_after = 0
    for b in actions[i+1:]:
        if b.period != a.period or b.time_s - a.time_s > WINDOW_S (20): break
        if b.type in RESTARTS ∪ {kickoff, goalkick}: break          # yeni duran oyun
        if lost_possession(b, sp.team) and ball_left_final_third(b): break
        if sp.first_contact is None and is_touch(b): sp.first_contact = (b.team, b.player)
        if b.type == pass and b.team == sp.team: passes_after += 1
        if b.time_s - a.time_s > PHASE1_S (5) or passes_after >= 2: phase = 2
        if is_shot(b): sp.shots.append(Shot(b, phase)); sp.xg_total += b.xg or 0
    sp.outcome = derive_outcome(sp)
```
- `shot_freekick` teslimin kendisi şut olduğu için doğrudan birinci faz şutu sayılır.
- **Doğrulama (ZORUNLU):** StatsBomb Open Data üzerinde, StatsBomb'un `play_pattern` alanıyla ("From Corner", "From Free Kick", "From Throw In") karşılaştırılır. Şut düzeyinde en az %95 uyum hedeflenir. Uyum raporu `docs/validation/` altına yazılır.

### 5.6 Veri kalitesi
Kontroller `pandera` şemalarıyla yapılır: zorunlu alanlar, koordinat aralıkları, periyot ve zaman tutarlılığı, yinelenen olaylar, referans bütünlüğü, maç başına makul olay sayısı. Her yükleme bir kalite raporu üretir. Kritik hata varsa yükleme "karantina" durumunda kalır ve metriklere girmez.

### 5.7 Tohum verisi
Tohum dosyalarının içeriği Ek A'da anlatılır. `make seed` bu dosyaları yükler. Tohum kayıtları `is_demo=false` ve `source='seed:<dosya>'` ile işaretlenir; metrikler ile arayüz bunları gerçek veri gibi kullanır, ancak kaynak rozeti gösterir.

---

## 6. Metrik kataloğu

### 6.1 Takım metrikleri
| id | TR etiket | Formül | Kaynak | Not |
|---|---|---|---|---|
| `set_piece_goals` | Duran top golü | Duran top dizilerinden gelen goller (penaltı hariç) | olaylar / tohum | |
| `set_piece_xg` | Duran top xG | Σ şut xG (tüm fazlar) | olaylar / tohum | |
| `set_piece_goal_share` | Duran top payı | set_piece_goals / goals | türetilir | 2025/26 lig toplamı %20,4 (166/812) |
| `set_piece_goals_minus_xg` | Gol eksi xG | set_piece_goals − set_piece_xg | türetilir | Bitiricilik ya da şans; kalıcı değildir |
| `set_pieces_per_match` | Maç başı duran top | tür bazında sayım / maç | olaylar | |
| `first_contact_win_pct` | İlk temas kazanma % | kendi ilk temaslarımız / teslimler | olaylar / kayıt | hem hücum hem savunma için |
| `shots_per_set_piece` | Duran top başına şut | şutlu dizi / dizi | olaylar / kayıt | |
| `xg_per_set_piece` | Duran top başına xG | set_piece_xg / dizi | olaylar | |
| `second_phase_xg_share` | İkinci faz payı | faz 2 xG / toplam duran top xG | olaylar | |
| `set_piece_goals_against` | Duran toptan yenilen | rakip dizilerinden yenilen goller | olaylar / **kulüp kaydı** | Kamuya açık kaynakta yok |
| `corners_per_match` | Korner / maç | | tohum / olaylar | |
| `goals_per_100_corners` | 100 kornere düşen gol | korner golleri / korner × 100 | olaylar | Tohumda yalnızca yaklaşık değer (tüm duran top golleri) |
| `headed_goals` | Kafa golü | | tohum / olaylar | |
| `direct_fk_goals` | Direkt serbest vuruş golü | | tohum / olaylar | |
| `aerial_win_pct` | Hava topu kazanma % | | tohum / olaylar | Savunma için **dolaylı** gösterge |
| `aerials_won_per_match` | Kazanılan hava topu / maç | | tohum | dolaylı |
| `fouls_committed_per_match` | Yapılan faul / maç | fouls_committed / maç | tohum | Rakibe serbest vuruş verme eğilimi |
| `fouls_won_per_match` | Kazanılan faul / maç | | tohum | |
| `clearances_per_match` | Uzaklaştırma / maç | | tohum | ikinci top göstergesi |
| `fast_break_goals` | Hızlı hücum golü | | tohum | Kendi kornerimizde denge riski |

### 6.2 Oyuncu metrikleri (P1)
Kullananlar için: teslim sayısı, teslimden sonra ilk temasın kendi takımımızda olma oranı ve hedef bölge dağılımı. Hedef oyuncular için: ilk temas, duran toptan kafa şutu ve xG, ceza sahasında hava topu. Savunmacılar için: duran topta ilk temas ve uzaklaştırma.

### 6.3 Rutin metrikleri
Her rutin için kullanım sayısı, ilk temas oranı, şut oranı, kullanım başına xG ve gol. **Oranlar her zaman Bayes büzülmesiyle birlikte gösterilir** (bkz. §6.4).

### 6.4 İstatistiksel ilkeler (ZORUNLU)
- **Küçük örneklem:** Oranlar beta-binom modeliyle büzülür. Önsel dağılımın parametreleri, kulübün ya da ligin tüm rutinlerinden momentler yöntemiyle hesaplanır: μ = ortalama, σ² = varyans, κ = μ(1−μ)/σ² − 1, α = μκ, β = (1−μ)κ. Sonsal ortalama = (başarı + α) / (deneme + α + β). Yanında %80 güvenilir aralık gösterilir.
- **Maç başına sayımlar:** Gamma-Poisson modeli kullanılır. Önsel Gamma(a, b) lig takımlarından kestirilir; sonsal ortalama (a + x) / (b + maç sayısı).
- **Az veri uyarısı:** Deneme sayısı 8'in altındaysa ya da maç sayısı 5'in altındaysa "Az veri" rozeti gösterilir. Kural motoru bu durumda güveni "Düşük" olarak işaretler.
- **Lig sırası:** En yüksek değer 1. sıradır; eşit değerler aynı sırayı alır. Yüzdelik değerler aynı veriden türetilir.
- **Rakibe göre düzeltme (P1):** Takım başına duran top xG'si için, hücum ve savunma etkileri ile iç saha avantajını içeren L2 düzenlemeli bir Poisson GLM (log bağlantılı) kullanılır. Çıktı duran top hücum ve savunma puanıdır.
- **xG:** Önce sağlayıcının xG'si kullanılır. Kendi modelimiz (P2) şu özellikleri kullanır: mesafe, açı, vücut bölgesi (kafa ya da ayak), asist türü, duran top türü, faz, altı pas içinde olup olmama. Model LightGBM ve kalibrasyonla eğitilir; Brier skoru, log loss ve kalibrasyon eğrisiyle, zamana göre bölünmüş çapraz doğrulamayla değerlendirilir ve sürümlenir.
- Tüm metrik fonksiyonları saftır: girdi bir DataFrame, çıktı bir DataFrame. Özellik tabanlı testler (`hypothesis`) şu değişmezleri doğrular: fazların toplamı toplam değere eşittir, oranlar [0, 1] aralığındadır, sıralama tutarlıdır.

---

## 7. Öneri motoru

### 7.1 İlkeler
1. **Açıklanabilirlik:** Her öneri `title`, `why` (kanıt cümlesi, gerçek sayılarla), `action` (sahada ne yapılacağı), `evidence` (JSON: metrik, değer, lig sırası, lig ortalaması, örneklem) ve `confidence` alanlarını taşır.
2. **Kural tabanlı çekirdek:** Kurallar JSON olarak tanımlanır (`seed/recommendation_rules.json`), kiracıya göre eşikleri ayarlanabilir, sürümlenir ve denetlenir. `eval` kullanılmaz; güvenli bir değerlendirici yazılır.
3. **Karar teknik ekibindir.** Öneriler "Öneri" olarak görünür; kabul, red ve not bilgisi gerekçesiyle kaydedilir.
4. **Geri besleme:** Maçtan sonra öneriyle ilişkili duran top sonuçları gösterilir. Nedensellik iddia edilmez; ekranda "ilişki, neden değil" uyarısı durur.

### 7.2 Kural biçimi
```json
{
  "id": "ATK_AERIAL_WEAK_OPP",
  "area": "attack",
  "priority": 1,
  "when": { "all": [ { "subject": "opponent", "metric": "aerial_win_pct", "op": "rank_gte", "value": 12 } ] },
  "title": "Ceza sahasına doğrudan orta gönderin",
  "why": "Rakip hava topu mücadelelerinin {opponent.aerial_win_pct|pct} kadarını kazanıyor; ligde {opponent.rank.aerial_win_pct}. sırada.",
  "action": "Kornerlerde topu altı pas ile penaltı noktası arasına, içe dönük vuruşla gönderin...",
  "template": "tpl-arka",
  "min_sample": { "matches": 5 },
  "enabled": true
}
```
- **Özneler:** `opponent`, `club`, `match` (iç saha / deplasman, hafta), `own_log` (kulübün kendi kayıtları; `routine_stats`, `defense_summary`).
- **Operatörler:** `gte`, `lte`, `gt`, `lt`, `eq`, `rank_gte`, `rank_lte`, `pctl_gte`, `pctl_lte`, `exists`. Birleştiriciler: `all`, `any`, `not`.
- **Biçimlendiriciler:** `pct` (%20,4), `dec1` (1,5), `int`, `signed` (+2,8). Sayılar Türkçe yerel ayarla gösterilir.
- **Güven:** Örneklem büyüklüğü ve eşikten uzaklıktan hesaplanır. Örneğin rank_gte 12 kuralında 18. sıra, 12. sıradan daha güçlü kanıttır. Çıktı `high`, `medium` ya da `low` olur.
- **Tekilleştirme:** Aynı şablona işaret eden önerilerden yalnızca en yüksek öncelikli olan gösterilir. Sıralama önce önceliğe, sonra güvene göredir.
- **Yönetim arayüzü:** Kural listesi, eşik düzenleme, belirli bir fikstür için "hangi kurallar tetikleniyor" deneme modu ve değişiklik geçmişi.

### 7.3 Markaj atama optimizasyonu (P1)
Rakibin hedef oyuncuları ile kendi savunmacılarımız arasındaki atama **Macar algoritmasıyla** (`scipy.optimize.linear_sum_assignment`) hesaplanır.
- Maliyet = max(0, rakip hava tehdidi − savunmacının hava kapasitesi) + pozisyon kısıtı cezaları.
- Hava kapasitesi boy, hava topu kazanma oranı ve varsa sıçrama verisinden oluşan normalize bir skordur.
- Alan savunması yapan oyuncular sabit tutulur.
- Çıktı bir önerilen eşleşme tablosudur; antrenör elle değiştirebilir ve bu değişiklik kaydedilir.

---

## 8. Spor bilimi modülü (P1)

### 8.1 Haftalık döngü (MD kodları; kulübe göre düzenlenebilir varsayılan şablon)
| Gün | Odak (varsayılan) | Duran top çalışması (öneri) |
|---|---|---|
| MD+1 | Toparlanma | Yok. Video üzerinden maç duran top incelemesi |
| MD-4 | Kuvvet ve gerilim | Savunma organizasyonu, orta yoğunluk |
| MD-3 | Dayanıklılık | Hücum rutinleri, tam tekrar |
| MD-2 | Hız | Kısa ve keskin prova, maç temposunda, düşük hacim |
| MD-1 | Aktivasyon | Yürüyüş temposunda üzerinden geçme, görevlerin teyidi |
| MD | Maç | Canlı kayıt |

Haftada iki maç oynanan dönemler için sıkıştırılmış bir şablon da bulunur.

### 8.2 Yük ve iyi oluş
- **Seans yükü (sRPE):** RPE (CR-10 ölçeği) × süre (dakika).
- **İyi oluş:** Hooper indeksi; uyku, stres, yorgunluk ve kas ağrısı (her biri 1-7).
- **Trend:** Akut ve kronik yük için üstel ağırlıklı hareketli ortalama (EWMA; akut λ = 2/(7+1), kronik λ = 2/(28+1)) ve oyuncu içi z-skorları.
- **Akut:kronik oran (ACWR):** Yöntemsel eleştirileri nedeniyle **karar aracı olarak değil**, yalnızca bağlam bilgisi olarak ve uyarıyla gösterilir.
- **Duran topa özgü yük:** Seans başına kafa vuruşu ve maksimal sıçrama tekrarları kaydedilir (elle ya da cihazdan). Oyuncunun haftalık sıçrama sayısı kişisel ortalamasının 2 standart sapma üstüne çıkarsa performans antrenörüne uyarı gider.
- Tüm uyarılar **"dikkat" niteliğindedir, tanı değildir**. Son söz sağlık ekibindedir.

### 8.3 Gizlilik
İyi oluş ve sağlık alanları yalnızca `performance` ve `medical` rollerine açıktır. Veri alan düzeyinde şifrelenir ve her erişim denetim kaydına yazılır. Oyuncu yalnızca kendi verisini görür.

---

## 9. Sistem mimarisi

```
[Next.js web (PWA)] ──HTTPS/JSON──> [FastAPI API] ──SQL──> [PostgreSQL 16 + RLS]
       │  ▲                          │    │                    ▲
       │  └──WebSocket (canlı kayıt)─┘    └──enqueue──> [Worker (Arq)] ──> [Redis]
       │                                                   │
       └──presigned URL──> [Object storage (S3 / MinIO)] <─┘ (video, PDF, ham veri)
                               [OIDC sağlayıcısı (Keycloak yerelde; Entra ID / Google canlıda)]
```

### 9.1 Teknoloji yığını ve gerekçe
| Katman | Seçim | Gerekçe |
|---|---|---|
| Monorepo | pnpm workspaces + Turborepo; Python için `uv` | Tek repo, paylaşılan tipler |
| Web | Next.js 15 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, shadcn/ui (Radix), TanStack Query ve Table, Zustand + zundo (geri al), next-intl, Serwist (PWA), Dexie (IndexedDB) | Olgun ekosistem, erişilebilir bileşenler, çevrimdışı destek |
| Grafik | Özel SVG saha bileşenleri + visx / d3-scale | Saha çizimleri PDF ile uyumlu olsun diye SVG |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | Analitik kod ile aynı dil; tip güvenliği |
| Analitik | pandas / polars, socceraction, kloppy, scikit-learn, LightGBM, scipy, mplsoccer (rapor görselleri), pandera | Futbol veri ekosisteminin standartları |
| İşler | Arq (Redis) | Basit ve async uyumlu |
| Veritabanı | PostgreSQL 16 (RLS, materialized view, pgcrypto) | İlişkisel model, satır düzeyi güvenlik |
| Depolama | S3 uyumlu (yerelde MinIO) | Video, PDF ve ham yükler |
| Kimlik | OIDC; web tarafında Auth.js v5, API tarafında JWT doğrulama | Kurumsal SSO'ya hazır |
| Video | ffmpeg ile HLS'ye dönüştürme (worker), hls.js oynatıcı | Tablette akıcı oynatma |
| PDF | Jinja2 HTML şablonu → Playwright (Chromium) ile PDF | Tasarım kontrolü |
| Tip köprüsü | FastAPI OpenAPI → `openapi-typescript` → `packages/api-client` | Uçtan uca tipler |
| Gözlem | OpenTelemetry, Sentry, yapılandırılmış JSON log | |

**Kaçınılacaklar:** Mikroservisler, GraphQL (REST yeterli), ORM dışında el yazısı SQL (materialized view ve RLS politikaları hariç).

### 9.2 Repo yapısı
```
kurgu/
  apps/web/                  Next.js uygulaması
  apps/api/                  FastAPI uygulaması (routers, services, schemas)
  analytics/kurgu_analytics/ ingestion/ canonical/ setpieces/ metrics/ recs/ models/ reports/
  packages/ui/               tasarım tokenları ve paylaşılan React bileşenleri
  packages/pitch/            saha geometrisi, bölgeler, koordinat dönüşümleri (TS)
  packages/api-client/       üretilmiş TS istemcisi
  infra/                     docker-compose, Dockerfile'lar, (ops.) terraform
  seed/                      tohum verisi
  docs/                      SPEC.md, adr/, PROGRESS.md, assumptions.md, validation/, runbooks/
  CLAUDE.md
```
Saha geometrisi ve bölge tanımları, TS (`packages/pitch`) ve Python (`kurgu_analytics.setpieces.zones`) tarafında aynı olmalıdır. Paylaşılan bir JSON (`packages/pitch/zones.json`) iki tarafça okunur ve ortak test vektörleriyle doğrulanır.

---

## 10. Veritabanı şeması (özet)

Kiracıya ait her tabloda `tenant_id uuid not null` bulunur ve RLS etkindir:
```sql
alter table x enable row level security;
create policy tenant_isolation on x
  using (tenant_id = current_setting('app.tenant_id')::uuid);
```
API her istekte `SET LOCAL app.tenant_id` çalıştırır. Lig verisi (takımlar, maçlar, lig olayları) `tenant_id` null olan paylaşılan tablolarda tutulur; bu tablolara yalnızca lisans kapsamındaki kiracılar okuma erişimi alır (`data_licenses` tablosu üzerinden).

| Tablo | Önemli alanlar |
|---|---|
| `tenants` | id, name, club_team_id, settings (json), data_region |
| `users`, `memberships` | user_id, tenant_id, role, player_id (oyuncu rolü için) |
| `audit_log` | actor, action, entity, entity_id, before/after (json), ip, at. Yalnızca ekleme yapılır |
| `competitions`, `seasons`, `teams`, `players` | kısa kod, isimler, boy, tercih edilen ayak |
| `provider_id_map` | bkz. §5.4 |
| `matches` | season_id, week, home_id, away_id, kickoff_at, score, status |
| `standings_snapshots` | season_id, week, team_id, played, won, drawn, lost, gf, ga, pts |
| `team_season_stats` | season_id, team_id, metric, value, source (tohum ve sağlayıcı) |
| `events` | bkz. §5.3; (match_id, time_s) ve (set_piece_id) indeksli |
| `set_pieces` | match_id, team_id, sp_type, sp_subtype, side, taker_id, target_zone, first_contact_team_id, first_contact_player_id, outcome, xg_total, goal (bool), phase_of_goal, routine_id, observed_scheme, video_clip_id, source (`provider` / `live_tag`) |
| `routines`, `routine_versions` | name, sp_type, diagram (json: players[], runs[], ball_paths[], frames[]), roles[], notes, from_template, version |
| `routine_assignments` | fixture_id, routine_version_id, role, player_id |
| `fixture_plans`, `plan_items` | fixture_id, opponent_id, md_code, title, detail, status, done_by, done_at |
| `recommendations` | fixture_id, rule_id, rule_version, area, priority, confidence, evidence (json), status (suggested / accepted / rejected), decided_by, reason |
| `rule_sets` | tenant_id, version, rules (json), published_at |
| `tagging_sessions`, `live_tags` | client_id (uuid), device_id, created_at_client, server_received_at, deleted (tombstone), payload |
| `video_assets`, `video_clips` | storage_key, duration, hls_key, match_id, offset_s; clip: start_s, end_s, set_piece_id |
| `reports` | type, params, status, storage_key, generated_by |
| `training_sessions`, `session_loads`, `wellness_entries`, `jump_logs` | md_code, duration, rpe, hooper puanları (şifreli), jumps, headers |
| `llm_runs` | purpose, input_hash, model, tokens, output, grounding_check (pass/fail) |

**Materialized view'ler:** `mv_team_setpiece_season`, `mv_league_benchmarks`, `mv_routine_stats`. Bunlar yükleme ya da kayıt senkronizasyonundan sonra worker tarafından eşzamanlı (`CONCURRENTLY`) yenilenir.

**Göç kuralları:** Alembic kullanılır; her göç geri alınabilir olmalıdır. CI, `upgrade → downgrade → upgrade` döngüsünü çalıştırır.

---

## 11. API

- REST, `/api/v1`, OpenAPI 3.1. Hatalar RFC 9457 `application/problem+json` biçimindedir. Sayfalama imleç tabanlıdır. Önbellek için ETag kullanılır. Senkronizasyon ve yükleme uçlarında `Idempotency-Key` başlığı zorunludur.

| Kaynak | Uçlar |
|---|---|
| Kimlik | `GET /me` |
| Lig | `GET /seasons/{id}/standings?week=`, `GET /seasons/{id}/team-metrics`, `GET /seasons/{id}/benchmarks` |
| Takım / rakip | `GET /teams/{id}/profile?season=` (metrikler, sıralar, bulgular), `GET /teams/{id}/set-pieces?season=&type=` |
| Fikstür | `GET /fixtures?team=&from=`, `GET /fixtures/{id}` |
| Hazırlık | `GET /fixtures/{id}/prep` (öneriler, eşleşme notları, plan), `POST /recommendations/{id}/decision`, `PATCH /plan-items/{id}` |
| Kurallar | `GET/PUT /rule-sets/current`, `POST /rule-sets/dry-run {fixture_id}` |
| Rutinler | `GET/POST /routines`, `GET/PUT /routines/{id}`, `GET /routines/{id}/versions`, `POST /routines/from-template/{tplId}`, `POST /fixtures/{id}/assignments` |
| Canlı kayıt | `POST /tagging-sessions`, `POST /tagging-sessions/{id}/sync` (toplu, idempotent), `WS /ws/tagging/{id}` |
| Video | `POST /video/uploads` (presigned multipart), `POST /video/assets/{id}/complete`, `GET/POST /clips` |
| Raporlar | `POST /reports {type, params}` (iş kuyruğu), `GET /reports/{id}` |
| İçe aktarım | `POST /imports` (dosya), `GET /imports/{id}` (eşleştirme ve doğrulama raporu), `POST /imports/{id}/commit` |
| Spor bilimi | `POST /sessions`, `POST /wellness`, `GET /players/{id}/load` |
| Yönetim | `/admin/users`, `/admin/data-sources`, `/admin/audit` |

**Çevrimdışı senkronizasyon protokolü:**
- İstemci her kaydı UUID'siyle IndexedDB'ye yazar ve kaydı kuyruğa ekler.
- `sync` ucu bir dizi `{id, op: upsert|delete, payload, client_ts}` kabul eder.
- Sunucu `id` üzerinden idempotent çalışır. Çakışmada son yazan kazanır, ancak silme işlemi mezar taşı (tombstone) olarak tutulur.
- Yanıtta sunucu sürümü ve reddedilen kayıtlar döner.

---

## 12. Kimlik, yetki, güvenlik ve KVKK

### 12.1 Rol ve izin matrisi
| İzin | admin | head_coach | sp_coach | analyst | performance | medical | player | viewer |
|---|---|---|---|---|---|---|---|---|
| Analiz ekranlarını okuma | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ |
| Rutin oluşturma ve düzenleme | ✓ | ✓ | ✓ | ✓ | – | – | – | – |
| Öneri kararı (kabul / red) | ✓ | ✓ | ✓ | – | – | – | – | – |
| Plan maddelerini işaretleme | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | – |
| Canlı kayıt ve video | ✓ | – | ✓ | ✓ | – | – | – | – |
| Yük ve iyi oluş | ✓* | – | – | – | ✓ | ✓ | kendi verisi | – |
| Sağlık notları | – | – | – | – | – | ✓ | – | – |
| Kural ayarları | ✓ | ✓ | – | – | – | – | – | – |
| Kullanıcı yönetimi, denetim kaydı | ✓ | – | – | – | – | – | – | – |
| Oyuncu görev kartı | ✓ | ✓ | ✓ | ✓ | – | – | kendi kartı | – |

\* Admin, yük ve iyi oluş verisinde yalnızca özet görür; ayrıntıya erişemez.

### 12.2 Güvenlik
- Admin, medical ve performance rolleri için çok faktörlü doğrulama (MFA) zorunludur. Oturumlar kısa ömürlü erişim token'ı ve yenileme token'ıyla yönetilir.
- Sağlık ve iyi oluş alanları uygulama düzeyinde zarf şifrelemeyle (KMS / yerelde anahtar dosyası) korunur. Yedekler de şifrelenir.
- Güvenlik başlıkları: CSP, HSTS, X-Content-Type-Options, çerçeveleme koruması. Oturum açma ve yükleme uçlarında hız sınırı uygulanır. Yüklenen dosyalarda tür doğrulaması, boyut sınırı ve (opsiyonel) ClamAV taraması yapılır. Videolar imzalı URL'lerle sunulur.
- Bağımlılık taraması (pip-audit, osv-scanner) ve imaj taraması (Trivy) CI'da çalışır.

### 12.3 KVKK
Sistem şu özellikleri sağlar:
- Aydınlatma metni ve açık rıza kaydı (sağlık verisi özel nitelikli kişisel veridir).
- Kişisel veri envanteri dökümü.
- Saklama süreleri ve otomatik silme.
- Kişinin kendi verisini dışa aktarma ve silme talebi akışı.
- Veri bölgesi seçimi (`tenants.data_region`).

Kulübün yükümlülükleri (VERBİS kaydı, yurt dışına aktarım koşulları, veri işleyen sözleşmeleri) **kulübün hukuk ekibince teyit edilir**. Bunlar `docs/compliance.md` dosyasında açık soru olarak listelenir.

### 12.4 Veri lisansları
Sağlayıcı verisi yalnızca lisanslı kiracıya gösterilir. Yeniden dağıtım yapılmaz; dışa aktarımlarda sağlayıcı verisi lisans koşuluna göre kısıtlanır ya da atıfla verilir.

---

## 13. Arayüz (frontend)

### 13.1 Bilgi mimarisi (rotalar)
| Rota | Sayfa | Birincil kullanıcı |
|---|---|---|
| `/` | Genel bakış: kulüp durumu, sıradaki maç, sezon önerileri, yaklaşan maçlar ve tehdit etiketleri | Teknik direktör |
| `/prep/[fixtureId]` | Maç hazırlığı: hücum ve savunma önerileri (kanıt ve güvenle), eşleşme notları, markaj önerisi, MD planı, onay | Duran top antrenörü |
| `/opponents/[teamId]` | Rakip analizi: profil çubukları, bulgular, sezon trendi, rakip dizileri ve klipler | Analist |
| `/league` | Puan durumu, duran top tabloları, dağılım grafiği | Herkes |
| `/routines`, `/routines/[id]` | Kütüphane, şablonlar, editör, sürümler, performans | Duran top antrenörü |
| `/live/[fixtureId]` | Canlı kayıt: tablet öncelikli, çevrimdışı çalışır | Analist |
| `/video` | Video merkezi: yükleme, klip, oynatma listesi | Analist |
| `/reports` | Rapor oluşturma ve arşiv | Analist |
| `/performance` | Spor bilimi (P1) | Performans antrenörü |
| `/me` | Oyuncu görünümü: kendi görev kartları (mobil) | Oyuncu |
| `/admin/*` | Kullanıcılar, roller, veri kaynakları, içe aktarım, kurallar, denetim kaydı | Yönetici |
| `/methodology` | Kaynaklar, tanımlar, kurallar, sınırlamalar | Herkes |

### 13.2 Kritik ekranlar ve davranışlar
- **Maç hazırlığı:** Her öneri kartında şunlar bulunur: alan etiketi, öncelik, güven düzeyi, "Neden" (sayılarla), "Ne yapın", şablona ya da rutine bağlantı ve kabul/red düğmesi (red için gerekçe istenir). Plan maddeleri MD kodlarına göre sıralanır, sorumlu kişi atanabilir ve ilerleme çubuğu gösterilir.
- **Rutin editörü:**
  - Çizim araçları: yarım saha SVG, oyuncu ekleme (rol seçimiyle), koşu okları, top yolu (kavisli, noktalı), perdeleme sembolü, bölge vurgusu.
  - Düzen yardımcıları: ızgaraya ve ayna eksenine hizalama (sol ve sağ korner varyasyonu tek tıkla), geri al / yinele.
  - Animasyon ve sürüm: kare kare animasyon (her kare oyuncu pozisyonları ve anahtar kareler arası enterpolasyon), sürüm geçmişi ve sürüm karşılaştırma.
  - Dışa aktarım: PNG ve PDF.
  - Erişilebilirlik: klavyeyle öğe seçme ve ok tuşlarıyla taşıma.
- **Canlı kayıt:**
  - Ekran büyük dokunma hedefleriyle çalışır (en az 56 px).
  - Klavye kısayolları: `C` korner, `F` serbest vuruş, `T` taç, `1-6` sonuç, `H` ya da `A` taraf, `R` rutin seçimi.
  - Kayıtlar IndexedDB'ye anında yazılır. Çevrimiçi / çevrimdışı durum ve bekleyen senkronizasyon sayısı sürekli görünür.
  - Son kayıt 10 saniye içinde geri alınabilir. Maç saati manuel ya da senkronize tutulur.
- **Rakip analizi:** Profil çubukları ligdeki en düşük ve en yüksek değer arasında çizilir; lig ortalaması ve kendi kulübün işaretlenir. Her metrikte kaynak rozeti ve "dolaylı" etiketi bulunur.

### 13.3 Tasarım sistemi (mevcut Kurgu kimliğinden)
- **Renk tokenları:**
  - Açık tema: `--bg #F2F4F1`, `--surface #FFFFFF`, `--ink #0F1B16`, `--ink-2 #44524B`, `--ink-3 #63706A`, `--line #E0E5E0`, `--brand #0E3B2E` (yan menü), `--pri #0E3B2E`, `--accent #E3A008` (vurgu, "sizin kulübünüz"), `--pos #1B7348`, `--neg #B94C16`, `--def #2F6FB3`, `--turf #17513A`.
  - Koyu tema karşılıkları tanımlanır.
- **Tipografi:** IBM Plex Sans (metin) ve IBM Plex Sans Condensed (başlık ve rakam); rakamlarda tabular sayılar.
- **Bileşenler:** AppShell (masaüstünde yan menü, mobilde alt sekme ve çekmece menü), KPI kartı, ProfileBar, RecommendationCard, PlanChecklist, FormChips (G/B/M harfli), TeamBadge (kod rozeti; kulüp logosu marka hakları nedeniyle kullanılmaz), Pitch/HalfPitch, RoutineBoard, DataTable (yapışkan ilk sütun, sıralama), EmptyState, SourceBadge, SampleSizeBadge.
- **Durumlar:** Her veri bileşeninin yükleniyor (iskelet), boş (ne yapılacağını söyleyen), hata (tekrar dene) ve az veri durumları vardır.

### 13.4 Erişilebilirlik, i18n ve performans
- WCAG 2.2 AA uyumu: metinde en az 4,5:1 kontrast, dokunma hedefleri en az 44 px, klavyeyle tam gezinme, `prefers-reduced-motion` desteği. Renk tek başına anlam taşımaz; her durum harf ya da metinle de belirtilir.
- i18n: `tr` varsayılan, `en` ikincil dil. Sayı ve tarih biçimleri yerel ayara uyar.
- **Performans bütçeleri:**
  - Orta seviye tablette 4G bağlantıda LCP ≤ 2,5 sn.
  - Rota başına ilk JS yükü ≤ 200 KB (gzip).
  - Özet uçlarında API p95 ≤ 300 ms.
  - Canlı kayıtta dokunuştan yerel kayda ≤ 50 ms.

---

## 14. Raporlar
- **Rakip raporu (PDF, 2-4 sayfa):** Özet, profil, bulgular, öneriler, rakip dizilerinin bölge ısı haritası, varsa klip QR kodları.
- **Maç planı (PDF):** Seçilen rutinler (diyagramlarıyla), görev atamaları, savunma organizasyonu, MD planı.
- **Oyuncu görev kartları (P1):** Oyuncu başına tek sayfa, mobil uyumlu.
- Raporlar worker'da üretilir. İlerleme gösterilir, dosya object storage'a yazılır ve imzalı URL ile indirilir. Her raporda kaynak ve veri tarihi yazar.

---

## 15. LLM entegrasyonu (P1)
- **Amaç:** Hesaplanmış metrikler, tetiklenen öneriler ve plan girdisinden kısa bir Türkçe teknik ekip brifingi üretmek.
- **Model:** Anthropic API kullanılır. Model adı `KURGU_LLM_MODEL`, API anahtarı `KURGU_ANTHROPIC_API_KEY` ortam değişkeninden okunur; ikisi de kodda sabitlenmez. **`ANTHROPIC_API_KEY` ve `ANTHROPIC_MODEL` adları kullanılmaz**: geliştiricinin Claude Code oturumu bu değişkenleri okuyabilir ve aboneliği API faturasına çevirebilir.
- **Kanıta bağlılık (ZORUNLU):**
  - Sistem istemi yalnızca verilen JSON'daki sayıların kullanılmasını, oyuncu adı ve sayı uydurulmamasını ve dolaylı göstergelerin belirtilmesini şart koşar.
  - Çıktı alındıktan sonra metindeki tüm sayılar çıkarılıp girdideki değerlerle eşleştirilir.
  - Eşleşmeyen sayı varsa çıktı reddedilir ve bir kez yeniden denenir. Yine başarısız olursa kullanıcıya "brifing üretilemedi" gösterilir.
- **Kayıt:** Her çalışma `llm_runs` tablosuna yazılır. Kiracı başına aylık bütçe ve istek sınırı uygulanır. Özellik kiracı ayarından kapatılabilir.

---

## 16. Test ve kalite
| Katman | Araç | Hedef |
|---|---|---|
| Alan ve metrik | pytest, hypothesis, altın veri setleri | Kapsam ≥ %90 |
| API | pytest + httpx, schemathesis (OpenAPI sözleşme testi) | Tüm uçlar |
| Web birim | Vitest, Testing Library | Kritik bileşenler |
| Uçtan uca | Playwright (docker compose ortamında) | Aşağıdaki kritik akışlar |
| Erişilebilirlik | axe (Playwright içinde) | Kritik sayfalarda 0 ciddi ihlal |
| Veri | pandera, çıkarım doğrulama raporu (§5.5) | ≥ %95 uyum |
| Yük | k6 | Hedef p95 değerleri |

**Kritik E2E akışları:**
1. Giriş → kulüp → sıradaki fikstür → önerileri kabul et → planı işaretle → PDF indir.
2. Canlı kayıt uçak modunda 20 kayıt → çevrimiçine dön → sunucuda 20 kayıt, yineleme yok.
3. Şablondan rutin oluştur → düzenle → yeni sürüm → maç kaydında kullan → rutin istatistiğinde görünür.
4. CSV içe aktar → eşleştirme → doğrulama hatasını düzelt → işle → metrikler güncellenir.
5. Oyuncu rolüyle giriş → yalnızca kendi görev kartını görür; başka oyuncunun verisine erişimi 403 döner.

---

## 17. DevOps ve gözlemlenebilirlik
- `docker compose` servisleri: postgres, redis, minio, keycloak, api, worker, web, mailpit.
- `Makefile` hedefleri: `dev`, `test`, `lint`, `typecheck`, `migrate`, `seed`, `e2e`, `openapi` (istemci üretimi).
- **CI (GitHub Actions):** lint (ruff, eslint), typecheck (mypy --strict, tsc), testler, göç döngüsü, OpenAPI farkı, derleme, e2e, güvenlik taramaları, kapsam eşikleri.
- **Ortamlar:** dev, staging ve prod ayrılır; özellik bayrakları kullanılır.
- **Yedekleme:** Günlük tam yedek ve WAL ile zamana dönük kurtarma yapılır. RPO ≤ 15 dk, RTO ≤ 4 saat. Aylık geri yükleme tatbikatının runbook'u yazılır.
- **Gözlem:** OpenTelemetry iz takibi, Sentry, `/healthz` ve `/readyz` uçları, iş kuyruğu metrikleri.

---

## 18. Ölçek varsayımları
- Kulüp başına yaklaşık 50 kullanıcı; eş zamanlı en fazla 15.
- Sezon başına 306 lig maçı; maç başına yaklaşık 3.500 olay. Lig kapsamı olduğunda sezonda yaklaşık 1 milyon olay.
- Kulüp başına sezonda yaklaşık 60 maç videosu, video başına 2-4 GB.
- v1 tek kulüp için dağıtılır, ancak şema ve RLS en fazla 20 kiracıyı destekleyecek şekilde kurulur.

---

## 19. Teslim planı

Her fazın sonunda: kabul kriterleri işaretlenir, demo verisiyle ekran görüntüleri `docs/demo/` altına alınır ve kısa bir rapor verilir.

**Faz 0: İskelet**
- [ ] Monorepo, docker compose ve `make dev` tek komutla ayağa kalkar.
- [ ] CI yeşil.
- [ ] Keycloak ile giriş çalışır; `/me` rol döner.
- [ ] Tasarım tokenları ve AppShell hazır; tüm rotalar boş durumda erişilebilir.

**Faz 1: Veri çekirdeği**
- [ ] Şema, göçler ve RLS kurulu (kiracılar arası erişim testi 403/boş döner).
- [ ] `make seed` tohum verisini yükler; Lig ve takım uçları tohum değerlerini birebir döner.
- [ ] StatsBomb Open Data adaptörü ve SPADL dönüşümü çalışır.
- [ ] Duran top çıkarımı ile doğrulama raporu hazır; `play_pattern` uyumu ≥ %95.
- [ ] CSV içe aktarım sihirbazı ve kalite raporu çalışır; karantina akışı işler.

**Faz 2: Metrikler ve analiz ekranları**
- [ ] Metrik modülü formülleri ve testleriyle hazır.
- [ ] Materialized view'ler yenileniyor.
- [ ] Genel bakış, Lig ve Rakip analizi sayfaları tohum verisiyle doğru sayıları gösterir. Örnekler:
  - 2025/26 lig duran top payı %20,4.
  - Trabzonspor 15 duran top golüyle 1.
  - Göztepe 15,4 duran top xG'si ile 1.
- [ ] Az veri rozeti ve kaynak rozetleri görünür.

**Faz 3: Rutin kütüphanesi**
- [ ] Editör: oyuncu (rolle), koşu, top yolu, perdeleme, ayna, geri al / yinele ve klavye desteği.
- [ ] Sürümleme çalışır.
- [ ] 7 şablon `seed/routine_templates.json` dosyasından yüklenir ve kütüphaneye eklenebilir.
- [ ] PNG ve PDF dışa aktarım çalışır.

**Faz 4: Maç hazırlığı ve öneri motoru**
- [ ] Kural değerlendirici güvenli (eval yok) ve testli.
- [ ] `seed/recommendation_rules.json` yüklenir; deneme modu çalışır.
- [ ] Öneriler kanıt ve güvenle gösterilir; kabul/red gerekçesi kaydedilir.
- [ ] MD planı şablonları, sorumlu atama ve ilerleme çalışır.
- [ ] Kabul testi: Trabzonspor seçiliyken 7. hafta Samsunspor deplasmanında en az şu iki öneri görünür:
  - "Ceza sahası çevresinde faul kazanın" (rakip faul yapmada 4.).
  - "Korner savunması haftanın öncelikli çalışması" (rakip korner/maç'ta 2.).

**Faz 5: Canlı kayıt ve video**
- [ ] PWA kurulabilir. Uçak modu E2E testi geçer. Çoklu cihaz senkronizasyonu çalışır.
- [ ] Video yükleme → HLS → klip → duran topa bağlama → rutin istatistiğinde klip görünür.

**Faz 6: Raporlar ve LLM**
- [ ] Rakip raporu ve maç planı PDF'leri 15 sn içinde üretilir.
- [ ] LLM brifingi sayı eşleştirme kontrolünden geçer; kontrol başarısız olursa kullanıcıya gösterilmez.

**Faz 7: Spor bilimi ve markaj optimizasyonu**
- [ ] sRPE, Hooper ve EWMA hesaplamaları testli.
- [ ] Sıçrama ve kafa yükü uyarıları çalışır.
- [ ] Rol izinleri doğrulanır.
- [ ] Macar algoritması önerisi elle düzeltilebilir ve kaydedilir.

**Faz 8: Sertleştirme**
- [ ] Güvenlik gözden geçirmesi (OWASP ASVS L2 kontrol listesi) tamam.
- [ ] Performans bütçeleri k6 ve Lighthouse ile doğrulandı.
- [ ] axe taramasında 0 ciddi ihlal.
- [ ] Türkçe kullanıcı kılavuzu yazıldı.
- [ ] Runbook'lar ve geri yükleme tatbikatı tamam.

**Her görev için bitmiş sayılma tanımı (DoD):**
- Testler yazıldı ve geçiyor; lint ve typecheck temiz.
- Göç geri alınabilir.
- Arayüz durumları (yükleniyor, boş, hata, az veri) mevcut.
- i18n anahtarları eklendi; erişilebilirlik kontrolü yapıldı.
- Telemetri eklendi.
- Dokümantasyon güncellendi (`docs/PROGRESS.md`, ilgili ADR).

---

## 20. Açık sorular (kulüple netleştirilecek)
1. **Veri:** Kulübün hangi sağlayıcılarla lisansı var (StatsBomb, Wyscout, Opta, GPS markası)? API erişimi var mı? *(Veri, engelleyici değil; Faz 1'de adaptör arayüzü hazırlanır.)*
2. **Barındırma:** Kulübün kendi bulutu mu, yönetilen hizmet mi? Veri bölgesi Türkiye içi mi olmalı? *(Hukuk ve BT)*
3. **Kimlik:** Kulüp Microsoft 365 mi, Google Workspace mi kullanıyor? *(BT)*
4. **Video:** Maç görüntülerinin kaynağı nedir: kulübün kendi kamerası mı, yayın görüntüsü mü? Hakları kimde? *(Hukuk)*
5. **Kapsam:** A takımı dışında U19 ve kadın takımı da kapsanacak mı? *(Sportif direktör)*
6. **Oyuncu erişimi:** Oyunculara kendi kartları için hesap açılacak mı, yoksa kartlar PDF ile mi paylaşılacak? *(Teknik direktör)*

---

## Ek A: Tohum dosyaları
- `seed/super_lig.json`:
  - Takımlar (kod, ad).
  - 2025/26 takım istatistikleri (18 takım). Duran top golü ve xG FotMob'dan (penaltı hariç); diğer alanlar Mackolik (Opta) kaynaklı. Kontrol: akan oyun + hızlı hücum + penaltı + duran top golleri toplamı, takımın toplam golünü 0-1 kendi kalesine gol farkıyla verir.
  - 2026/27 duran top verisi (ilk 6 hafta, FotMob).
  - 2026/27 puan durumu (6. hafta sonu), 1-6. hafta sonuçları, 7-12. hafta fikstürü (TFF). Kontrol: sonuçlardan yeniden hesaplanan puan tablosu TFF tablosuyla birebir tutar.
  - Premier Lig 2025/26 karşılaştırma değeri.
  - `meta.license_note`: Veriler kamuya açık sayfalardan elle derlenmiş özetlerdir; yalnızca geliştirme ve demo içindir. Ticari ve canlı kullanımda lisanslı veriyle değiştirilir.
- `seed/routine_templates.json`: Kanonik koordinatlarda (§4) 7 şablon: yakın direk sıçratma, arka direğe geç koşu, kısa korner, ceza yayına geri çekme, serbest vuruşta ikinci direğe orta, uzun taç, karma korner savunması. Her şablonda roller, ne zaman kullanılacağı ve notlar bulunur.
- `seed/recommendation_rules.json`: Başlangıç kural seti (§7.2 biçiminde).

## Ek B: Başarı metrikleri
- **Öncü göstergeler:** Haftalık aktif personel kullanıcı sayısı; planı tamamlanan fikstür oranı (hedef ≥ %80); rapor hazırlama süresi (hedef < 30 dk); maç kayıt kapsamı (hedef ≥ %90); öneri kabul oranı (izlenir, hedef konmaz).
- **Gecikmeli göstergeler:** Sezon içi duran top gol farkı (duran top golü − yenilen), duran top xG farkı ve ilk temas kazanma oranı trendi. Bu göstergeler gürültülüdür; en az yarım sezonluk pencereyle ve güven aralığıyla değerlendirilir.
