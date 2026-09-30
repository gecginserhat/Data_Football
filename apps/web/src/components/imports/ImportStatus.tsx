import { cn } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";

export type ImportStatusValue = "uploaded" | "validated" | "quarantined" | "committed" | "failed";

const TONE: Record<ImportStatusValue, string> = {
  uploaded: "border-accent bg-accent/15 text-ink",
  validated: "border-pos/50 bg-pos/10 text-ink",
  quarantined: "border-neg/60 bg-neg/10 text-ink",
  committed: "border-pri bg-pri text-brand-ink",
  failed: "border-neg bg-neg text-brand-ink",
};

/** Durum rozeti: renk tek başına anlam taşımaz, durum adı her zaman yazılır. */
export async function ImportStatus({ status }: { status: string }) {
  const t = await getTranslations("imports.status");
  const value = (status in TONE ? status : "failed") as ImportStatusValue;
  return (
    <span
      data-testid="import-status"
      data-status={value}
      className={cn(
        "inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold",
        TONE[value],
      )}
    >
      {t(value)}
    </span>
  );
}
