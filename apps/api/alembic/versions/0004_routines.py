"""Rutin kütüphanesi: şablonlar, rutinler, değişmez sürümler ve rutin istatistiği (ADR-0008).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

- `routine_templates`: paylaşılan şablonlar (kiracısız). Tüm kiracılar okur; göç rolü yazar
  (`kurgu-seed`, A-40).
- `routines`: kiracının rutin başlık kaydı (güncel ad, tür, taraf, güncel sürüm, arşiv).
  Silinmez, arşivlenir (A-41).
- `routine_versions`: değişmez anlık görüntüler. Uygulama rollerine güncelleme ve silme yok.
- `set_pieces.routine_id`: aynı kiracının rutinine bileşik yabancı anahtar; paylaşılan
  dizilerde boş kalır.
- `v_routine_stats` (`security_invoker`): rutin başına ham sayımlar (SPEC §6.3). Oranlar ve
  büzülme `kurgu_analytics.metrics` içinde (ADR-0007, A-44).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")

DDL = (
    """
create table routine_templates (
  id varchar(64) primary key,
  name varchar(200) not null,
  sp_type varchar(16) not null,
  side varchar(8),
  is_defensive boolean not null default false,
  when_to_use text not null default '',
  notes text not null default '',
  diagram jsonb not null,
  sort_order integer not null default 0,
  updated_at timestamptz not null default now(),
  constraint ck_routine_templates_sp_type check (sp_type in ('corner', 'free_kick', 'throw_in')),
  constraint ck_routine_templates_side check (side in ('left', 'right'))
)
""",
    """
create table routines (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_routines_tenant_id_tenants references tenants(id) on delete cascade,
  name varchar(120) not null,
  sp_type varchar(16) not null,
  side varchar(8),
  is_defensive boolean not null default false,
  from_template varchar(64)
    constraint fk_routines_from_template_routine_templates references routine_templates(id),
  current_version integer not null default 1,
  archived_at timestamptz,
  is_demo boolean not null default false,
  created_by uuid constraint fk_routines_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_by uuid constraint fk_routines_updated_by_users references users(id),
  updated_at timestamptz not null default now(),
  constraint uq_routines_id_tenant unique (id, tenant_id),
  constraint ck_routines_sp_type check (sp_type in ('corner', 'free_kick', 'throw_in')),
  constraint ck_routines_side check (side in ('left', 'right')),
  constraint ck_routines_current_version check (current_version >= 1),
  constraint ck_routines_name check (length(btrim(name)) > 0)
)
""",
    "create index ix_routines_tenant_updated on routines (tenant_id, updated_at desc)",
    """
create table routine_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_routine_versions_tenant_id_tenants references tenants(id) on delete cascade,
  routine_id uuid not null,
  version integer not null,
  name varchar(120) not null,
  side varchar(8),
  notes text not null default '',
  when_to_use text not null default '',
  diagram jsonb not null,
  message varchar(200),
  created_by uuid constraint fk_routine_versions_created_by_users references users(id),
  created_at timestamptz not null default now(),
  constraint fk_routine_versions_routine foreign key (routine_id, tenant_id)
    references routines (id, tenant_id) on delete cascade,
  constraint uq_routine_versions_routine_version unique (routine_id, version),
  constraint ck_routine_versions_version check (version >= 1),
  constraint ck_routine_versions_side check (side in ('left', 'right'))
)
""",
    "create index ix_routine_versions_tenant_id on routine_versions (tenant_id)",
    """
alter table set_pieces
  add constraint fk_set_pieces_routine foreign key (routine_id, tenant_id)
    references routines (id, tenant_id),
  add constraint ck_set_pieces_routine_tenant check (routine_id is null or tenant_id is not null)
""",
    "create index ix_set_pieces_routine_id on set_pieces (routine_id) where routine_id is not null",
    """
create view v_routine_stats with (security_invoker = true) as
select r.tenant_id, r.id as routine_id,
       count(p.id) as uses,
       count(distinct p.match_id) as matches,
       count(p.id) filter (where p.first_contact_team_id is not null) as with_contact,
       count(p.id) filter (where p.first_contact_team_id = p.team_id) as first_contact_won,
       count(p.id) filter (where p.shots > 0) as with_shot,
       coalesce(sum(p.xg_total), 0)::double precision as xg,
       count(p.id) filter (where p.goal) as goals
from routines r
left join set_pieces p on p.routine_id = r.id and p.tenant_id = r.tenant_id
group by r.tenant_id, r.id
""",
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)

    op.execute("alter table routine_templates enable row level security")
    op.execute("create policy read_all on routine_templates for select using (true)")
    for table in ("routines", "routine_versions"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy tenant_isolation on {table}"
            " using (tenant_id = kurgu_current_tenant())"
            " with check (tenant_id = kurgu_current_tenant())"
        )
    for role in APP_ROLES:
        op.execute(f"grant select on routine_templates, v_routine_stats to {role}")
        op.execute(f"grant select, insert, update on routines to {role}")
        # Sürümler değişmez: güncelleme ve silme yetkisi yok (A-41).
        op.execute(f"grant select, insert on routine_versions to {role}")


def downgrade() -> None:
    op.execute("drop view v_routine_stats")
    op.execute("drop index ix_set_pieces_routine_id")
    op.execute(
        "alter table set_pieces drop constraint ck_set_pieces_routine_tenant,"
        " drop constraint fk_set_pieces_routine"
    )
    op.execute("drop table routine_versions")
    op.execute("drop table routines")
    op.execute("drop table routine_templates")
