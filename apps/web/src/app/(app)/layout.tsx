import { ErrorState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { ShellFooter } from "@/components/ShellFooter";
import { getMe, permissionSet } from "@/lib/api";
import { signOutAction } from "@/lib/actions";
import { ROUTES, canSee } from "@/lib/routes";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const result = await getMe();
  const t = await getTranslations();

  if (result.status !== "ok") {
    return (
      <main className="mx-auto max-w-lg p-6">
        <ErrorState
          title={t("states.errorTitle")}
          description={t("states.errorDescription")}
          retryLabel={t("states.retry")}
        />
        {result.status === "unauthenticated" ? (
          <form action={signOutAction} className="mt-4">
            <button
              type="submit"
              className="min-h-11 rounded-md bg-pri px-4 text-sm text-brand-ink"
            >
              {t("app.signOut")}
            </button>
          </form>
        ) : null}
      </main>
    );
  }

  const { me } = result;
  const permissions = permissionSet(me);
  const visible = ROUTES.filter((r) => canSee(r, permissions)).map((r) => r.key);

  return (
    <AppShell
      visible={visible}
      clubName={me.active_tenant?.tenant_name ?? null}
      userName={me.name ?? me.email ?? null}
      footer={<ShellFooter />}
    >
      {children}
    </AppShell>
  );
}
