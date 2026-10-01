#!/usr/bin/env bash
# Şifreli veritabanı yedeği (ADR-0018). Zamanlayıcıdan (cron, systemd timer) günde bir çalışır.
#   BACKUP_DATABASE_URL     kurgu_backup rolüyle bağlantı (BYPASSRLS, yalnız okur)
#   KURGU_BACKUP_RECIPIENTS age açık anahtar dosyası (özel anahtar burada durmaz)
#   KURGU_BACKUP_TARGET     dizin ya da s3://kova/önek (S3_* değişkenleri kullanılır)
set -euo pipefail
: "${BACKUP_DATABASE_URL:?BACKUP_DATABASE_URL gerekli}"
: "${KURGU_BACKUP_RECIPIENTS:?KURGU_BACKUP_RECIPIENTS gerekli}"
: "${KURGU_BACKUP_TARGET:?KURGU_BACKUP_TARGET gerekli}"
cd "$(dirname "$0")/../.."
exec uv run kurgu-backup create \
  --database-url "$BACKUP_DATABASE_URL" \
  --recipients "$KURGU_BACKUP_RECIPIENTS" \
  --target "$KURGU_BACKUP_TARGET"
