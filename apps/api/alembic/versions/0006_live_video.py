"""Canlı kayıt senkronizasyonu ve video (ADR-0004, ADR-0010).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

- `tagging_sessions`: maç başına tek oturum (A-56) ve oturumun son sıra numarası (`last_seq`).
- `live_tags`: sunucu sıra numarası (`server_seq`, çekme için), son yazan kazanır karşılaştırması
  için istemci zamanı (`client_ts`).
- `video_assets`: yüklenen maç videoları ve HLS durumu (A-60, A-61).
- `video_clips`: video içindeki aralıklar; isteğe bağlı duran top bağı (A-62).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
TENANT_TABLES = ("video_assets", "video_clips")

DDL = (
    "alter table tagging_sessions add column last_seq bigint not null default 0",
    """
create unique index uq_tagging_sessions_match on tagging_sessions (tenant_id, match_id)
  where not deleted and match_id is not null
""",
    """
alter table live_tags
  add column server_seq bigint not null default 0,
  add column client_ts timestamptz,
  add column updated_at timestamptz not null default now()
""",
    "update live_tags set client_ts = created_at_client",
    "alter table live_tags alter column client_ts set not null",
    "create index ix_live_tags_session_seq on live_tags (session_id, server_seq)",
    """
create table video_assets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_video_assets_tenant_id_tenants references tenants(id) on delete cascade,
  match_id uuid constraint fk_video_assets_match_id_matches references matches(id),
  title varchar(200) not null,
  filename varchar(255) not null,
  content_type varchar(64) not null,
  size_bytes bigint not null,
  part_size integer not null,
  parts integer not null,
  storage_key varchar(512) not null,
  upload_id varchar(512),
  status varchar(16) not null default 'uploading',
  error text,
  duration_s double precision,
  hls_key varchar(512),
  offset_s double precision not null default 0,
  idempotency_key varchar(128),
  created_by uuid constraint fk_video_assets_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_video_assets_id_tenant unique (id, tenant_id),
  constraint uq_video_assets_idempotency unique (tenant_id, idempotency_key),
  constraint ck_video_assets_status
    check (status in ('uploading', 'processing', 'ready', 'failed')),
  constraint ck_video_assets_size check (size_bytes > 0 and parts > 0 and part_size > 0)
)
""",
    "create index ix_video_assets_tenant_match on video_assets (tenant_id, match_id)",
    """
create table video_clips (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_video_clips_tenant_id_tenants references tenants(id) on delete cascade,
  asset_id uuid not null,
  start_s double precision not null,
  end_s double precision not null,
  title varchar(200) not null default '',
  set_piece_id uuid
    constraint fk_video_clips_set_piece_id_set_pieces references set_pieces(id)
    on delete set null,
  created_by uuid constraint fk_video_clips_created_by_users references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint fk_video_clips_asset foreign key (asset_id, tenant_id)
    references video_assets(id, tenant_id) on delete cascade,
  constraint ck_video_clips_range check (start_s >= 0 and end_s > start_s)
)
""",
    "create index ix_video_clips_asset on video_clips (asset_id)",
    "create index ix_video_clips_set_piece on video_clips (set_piece_id)",
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
        op.execute(f"grant select, insert, update, delete on video_assets, video_clips to {role}")


def downgrade() -> None:
    op.execute("drop table video_clips")
    op.execute("drop table video_assets")
    op.execute("drop index ix_live_tags_session_seq")
    op.execute(
        "alter table live_tags drop column updated_at, drop column client_ts,"
        " drop column server_seq"
    )
    op.execute("drop index uq_tagging_sessions_match")
    op.execute("alter table tagging_sessions drop column last_seq")
