import { useFormatter, useTranslations } from "next-intl";

/** Hava skoru (0-1) ve skora giren bileşenler (A-81). Bileşen yoksa "—" ve açıklama. */
export function AerialValue({
  score,
}: {
  score: { value: number; components: string[] } | null | undefined;
}) {
  const t = useTranslations("squad");
  const format = useFormatter();
  if (!score) {
    return (
      <span className="text-xs text-ink-3" title={t("noScore")}>
        —
      </span>
    );
  }
  const parts = score.components.map((c) => t(`components.${c}`)).join(", ");
  return (
    <span className="inline-flex flex-col items-end">
      <span className="font-condensed text-base font-semibold tabular-nums">
        {format.number(score.value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      <span className="text-[11px] text-ink-3">{parts}</span>
    </span>
  );
}
