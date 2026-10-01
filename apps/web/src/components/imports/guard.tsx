import { EmptyState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import { getMe, permissionSet } from "@/lib/api";

/** İçe aktarım yalnızca yöneticilere açıktır (SPEC §11 `/admin/*`). */
export async function canImport(): Promise<boolean> {
  const result = await getMe();
  return result.status === "ok" && permissionSet(result.me).has("user_admin_audit");
}

export async function Forbidden() {
  const t = await getTranslations();
  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t("imports.title")}</h1>
      <EmptyState
        title={t("states.forbiddenTitle")}
        description={t("states.forbiddenDescription")}
      />
    </>
  );
}
