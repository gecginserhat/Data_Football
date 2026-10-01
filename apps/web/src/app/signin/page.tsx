import { getTranslations } from "next-intl/server";
import { signInAction } from "@/lib/actions";

export default async function SignInPage() {
  const t = await getTranslations();
  return (
    <main className="flex min-h-dvh items-center justify-center bg-brand p-6">
      <section className="w-full max-w-sm rounded-lg bg-surface p-8 shadow-lg">
        <p className="font-condensed text-3xl font-bold text-brand">{t("app.name")}</p>
        <p className="mt-1 text-sm text-ink-3">{t("app.tagline")}</p>
        <h1 className="mt-8 font-condensed text-xl font-semibold">{t("auth.title")}</h1>
        <p className="mt-2 text-sm text-ink-2">{t("auth.description")}</p>
        <form action={signInAction} className="mt-6">
          <button
            type="submit"
            className="min-h-11 w-full rounded-md bg-pri px-4 font-medium text-brand-ink hover:opacity-90"
          >
            {t("auth.signIn")}
          </button>
        </form>
      </section>
    </main>
  );
}
