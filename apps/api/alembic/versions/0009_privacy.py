"""KVKK veri yaşam döngüsü (Faz 8; ADR-0019, A-92).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01

- `health_consents`: iyi oluş verisi için açık rıza; oyuncu başına en çok bir etkin kayıt.
- `privacy_requests`: veri sahibi talepleri (dışa aktarma, silme) ve kararları.
- `squad_players.erased_at`: silme talebiyle anonimleştirilen kadro kaydı.
- Gecelik saklama görevi (worker) için: `tenants` üzerinde worker'a yalnız okuma politikası
  (kiracıları dolaşmak için) ve denetim kaydını silen SECURITY DEFINER `kurgu_purge_audit()`
  (uygulama rollerinin denetim kaydında silme yetkisi yoktur).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
TENANT_TABLES = ("health_consents", "privacy_requests")

DDL = (
    "alter table squad_players add column erased_at timestamptz",
    """
create table health_consents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_health_consents_tenant_id_tenants references tenants(id) on delete cascade,
  squad_player_id uuid not null,
  text_version varchar(32) not null,
  method varchar(8) not null,
  reference varchar(200),
  recorded_by uuid constraint fk_health_consents_recorded_by_users references users(id),
  given_at timestamptz not null default now(),
  withdrawn_at timestamptz,
  withdrawn_by uuid constraint fk_health_consents_withdrawn_by_users references users(id),
  is_demo boolean not null default false,
  constraint fk_health_consents_player foreign key (squad_player_id, tenant_id)
    references squad_players (id, tenant_id) on delete cascade,
  constraint ck_health_consents_method check (method in ('self', 'paper')),
  constraint ck_health_consents_reference check (method = 'self' or reference is not null)
)
""",
    """
create unique index uq_health_consents_active on health_consents (tenant_id, squad_player_id)
  where withdrawn_at is null
""",
    """
create table privacy_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_privacy_requests_tenant_id_tenants references tenants(id) on delete cascade,
  squad_player_id uuid not null,
  kind varchar(8) not null,
  status varchar(10) not null default 'open',
  reason varchar(500),
  requested_by uuid constraint fk_privacy_requests_requested_by_users references users(id),
  created_at timestamptz not null default now(),
  decided_by uuid constraint fk_privacy_requests_decided_by_users references users(id),
  decided_at timestamptz,
  note varchar(500),
  constraint fk_privacy_requests_player foreign key (squad_player_id, tenant_id)
    references squad_players (id, tenant_id) on delete cascade,
  constraint ck_privacy_requests_kind check (kind in ('erasure')),
  constraint ck_privacy_requests_status check (status in ('open', 'completed', 'rejected'))
)
""",
    """
create unique index uq_privacy_requests_open on privacy_requests (tenant_id, squad_player_id, kind)
  where status = 'open'
""",
    "create policy worker_list on tenants for select to kurgu_worker using (true)",
    """
create function kurgu_purge_audit(p_tenant uuid, p_before timestamptz) returns bigint
  language plpgsql security definer set search_path = public
  as $$
declare removed bigint;
begin
  perform set_config('app.tenant_id', p_tenant::text, true);
  delete from audit_log where tenant_id = p_tenant and at < p_before;
  get diagnostics removed = row_count;
  return removed;
end
$$
""",
    "revoke all on function kurgu_purge_audit(uuid, timestamptz) from public",
    "grant execute on function kurgu_purge_audit(uuid, timestamptz) to kurgu_worker",
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
    op.execute("drop function kurgu_purge_audit(uuid, timestamptz)")
    op.execute("drop policy worker_list on tenants")
    for table in reversed(TENANT_TABLES):
        op.execute(f"drop table {table}")
    op.execute("alter table squad_players drop column erased_at")
