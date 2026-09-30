import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Faz 0 kabul kriterleri: Keycloak ile giriş çalışır, /me rol döner,
 * AppShell hazır ve tüm rotalar boş durumda erişilebilir.
 */
const password = process.env.KURGU_DEV_USER_PASSWORD ?? "change-me-dev-user";

const ROUTES = [
  "/",
  "/prep",
  "/prep/ornek-fikstur",
  "/opponents",
  "/opponents/ts",
  "/league",
  "/routines",
  "/routines/ornek-rutin",
  "/live",
  "/live/ornek-fikstur",
  "/video",
  "/reports",
  "/performance",
  "/me",
  "/admin",
  "/methodology",
];

async function signIn(page: Page, username: string) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/signin/);
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(/localhost:\d+\/$/);
}

async function expectNoSeriousA11yViolations(page: Page) {
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

test("unauthenticated visitors are sent to sign in", async ({ page }) => {
  await page.goto("/prep");
  await expect(page).toHaveURL(/\/signin/);
  await expect(page.getByRole("heading", { name: "Kurgu'ya giriş" })).toBeVisible();
  await expectNoSeriousA11yViolations(page);
});

test("set-piece coach signs in, sees role on /me and every route", async ({ page }) => {
  await signIn(page, "sp-coach");

  await page.goto("/me");
  await expect(page.getByTestId("me-roles")).toHaveText("Duran top antrenörü");
  await expect(page.getByTestId("me-active-club")).toHaveText("Trabzonspor (demo)");

  for (const route of ROUTES) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBeLessThan(400);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoSeriousA11yViolations(page);
    if (process.env.E2E_SCREENSHOTS) {
      const name = route === "/" ? "overview" : route.slice(1).replaceAll("/", "-");
      await page.screenshot({
        path: `../../docs/demo/faz0/${test.info().project.name}-${name}.png`,
        fullPage: true,
      });
    }
  }
});

test("viewer does not see live tagging and gets a forbidden state", async ({ page }) => {
  await signIn(page, "viewer");
  await expect(page.getByRole("link", { name: "Canlı kayıt" })).toHaveCount(0);
  await page.goto("/live");
  await expect(page.getByText("Bu sayfaya erişiminiz yok")).toBeVisible();
});
