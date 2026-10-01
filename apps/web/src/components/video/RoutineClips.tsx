import { TeamBadge } from "@kurgu/ui";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { formatClock } from "@/lib/live/model";
import { listClips } from "@/lib/live-data";

/** Rutinle kaydedilmiş duran toplara bağlı klipler (A-62); rutin istatistiğinin yanında. */
export async function RoutineClips({ routineId }: { routineId: string }) {
  const clips = await listClips({ routine_id: routineId });
  if (clips.status !== "ok") return null;
  const t = await getTranslations("video");
  const tA = await getTranslations("analysis");
  return (
    <section
      aria-labelledby="routine-clips"
      className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3"
      data-testid="routine-clips"
    >
      <h2 id="routine-clips" className="font-condensed text-base font-semibold">
        {t("routineClips")} ({clips.data.length})
      </h2>
      {clips.data.length === 0 ? (
        <p className="text-sm text-ink-2">{t("routineClipsEmpty")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {clips.data.map((clip) => (
            <li key={clip.id}>
              <Link
                href={`/video/${clip.asset_id}?clip=${clip.id}`}
                className="flex min-h-11 flex-wrap items-center gap-2 rounded-md px-1 text-sm hover:bg-bg"
              >
                {clip.set_piece ? (
                  <TeamBadge code={clip.set_piece.team_code} name={clip.set_piece.team_code} />
                ) : null}
                <span className="font-medium">{clip.title || t("untitled")}</span>
                <span className="text-ink-2 tabular-nums">
                  {clip.set_piece
                    ? `${formatClock(clip.set_piece.start_time_s)} · ${
                        clip.set_piece.outcome ? tA(`outcome.${clip.set_piece.outcome}`) : ""
                      }`
                    : null}
                </span>
                <span className="text-xs text-ink-3">{clip.asset_title}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
