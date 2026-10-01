import { expect, test } from "@playwright/test";
import { signIn, totp } from "./helpers";

/** Sertleştirme (Faz 8, ADR-0016): MFA adım yükseltme ve güvenlik başlıkları. */

const otpSecret = process.env.KURGU_DEV_OTP_SECRET ?? "change-me-dev-otp-01";

test.skip(({ isMobile }) => isMobile, "Tek görünümde yeterli");

test("a performance user without a second factor is stepped up to TOTP", async ({ page }) => {
  await signIn(page, "mfa-performance");
  // Parolayla gelen token MFA kanıtı taşımaz; uygulama adım yükseltme ister.
  await expect(page.getByTestId("mfa-required")).toBeVisible();
  await page.getByRole("button", { name: "Kodla devam et" }).click();

  await expect(page.locator("#otp")).toBeVisible();
  await page.locator("#otp").fill(totp(otpSecret));
  await page.locator("#kc-login").click();

  await expect(page).toHaveURL(/localhost:\d+\/$/);
  await expect(page.getByTestId("mfa-required")).toHaveCount(0);
  await page.goto("/performance");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Test Kulübü").first()).toBeVisible();
});

test("pages are served with a nonce-based content security policy", async ({ page }) => {
  const response = await page.goto("/signin");
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("object-src 'none'");
  // Nonce her istekte değişir.
  const again = (await page.goto("/signin"))?.headers()["content-security-policy"];
  expect(again).not.toEqual(csp);
  // Sayfa CSP ihlali olmadan çalışır: giriş düğmesi etkileşimli.
  await expect(page.getByRole("button", { name: "Giriş yap" })).toBeEnabled();
});

test("signing out also ends the identity provider session", async ({ page }) => {
  await signIn(page, "sp-coach");
  await page.getByRole("button", { name: "Çıkış yap" }).first().click();
  await expect(page).toHaveURL(/\/signin/);
  // Keycloak oturumu kapandığı için giriş yeniden parola ister.
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.locator("#password")).toBeVisible();
});
