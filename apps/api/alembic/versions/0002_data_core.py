"""Veri çekirdeği: paylaşılan lig tabloları, kiracı tabloları ve RLS politikaları.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30

RLS tasarımı (ADR-0002, Faz 1 notu):
- Paylaşılan lig tablolarında `tenant_id` yoktur. ENABLE RLS kullanılır (tablo sahibi olan
  göç rolü tohum yüklerken atlar; `kurgu_app` ve `kurgu_worker` tabidir).
- Okuma `data_licenses` üzerinden açılır. Yarışmaya bağlı tablolar (`seasons`, `matches`,
  `events`, `standings_snapshots`, `team_season_stats`, `season_stats`) yalnızca lisanslı
  yarışmaları gösterir. Birden çok yarışmada yer alan varlıklar (`teams`, `players`,
  `provider_id_map`) kiracının geçerli en az bir lisansı varsa görünür.
- Paylaşılan tablolara yazma yalnızca `kurgu_worker` rolüne açıktır (sağlayıcı yüklemesi).
- Kiracı tabloları FORCE RLS kullanır. `set_pieces` iki kaynaklıdır: sağlayıcıdan çıkarılan
  diziler paylaşılır (`tenant_id` null, `source='provider'`), canlı kayıt dizileri kiracıya
  aittir (`source='live_tag'`).
- `audit_log` yalnızca eklemedir: uygulama rollerine update/delete yetkisi verilmez.
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")

# Yarışma lisansı üzerinden okunan paylaşılan tablolar ve lisans ifadesi.
SHARED_BY_COMPETITION = {
    "competitions": "kurgu_licensed(id)",
    "seasons": "kurgu_licensed(competition_id)",
    "matches": "kurgu_licensed_season(season_id)",
    "standings_snapshots": "kurgu_licensed_season(season_id)",
    "team_season_stats": "kurgu_licensed_season(season_id)",
    "season_stats": "kurgu_licensed_season(season_id)",
    "events": "kurgu_licensed_match(match_id)",
}
# Birden çok yarışmada yer alan paylaşılan varlıklar.
SHARED_ANY_LICENSE = ("teams", "players", "provider_id_map")
SHARED_TABLES = (*SHARED_BY_COMPETITION, *SHARED_ANY_LICENSE)
TENANT_TABLES = ("data_licenses", "audit_log", "imports", "tagging_sessions", "live_tags")
# Kiracı ya da paylaşılan olabilen tablolar (tenant_id null = paylaşılan).
MIXED_TABLES = ("ingestion_runs", "raw_payloads", "set_pieces")

DDL = """
create table competitions (
  id uuid primary key default gen_random_uuid(),
  code varchar(32) not null,
  name varchar(200) not null,
  country varchar(64),
  team_type varchar(16) not null default 'first',
  created_at timestamptz not null default now(),
  constraint uq_competitions_code unique (code),
  constraint ck_competitions_team_type check (team_type in ('first', 'u19', 'women', 'other'))
);

create table seasons (
  id uuid primary key default gen_random_uuid(),
  competition_id uuid not null
    constraint fk_seasons_competition_id_competitions references competitions(id),
  code varchar(32) not null,
  label varchar(64) not null,
  start_date date,
  end_date date,
  matches_per_team smallint,
  created_at timestamptz not null default now(),
  constraint uq_seasons_competition_code unique (competition_id, code)
);

create table teams (
  id uuid primary key default gen_random_uuid(),
  code varchar(16) not null,
  name varchar(200) not null,
  official_name varchar(300),
  country varchar(64),
  team_type varchar(16) not null default 'first',
  created_at timestamptz not null default now(),
  constraint ck_teams_team_type check (team_type in ('first', 'u19', 'women', 'other'))
);
create index ix_teams_code on teams (code);

create table players (
  id uuid primary key default gen_random_uuid(),
  name varchar(200) not null,
  known_name varchar(200),
  birth_date date,
  height_cm smallint,
  preferred_foot varchar(8),
  current_team_id uuid constraint fk_players_current_team_id_teams references teams(id),
  created_at timestamptz not null default now(),
  constraint ck_players_preferred_foot check (preferred_foot in ('left', 'right', 'both')),
  constraint ck_players_height check (height_cm between 120 and 230)
);

