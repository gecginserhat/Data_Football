#!/usr/bin/env bash
# ANTHROPIC_API_KEY / ANTHROPIC_MODEL adları repoda kullanılmaz (CLAUDE.md, SPEC §15).
# Claude Code bu değişkenleri okuyup aboneliği API faturasına çevirebilir.
# Yalnızca bu kuralı anlatan belgeler ve kontrolün kendisi hariç tutulur.
set -euo pipefail
cd "$(dirname "$0")/.."
matches=$(git grep -nE '(^|[^_A-Z])ANTHROPIC_(API_KEY|MODEL)\b' -- \
  ':!CLAUDE.md' ':!BASLANGIC.md' ':!docs/**' ':!scripts/check-forbidden-env.sh' \
  ':!apps/web/eslint.config.mjs' ':!.env.example' || true)
if [[ -n "$matches" ]]; then
  echo "Yasaklı ortam değişkeni adı bulundu. KURGU_ANTHROPIC_API_KEY / KURGU_LLM_MODEL kullanın:"
  echo "$matches"
  exit 1
fi
echo "forbidden env names: ok"
