"""Kadro, yük ve iyi oluş, markaj ve rol atamaları (Faz 7; ADR-0014, ADR-0015, A-79 … A-87).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01

- `squad_players`: kulübün kendi kadrosu (A-79). `memberships.player_id` buraya bağlanır.
- `opponent_targets`: rakip takımın elle girilen hedef oyuncuları (A-80).
- `training_sessions`, `session_loads`: seans ve oyuncu başına RPE, süre, kafa, sıçrama (A-83).
- `wellness_entries`: Hooper puanları; `scores` alan düzeyinde şifreli zarftır (ADR-0014).
- `marking_plans`: kaydedilen markaj eşleşmesi, sürümlü (ADR-0015, A-82).
- `routine_assignments`: fikstürde rutin rolü → kadro oyuncusu (A-87).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
TENANT_TABLES = (
    "squad_players",
    "opponent_targets",
    "training_sessions",
    "session_loads",
    "wellness_entries",
    "marking_plans",
    "routine_assignments",
)
MD_CODES = "('MD-4', 'MD-3', 'MD-2', 'MD-1', 'MD', 'MD+1')"
POSITIONS = "('GK', 'DEF', 'MID', 'FWD')"

DDL = (
    f"""
create table squad_players (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_squad_players_tenant_id_tenants references tenants(id) on delete cascade,
  name varchar(120) not null,
  shirt_number smallint,
  position varchar(3) not null,
  height_cm smallint,
  aerial_win_pct numeric(4, 3),
  jump_score numeric(4, 3),
  active boolean not null default true,
  is_demo boolean not null default false,
  created_by uuid constraint fk_squad_players_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_squad_players_id_tenant unique (id, tenant_id),
  constraint ck_squad_players_name check (length(btrim(name)) > 0),
  constraint ck_squad_players_shirt check (shirt_number between 1 and 99),
  constraint ck_squad_players_position check (position in {POSITIONS}),
  constraint ck_squad_players_height check (height_cm between 150 and 215),
  constraint ck_squad_players_aerial check (aerial_win_pct between 0 and 1),
  constraint ck_squad_players_jump check (jump_score between 0 and 1)
)
""",
    """
create unique index uq_squad_players_shirt on squad_players (tenant_id, shirt_number)
  where active and shirt_number is not null
""",
    # Oyuncu hesabı paylaşılan `players` yerine kulübün kadro kaydına bağlanır (A-79).
    "alter table memberships drop constraint fk_memberships_player_id_players",
    """
alter table memberships add constraint fk_memberships_player foreign key (player_id, tenant_id)
  references squad_players (id, tenant_id) on delete set null (player_id)
""",
    """
create table opponent_targets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_opponent_targets_tenant_id_tenants references tenants(id) on delete cascade,
  team_id uuid not null constraint fk_opponent_targets_team_id_teams references teams(id),
  name varchar(120) not null,
  shirt_number smallint,
  height_cm smallint,
  aerial_win_pct numeric(4, 3),
  sp_goals smallint,
  notes varchar(400) not null default '',
  created_by uuid constraint fk_opponent_targets_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_opponent_targets_name check (length(btrim(name)) > 0),
  constraint ck_opponent_targets_shirt check (shirt_number between 1 and 99),
  constraint ck_opponent_targets_height check (height_cm between 150 and 215),
  constraint ck_opponent_targets_aerial check (aerial_win_pct between 0 and 1),
  constraint ck_opponent_targets_goals check (sp_goals between 0 and 50)
)
""",
    "create index ix_opponent_targets_team on opponent_targets (tenant_id, team_id)",
    f"""
create table training_sessions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_training_sessions_tenant_id_tenants references tenants(id) on delete cascade,
  date date not null,
  md_code varchar(8),
  fixture_id uuid constraint fk_training_sessions_fixture_id_matches references matches(id),
  title varchar(120) not null,
  is_demo boolean not null default false,
  created_by uuid constraint fk_training_sessions_created_by_users references users(id),
  created_at timestamptz not null default now(),
  constraint uq_training_sessions_id_tenant unique (id, tenant_id),
  constraint ck_training_sessions_md_code check (md_code in {MD_CODES}),
  constraint ck_training_sessions_title check (length(btrim(title)) > 0)
)
""",
    "create index ix_training_sessions_date on training_sessions (tenant_id, date)",
    """
