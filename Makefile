# Kurgu geliştirme komutları (CLAUDE.md "Komutlar"). Repo kökünden çalıştırın.
SHELL := /bin/bash
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml
UV := uv run

-include .env
export

.PHONY: help doctor env install dev down logs ps migrate migrate-cycle seed seed-report openapi \
        lint typecheck test test-py test-js e2e format

help: ## Komutları listeler
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

doctor: ## Araçları ve portları kontrol eder
	@scripts/doctor.sh

env: ## .env yoksa .env.example'dan oluşturur
	@test -f .env || { cp .env.example .env; echo ".env oluşturuldu. Gerekirse değerleri düzenleyin."; }

install: ## JS ve Python bağımlılıklarını kurar
	pnpm install --frozen-lockfile
	uv sync --all-packages --frozen

dev: env ## Tüm servisleri ayağa kaldırır (web: http://localhost:3000)
	$(COMPOSE) up --build -d
	@scripts/wait-for-stack.sh
	@echo "Test kullanıcıları: docs/runbooks/local-dev.md"

down: ## Servisleri durdurur (veri kalır)
	$(COMPOSE) down

logs: ## Servis loglarını izler
	$(COMPOSE) logs -f --tail=100

ps: ## Servis durumlarını gösterir
	$(COMPOSE) ps

migrate: ## Alembic upgrade head (compose içindeki veritabanına)
	$(COMPOSE) run --rm migrate alembic -c apps/api/alembic.ini upgrade head

migrate-cycle: ## upgrade → downgrade → upgrade döngüsü (CI ile aynı)
	cd apps/api && $(UV) alembic upgrade head && $(UV) alembic downgrade base && $(UV) alembic upgrade head

seed: ## Tohum verisini yükler (geliştirme kimlikleri, lig verisi, lisanslar; idempotent)
	$(COMPOSE) run --rm migrate kurgu-seed

seed-report: ## Tohum bütünlük raporunu docs/validation/seed_integrity.md dosyasına yazar
	$(UV) kurgu-seed --report docs/validation/seed_integrity.md

openapi: ## OpenAPI şemasından TS istemcisini yeniden üretir
	$(UV) kurgu-openapi packages/api-client/openapi.json
	pnpm --filter @kurgu/api-client generate

lint: ## ruff, import-linter, eslint, prettier ve yasaklı ad kontrolü
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) lint-imports
	pnpm lint
	pnpm format:check
	@scripts/check-forbidden-env.sh

typecheck: ## mypy --strict ve tsc
	$(UV) mypy apps/api/src analytics/kurgu_analytics apps/api/tests
	pnpm typecheck

test: test-py test-js ## Tüm birim testleri

test-py: ## Python testleri (PostgreSQL ve Redis gerekir; `make dev` ya da yerel servisler)
	TEST_ADMIN_DATABASE_URL=$${TEST_ADMIN_DATABASE_URL:-postgresql://postgres:$${POSTGRES_SUPERUSER_PASSWORD:-postgres}@localhost:$${POSTGRES_PORT:-5432}/postgres} $(UV) pytest

test-js: ## JS testleri
	pnpm test

e2e: ## Playwright uçtan uca testleri (`make dev` çalışıyor olmalı)
	pnpm --filter @kurgu/web e2e

format: ## Kodu biçimlendirir
	$(UV) ruff format .
	$(UV) ruff check --fix .
	pnpm format
