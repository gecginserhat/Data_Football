import { roleLabel } from "@kurgu/pitch";
import { EmptyState, TeamBadge } from "@kurgu/ui";
import { getFormatter, getLocale, getTranslations } from "next-intl/server";
import { BoardView } from "@/components/routines/board";
import { toDiagram } from "@/lib/routines";
import type { TaskCard } from "@/lib/squad";

/** Oyuncunun görev kartları (A-87): yaklaşan maçta rutin rolü ve markaj görevi. */
export async function TaskCards({ cards }: { cards: TaskCard[] }) {
  const t = await getTranslations("cards");
  const format = await getFormatter();
  const locale = await getLocale();
  if (cards.length === 0) {
    return <EmptyState title={t("emptyTitle")} description={t("empty")} />;
  }
  return (
    <div className="flex flex-col gap-4" data-testid="task-cards">
      {cards.map((card) => {
        const f = card.fixture;
        return (
          <article
            key={f.id}
            className="rounded-lg border border-line bg-surface p-4"
            data-testid="task-card"
          >
            <header className="mb-3 flex flex-wrap items-center gap-2">
              <TeamBadge code={f.opponent.code} name={f.opponent.name} />
              <h3 className="font-condensed text-lg font-semibold">
                {t("fixture", {
                  opponent: f.opponent.name,
                  venue: t(f.is_home ? "home" : "away"),
                })}
              </h3>
              <span className="text-sm text-ink-3">
                {f.kickoff_at
                  ? format.dateTime(new Date(f.kickoff_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                      timeZone: "Europe/Istanbul",
                    })
                  : t("dateTbd")}
              </span>
            </header>
            {card.marking ? (
              <p
                className="mb-3 rounded-md bg-accent/10 px-3 py-2 text-sm"
                data-testid="card-marking"
              >
                <span className="font-medium">{t("marking")}: </span>
                {card.marking.zonal
                  ? t("zonal")
                  : card.marking.target
                    ? t("markTarget", {
                        target: card.marking.target.shirt_number
                          ? `${card.marking.target.shirt_number} · ${card.marking.target.name}`
                          : card.marking.target.name,
                        height: card.marking.target.height_cm ?? "—",
                      })
                    : t("unmarked")}
              </p>
            ) : null}
            {card.routines.length ? (
              <ul className="grid gap-4 sm:grid-cols-2">
                {card.routines.map((r) => {
                  const role = roleLabel("own", r.role, locale);
                  return (
                    <li
                      key={`${r.routine_id}-${r.diagram_player_id}`}
                      className="flex gap-3"
                      data-testid="card-routine"
                      data-routine={r.routine_id}
                    >
                      <BoardView
                        diagram={toDiagram(r.diagram)}
                        highlight={r.diagram_player_id}
                        label={t("diagram", { name: r.name, role })}
                        className="w-28 shrink-0"
                      />
                      <div className="flex flex-col gap-1 text-sm">
                        <span className="font-medium">{r.name}</span>
                        <span>
                          {t("role")}: <span className="font-medium">{role}</span>
                          {r.number ? ` (${r.number})` : ""}
                          {r.label ? ` · ${r.label}` : ""}
                        </span>
                        <span className="text-xs text-ink-3">
                          {t(`spType.${r.sp_type}`)} · {t("version", { version: r.version })}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-ink-3">{t("noRoutines")}</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
