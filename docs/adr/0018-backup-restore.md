# ADR-0018: Yedekleme, şifreleme ve geri yükleme

- **Durum:** Kabul edildi · 01.10.2026
- **İlgili:** SPEC §12.2 ("Yedekler de şifrelenir"), §17 (RPO ≤ 15 dk, RTO ≤ 4 saat); A-95; ADR-0014

## Bağlam
Veritabanı kulübün tüm kaydını ve şifreli iyi oluş verisini tutar. Nesne deposunda videolar, raporlar ve içe aktarılan dosyalar durur. Yedek şifrelenmeli ve şifre çözme anahtarı yedeğin yanında durmamalıdır.

## Karar
- Günlük mantıksal yedek: `pg_dump --format=custom` çıktısı akış halinde `age` ile şifrelenir ve nesne deposunun ayrı yedek kovasına yazılır (`infra/backup/backup.sh`). Yedek sunucusu yalnız kulübün `age` açık anahtarını bilir.
- Zamana dönük kurtarma: üretimde WAL-G ile temel yedek ve sürekli WAL arşivi (`archive_timeout = 60s`) kullanılır. Bu, 15 dakikalık RPO'yu karşılar. Yapılandırma runbook'tadır.
- Geri yükleme tatbikatı (`infra/backup/restore-drill.sh`) son yedeği indirir, çözer, boş bir veritabanına açar ve doğrular: göç sürümü, tablo satır sayıları ve bir iyi oluş kaydının `KURGU_DATA_KEYS` ile çözülmesi. Süreyi ve sonucu `docs/runbooks/drills/` altına yazar.
- Nesne deposu için kova sürümlemesi ve sağlayıcının çoğaltması kullanılır. Videolar yedek kapsamına alınmaz; kaynakları kulüptedir.

## Sonuçlar
- Şifreli yedek, `age` özel anahtarı ve `KURGU_DATA_KEYS` olmadan işe yaramaz. İkisinin ayrı kasalarda saklanması runbook'ta zorunlu adımdır.
- Yerel ortamda yalnız tam yedek tatbik edilir; WAL arşivi üretim ortamında kurulurken ayrıca tatbik edilmelidir.
