import { cn } from "../cn";

export interface TeamBadgeProps {
  /** Kısa kulüp kodu (GS, TS, GÖZ…). Logo kullanılmaz (SPEC §13.3). */
  code: string;
  name: string;
  highlight?: boolean;
}

export function TeamBadge({ code, name, highlight = false }: TeamBadgeProps) {
  return (
    <abbr
      title={name}
      className={cn(
        "inline-flex min-w-10 items-center justify-center rounded px-1.5 py-0.5 font-condensed text-xs font-semibold tabular-nums no-underline",
        highlight ? "bg-accent text-accent-ink" : "bg-brand text-brand-ink",
      )}
    >
      {code}
    </abbr>
  );
}

export interface SourceBadgeProps {
  /** Kaynak adı, ör. "Tohum: FotMob". */
  label: string;
}

/** Her metrikte verinin kaynağını gösterir (SPEC §13.2). */
export function SourceBadge({ label }: SourceBadgeProps) {
  return (
    <span className="inline-flex items-center rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-3">
      {label}
    </span>
  );
}

export interface SampleSizeBadgeProps {
  /** Deneme sayısı; 8'in altındaysa uyarı gösterilir (SPEC §6.4). */
  n?: number;
  /** Maç sayısı; 5'in altındaysa uyarı gösterilir. */
  matches?: number;
  label: string;
}

export const LOW_SAMPLE_MIN_N = 8;
export const LOW_SAMPLE_MIN_MATCHES = 5;

export function isLowSample(n?: number, matches?: number): boolean {
  return (n !== undefined && n < LOW_SAMPLE_MIN_N) || (matches !== undefined && matches < LOW_SAMPLE_MIN_MATCHES);
}

/** "Az veri" rozeti; örneklem yeterliyse hiçbir şey çizmez. */
export function SampleSizeBadge({ n, matches, label }: SampleSizeBadgeProps) {
  if (!isLowSample(n, matches)) return null;
  return (
    <span className="inline-flex items-center rounded bg-accent/15 px-1.5 py-0.5 text-[11px] font-medium text-ink">
      {label}
    </span>
  );
}
