#!/usr/bin/env bash
# Geliştirme ortamı kontrolü (BASLANGIC.md §2). Eksik araçları ve dolu portları listeler.
set -uo pipefail
cd "$(dirname "$0")/.."
status=0
check() {
  local name=$1; shift
  if out=$("$@" 2>&1); then
    printf "  ok    %-10s %s\n" "$name" "$(echo "$out" | head -1)"
  else
    printf "  EKSİK %-10s (%s)\n" "$name" "$*"; status=1
  fi
}
echo "Araçlar:"
check docker docker version --format '{{.Server.Version}}'
check compose docker compose version --short
check node node -v
check pnpm pnpm -v
check uv uv --version
check git git --version
check make make --version

echo "Satır sonu ayarı:"
autocrlf=$(git config --get core.autocrlf || echo "(ayarsız)")
if [[ "$autocrlf" == "true" ]]; then
  echo "  UYARI core.autocrlf=true. WSL'de 'git config --global core.autocrlf input' önerilir."
else
  echo "  ok    core.autocrlf=$autocrlf"
fi

echo "Konum:"
if [[ "$PWD" == /mnt/* ]]; then
  echo "  UYARI Proje Windows diskinde ($PWD). ~/projects/kurgu altına taşıyın; aksi halde yavaş çalışır."
else
  echo "  ok    $PWD"
fi

echo "Portlar (.env ya da varsayılan):"
[[ -f .env ]] && set -a && source .env && set +a
for p in "${WEB_PORT:-3000}" "${API_PORT:-8000}" "${POSTGRES_PORT:-5432}" "${REDIS_PORT:-6379}" \
         "${MINIO_PORT:-9000}" "${MINIO_CONSOLE_PORT:-9001}" "${KEYCLOAK_PORT:-8080}" "${MAILPIT_UI_PORT:-8025}"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then
    echo "  DOLU  $p (Kurgu zaten çalışıyor olabilir; değilse .env içinde portu değiştirin)"
  else
    echo "  boş   $p"
  fi
done
exit $status
