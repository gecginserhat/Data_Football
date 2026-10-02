#!/usr/bin/env bash
# Geri yükleme tatbikatı (ADR-0018). Son yedeği geçici bir veritabanına açar, doğrular, siler ve
# sonucu docs/runbooks/drills/ altına yazar. Çıkış kodu: 0 başarılı, 2 doğrulama hatası, 1 hata.
#   DRILL_ADMIN_URL         veritabanı oluşturabilen rol (kümede kurgu_* rolleri bulunmalı)
#   KURGU_BACKUP_IDENTITY   age özel anahtar dosyası (kasadan geçici olarak)
#   KURGU_BACKUP_TARGET     dizin ya da s3://kova/önek
#   KURGU_DATA_KEYS         şifreli alanların anahtarları (iyi oluş kaydı çözülerek denetlenir)
set -euo pipefail
: "${DRILL_ADMIN_URL:?DRILL_ADMIN_URL gerekli}"
: "${KURGU_BACKUP_IDENTITY:?KURGU_BACKUP_IDENTITY gerekli}"
: "${KURGU_BACKUP_TARGET:?KURGU_BACKUP_TARGET gerekli}"
cd "$(dirname "$0")/../.."
exec uv run kurgu-backup drill \
  --admin-url "$DRILL_ADMIN_URL" \
  --identity "$KURGU_BACKUP_IDENTITY" \
  --target "$KURGU_BACKUP_TARGET" \
  --environment "${DRILL_ENVIRONMENT:-${KURGU_ENV:-development}}" \
  --report-dir docs/runbooks/drills
