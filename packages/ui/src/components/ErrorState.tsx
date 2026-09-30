import { cn } from "../cn";

export interface ErrorStateProps {
  title: string;
  description: string;
  retryLabel: string;
  onRetry?: () => void;
  className?: string;
}

/** Hata durumu: tekrar dene düğmesiyle (SPEC §13.3). */
export function ErrorState({ title, description, retryLabel, onRetry, className }: ErrorStateProps) {
  return (
    <section
      role="alert"
      className={cn("flex flex-col items-start gap-3 rounded-lg border border-neg/40 bg-surface p-6", className)}
    >
      <h2 className="font-condensed text-lg font-semibold text-neg">{title}</h2>
      <p className="max-w-prose text-sm text-ink-2">{description}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 rounded-md border border-line px-4 text-sm font-medium text-ink hover:bg-bg focus-visible:outline-2 focus-visible:outline-focus"
        >
          {retryLabel}
        </button>
      ) : null}
    </section>
  );
}