create table matches (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null constraint fk_matches_season_id_seasons references seasons(id),
  week smallint,
  stage varchar(64),
  home_team_id uuid not null constraint fk_matches_home_team_id_teams references teams(id),
  away_team_id uuid not null constraint fk_matches_away_team_id_teams references teams(id),
  kickoff_at timestamptz,
  home_score smallint,
  away_score smallint,
  status varchar(16) not null default 'scheduled',
  source varchar(64) not null,
  is_demo boolean not null default false,
  extra jsonb not null default '{}',
  created_at timestamptz not null default now(),
  constraint ck_matches_status
    check (status in ('scheduled', 'finished', 'postponed', 'cancelled')),
  constraint ck_matches_distinct_teams check (home_team_id <> away_team_id),
  constraint ck_matches_score_when_finished
    check (status <> 'finished' or (home_score is not null and away_score is not null))
);
create index ix_matches_season_week on matches (season_id, week);
create index ix_matches_home_team_id on matches (home_team_id);
create index ix_matches_away_team_id on matches (away_team_id);

create table standings_snapshots (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null
    constraint fk_standings_snapshots_season_id_seasons references seasons(id),
  week smallint not null,
  team_id uuid not null constraint fk_standings_snapshots_team_id_teams references teams(id),
  position smallint not null,
  played smallint not null,
  won smallint not null,
  drawn smallint not null,
  lost smallint not null,
  gf smallint not null,
  ga smallint not null,
  pts smallint not null,
  source varchar(64) not null,
  is_demo boolean not null default false,
  constraint uq_standings_snapshots_season_week_team unique (season_id, week, team_id),
  constraint ck_standings_snapshots_played check (played = won + drawn + lost)
);

create table team_season_stats (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null
    constraint fk_team_season_stats_season_id_seasons references seasons(id),
  team_id uuid not null constraint fk_team_season_stats_team_id_teams references teams(id),
  metric varchar(64) not null,
  value numeric not null,
  as_of_week smallint,
  source varchar(64) not null,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  constraint uq_team_season_stats_key
    unique nulls not distinct (season_id, team_id, metric, source, as_of_week)
);
create index ix_team_season_stats_season_metric on team_season_stats (season_id, metric);

create table season_stats (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null constraint fk_season_stats_season_id_seasons references seasons(id),
  metric varchar(64) not null,
  value numeric not null,
  source varchar(64) not null,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  constraint uq_season_stats_key unique (season_id, metric, source)
);

create table provider_id_map (
  id uuid primary key default gen_random_uuid(),
  entity_type varchar(16) not null,
  provider varchar(32) not null,
  provider_id varchar(128) not null,
  kurgu_id uuid not null,
  confidence numeric(4, 3) not null default 1,
  confirmed_by uuid constraint fk_provider_id_map_confirmed_by_users references users(id),
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint uq_provider_id_map_key unique (entity_type, provider, provider_id),
  constraint ck_provider_id_map_entity_type
    check (entity_type in ('competition', 'season', 'team', 'player', 'match')),
  constraint ck_provider_id_map_confidence check (confidence between 0 and 1)
);
create index ix_provider_id_map_kurgu_id on provider_id_map (kurgu_id);

create table data_licenses (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_data_licenses_tenant_id_tenants references tenants(id) on delete cascade,
  provider varchar(32) not null,
  competition_id uuid
    constraint fk_data_licenses_competition_id_competitions references competitions(id),
  valid_from date not null default current_date,
  valid_to date,
  terms_note text,
  created_at timestamptz not null default now(),
  constraint ck_data_licenses_valid_range check (valid_to is null or valid_to >= valid_from)
);
create index ix_data_licenses_tenant_id on data_licenses (tenant_id);

create table ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid constraint fk_ingestion_runs_tenant_id_tenants references tenants(id)
    on delete cascade,
  provider varchar(32) not null,
  kind varchar(32) not null,
  status varchar(16) not null default 'pending',
  params jsonb not null default '{}',
  stats jsonb not null default '{}',
  quality_report jsonb,
  error text,
  created_by uuid constraint fk_ingestion_runs_created_by_users references users(id),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  constraint ck_ingestion_runs_status
    check (status in ('pending', 'running', 'succeeded', 'quarantined', 'failed'))
);
create index ix_ingestion_runs_tenant_id on ingestion_runs (tenant_id);

