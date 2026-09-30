import { getTranslations } from "next-intl/server";

/** Sunucu eyleminin `?error=` ile döndürdüğü hata kodunu okunur mesaja çevirir. */
export async function ErrorNotice({ code }: { code?: string }) {
  if (!code) return null;
  const t = await getTranslations("imports.errors");
  const message = t.has(code) ? t(code) : t("default", { code });
  return (
    <p
      role="alert"
      className="mb-4 rounded-md border border-neg/50 bg-neg/10 px-4 py-3 text-sm text-ink"
    >
      {message}
    </p>
  );
}
