import AxeBuilder from "@axe-core/playwright";
import { createHmac } from "node:crypto";
import { expect, type Page } from "@playwright/test";

/** Geliştirme kimlikleriyle Keycloak üzerinden giriş ve erişilebilirlik kontrolü. */
const password = process.env.KURGU_DEV_USER_PASSWORD ?? "change-me-dev-user";

export async function signIn(page: Page, username: string) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/signin/);
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(/localhost:\d+\/$/);
}

export async function expectNoSeriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);
}

/**
 * RFC 6238 TOTP (HMAC-SHA1, 6 hane, 30 sn). Keycloak içe aktarılan OTP anahtarını ham metin olarak
 * saklar; anahtar baytları metnin UTF-8 kodlamasıdır.
 */
export function totp(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const mac = createHmac("sha1", Buffer.from(secret, "utf8")).update(counter).digest();
  const offset = mac[mac.length - 1]! & 0x0f;
  const code = (mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(code).padStart(6, "0");
}