create table raw_payloads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid constraint fk_raw_payloads_tenant_id_tenants references tenants(id)
    on delete cascade,
  provider varchar(32) not null,
  kind varchar(32) not null,
  source_hash char(64) not null,
  storage_key varchar(500) not null,
  content_type varchar(100),
  size_bytes bigint not null,
  ingestion_run_id uuid
    constraint fk_raw_payloads_ingestion_run_id_ingestion_runs references ingestion_runs(id),
  fetched_at timestamptz not null default now(),
  constraint uq_raw_payloads_source unique nulls not distinct (tenant_id, provider, source_hash)
);

create table set_pieces (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid constraint fk_set_pieces_tenant_id_tenants references tenants(id)
    on delete cascade,
  match_id uuid not null constraint fk_set_pieces_match_id_matches references matches(id),
  team_id uuid not null constraint fk_set_pieces_team_id_teams references teams(id),
  period smallint not null,
  start_time_s double precision not null,
  sp_type varchar(16) not null,
  sp_subtype varchar(16),
  side varchar(8),
  taker_id uuid constraint fk_set_pieces_taker_id_players references players(id),
  start_x real,
  start_y real,
  end_x real,
  end_y real,
  target_zone varchar(4),
  first_contact_team_id uuid
    constraint fk_set_pieces_first_contact_team_id_teams references teams(id),
  first_contact_player_id uuid
    constraint fk_set_pieces_first_contact_player_id_players references players(id),
  outcome varchar(32),
  shots smallint not null default 0,
  xg_total real not null default 0,
  xg_phase1 real not null default 0,
  xg_phase2 real not null default 0,
  goal boolean not null default false,
  phase_of_goal smallint,
  routine_id uuid,
  observed_scheme varchar(16),
  video_clip_id uuid,
  source varchar(16) not null,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  constraint ck_set_pieces_sp_type check (sp_type in ('corner', 'free_kick', 'throw_in')),
  constraint ck_set_pieces_side check (side in ('left', 'right')),
  constraint ck_set_pieces_target_zone
    check (target_zone in ('NP', 'C6', 'FP', 'PS', 'ED', 'SH', 'OT')),
  constraint ck_set_pieces_outcome check (outcome in (
    'goal', 'shot_on_target', 'shot_off_target', 'shot_blocked', 'first_contact_no_shot',
    'cleared', 'possession_retained', 'counter_conceded')),
  constraint ck_set_pieces_phase_of_goal check (phase_of_goal in (1, 2)),
  constraint ck_set_pieces_observed_scheme check (observed_scheme in ('zonal', 'man', 'hybrid')),
  constraint ck_set_pieces_source_owner check (
    (source = 'provider' and tenant_id is null) or (source = 'live_tag' and tenant_id is not null))
);
create index ix_set_pieces_match_id on set_pieces (match_id);
create index ix_set_pieces_team_type on set_pieces (team_id, sp_type);
create index ix_set_pieces_tenant_id on set_pieces (tenant_id);

create table events (
  id bigint generated always as identity primary key,
  match_id uuid not null constraint fk_events_match_id_matches references matches(id)
    on delete cascade,
  action_index integer not null,
  period smallint not null,
  time_s double precision not null,
  team_id uuid not null constraint fk_events_team_id_teams references teams(id),
  player_id uuid constraint fk_events_player_id_players references players(id),
  type varchar(32) not null,
  result varchar(16) not null,
  bodypart varchar(16) not null,
  start_x real not null,
  start_y real not null,
  end_x real not null,
  end_y real not null,
  sequence_id integer,
  set_piece_id uuid constraint fk_events_set_piece_id_set_pieces references set_pieces(id)
    on delete set null,
  xg real,
  xg_source varchar(32),
  provider varchar(32) not null,
  provider_event_id varchar(64),
  raw_ref uuid constraint fk_events_raw_ref_raw_payloads references raw_payloads(id),
  extra jsonb not null default '{}',
  constraint uq_events_match_action unique (match_id, action_index),
  constraint ck_events_period check (period between 1 and 5),
  constraint ck_events_time check (time_s >= 0),
  constraint ck_events_x check (start_x between 0 and 105 and end_x between 0 and 105),
  constraint ck_events_y check (start_y between 0 and 68 and end_y between 0 and 68),
  constraint ck_events_xg check (xg is null or xg between 0 and 1)
);
create index ix_events_match_time on events (match_id, period, time_s);
create index ix_events_set_piece_id on events (set_piece_id) where set_piece_id is not null;

