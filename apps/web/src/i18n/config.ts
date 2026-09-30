export const locales = ["tr", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "tr";
export const LOCALE_COOKIE = "NEXT_LOCALE";

export function isLocale(value: string | undefined): value is Locale {
  return value !== undefined && (locales as readonly string[]).includes(value);
}
