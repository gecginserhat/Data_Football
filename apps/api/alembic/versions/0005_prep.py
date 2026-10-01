"""Maç hazırlığı: kural setleri, öneri kararları ve MD planı (ADR-0009).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

- `rule_sets`: kural seti sürümleri. Kiracısız satır varsayılan settir (0. sürüm, tohumdan);
  kulüp sürümleri 1'den başlar ve değişmezdir (A-51). Uygulama rolleri ekler ve okur.
- `recommendations`: öneri kararları. Kimlik belirlenimcidir (fikstür, kural, rutin); karar
  anında kanıt, metin ve kural sürümü anlık görüntü olarak yazılır (A-50).
- `fixture_plans`, `plan_items`: fikstür başına MD planı ve maddeleri (A-52).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
MD_CODES = "('MD-4', 'MD-3', 'MD-2', 'MD-1', 'MD', 'MD+1')"

DDL = (
    """
create table rule_sets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid
    constraint fk_rule_sets_tenant_id_tenants references tenants(id) on delete cascade,
  version integer not null,
  label varchar(32),
  rules jsonb not null,
  message varchar(200),
  published_by uuid constraint fk_rule_sets_published_by_users references users(id),
  published_at timestamptz not null default now(),
  constraint uq_rule_sets_tenant_version unique nulls not distinct (tenant_id, version),
  constraint ck_rule_sets_version check (
    (tenant_id is null and version = 0) or (tenant_id is not null and version >= 1)
  )
)
""",
    """
create table recommendations (
  id uuid primary key,
  tenant_id uuid not null
    constraint fk_recommendations_tenant_id_tenants references tenants(id) on delete cascade,
  fixture_id uuid not null constraint fk_recommendations_fixture_id_matches references matches(id),
  rule_id varchar(64) not null,
  routine_id uuid,
  rule_set_version integer not null,
  area varchar(16) not null,
  priority smallint not null,
  confidence varchar(8) not null,
  title text not null,
  why text not null,
  action text not null,
  template_id varchar(64),
  evidence jsonb not null default '[]'::jsonb,
  status varchar(12) not null,
  reason text,
  decided_by uuid constraint fk_recommendations_decided_by_users references users(id),
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_recommendations_id_tenant unique (id, tenant_id),
  constraint fk_recommendations_routine foreign key (routine_id, tenant_id)
    references routines (id, tenant_id),
  constraint ck_recommendations_status check (status in ('suggested', 'accepted', 'rejected')),
  constraint ck_recommendations_area check (area in ('attack', 'defense', 'balance', 'season')),
  constraint ck_recommendations_confidence check (confidence in ('high', 'medium', 'low')),
  constraint ck_recommendations_reason check (
    status <> 'rejected' or length(btrim(coalesce(reason, ''))) > 0
  )
)
""",
    "create index ix_recommendations_tenant_fixture on recommendations (tenant_id, fixture_id)",
    """
create table fixture_plans (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_fixture_plans_tenant_id_tenants references tenants(id) on delete cascade,
  fixture_id uuid not null constraint fk_fixture_plans_fixture_id_matches references matches(id),
  template varchar(16) not null,
  created_by uuid constraint fk_fixture_plans_created_by_users references users(id),
  created_at timestamptz not null default now(),
  constraint uq_fixture_plans_tenant_fixture unique (tenant_id, fixture_id),
  constraint uq_fixture_plans_id_tenant unique (id, tenant_id),
  constraint ck_fixture_plans_template check (template in ('standard', 'congested'))
)
""",
    f"""
create table plan_items (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_plan_items_tenant_id_tenants references tenants(id) on delete cascade,
  plan_id uuid not null,
  md_code varchar(8) not null,
  position integer not null default 0,
  title varchar(200) not null,
  detail text not null default '',
  recommendation_id uuid,
  routine_id uuid,
  assignee_id uuid constraint fk_plan_items_assignee_id_users references users(id),
  status varchar(8) not null default 'todo',
  done_by uuid constraint fk_plan_items_done_by_users references users(id),
  done_at timestamptz,
  created_by uuid constraint fk_plan_items_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint fk_plan_items_plan foreign key (plan_id, tenant_id)
    references fixture_plans (id, tenant_id) on delete cascade,
  constraint fk_plan_items_recommendation foreign key (recommendation_id, tenant_id)
    references recommendations (id, tenant_id) on delete set null (recommendation_id),
  constraint fk_plan_items_routine foreign key (routine_id, tenant_id)
    references routines (id, tenant_id),
  constraint ck_plan_items_md_code check (md_code in {MD_CODES}),
  constraint ck_plan_items_status check (status in ('todo', 'done')),
  constraint ck_plan_items_done check ((status = 'done') = (done_at is not null)),
  constraint ck_plan_items_title check (length(btrim(title)) > 0)
)
""",
    "create index ix_plan_items_plan on plan_items (plan_id, md_code, position)",
)

TENANT_TABLES = ("recommendations", "fixture_plans", "plan_items")


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)

    # Varsayılan set kiracısızdır; göç rolü (`kurgu-seed`) yazar, kiracılar okur (A-51).
    op.execute("alter table rule_sets enable row level security")
    op.execute("alter table rule_sets force row level security")
    op.execute(
        "create policy owner_shared on rule_sets for all to kurgu_owner"
        " using (tenant_id is null) with check (tenant_id is null)"
    )
    op.execute(
        "create policy read_default_or_own on rule_sets for select"
        " using (tenant_id is null or tenant_id = kurgu_current_tenant())"
    )
    op.execute(
        "create policy insert_own on rule_sets for insert"
        " with check (tenant_id = kurgu_current_tenant())"
    )
    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy tenant_isolation on {table}"
            " using (tenant_id = kurgu_current_tenant())"
            " with check (tenant_id = kurgu_current_tenant())"
        )
    for role in APP_ROLES:
        # Kural seti sürümleri değişmez: yalnızca okuma ve ekleme.
        op.execute(f"grant select, insert on rule_sets to {role}")
        op.execute(f"grant select, insert, update on recommendations, fixture_plans to {role}")
        op.execute(f"grant select, insert, update, delete on plan_items to {role}")


def downgrade() -> None:
    op.execute("drop table plan_items")
    op.execute("drop table fixture_plans")
    op.execute("drop table recommendations")
    op.execute("drop table rule_sets")