create table session_loads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_session_loads_tenant_id_tenants references tenants(id) on delete cascade,
  session_id uuid not null,
  squad_player_id uuid not null,
  rpe numeric(3, 1) not null,
  minutes smallint not null,
  headers smallint not null default 0,
  jumps smallint not null default 0,
  created_at timestamptz not null default now(),
  constraint fk_session_loads_session foreign key (session_id, tenant_id)
    references training_sessions (id, tenant_id) on delete cascade,
  constraint fk_session_loads_player foreign key (squad_player_id, tenant_id)
    references squad_players (id, tenant_id) on delete cascade,
  constraint uq_session_loads_session_player unique (session_id, squad_player_id),
  constraint ck_session_loads_rpe check (rpe between 0 and 10),
  constraint ck_session_loads_minutes check (minutes between 0 and 300),
  constraint ck_session_loads_headers check (headers between 0 and 500),
  constraint ck_session_loads_jumps check (jumps between 0 and 1000)
)
""",
    "create index ix_session_loads_player on session_loads (tenant_id, squad_player_id)",
    """
create table wellness_entries (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_wellness_entries_tenant_id_tenants references tenants(id) on delete cascade,
  squad_player_id uuid not null,
  date date not null,
  scores jsonb not null,
  entered_by uuid constraint fk_wellness_entries_entered_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint fk_wellness_entries_player foreign key (squad_player_id, tenant_id)
    references squad_players (id, tenant_id) on delete cascade,
  constraint uq_wellness_entries_player_date unique (tenant_id, squad_player_id, date),
  constraint ck_wellness_entries_envelope check (scores ? 'ciphertext' and scores ? 'kid')
)
""",
    """
create table marking_plans (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_marking_plans_tenant_id_tenants references tenants(id) on delete cascade,
  fixture_id uuid not null constraint fk_marking_plans_fixture_id_matches references matches(id),
  version integer not null,
  assignments jsonb not null,
  zonal jsonb not null default '[]',
  suggested jsonb not null,
  overridden smallint not null default 0,
  note varchar(400),
  created_by uuid constraint fk_marking_plans_created_by_users references users(id),
  created_at timestamptz not null default now(),
  constraint uq_marking_plans_fixture_version unique (tenant_id, fixture_id, version),
  constraint ck_marking_plans_version check (version >= 1)
)
""",
    """
create table routine_assignments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_routine_assignments_tenant_id_tenants references tenants(id) on delete cascade,
  fixture_id uuid not null
    constraint fk_routine_assignments_fixture_id_matches references matches(id),
  routine_id uuid not null,
  routine_version integer not null,
  diagram_player_id varchar(32) not null,
  role varchar(32) not null,
  squad_player_id uuid not null,
  assigned_by uuid constraint fk_routine_assignments_assigned_by_users references users(id),
  assigned_at timestamptz not null default now(),
  constraint fk_routine_assignments_routine foreign key (routine_id, tenant_id)
    references routines (id, tenant_id) on delete cascade,
  constraint fk_routine_assignments_player foreign key (squad_player_id, tenant_id)
    references squad_players (id, tenant_id) on delete cascade,
  constraint uq_routine_assignments_slot
    unique (tenant_id, fixture_id, routine_id, diagram_player_id)
)
""",
    """
create index ix_routine_assignments_player
  on routine_assignments (tenant_id, squad_player_id, fixture_id)
""",
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
        op.execute(f"grant select, insert, update, delete on {', '.join(TENANT_TABLES)} to {role}")


def downgrade() -> None:
    op.execute("alter table memberships drop constraint fk_memberships_player")
    op.execute("update memberships set player_id = null where player_id is not null")
    op.execute(
        "alter table memberships add constraint fk_memberships_player_id_players"
        " foreign key (player_id) references players(id)"
    )
    for table in reversed(TENANT_TABLES):
        op.execute(f"drop table {table}")
