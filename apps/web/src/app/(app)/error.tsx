"use client";

import { ErrorState } from "@kurgu/ui";
import { useTranslations } from "next-intl";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("states");
  return (
    <ErrorState
      title={t("errorTitle")}
      description={t("errorDescription")}
      retryLabel={t("retry")}
      onRetry={reset}
    />
  );
}
