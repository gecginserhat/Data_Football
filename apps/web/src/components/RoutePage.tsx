import { EmptyState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import { getMe, permissionSet } from "@/lib/api";
import { canSee, routeByKey, type RouteKey } from "@/lib/routes";

export interface RoutePageProps {
  routeKey: Exclude<RouteKey, "me">;
  /** Detay rotaları (ör. /prep/[fixtureId]) için kayıt kimliği. */
  recordId?: string;
}

/** Faz 0: her rota yetki kontrolüyle ve yol gösteren boş durumuyla açılır. */
export async function RoutePage({ routeKey, recordId }: RoutePageProps) {
  const t = await getTranslations();
  const result = await getMe();
  const permissions = result.status === "ok" ? permissionSet(result.me) : new Set<string>();

  if (!canSee(routeByKey(routeKey), permissions)) {
    return (
      <>
        <h1 className="mb-6 font-condensed text-2xl font-semibold">
          {t(`pages.${routeKey}.title`)}
        </h1>
        <EmptyState
          title={t("states.forbiddenTitle")}
          description={t("states.forbiddenDescription")}
        />
      </>
    );
  }

  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t(`pages.${routeKey}.title`)}</h1>
      <EmptyState
        title={t(`pages.${routeKey}.emptyTitle`)}
        description={
          recordId ? t("pages.detail.emptyDescription") : t(`pages.${routeKey}.emptyDescription`)
        }
      />
    </>
  );
}
