# Yedekleme ve geri yükleme

İlgili: ADR-0018, A-95. Hedefler: RPO ≤ 15 dk, RTO ≤ 4 saat (SPEC §17).

## Ne yedeklenir
| Varlık | Nasıl | Nerede |
|---|---|---|
| PostgreSQL (tüm kulüp kaydı, şifreli iyi oluş dahil) | Günlük `kurgu-backup create` (pg_dump + age) ve üretimde WAL-G sürekli arşiv | Ayrı yedek kovası |
| Nesne deposu (raporlar, içe aktarılan dosyalar, HLS) | Kova sürümlemesi + sağlayıcı çoğaltması | Sağlayıcı |
| Videoların kaynak dosyaları | Yedeklenmez; kaynak kulüptedir | Kulüp |
| Anahtarlar (`KURGU_DATA_KEYS`, age özel anahtarı, `.env`) | Kasada, veritabanı yedeğinden ayrı | Kasa (iki kişi erişir) |

Şifreli yedek, age özel anahtarı **ve** `KURGU_DATA_KEYS` olmadan kullanılamaz. İkisi aynı yerde saklanmaz.

## İlk kurulum
1. Kulüp için age anahtar çifti üretin (yalnız bir kez, güvenli bir makinede):
   `age-keygen -o kurgu-backup.key` · açık anahtar: `age-keygen -y kurgu-backup.key > infra/backup/recipients.txt`.
   Özel anahtar dosyasını kasaya koyun ve sunucudan silin.
2. Yedek rolü: `infra/postgres/init/01-roles.sh` yeni kümelerde `kurgu_backup` rolünü (yalnız okur, BYPASSRLS) oluşturur. Var olan kümede bir kez süper kullanıcıyla:
   ```sql
   create role kurgu_backup login password '<.env içindeki KURGU_BACKUP_PASSWORD>' nosuperuser bypassrls;
   grant pg_read_all_data to kurgu_backup;
   ```
3. `.env`: `BACKUP_DATABASE_URL`, `KURGU_BACKUP_RECIPIENTS`, `KURGU_BACKUP_TARGET` (`s3://kurgu-backups/prod` gibi; kova uygulamanın kovasından ayrı olmalı, yazma yetkisi yalnız ekleme).
4. Zamanlayıcı: her gece 02:00 `make backup` (systemd timer ya da cron). Başarısızlık e-postayla/uyarıyla bildirilir; çıkış kodu 0 değilse alarm.
5. Üretimde WAL-G: `archive_mode=on`, `archive_timeout=60`, `archive_command='wal-g wal-push %p'`, haftalık `wal-g backup-push`. WAL-G şifrelemesi için aynı kasadaki ayrı bir anahtar kullanılır (`WALG_LIBSODIUM_KEY`).

## Günlük kontrol
- Son yedeğin manifesti (`kurgu-*.json`) 26 saatten eski olmamalı.
- Manifest boyutu bir önceki günün yarısından küçükse inceleyin.

## Geri yükleme tatbikatı (ayda bir, zorunlu)
1. Özel anahtarı kasadan geçici bir dosyaya alın; `KURGU_BACKUP_IDENTITY` ile gösterin.
2. `make restore-drill`. Betik son yedeği indirir, özetini doğrular, çözer, `kurgu_drill_<zaman>` veritabanına açar, göç sürümünü, tüm tablo satır sayılarını ve bir iyi oluş kaydının `KURGU_DATA_KEYS` ile çözülmesini denetler, sonra veritabanını siler.
3. Sonuç `docs/runbooks/drills/<tarih>-restore-drill.md` dosyasına yazılır; commit edin. Çıkış kodu 2 ise doğrulama başarısızdır: olay olarak ele alın.
4. Özel anahtar dosyasını silin.

Son tatbikat: [2026-10-01](drills/2026-10-01-restore-drill.md) (yerel, başarılı).

## Gerçek geri yükleme (felaket)
1. Uygulamayı bakım moduna alın: web ve API'yi durdurun (`docker compose stop web api worker`).
2. Hedef kümede rolleri hazırlayın (`01-roles.sh`). Boş veritabanı: `create database kurgu owner kurgu_owner`.
3. Zamana dönük kurtarma gerekiyorsa WAL-G ile (`wal-g backup-fetch` + `recovery_target_time`). Değilse son mantıksal yedek:
   ```bash
   age --decrypt -i kurgu-backup.key -o kurgu.dump kurgu-<zaman>.dump.age
   pg_restore --list kurgu.dump | grep -v 'MATERIALIZED VIEW DATA' > restore.list
   pg_restore --exit-on-error --use-list=restore.list --dbname=postgresql://postgres@.../kurgu kurgu.dump
   ```
   Görünümler sahibinin rolüyle ve satır güvenliği açıkken doldurulmalıdır (FORCE RLS):
   ```sql
   set role kurgu_owner;
   refresh materialized view mv_team_setpiece_season;
   refresh materialized view mv_league_benchmarks;
   reset role;
   ```
   `kurgu-backup drill --keep` bu adımları aynı sırayla yapar ve veritabanını silmez.
4. `uv run alembic current` yedekteki sürümü göstermeli. Uygulama sürümü yedekten yeniyse `make migrate`.
5. Uygulamayı açın, `GET /readyz`, giriş ve bir iyi oluş kaydının açılmasıyla doğrulayın.
6. Olay kaydına geri yükleme noktasını ve kaybolan aralığı yazın; kulüp yöneticisine bildirin.
