import { cn } from "@kurgu/ui";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { Season } from "@/lib/analysis";

/** Sezon seçimi bağlantılarla yapılır (`?season=`); JavaScript gerektirmez. */
export function SeasonPicker({
  seasons,
  current,
  basePath,
}: {
  seasons: Season[];
  current: Season;
  basePath: string;
}) {
  const t = useTranslations("analysis");
  return (
    <nav aria-label={t("seasonPicker")} className="flex flex-wrap gap-2">
      {seasons.map((s) => {
        const active = s.id === current.id;
        return (
          <Link
            key={s.id}
            href={`${basePath}?season=${s.id}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex min-h-11 items-center rounded-md border px-3 text-sm",
              active
                ? "border-pri bg-pri text-brand-ink"
                : "border-line bg-surface hover:border-pri",
            )}
          >
            {s.competition.name} · {s.label}
          </Link>
        );
      })}
    </nav>
  );
}
