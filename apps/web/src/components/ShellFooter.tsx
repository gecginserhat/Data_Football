import { getLocale, getTranslations } from "next-intl/server";
import { locales } from "@/i18n/config";
import { setLocale, signOutAction } from "@/lib/actions";

export async function ShellFooter() {
  const t = await getTranslations("app");
  const current = await getLocale();
  return (
    <div className="flex flex-col gap-2">
      <form action={setLocale} className="flex items-center gap-1" aria-label={t("language")}>
        {locales.map((locale) => (
          <button
            key={locale}
            type="submit"
            name="locale"
            value={locale}
            aria-pressed={locale === current}
            className="min-h-11 min-w-11 rounded-md px-2 text-xs uppercase text-brand-ink/80 aria-pressed:bg-white/10 aria-pressed:font-semibold aria-pressed:text-brand-ink aria-pressed:underline"
          >
            {locale}
          </button>
        ))}
      </form>
      <form action={signOutAction}>
        <button
          type="submit"
          className="min-h-11 w-full rounded-md px-3 text-left text-sm text-brand-ink/80 hover:bg-white/5"
        >
          {t("signOut")}
        </button>
      </form>
    </div>
  );
}
