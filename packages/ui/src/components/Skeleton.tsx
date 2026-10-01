import { cn } from "../cn";

export interface SkeletonProps {
  className?: string;
  /** Ekran okuyucu için yükleniyor metni. */
  label: string;
}

/** Yükleniyor durumu için iskelet blok. */
export function Skeleton({ className, label }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("animate-pulse rounded-md bg-line motion-reduce:animate-none", className)}
    >
      <span className="sr-only">{label}</span>
    </div>
  );
}
