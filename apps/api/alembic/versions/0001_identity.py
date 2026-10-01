"""Kimlik tabloları, RLS politikaları ve kullanıcı çözümleme fonksiyonu.

Revision ID: 0001
Revises:
Create Date: 2026-09-30

RLS tasarımı (ADR-0002):
- `app.tenant_id` ve `app.user_id` ayarları API tarafından her işlemde `SET LOCAL` ile yazılır.
- `kurgu_current_tenant()` / `kurgu_current_user()` boş ayarı NULL'a çevirir; NULL hiçbir
  satırla eşleşmez (güvenli varsayılan).
- `tenants` ve `memberships` FORCE RLS kullanır. `users` yalnızca ENABLE RLS kullanır, çünkü
  SECURITY DEFINER `kurgu_resolve_user` fonksiyonu tablo sahibi olarak (iss, sub)
  aramasını kullanıcı kimliği henüz bilinmeden yapmalıdır. Uygulama rolü sahip olmadığı
  için yine RLS'ye tabidir.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("admin", "head_coach", "sp_coach", "analyst", "performance", "medical", "player", "viewer")
APP_ROLES = ("kurgu_app", "kurgu_worker")


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")
    op.execute(
        """
        create function kurgu_current_tenant() returns uuid
        language sql stable as
        $$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$
        """
    )
    op.execute(
        """
        create function kurgu_current_user() returns uuid
        language sql stable as
        $$ select nullif(current_setting('app.user_id', true), '')::uuid $$
        """
    )

    op.create_table(
        "tenants",
        sa.Column(
            "id", postgresql.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("club_team_id", postgresql.UUID()),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("data_region", sa.String(16), nullable=False, server_default="tr"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )
    op.create_table(
        "users",
        sa.Column(
            "id", postgresql.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )
    role_list = ", ".join(f"'{r}'" for r in ROLES)
    op.create_table(
        "memberships",
        sa.Column(
            "id", postgresql.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("user_id", postgresql.UUID(), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("player_id", postgresql.UUID()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_memberships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "tenant_id", "role", name="uq_memberships_user_tenant_role"),
        sa.CheckConstraint(f"role in ({role_list})", name="ck_memberships_role_valid"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    # --- RLS ---
    for table in ("tenants", "memberships"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
    op.execute("alter table users enable row level security")

    op.execute(
        """
        create policy membership_access on memberships
          using (tenant_id = kurgu_current_tenant() or user_id = kurgu_current_user())
          with check (tenant_id = kurgu_current_tenant())
        """
    )
    op.execute(
        """
        create policy tenant_access on tenants
          using (
            id = kurgu_current_tenant()
            or exists (
              select 1 from memberships m
              where m.tenant_id = tenants.id and m.user_id = kurgu_current_user()
            )
          )
          with check (id = kurgu_current_tenant())
        """
    )
    op.execute(
        """
        create policy user_access on users
          using (
            id = kurgu_current_user()
            or exists (
              select 1 from memberships m
              where m.user_id = users.id and m.tenant_id = kurgu_current_tenant()
            )
          )
          with check (id = kurgu_current_user())
        """
    )

    op.execute(
        """
        create function kurgu_resolve_user(p_issuer text, p_subject text, p_email text, p_name text)
        returns uuid
        language plpgsql security definer
        set search_path = public, pg_temp
        as $$
        declare
          v_id uuid;
        begin
          insert into users (issuer, subject, email, display_name, last_seen_at)
          values (p_issuer, p_subject, p_email, p_name, now())
          on conflict (issuer, subject) do update
            set email = coalesce(excluded.email, users.email),
                display_name = coalesce(excluded.display_name, users.display_name),
                last_seen_at = now()
          returning id into v_id;
          return v_id;
        end
        $$
        """
    )
    op.execute("revoke all on function kurgu_resolve_user(text, text, text, text) from public")

    for role in APP_ROLES:
        op.execute(f"grant select, insert, update, delete on tenants, memberships to {role}")
        op.execute(f"grant select, update on users to {role}")
        op.execute(
            f"grant execute on function kurgu_resolve_user(text, text, text, text) to {role}"
        )
        op.execute(
            f"grant execute on function kurgu_current_tenant(), kurgu_current_user() to {role}"
        )


def downgrade() -> None:
    op.execute("drop function if exists kurgu_resolve_user(text, text, text, text)")
    op.execute("drop policy if exists user_access on users")
    op.execute("drop policy if exists tenant_access on tenants")
    op.execute("drop policy if exists membership_access on memberships")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("drop function if exists kurgu_current_user()")
    op.execute("drop function if exists kurgu_current_tenant()")