create table imports (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null constraint fk_imports_tenant_id_tenants references tenants(id)
    on delete cascade,
  kind varchar(32) not null,
  filename varchar(255) not null,
  content_type varchar(100) not null,
  size_bytes bigint not null,
  source_hash char(64) not null,
  storage_key varchar(500) not null,
  status varchar(16) not null default 'uploaded',
  mapping jsonb not null default '{}',
  quality_report jsonb,
  ingestion_run_id uuid
    constraint fk_imports_ingestion_run_id_ingestion_runs references ingestion_runs(id),
  created_by uuid constraint fk_imports_created_by_users references users(id),
  created_at timestamptz not null default now(),
  committed_at timestamptz,
  constraint ck_imports_kind check (kind in ('team_season_stats', 'events')),
  constraint ck_imports_status check (
    status in ('uploaded', 'validated', 'quarantined', 'committed', 'failed'))
);
create index ix_imports_tenant_id on imports (tenant_id);

create table tagging_sessions (
  id uuid primary key,
  tenant_id uuid not null
    constraint fk_tagging_sessions_tenant_id_tenants references tenants(id) on delete cascade,
  match_id uuid constraint fk_tagging_sessions_match_id_matches references matches(id),
  device_id varchar(64) not null,
  created_by uuid constraint fk_tagging_sessions_created_by_users references users(id),
  created_at_client timestamptz not null,
  server_received_at timestamptz not null default now(),
  status varchar(16) not null default 'open',
  deleted boolean not null default false,
  constraint ck_tagging_sessions_status check (status in ('open', 'closed'))
);
create index ix_tagging_sessions_tenant_id on tagging_sessions (tenant_id);

create table live_tags (
  id uuid primary key,
  tenant_id uuid not null
    constraint fk_live_tags_tenant_id_tenants references tenants(id) on delete cascade,
  session_id uuid not null
    constraint fk_live_tags_session_id_tagging_sessions references tagging_sessions(id)
    on delete cascade,
  device_id varchar(64) not null,
  created_at_client timestamptz not null,
  server_received_at timestamptz not null default now(),
  server_version integer not null default 1,
  deleted boolean not null default false,
  payload jsonb not null default '{}'
);
create index ix_live_tags_session_id on live_tags (session_id);

create table audit_log (
  id bigint generated always as identity primary key,
  tenant_id uuid not null
    constraint fk_audit_log_tenant_id_tenants references tenants(id) on delete cascade,
  actor_id uuid constraint fk_audit_log_actor_id_users references users(id),
  action varchar(64) not null,
  entity varchar(64) not null,
  entity_id varchar(128),
  before jsonb,
  after jsonb,
  ip inet,
  at timestamptz not null default now()
);
create index ix_audit_log_tenant_at on audit_log (tenant_id, at desc);

alter table tenants add constraint fk_tenants_club_team_id_teams
  foreign key (club_team_id) references teams(id);
alter table memberships add constraint fk_memberships_player_id_players
  foreign key (player_id) references players(id);
