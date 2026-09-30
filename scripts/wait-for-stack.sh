#!/usr/bin/env bash
# `make dev` sonrası web arayüzü yanıt verene kadar bekler. Tek seferlik servisler
# (migrate, minio-init) başarısız olursa hemen durur ve loglarını gösterir.
set -uo pipefail
cd "$(dirname "$0")/.."
# COMPOSE_FILES ile ek dosyalar verilebilir (CI: infra/docker-compose.ci.yml).
read -r -a files <<< "${COMPOSE_FILES:--f infra/docker-compose.yml}"
compose=(docker compose --env-file .env "${files[@]}")
url="http://localhost:${WEB_PORT:-3000}/signin"
deadline=$((SECONDS + ${WAIT_TIMEOUT:-600}))
while (( SECONDS < deadline )); do
  for svc in migrate minio-init; do
    code=$("${compose[@]}" ps -a --format '{{.Service}} {{.ExitCode}} {{.State}}' | awk -v s="$svc" '$1==s && $3=="exited" {print $2}')
    if [[ -n "$code" && "$code" != "0" ]]; then
      echo "$svc başarısız oldu (çıkış kodu $code):"
      "${compose[@]}" logs --tail=80 "$svc"
      exit 1
    fi
  done
  if curl -fsS -o /dev/null "$url"; then
    echo "Kurgu hazır: http://localhost:${WEB_PORT:-3000}"
    exit 0
  fi
  sleep 5
done
echo "Zaman aşımı: $url yanıt vermedi."
"${compose[@]}" ps -a
exit 1
