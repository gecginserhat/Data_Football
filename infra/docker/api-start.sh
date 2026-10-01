#!/bin/sh
# Üretim API süreci (A-99): birden çok uvicorn işçisi; Prometheus sayaçları işçiler arasında
# paylaşılan dizinde toplanır ve her açılışta sıfırlanır.
set -eu
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/kurgu-metrics}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
exec uvicorn kurgu_api.main:app --host 0.0.0.0 --port 8000 \
  --workers "${KURGU_API_WORKERS:-2}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
