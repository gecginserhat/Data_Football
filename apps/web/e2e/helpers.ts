import AxeBuilder from "@axe-core/playwright";
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