"""

FUNCTIONS = """
create function kurgu_licensed(p_competition uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (
    select 1 from data_licenses l
    where l.tenant_id = kurgu_current_tenant()
      and (l.competition_id is null or l.competition_id = p_competition)
      and l.valid_from <= current_date
      and (l.valid_to is null or l.valid_to >= current_date)
  )
$$;

create function kurgu_has_any_license() returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (
    select 1 from data_licenses l
    where l.tenant_id = kurgu_current_tenant()
      and l.valid_from <= current_date
      and (l.valid_to is null or l.valid_to >= current_date)
  )
$$;

create function kurgu_licensed_season(p_season uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (
    select 1 from seasons s where s.id = p_season and kurgu_licensed(s.competition_id)
  )
$$;

create function kurgu_licensed_match(p_match uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (
    select 1 from matches m join seasons s on s.id = m.season_id
    where m.id = p_match and kurgu_licensed(s.competition_id)
  )
$$;
"""
LICENSE_FUNCTIONS = (
    "kurgu_licensed(uuid)",
    "kurgu_has_any_license()",
    "kurgu_licensed_season(uuid)",
    "kurgu_licensed_match(uuid)",
)


def _run_script(sql: str) -> None:
    """asyncpg tek ifadede birden çok komut kabul etmez; betik ifade ifade çalıştırılır."""
    for statement in re.split(r";\s*\n", sql):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _run_script(DDL)
    _run_script(FUNCTIONS)

    for table in SHARED_TABLES:
        op.execute(f"alter table {table} enable row level security")
    for table in (*TENANT_TABLES, *MIXED_TABLES):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")

    # Paylaşılan tablolar: lisanslı okuma herkese, yazma yalnızca worker'a.
    for table, predicate in SHARED_BY_COMPETITION.items():
        op.execute(f"create policy licensed_read on {table} for select using ({predicate})")
    for table in SHARED_ANY_LICENSE:
        op.execute(
            f"create policy licensed_read on {table} for select using (kurgu_has_any_license())"
        )
    for table in SHARED_TABLES:
        op.execute(
            f"create policy worker_write on {table} for all to kurgu_worker"
            " using (true) with check (true)"
        )

    # Kiracı tabloları.
    for table in TENANT_TABLES:
        op.execute(
            f"create policy tenant_isolation on {table}"
            " using (tenant_id = kurgu_current_tenant())"
            " with check (tenant_id = kurgu_current_tenant())"
        )

    # Karma tablolar: kiracı kendi satırlarını görür; paylaşılan satırları worker yazar.
    for table in ("ingestion_runs", "raw_payloads"):
        op.execute(
            f"create policy tenant_isolation on {table}"
            " using (tenant_id = kurgu_current_tenant())"
            " with check (tenant_id = kurgu_current_tenant())"
        )
        op.execute(
            f"create policy worker_shared on {table} for all to kurgu_worker"
            " using (tenant_id is null) with check (tenant_id is null)"
        )
    # Okuma: kendi dizileri ve lisanslı maçların paylaşılan dizileri. Yazma: yalnızca kendi.
    op.execute(
        "create policy licensed_read on set_pieces for select"
        " using (tenant_id is null and kurgu_licensed_match(match_id))"
    )
    op.execute(
        "create policy tenant_isolation on set_pieces"
        " using (tenant_id = kurgu_current_tenant())"
        " with check (tenant_id = kurgu_current_tenant())"
    )
    op.execute(
        "create policy worker_shared on set_pieces for all to kurgu_worker"
        " using (tenant_id is null) with check (tenant_id is null and source = 'provider')"
    )

    functions = ", ".join(LICENSE_FUNCTIONS)
    op.execute(f"revoke all on function {functions} from public")
    for role in APP_ROLES:
        op.execute(f"grant execute on function {functions} to {role}")
        op.execute(f"grant select on {', '.join(SHARED_TABLES)} to {role}")
        op.execute(f"grant select on data_licenses to {role}")
        op.execute(
            "grant select, insert, update, delete on"
            " imports, tagging_sessions, live_tags, ingestion_runs, raw_payloads, set_pieces"
            f" to {role}"
        )
        op.execute(f"grant select, insert on audit_log to {role}")
    op.execute(f"grant insert, update, delete on {', '.join(SHARED_TABLES)} to kurgu_worker")
    op.execute("grant usage on all sequences in schema public to kurgu_app, kurgu_worker")


def downgrade() -> None:
    op.execute("alter table memberships drop constraint fk_memberships_player_id_players")
    op.execute("alter table tenants drop constraint fk_tenants_club_team_id_teams")
    for table in (
        "audit_log",
        "live_tags",
        "tagging_sessions",
        "imports",
        "events",
        "set_pieces",
        "raw_payloads",
        "ingestion_runs",
        "data_licenses",
        "provider_id_map",
        "season_stats",
        "team_season_stats",
        "standings_snapshots",
        "matches",
        "players",
        "teams",
        "seasons",
        "competitions",
    ):
        # Politikalar lisans fonksiyonlarına bağlıdır; tablo düşünce birlikte düşerler.
        op.execute(f"drop table {table}")
    for function in LICENSE_FUNCTIONS:
        op.execute(f"drop function {function}")
