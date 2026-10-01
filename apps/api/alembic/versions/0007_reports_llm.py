"""Raporlar ve LLM çalışmaları (ADR-0012, ADR-0013).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

- `reports`: worker'da üretilen PDF raporlar; durum, ilerleme, depo anahtarı ve üretim süresi
  (A-68 … A-71).
- `llm_runs`: her LLM denemesi; girdi, çıktı, doğrulama sonucu, token ve süre (SPEC §15, A-73 …
  A-76). Reddedilen çıktı kayıtta kalır ama kullanıcıya gösterilmez.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
TENANT_TABLES = ("reports", "llm_runs")

DDL = (
    """
create table reports (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_reports_tenant_id_tenants references tenants(id) on delete cascade,
  type varchar(32) not null,
  fixture_id uuid not null constraint fk_reports_fixture_id_matches references matches(id),
  params jsonb not null default '{}',
  status varchar(16) not null default 'queued',
  progress smallint not null default 0,
  storage_key varchar(512),
  size_bytes bigint,
  pages smallint,
  error text,
  data_as_of jsonb,
  created_by uuid constraint fk_reports_created_by_users references users(id),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  duration_ms integer,
  constraint ck_reports_type check (type in ('opponent', 'match_plan')),
  constraint ck_reports_status check (status in ('queued', 'running', 'ready', 'failed')),
  constraint ck_reports_progress check (progress between 0 and 100)
)
""",
    "create index ix_reports_tenant_created on reports (tenant_id, created_at desc)",
    "create index ix_reports_fixture on reports (fixture_id)",
    """
create table llm_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_llm_runs_tenant_id_tenants references tenants(id) on delete cascade,
  kind varchar(32) not null,
  fixture_id uuid constraint fk_llm_runs_fixture_id_matches references matches(id),
  attempt smallint not null default 1,
  model varchar(128) not null,
  status varchar(16) not null,
  input jsonb not null,
  output text,
  unmatched jsonb not null default '[]',
  error text,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  duration_ms integer,
  created_by uuid constraint fk_llm_runs_created_by_users references users(id),
  created_at timestamptz not null default now(),
  constraint ck_llm_runs_kind check (kind in ('briefing')),
  constraint ck_llm_runs_status check (status in ('verified', 'rejected', 'error'))
)
""",
    "create index ix_llm_runs_tenant_created on llm_runs (tenant_id, created_at)",
    "create index ix_llm_runs_fixture on llm_runs (fixture_id, created_at desc)",
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy tenant_isolation on {table}"
            " using (tenant_id = kurgu_current_tenant())"
            " with check (tenant_id = kurgu_current_tenant())"
        )
    for role in APP_ROLES:
        op.execute(f"grant select, insert, update, delete on reports, llm_runs to {role}")


def downgrade() -> None:
    op.execute("drop table llm_runs")
    op.execute("drop table reports")
