"""Metrik görünümleri: duran top toplamları ve lig toplamları (ADR-0007).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

- `v_team_setpiece_agg`: `set_pieces` + `matches` üzerinden takım-sezon ham toplamları. Çağıranın
  RLS'siyle çalışır (`security_invoker`); API kiracının kendi satırlarını buradan okur.
- `mv_team_setpiece_season`: aynı toplamların yalnızca paylaşılan (`tenant_id` null) satırları.
- `mv_league_benchmarks`: sezon × ham alan başına lig toplamı ve takım sayısı (paylaşılan son
  kesit, puan durumu ve olay toplamları).
- Materialized view'lerde RLS yoktur. Uygulama rolleri bunları doğrudan okuyamaz; lisans süzgeçli
  `security_barrier` görünümlerle (`v_team_setpiece_season`, `v_league_benchmarks`) okur.
- Formül yoktur: görünümler yalnızca sayım ve toplam tutar; oranlar `kurgu_analytics.metrics`
  içinde hesaplanır.
- Yenileme `kurgu_refresh_metric_views()` ile (`CONCURRENTLY`); tohum ve sağlayıcı yüklemesinden
  sonra çağrılır.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGG_VIEW = """
create view v_team_setpiece_agg with (security_invoker = true) as
with sp as (
  select p.tenant_id, m.season_id, p.match_id, p.team_id,
         case when p.team_id = m.home_team_id then m.away_team_id else m.home_team_id end
           as opponent_id,
         p.sp_type, p.first_contact_team_id, p.shots, p.xg_total, p.xg_phase1, p.xg_phase2,
         p.goal
  from set_pieces p join matches m on m.id = p.match_id
),
games as (
  select m.tenant_id, m.season_id, t.team_id, count(*) as matches
  from matches m
  cross join lateral (values (m.home_team_id), (m.away_team_id)) as t (team_id)
  where m.status = 'finished' and exists (select 1 from set_pieces p where p.match_id = m.id)
  group by m.tenant_id, m.season_id, t.team_id
),
att as (
  select tenant_id, season_id, team_id,
         count(*) as set_pieces,
         count(*) filter (where sp_type = 'corner') as corners,
         count(*) filter (where first_contact_team_id is not null) as sp_with_contact,
         count(*) filter (where first_contact_team_id = team_id) as sp_first_contact_won,
         count(*) filter (where shots > 0) as sp_with_shot,
         sum(xg_total) as set_piece_xg,
         sum(xg_phase1) as sp_xg_phase1,
         sum(xg_phase2) as sp_xg_phase2,
         count(*) filter (where goal) as set_piece_goals,
         count(*) filter (where goal and sp_type = 'corner') as corner_goals
  from sp group by tenant_id, season_id, team_id
),
def as (
  select tenant_id, season_id, opponent_id as team_id,
         count(*) filter (where first_contact_team_id is not null) as def_sp_with_contact,
         count(*) filter (where first_contact_team_id = opponent_id) as def_sp_first_contact_won,
         count(*) filter (where goal) as set_piece_goals_against
  from sp group by tenant_id, season_id, opponent_id
)
select g.tenant_id, g.season_id, g.team_id, g.matches,
       coalesce(a.set_pieces, 0) as set_pieces,
       coalesce(a.corners, 0) as corners,
       coalesce(a.sp_with_contact, 0) as sp_with_contact,
       coalesce(a.sp_first_contact_won, 0) as sp_first_contact_won,
       coalesce(a.sp_with_shot, 0) as sp_with_shot,
       coalesce(a.set_piece_xg, 0)::double precision as set_piece_xg,
       coalesce(a.sp_xg_phase1, 0)::double precision as sp_xg_phase1,
       coalesce(a.sp_xg_phase2, 0)::double precision as sp_xg_phase2,
       coalesce(a.set_piece_goals, 0) as set_piece_goals,
       coalesce(a.corner_goals, 0) as corner_goals,
       coalesce(d.def_sp_with_contact, 0) as def_sp_with_contact,
       coalesce(d.def_sp_first_contact_won, 0) as def_sp_first_contact_won,
       coalesce(d.set_piece_goals_against, 0) as set_piece_goals_against
from games g
left join att a on a.tenant_id is not distinct from g.tenant_id
  and a.season_id = g.season_id and a.team_id = g.team_id
left join def d on d.tenant_id is not distinct from g.tenant_id
  and d.season_id = g.season_id and d.team_id = g.team_id
