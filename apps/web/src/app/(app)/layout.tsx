import { ErrorState } from "@kurgu/ui";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { ServiceWorker } from "@/components/ServiceWorker";
import { ShellFooter } from "@/components/ShellFooter";
import { getMe, permissionSet } from "@/lib/api";
import { signOutAction, stepUpAction } from "@/lib/actions";
import { ROUTES, canSee } from "@/lib/routes";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const result = await getMe();
  const t = await getTranslations();

  if (result.status === "mfa-required") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-brand p-6">
        <section
          className="w-full max-w-sm rounded-lg bg-surface p-8 shadow-lg"
          data-testid="mfa-required"
        >
          <h1 className="font-condensed text-xl font-semibold">{t("auth.mfaTitle")}</h1>
          <p className="mt-2 text-sm text-ink-2">{t("auth.mfaDescription")}</p>
          <form action={stepUpAction} className="mt-6">
            <button
              type="submit"
              className="min-h-11 w-full rounded-md bg-pri px-4 font-medium text-brand-ink hover:opacity-90"
            >
              {t("auth.mfaContinue")}
            </button>
          </form>
          <form action={signOutAction} className="mt-3">
            <button type="submit" className="min-h-11 w-full text-sm text-ink-2 underline">
              {t("app.signOut")}
            </button>
          </form>
        </section>
      </main>
    );
  }

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
      <ServiceWorker />
      {children}
    </AppShell>
  );
}
