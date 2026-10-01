import { useTranslations } from "next-intl";
import type { Profile } from "@/lib/analysis";

const STYLE = {
  W: "bg-pos text-surface",
  D: "bg-ink-3 text-surface",
  L: "bg-neg text-surface",
} as const;

/** Son maçlar: G/B/M harfleriyle (renk tek başına anlam taşımaz, SPEC §13.4). */
export function FormChips({ form }: { form: Profile["form"] }) {
  const t = useTranslations("analysis.form");
  if (form.length === 0) return <p className="text-sm text-ink-3">{t("empty")}</p>;
  return (
    <ol className="flex gap-1" aria-label={t("label")}>
      {form.map((f) => (
        <li key={f.match_id}>
          <abbr
            title={t("detail", {
              result: t(`result.${f.result}`),
              opponent: f.opponent.name,
              gf: f.goals_for,
              ga: f.goals_against,
              venue: t(f.home ? "home" : "away"),
            })}
            className={`inline-flex size-7 items-center justify-center rounded font-condensed text-sm font-semibold no-underline ${STYLE[f.result]}`}
          >
            {t(`letter.${f.result}`)}
          </abbr>
        </li>
      ))}
    </ol>
  );
}
