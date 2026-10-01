# ADR-0007: Metrik görünümleri ve formüllerin yeri

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §6, §10 (materialized view'ler), CLAUDE.md "Formüller tek yerde"; A-35, A-36

## Bağlam
SPEC §10 üç materialized view öngörüyor: `mv_team_setpiece_season`, `mv_league_benchmarks`, `mv_routine_stats`. CLAUDE.md ise metrik formüllerinin yalnızca `analytics/kurgu_analytics/metrics/` altında, saf Python fonksiyonları olarak bulunmasını istiyor. Ayrıca materialized view'ler RLS desteklemez; karma lig tablolarında kiracının içe aktardığı satırlar (`tenant_id` dolu) başka kiracıya görünmemeli.

## Karar
- **Görünümler yalnızca ham toplam tutar.** Sayım ve toplam SQL'de, oranlar, büzülme, sıra ve yüzdelik Python'da (`kurgu_analytics.metrics`). SQL'de bölme yoktur.
- **`v_team_setpiece_agg`** (`security_invoker`): `set_pieces` + `matches` üzerinden takım-sezon hücum ve savunma toplamları. Çağıranın RLS'siyle çalışır; API kiracının kendi satırlarını buradan istek anında okur.
- **`mv_team_setpiece_season`**: aynı toplamların yalnızca paylaşılan satırları (`tenant_id` null). Olay verisinin taranması pahalı olan kısım budur.
- **`mv_league_benchmarks`**: sezon × ham alan başına lig toplamı ve takım sayısı (paylaşılan son takım-sezon kesiti, son puan durumu `standings.*`, olay toplamları `events.*`). Lig toplamı oranları (%20,4 gibi) `league_totals` ile Python'da hesaplanır.
- **Erişim:** Uygulama rolleri materialized view'leri doğrudan okuyamaz. Lisans süzgeçli `security_barrier` görünümler (`v_team_setpiece_season`, `v_league_benchmarks`, `kurgu_licensed_season`) üzerinden okunur.
- **Yenileme:** `kurgu_refresh_metric_views()` (security definer, `CONCURRENTLY`, benzersiz dizinlerle). Tohum yüklemesinin ve en az bir maç yükleyen sağlayıcı işinin sonunda çağrılır; worker'da `refresh_metric_views_job` da var. Kiracı içe aktarımları görünümleri etkilemez, yenileme gerektirmez.
- **Lig kıyasları** (metrik başına en düşük, en yüksek, ortalama) istek anında `team_metrics` çıktısından hesaplanır: 18 takım × ~20 metrik milisaniyeler sürer ve kiracının kendi kaydını içeren birleşik tabloyla tutarlı kalır (A-36).
- **`mv_routine_stats`** yerine Faz 3'te `security_invoker` görünüm `v_routine_stats` geldi: rutin kayıtları kiracıya ait (A-44, ADR-0008).

## Sonuçlar
- **Artı:** Formüller tek yerde, test edilebilir; SQL ile Python arasında çift tanım yok.
- **Artı:** Kiracı izolasyonu korunur; materialized view'de kiracı satırı yok.
- **Eksi:** Kiracı içe aktarım toplamları her istekte hesaplanır. Bir kulübün kendi maç sayısı küçük olduğundan kabul edilebilir; büyürse kiracı başına önbellek eklenir.
- **Eksi:** Göç rolü (`kurgu_owner`) paylaşılan dizileri okuyabilmek için `set_pieces` üzerinde `owner_read` politikası aldı (yalnızca `tenant_id is null`, yalnızca okuma).

## Değerlendirilen seçenekler
- **Oranları SQL'de hesaplamak:** Daha hızlı ama formüller iki yerde olurdu. Reddedildi.
- **Materialized view'e kiracı satırlarını da koymak:** RLS yok; her okuma için ayrı süzgeç gerekir ve hata riski yüksek. Reddedildi.
