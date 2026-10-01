import { Skeleton } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";

export default async function Loading() {
  const t = await getTranslations("states");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-8 w-48" label={t("loading")} />
      <Skeleton className="h-32 w-full" label={t("loading")} />
    </div>
  );
}
