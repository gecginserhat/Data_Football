import { EmptyState, TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";
import { FormChips } from "@/components/analysis/FormChips";
import { canReadAnalysis } from "@/components/analysis/guard";
import { KpiCard } from "@/components/analysis/KpiCard";
import { ProfileBar } from "@/components/analysis/ProfileBar";
import { SeasonPicker } from "@/components/analysis/SeasonPicker";
import { NotLoaded, PageTitle, Section } from "@/components/analysis/States";
import { getProfile, getSeasons, getTeamSetPieces, orderSeasons, pickSeason } from "@/lib/analysis";
import { METRIC_META, METRIC_ORDER, type MetricGroup } from "@/lib/metric-display";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const KPIS = [
  "set_piece_goals",
  "set_piece_xg",
  "set_piece_goal_share",
  "set_piece_goals_minus_xg",
];
const GROUPS: MetricGroup[] = ["attack", "defence", "other"];

export default async function OpponentPage({
  params,
  searchParams,
}: {
  params: Promise<{ teamId: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const t = await getTranslations("analysis");
  const tStates = await getTranslations("states");
  const format = await getFormatter();
  if (!(await canReadAnalysis())) {
    return (
      <>
        <PageTitle>{t("opponents.title")}</PageTitle>
        <EmptyState
          title={tStates("forbiddenTitle")}
          description={tStates("forbiddenDescription")}
        />
      </>
    );
  }
  const { teamId } = await params;
  const { season: requested } = await searchParams;
  const seasons = await getSeasons();
  const season = seasons.status === "ok" ? pickSeason(seasons.data, requested) : undefined;
  if (!UUID_RE.test(teamId) || seasons.status !== "ok" || !season) {
    return (
      <>
        <PageTitle>{t("opponents.title")}</PageTitle>
        <NotLoaded result={seasons.status === "ok" ? { status: "missing" } : seasons} />
      </>
    );
  }
  const [profile, setPieces] = await Promise.all([
    getProfile(teamId, season.id),
    getTeamSetPieces(teamId, season.id),
  ]);
  if (profile.status !== "ok") {
    return (
      <>
        <PageTitle>{t("opponents.title")}</PageTitle>
        <NotLoaded result={profile} />
      </>
    );
  }
  const p = profile.data;
  const isClub = p.club?.id === p.team.id;
  const club = !isClub && p.club ? p.club : null;
  const metrics = METRIC_ORDER.filter((m) => p.values[m]);

  return (
    <>
      <nav aria-label={t("breadcrumb")} className="mb-2 text-sm">
        <Link
          href={`/opponents?season=${season.id}`}
          className="text-pri underline-offset-2 hover:underline"
        >
          ← {t("opponents.title")}
        </Link>
      </nav>
      <PageTitle
        sub={
          p.as_of_week
            ? t("opponents.asOfWeek", { season: p.season.label, week: p.as_of_week })
            : t("opponents.fullSeason", { season: p.season.label })
        }
      >
        <span className="flex flex-wrap items-center gap-3">
          <TeamBadge code={p.team.code} name={p.team.name} highlight={isClub} />
          {p.team.name}
        </span>
      </PageTitle>
      <div className="mb-6">
        <SeasonPicker
          seasons={orderSeasons(seasons.data)}
          current={season}
          basePath={`/opponents/${teamId}`}
        />
      </div>

      {p.standing || p.form.length > 0 ? (
        <Section id="status" title={t("opponents.status")}>
          <div className="flex flex-wrap items-center gap-6 rounded-lg border border-line bg-surface p-4">
            {p.standing ? (
              <p className="text-sm" data-testid="standing">
                {t("opponents.standing", {
                  position: p.standing.position,
                  pts: p.standing.pts,
                  played: p.standing.played,
                  week: p.standing_week ?? 0,
                })}
              </p>
            ) : null}
            <FormChips form={p.form} />
          </div>
        </Section>
      ) : null}

      {metrics.length === 0 ? (
        <EmptyState title={t("opponents.noMetricsTitle")} description={t("opponents.noMetrics")} />
      ) : (
        <>
          <Section id="kpis" title={t("opponents.summary")}>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {KPIS.map((m) => (
                <KpiCard key={m} metric={m} value={p.values[m]} />
              ))}
            </div>
          </Section>
          {GROUPS.map((group) => {
            const groupMetrics = metrics.filter((m) => METRIC_META[m]?.group === group);
            if (groupMetrics.length === 0) return null;
            return (
              <Section
                key={group}
                id={`group-${group}`}
                title={t(`groups.${group}`)}
                action={
                  club ? (
                    <span className="flex items-center gap-3 text-xs text-ink-2">
                      <Legend shape="circle" label={p.team.code} />
                      <Legend shape="diamond" label={t("legend.club", { code: club.code })} />
                      <Legend shape="tick" label={t("legend.mean")} />
                    </span>
                  ) : (
                    <span className="flex items-center gap-3 text-xs text-ink-2">
                      <Legend shape="circle" label={p.team.code} />
                      <Legend shape="tick" label={t("legend.mean")} />
                    </span>
                  )
                }
              >
                {group === "defence" ? (
                  <p className="mb-2 text-xs text-ink-3">{t("opponents.defenceNote")}</p>
                ) : null}
                <div className="divide-y divide-line rounded-lg border border-line bg-surface px-4">
                  {groupMetrics.map((m) => (
                    <ProfileBar
                      key={m}
                      metric={m}
                      value={p.values[m]!}
                      benchmark={p.benchmarks[m]}
                      club={
                        club && p.club_values[m]
                          ? { code: club.code, value: p.club_values[m] }
                          : undefined
                      }
                    />
                  ))}
                </div>
              </Section>
            );
          })}
        </>
      )}

      <Section id="sequences" title={t("opponents.sequences")}>
        {setPieces.status !== "ok" ? (
          <NotLoaded result={setPieces} />
        ) : setPieces.data.length === 0 ? (
          <EmptyState
            title={t("opponents.noSequencesTitle")}
            description={t("opponents.noSequences")}
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full min-w-max text-left text-sm tabular-nums">
              <thead className="border-b border-line text-xs text-ink-3">
                <tr>
                  <th scope="col" className="px-3 py-2">
                    {t("sequence.match")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("sequence.minute")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("sequence.type")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("sequence.zone")}
                  </th>
                  <th scope="col" className="px-3 py-2">
                    {t("sequence.outcome")}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right">
                    {t("sequence.xg")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {setPieces.data.map((sp) => (
                  <tr key={sp.id} className="border-b border-line last:border-0">
                    <td className="px-3 py-2">
                      <TeamBadge code={sp.opponent.code} name={sp.opponent.name} />
                      {sp.week ? (
                        <span className="ml-2 text-xs text-ink-3">
                          {t("sequence.week", { week: sp.week })}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">{Math.floor(sp.start_time_s / 60) + 1}&apos;</td>
                    <td className="px-3 py-2">{t(`spType.${sp.sp_type}`)}</td>
                    <td className="px-3 py-2">{sp.target_zone ?? "–"}</td>
                    <td className="px-3 py-2">
                      {sp.goal ? (
                        <strong>{t("sequence.goal")}</strong>
                      ) : sp.outcome ? (
                        t(`outcome.${sp.outcome}`)
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {format.number(sp.xg_total, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}

function Legend({ shape, label }: { shape: "circle" | "diamond" | "tick"; label: string }) {
  const mark =
    shape === "circle" ? (
      <span className="size-2.5 rounded-full bg-pri" />
    ) : shape === "diamond" ? (
      <span className="size-2.5 rotate-45 bg-accent" />
    ) : (
      <span className="h-3 w-0.5 bg-ink-3" />
    );
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className="inline-flex">
        {mark}
      </span>
      {label}
    </span>
  );
}
