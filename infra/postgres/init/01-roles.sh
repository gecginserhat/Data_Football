#!/usr/bin/env bash
# Kurgu veritabanı rolleri (ADR-0002). postgres imajının ilk açılışında bir kez çalışır.
#   kurgu_owner  : tabloların sahibi; göçleri çalıştırır.
#   kurgu_app    : API; NOBYPASSRLS, tablo sahibi değil.
#   kurgu_worker : worker; NOBYPASSRLS.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$KURGU_OWNER_PASSWORD" \
  -v app_pw="$KURGU_APP_PASSWORD" \
  -v worker_pw="$KURGU_WORKER_PASSWORD" \
  -v db="$POSTGRES_DB" <<'SQL'
create role kurgu_owner login password :'owner_pw' nosuperuser nocreaterole nocreatedb;
create role kurgu_app login password :'app_pw' nosuperuser nobypassrls;
create role kurgu_worker login password :'worker_pw' nosuperuser nobypassrls;

alter database :"db" owner to kurgu_owner;
alter schema public owner to kurgu_owner;
grant usage on schema public to kurgu_app, kurgu_worker;
grant connect on database :"db" to kurgu_app, kurgu_worker;
SQL
