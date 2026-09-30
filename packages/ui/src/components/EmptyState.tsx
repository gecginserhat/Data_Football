import type { ReactNode } from "react";
import { cn } from "../cn";

export interface EmptyStateProps {
  title: string;
  /** Kullanıcıya ne yapması gerektiğini söyleyen cümle. */
  description: string;
  action?: ReactNode;
  className?: string;
}

/** Boş durum: ne yapılacağını söyler (SPEC §13.3 "Durumlar"). */
export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <section
      className={cn(
        "flex flex-col items-start gap-3 rounded-lg border border-dashed border-line bg-surface p-6",
        className,
      )}
      aria-label={title}
    >
      <h2 className="font-condensed text-lg font-semibold text-ink">{title}</h2>
      <p className="max-w-prose text-sm text-ink-2">{description}</p>
      {action ? <div>{action}</div> : null}
    </section>
  );
}
