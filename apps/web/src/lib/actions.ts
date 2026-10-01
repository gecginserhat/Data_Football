"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { signIn, signOut } from "@/auth";
import { isLocale, LOCALE_COOKIE } from "@/i18n/config";
import { TENANT_COOKIE } from "./api";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const cookieOptions = {
  httpOnly: true,
  sameSite: "lax",
  path: "/",
  secure: (process.env.AUTH_URL ?? "").startsWith("https://"),
} as const;

export async function selectTenant(formData: FormData): Promise<void> {
  const tenantId = String(formData.get("tenantId") ?? "");
  if (!UUID_RE.test(tenantId)) return;
  (await cookies()).set(TENANT_COOKIE, tenantId, cookieOptions);
  revalidatePath("/", "layout");
}

export async function setLocale(formData: FormData): Promise<void> {
  const locale = String(formData.get("locale") ?? "");
  if (!isLocale(locale)) return;
  (await cookies()).set(LOCALE_COOKIE, locale, { ...cookieOptions, httpOnly: false });
  revalidatePath("/", "layout");
}

export async function signInAction(): Promise<void> {
  await signIn("keycloak", { redirectTo: "/" });
}

export async function signOutAction(): Promise<void> {
  (await cookies()).delete(TENANT_COOKIE);
  await signOut({ redirectTo: "/signin" });
}
