"use client";

import { useFormStatus } from "react-dom";

/** Form gönderilirken düğmeyi kilitler ve bekleme metnini gösterir. */
export function PendingButton({
  children,
  pendingLabel,
  className,
  name,
  value,
  testId,
}: {
  children: React.ReactNode;
  pendingLabel: string;
  className: string;
  name?: string;
  value?: string;
  testId?: string;
}) {
  const { pending, data } = useFormStatus();
  const mine = pending && (!name || data?.get(name) === value);
  return (
    <button
      type="submit"
      name={name}
      value={value}
      disabled={pending}
      aria-busy={mine}
      className={className}
      data-testid={testId}
    >
      {mine ? pendingLabel : children}
    </button>
  );
}
