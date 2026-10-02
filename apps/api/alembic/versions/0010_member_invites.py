"""Kulüp üyeliği davetleri (A-100).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02

- `membership_invites`: yöneticinin e-posta adresine verdiği roller. Kullanıcı Kurgu'ya ilk kez
  (ya da yeniden) doğrulanmış aynı e-postayla girince davet üyeliğe dönüşür.
- `kurgu_claim_invites()`: SECURITY DEFINER. Giriş anında kullanıcının hangi kulüpten davet
  aldığı bilinmez; fonksiyon sahibi davetleri tüm kiracılarda yalnız bu iş için okur (sahibe
  özel politika), her davet için kiracı bağlamını ayarlayıp üyeliği ve denetim kaydını yazar.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("kurgu_app", "kurgu_worker")
ROLES = ("admin", "head_coach", "sp_coach", "analyst", "performance", "medical", "player", "viewer")

DDL = (
    f"""
create table membership_invites (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null
    constraint fk_membership_invites_tenant_id_tenants references tenants(id) on delete cascade,
  email varchar(254) not null,
  roles varchar(16)[] not null,
  invited_by uuid constraint fk_membership_invites_invited_by_users references users(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  accepted_at timestamptz,
  accepted_by uuid constraint fk_membership_invites_accepted_by_users references users(id),
  revoked_at timestamptz,
  constraint ck_membership_invites_email
    check (email = lower(email) and position('@' in email) > 1),
  constraint ck_membership_invites_roles check (
    cardinality(roles) > 0 and roles <@ array[{", ".join(f"'{r}'" for r in ROLES)}]::varchar[]
  )
)
""",
    """
create unique index uq_membership_invites_pending on membership_invites (tenant_id, email)
  where accepted_at is null and revoked_at is null
""",
    """
create index ix_membership_invites_email on membership_invites (email)
  where accepted_at is null and revoked_at is null
""",
    "alter table membership_invites enable row level security",
    "alter table membership_invites force row level security",
    """
create policy tenant_isolation on membership_invites
  using (tenant_id = kurgu_current_tenant())
  with check (tenant_id = kurgu_current_tenant())
""",
    # Davet sahibi rol (göçü çalıştıran, tabloların sahibi) yalnız claim fonksiyonu içinde çalışır.
    """
do $$ begin
  execute format(
    'create policy owner_claim on membership_invites to %I using (true) with check (true)',
    current_user
  );
end $$
""",
    """
create function kurgu_claim_invites(p_user uuid, p_email text) returns integer
  language plpgsql security definer set search_path = public, pg_temp
  as $$
declare
  inv record;
  r text;
  claimed integer := 0;
begin
  for inv in
    select id, tenant_id, roles from membership_invites
     where email = lower(p_email) and accepted_at is null and revoked_at is null
       and expires_at > now()
     for update
  loop
    perform set_config('app.tenant_id', inv.tenant_id::text, true);
    foreach r in array inv.roles loop
      insert into memberships (user_id, tenant_id, role) values (p_user, inv.tenant_id, r)
      on conflict (user_id, tenant_id, role) do nothing;
    end loop;
    update membership_invites set accepted_at = now(), accepted_by = p_user where id = inv.id;
    insert into audit_log (tenant_id, actor_id, action, entity, entity_id, after)
    values (inv.tenant_id, p_user, 'invite.accepted', 'membership_invites', inv.id::text,
            jsonb_build_object('roles', to_jsonb(inv.roles)));
    claimed := claimed + 1;
  end loop;
  perform set_config('app.tenant_id', '', true);
  return claimed;
end
$$
""",
    "revoke all on function kurgu_claim_invites(uuid, text) from public",
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)
    for role in APP_ROLES:
        op.execute(f"grant select, insert, update on membership_invites to {role}")
    op.execute("grant execute on function kurgu_claim_invites(uuid, text) to kurgu_app")


def downgrade() -> None:
    op.execute("drop function kurgu_claim_invites(uuid, text)")
    op.execute("drop table membership_invites")