"""

TEAM_MV = """
create materialized view mv_team_setpiece_season as
select season_id, team_id, matches, set_pieces, corners, sp_with_contact, sp_first_contact_won,
       sp_with_shot, set_piece_xg, sp_xg_phase1, sp_xg_phase2, set_piece_goals, corner_goals,
       def_sp_with_contact, def_sp_first_contact_won, set_piece_goals_against
from v_team_setpiece_agg where tenant_id is null
"""

LEAGUE_MV = """
create materialized view mv_league_benchmarks as
with latest_stats as (
  select distinct on (season_id, team_id, metric) season_id, team_id, metric, value
  from team_season_stats where tenant_id is null
  order by season_id, team_id, metric, coalesce(as_of_week, 1000) desc, source
),
latest_week as (
  select season_id, max(week) as week from standings_snapshots group by season_id
),
standings as (
  select s.season_id, s.team_id, v.metric, v.value
  from standings_snapshots s
  join latest_week w on w.season_id = s.season_id and w.week = s.week
  cross join lateral (values ('standings.goals', s.gf::numeric),
                             ('standings.matches', s.played::numeric)) as v (metric, value)
),
events as (
  select t.season_id, t.team_id, v.metric, v.value
  from mv_team_setpiece_season t
  cross join lateral (values
    ('events.matches', t.matches::numeric),
    ('events.set_pieces', t.set_pieces::numeric),
    ('events.corners', t.corners::numeric),
    ('events.sp_with_contact', t.sp_with_contact::numeric),
    ('events.sp_first_contact_won', t.sp_first_contact_won::numeric),
    ('events.sp_with_shot', t.sp_with_shot::numeric),
    ('events.set_piece_xg', t.set_piece_xg::numeric),
    ('events.sp_xg_phase1', t.sp_xg_phase1::numeric),
    ('events.sp_xg_phase2', t.sp_xg_phase2::numeric),
    ('events.set_piece_goals', t.set_piece_goals::numeric),
    ('events.corner_goals', t.corner_goals::numeric),
    ('events.def_sp_with_contact', t.def_sp_with_contact::numeric),
    ('events.def_sp_first_contact_won', t.def_sp_first_contact_won::numeric),
    ('events.set_piece_goals_against', t.set_piece_goals_against::numeric)
  ) as v (metric, value)
),
merged as (
  select * from latest_stats
  union all select * from standings
  union all select * from events
)
select season_id, metric, sum(value) as total, count(*)::int as teams
from merged group by season_id, metric
"""

REFRESH_FUNCTION = """
create function kurgu_refresh_metric_views() returns void
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  refresh materialized view concurrently mv_team_setpiece_season;
  refresh materialized view concurrently mv_league_benchmarks;
end
$$
"""


def upgrade() -> None:
    # Göç rolü (görünüm sahibi) paylaşılan dizileri yenileme sırasında okuyabilmeli.
    op.execute(
        "create policy owner_read on set_pieces for select to kurgu_owner using (tenant_id is null)"
    )
    op.execute(AGG_VIEW)
    op.execute(TEAM_MV)
    op.execute(
        "create unique index uq_mv_team_setpiece_season on mv_team_setpiece_season"
        " (season_id, team_id)"
    )
    op.execute(LEAGUE_MV)
    op.execute(
        "create unique index uq_mv_league_benchmarks on mv_league_benchmarks (season_id, metric)"
    )
    op.execute(
        "create view v_team_setpiece_season with (security_barrier = true) as"
        " select * from mv_team_setpiece_season where kurgu_licensed_season(season_id)"
    )
    op.execute(
        "create view v_league_benchmarks with (security_barrier = true) as"
        " select * from mv_league_benchmarks where kurgu_licensed_season(season_id)"
    )
    op.execute(REFRESH_FUNCTION)
    op.execute("revoke all on mv_team_setpiece_season, mv_league_benchmarks from public")
    op.execute("revoke all on function kurgu_refresh_metric_views() from public")
    for role in ("kurgu_app", "kurgu_worker"):
        op.execute(
            f"grant select on v_team_setpiece_agg, v_team_setpiece_season, v_league_benchmarks"
            f" to {role}"
        )
    op.execute("grant execute on function kurgu_refresh_metric_views() to kurgu_worker")


def downgrade() -> None:
    op.execute("drop function kurgu_refresh_metric_views()")
    op.execute("drop view v_league_benchmarks")
    op.execute("drop view v_team_setpiece_season")
    op.execute("drop materialized view mv_league_benchmarks")
    op.execute("drop materialized view mv_team_setpiece_season")
    op.execute("drop view v_team_setpiece_agg")
    op.execute("drop policy owner_read on set_pieces")
