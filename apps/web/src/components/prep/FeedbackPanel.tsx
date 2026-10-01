import { TeamBadge } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import { formatClock } from "@/lib/live/model";
import { getMatchSetPieces, type MatchSetPiece } from "@/lib/live-data";
import type { PrepFixture, Recommendation } from "@/lib/prep";

/**
 * Öneri geri bildirimi (A-54, A-63): kabul edilen önerilerin yanında maçtaki canlı kayıtlar.
 * Hücum önerisinde kulübün, savunma önerisinde rakibin duran topları. Puan hesaplanmaz.
 */
export async function FeedbackPanel({
  fixture,
  recommendations,
}: {
  fixture: PrepFixture;
  recommendations: Recommendation[];
}) {
  const pieces = await getMatchSetPieces(fixture.id);
  if (pieces.status !== "ok") return null;
  const tagged = pieces.data.filter((p) => p.source === "live_tag");
  const accepted = recommendations.filter(
    (r) => r.status === "accepted" && (r.area === "attack" || r.area === "defense"),
  );
  if (tagged.length === 0 || accepted.length === 0) return null;

  const t = await getTranslations("prep.feedback");
  const tA = await getTranslations("analysis");
  const tLive = await getTranslations("live");
  const groups = [
    { area: "attack" as const, team: fixture.club },
    { area: "defense" as const, team: fixture.opponent },
  ]
    .map((g) => ({
      ...g,
      recs: accepted.filter((r) => r.area === g.area),
      pieces: tagged.filter((p) => p.team_id === g.team.id),
    }))
    .filter((g) => g.recs.length > 0);

  const row = (p: MatchSetPiece) => (
    <li key={p.id} className="flex flex-wrap items-center gap-2 text-sm">
      <span className="w-20 tabular-nums">
        {formatClock(p.start_time_s)}{" "}
        <span className="text-xs text-ink-3">{tLive(`periodShort.${p.period}`)}</span>
      </span>
      <span>{tA(`spType.${p.sp_type}`)}</span>
      <span className="font-medium">{p.outcome ? tA(`outcome.${p.outcome}`) : "–"}</span>
    </li>
  );

  return (
    <section
      aria-labelledby="feedback-title"
      className="mb-8 rounded-lg border border-line bg-surface p-4"
      data-testid="feedback-panel"
    >
      <h2 id="feedback-title" className="font-condensed text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="mb-3 text-sm text-ink-2">{t("caveat")}</p>
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((g) => (
          <div key={g.area} className="flex flex-col gap-2" data-area={g.area}>
            <h3 className="flex items-center gap-2 font-medium">
              <TeamBadge code={g.team.code} name={g.team.name} />
              {t(g.area, { team: g.team.name })}
            </h3>
            <ul className="list-disc pl-5 text-sm text-ink-2">
              {g.recs.map((r) => (
                <li key={r.id}>{r.title}</li>
              ))}
            </ul>
            {g.pieces.length ? (
              <ol className="flex flex-col gap-1">{g.pieces.map(row)}</ol>
            ) : (
              <p className="text-sm text-ink-3">{t("none")}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
